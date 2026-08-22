"""C08 — nhìn cả DANH MỤC như một vùng, không phải một danh sách.

VÌ SAO CẦN: hợp tác xã có 200 thửa không hỏi "thửa số 137 thế nào". Họ hỏi
"vụ này chỗ nào của tôi sắp gãy" và "có nên điều máy bơm sang khu Đông không".
Trước file này, C08 chỉ trả về một danh sách phẳng — người dùng phải tự bấm
từng thửa rồi tự nhớ, tức là phần mềm giao lại đúng việc mà nó lẽ ra phải làm.

Đây cũng chính là MỤC ĐÍCH mà bản thiết kế gán cho tầng "PostGIS · tổng hợp
không gian". Thứ thiếu không phải một chỉ mục nhanh hơn — với vài trăm thửa thì
vòng lặp Python đã nhanh hơn mọi chỉ mục — mà là NĂNG LỰC gộp theo vùng. Nên
làm đúng cái đó, và ghi rõ khi nào mới cần đến chỉ mục thật.

CHỌN Ô GỘP 0,1°: khoảng 11 km, cỡ một xã lớn hoặc một khu tưới. Nhỏ hơn thì mỗi
thửa một ô, gộp thành vô nghĩa; lớn hơn thì trộn lẫn hai vùng canh tác khác hẳn
nhau.
"""
from __future__ import annotations

import math

CELL_DEG = 0.1              # ~11 km — cỡ một xã lớn / một khu tưới
MAX_PLOTS = 300             # trần an toàn, xem ghi chú ở dưới

_RANK = {"danger": 0, "warning": 1, "safe": 2, "unknown": 3}


def _cell(lat: float, lon: float) -> str:
    return (f"{math.floor(lat / CELL_DEG) * CELL_DEG:.1f},"
            f"{math.floor(lon / CELL_DEG) * CELL_DEG:.1f}")


def overview(plots: list, include_heavy: bool = False) -> dict:
    """Quét cả danh mục ĐỒNG THỜI rồi gộp theo vùng.

    `plots` là các bản ghi có .id/.name/.lat/.lon/.area_ha — không nhận Session
    để hàm này test được mà không cần database.
    """
    from app.schemas import Location
    from app.services import jobs, scan as scan_svc

    if not plots:
        return {"available": False,
                "message": ("Danh mục chưa có thửa nào. Bấm bản đồ rồi lưu thửa, "
                            "sau đó quay lại đây để xem toàn cảnh.")}

    truncated = len(plots) > MAX_PLOTS
    use = plots[:MAX_PLOTS]

    def _task(p):
        return lambda: (p, scan_svc.scan(
            Location(lat=p.lat, lon=p.lon, area_ha=p.area_ha),
            include_heavy=include_heavy))

    results = [r for r in jobs.gather([_task(p) for p in use]) if r is not None]
    if not results:
        return {"available": False,
                "message": ("Không quét được thửa nào — nhiều khả năng nguồn dữ "
                            "liệu đang không phản hồi. Thử lại sau ít phút.")}

    rows, cells = [], {}
    lats, lons = [], []
    counts = {"danger": 0, "warning": 0, "safe": 0, "unknown": 0}
    total_ha = 0.0
    at_risk_ha = 0.0

    for p, res in results:
        # Mức của cả thửa = mức nặng nhất trong các MỐI ĐE DOẠ có dữ liệu thật.
        #
        # Hai bộ lọc, mỗi cái chặn một kiểu sai khác nhau:
        #   is_real — mô-đun đang chờ ảnh vệ tinh trả "unknown", mà "chưa đủ dữ
        #             liệu" không phải một đánh giá; trộn vào làm cả danh mục
        #             trông đáng ngờ hơn thực tế.
        #   threat  — điện mặt trời "danger" nghĩa là bức xạ trung bình. Không
        #             lọc thì bảng báo "4/4 thửa đang cảnh báo" trong khi thật
        #             ra chỉ là tiềm năng điện mặt trời hơi kém.
        real = [m for m in res.modules if m.is_real and m.threat]
        worst = min((m.risk_level for m in real), key=lambda r: _RANK.get(r, 9),
                    default="unknown")
        drivers = sorted(
            [m for m in real if m.risk_level in ("danger", "warning")],
            key=lambda m: _RANK.get(m.risk_level, 9))[:3]

        ha = float(p.area_ha or 0.0)
        total_ha += ha
        counts[worst] = counts.get(worst, 0) + 1
        if worst in ("danger", "warning"):
            at_risk_ha += ha

        lats.append(p.lat)
        lons.append(p.lon)
        rows.append({
            "plot_id": p.id, "name": p.name, "lat": p.lat, "lon": p.lon,
            "area_ha": p.area_ha,
            "risk_level": worst,
            "score": res.terrascore.score if res.terrascore else None,
            "grade": res.terrascore.grade if res.terrascore else None,
            "drivers": [{"id": m.id, "name": m.name, "icon": m.icon,
                         "risk_level": m.risk_level, "headline": m.headline}
                        for m in drivers],
        })

        key = _cell(p.lat, p.lon)
        c = cells.setdefault(key, {"cell": key, "plots": 0, "area_ha": 0.0,
                                   "danger": 0, "warning": 0, "safe": 0,
                                   "unknown": 0, "modules": {}})
        c["plots"] += 1
        c["area_ha"] = round(c["area_ha"] + ha, 2)
        c[worst] = c.get(worst, 0) + 1
        for m in drivers:
            c["modules"][m.id] = c["modules"].get(m.id, 0) + 1

    for c in cells.values():
        c["at_risk_pct"] = round(
            100.0 * (c["danger"] + c["warning"]) / c["plots"], 1)
        c["top_driver"] = (max(c["modules"].items(), key=lambda kv: kv[1])[0]
                           if c["modules"] else None)

    ranked_cells = sorted(cells.values(),
                          key=lambda c: (-c["danger"], -c["at_risk_pct"],
                                         -c["plots"]))
    rows.sort(key=lambda r: (_RANK.get(r["risk_level"], 9),
                             r["score"] if r["score"] is not None else 999))

    n = len(rows)
    at_risk = counts["danger"] + counts["warning"]
    worst_cell = ranked_cells[0] if ranked_cells else None

    head = (f"{at_risk}/{n} thửa đang ở mức cảnh báo trở lên"
            + (f" ({round(at_risk_ha, 1)}/{round(total_ha, 1)} ha)"
               if total_ha > 0 else "")
            + (f". Nặng nhất là vùng {worst_cell['cell']}: "
               f"{worst_cell['danger']} thửa nguy hiểm trên "
               f"{worst_cell['plots']} thửa."
               if worst_cell and worst_cell["danger"] else "")
            if at_risk else
            f"Cả {n} thửa trong danh mục đều an toàn 7 ngày tới.")

    return {
        "available": True,
        "plots_scanned": n,
        "plots_total": len(plots),
        "truncated": truncated,
        "counts": counts,
        "total_ha": round(total_ha, 2),
        "at_risk_ha": round(at_risk_ha, 2),
        "bbox": {"min_lat": min(lats), "max_lat": max(lats),
                 "min_lon": min(lons), "max_lon": max(lons)},
        "cells": ranked_cells,
        "cell_deg": CELL_DEG,
        "plots": rows,
        "headline": head,
        "method": (
            f"Quét đồng thời từng thửa, lấy mức nặng nhất trong các hiểm họa "
            f"CÓ DỮ LIỆU THẬT, rồi gộp theo ô {CELL_DEG}° (~11 km, cỡ một xã "
            "lớn hoặc một khu tưới)."),
        "caveat": (
            (f"Danh mục có {len(plots)} thửa, chỉ quét {MAX_PLOTS} thửa đầu để "
             "không đốt hạn mức nguồn dữ liệu miễn phí. "
             if truncated else "")
            + "Mô-đun đang chờ ảnh vệ tinh KHÔNG được tính vào mức của thửa — "
            "'chưa đủ dữ liệu' không phải một đánh giá, trộn vào sẽ làm cả danh "
            "mục trông đáng ngờ hơn thực tế."),
    }
