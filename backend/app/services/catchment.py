"""Mưa ở THƯỢNG NGUỒN sắp chảy xuống đây.

VÌ SAO CẦN: cho tới file này, module Lũ và Sạt lở chỉ nhìn lượng mưa rơi trên
CHÍNH thửa đó. Nhưng lũ quét và lũ hạ nguồn đến từ nước rơi ở trên cao rồi dồn
xuống — Trà Leng 2020 không phải vì mưa tại chỗ, mà vì cả sườn núi phía trên
ngậm nước. Một mảnh đất có thể khô ráo suốt buổi sáng rồi ngập trong một giờ vì
chuyện xảy ra cách đó mười cây số về phía núi.

Bản thiết kế xếp việc này vào ô "Graph Neural Network — rủi ro lan truyền (lũ
hạ nguồn)". Xét theo MỤC ĐÍCH thì thứ người dùng cần không phải một mạng nơ-ron
đồ thị, mà là câu trả lời: "phía trên tôi có đang mưa không, và nước đó có chảy
về phía tôi không". Câu đó trả lời được bằng DEM và lưới mưa đã có.

CÁCH LÀM: lấy mẫu một nan quạt điểm quanh thửa, giữ lại những điểm CAO HƠN
(nước từ đó chảy xuống đây), rồi cân theo độ chênh cao và khoảng cách. Điểm cao
hơn 100 m cách 3 km đóng góp mạnh hơn điểm cao hơn 10 m cách 12 km.

GIỚI HẠN PHẢI NÓI THẲNG, VÌ NÓ QUYẾT ĐỊNH KHI NÀO ĐƯỢC TIN:
  · Đây KHÔNG phải lưu vực được phân định đúng cách. Nó là một nan quạt lấy mẫu
    theo hướng dốc lên, giả định nước chảy thẳng xuống dốc.
  · Bỏ qua lòng sông, đê bao, cống và hồ chứa — ở ĐBSCL thì chính mấy thứ đó
    mới quyết định nước đi đâu.
  · Ở đồng bằng, chênh lệch cao độ nhỏ hơn sai số đứng của DEM, nên tín hiệu là
    NHIỄU. Hàm này TỪ CHỐI trả kết quả khi địa hình quá phẳng, thay vì trả một
    con số trông có vẻ chính xác.

Vì vậy kết quả được trả về như một ĐỐI CHỨNG ĐỘC LẬP, giống lưu lượng sông
GloFAS — không cộng thẳng vào chỉ số đã hiệu chuẩn, để không đếm hai lần và
không làm hỏng phép hiệu chuẩn theo phân vị.
"""
from __future__ import annotations

import math

from app.services.reqlang import tr

# Nan quạt lấy mẫu: 8 hướng × 3 vòng = 24 điểm, gọn trong một lượt gọi
# Open-Meteo (trần 100 toạ độ) cho cả cao độ lẫn mưa.
BEARINGS = 8
RADII_KM = (3.0, 7.0, 12.0)

# Dưới ngưỡng này thì chênh cao nằm trong sai số đứng của DEM toàn cầu —
# nói "thượng nguồn" ở đồng bằng là nói bừa.
MIN_RELIEF_M = 20.0

# Điểm phải cao hơn thửa ít nhất chừng này mới tính là thượng nguồn.
MIN_DROP_M = 5.0


def _offset(lat: float, lon: float, km: float, bearing_deg: float):
    d = km / 6371.0
    b = math.radians(bearing_deg)
    la1, lo1 = math.radians(lat), math.radians(lon)
    la2 = math.asin(math.sin(la1) * math.cos(d)
                    + math.cos(la1) * math.sin(d) * math.cos(b))
    lo2 = lo1 + math.atan2(math.sin(b) * math.sin(d) * math.cos(la1),
                           math.cos(d) - math.sin(la1) * math.sin(la2))
    return round(math.degrees(la2), 4), round(math.degrees(lo2), 4)


def _fan(lat: float, lon: float):
    pts = [(lat, lon)]
    for km in RADII_KM:
        for i in range(BEARINGS):
            pts.append(_offset(lat, lon, km, i * 360.0 / BEARINGS))
    return pts


def rain7_thresholds(lat: float, lon: float) -> tuple[float, float] | None:
    """(P90, P97) tổng mưa 7 ngày tại chỗ, 10 năm ERA5. None nếu không tải được khí hậu nền."""
    from app.services import calibration
    dist = calibration.climatology("rain7", lat, lon)
    if not dist:
        return None
    q = lambda f: dist[min(len(dist) - 1, int(f * (len(dist) - 1)))]   # noqa: E731
    return round(q(0.90), 1), round(q(0.97), 1)


def upstream(lat: float, lon: float) -> dict | None:
    """Mưa dự báo ở phần đất cao hơn quanh thửa, cân theo độ dốc về phía thửa.

    Trả None khi không lấy được dữ liệu. Trả dict với `available=False` khi lấy
    được nhưng địa hình quá phẳng để nói chuyện thượng nguồn — hai tình huống
    khác nhau, người gọi cần phân biệt.
    """
    from app.services import realdata

    pts = _fan(lat, lon)
    elevs = realdata.elevation_multi(pts)
    if not elevs or elevs[0] is None:
        return None

    here = elevs[0]
    ring = [(p, e) for p, e in zip(pts[1:], elevs[1:]) if e is not None]
    if len(ring) < BEARINGS:
        return None

    vals = [e for _, e in ring] + [here]
    relief = max(vals) - min(vals)
    if relief < MIN_RELIEF_M:
        return {
            "available": False,
            "reason": "flat",
            "here_m": here,
            "relief_m": round(relief, 1),
            "message": tr(
                f"Chênh cao quanh thửa chỉ {relief:.0f} m trong bán kính "
                f"{RADII_KM[-1]:.0f} km — nằm trong sai số đứng của DEM toàn cầu. "
                "Ở địa hình này nước đi đâu là do đê bao, cống và kênh quyết "
                "định, không do độ dốc; phần mềm không đoán thay.",
                f"Relief around the plot is only {relief:.0f} m within a "
                f"{RADII_KM[-1]:.0f} km radius — within the global DEM's "
                "vertical error margin. On terrain like this, where water goes "
                "is decided by dikes, culverts and canals, not slope; the app "
                "doesn't guess."),
        }

    # Giữ lại phần đất CAO HƠN — nước từ đó chảy về phía thửa.
    up = []
    for (pla, plo), e in ring:
        drop = e - here
        if drop < MIN_DROP_M:
            continue
        km = _km(lat, lon, pla, plo)
        # Trọng số: dốc về phía thửa (m trên km). Gần và cao thì nặng ký hơn.
        up.append({"lat": pla, "lon": plo, "elev": e,
                   "drop_m": round(drop, 1), "km": round(km, 1),
                   "w": drop / max(1.0, km)})

    if not up:
        return {
            "available": False, "reason": "no_upslope",
            "here_m": here, "relief_m": round(relief, 1),
            "message": tr(
                "Thửa này nằm ở phần cao của khu vực — không có sườn "
                "nào đáng kể đổ nước về đây. Đó là tin tốt cho nguy cơ "
                "ngập từ thượng nguồn.",
                "This plot sits on the high ground of the area — no slope "
                "of any size drains toward it. That's good news for "
                "upstream flood risk."),
        }

    rain = realdata.weather_multi([(u["lat"], u["lon"]) for u in up])
    tot_w = sum(u["w"] for u in up)
    acc = 0.0
    counted = 0
    for u, rows in zip(up, rain):
        if not rows:
            continue
        mm = sum(r["precip"] for r in rows)
        u["rain_7d_mm"] = round(mm, 1)
        acc += mm * u["w"]
        counted += 1
    if counted == 0:
        return None

    weighted = acc / tot_w if tot_w else 0.0

    # So với mưa tại chỗ: điều người dùng cần biết là "trên kia có mưa NHIỀU HƠN
    # ở đây không". Mưa thượng nguồn bằng mưa tại chỗ thì không thêm thông tin.
    local = realdata.weather_7d(lat, lon)
    local_mm = sum(r["precip"] for r in local) if local else None
    extra = (weighted - local_mm) if local_mm is not None else None

    # Kiểm A–Z 21/11/2026, P1-1: ngưỡng CỐ ĐỊNH 200/100 mm báo NGUY HIỂM ở Quảng Điền (Huế) với 210 mm thượng nguồn,
    # trong khi mô-đun Lũ (đã hiệu chuẩn) báo "ít nguy cơ" — ở Huế 7 ngày mưa ≥ 200 mm xảy ra 4,2% số tuần cả năm, 12,6%
    # tháng 10–12 (ERA5 2015–2024, đo 21/11/2026). Nay ngưỡng theo khí hậu 10 năm TẠI CHỖ, cùng thang với mô-đun Lũ:
    # cảnh báo ≥ P90, nguy hiểm ≥ P97 của tổng mưa 7 ngày — không thấp hơn 100/200 mm. Không tải được khí hậu nền thì
    # giữ ngưỡng tuyệt đối và ghi rõ.
    th = rain7_thresholds(lat, lon)
    warn_mm, danger_mm = (max(100.0, th[0]), max(200.0, th[1])) if th else (100.0, 200.0)

    if weighted >= danger_mm and (extra is None or extra > 20):
        level = "danger"
        verdict = tr("thượng nguồn đang mưa rất lớn và nước sẽ dồn về đây",
                     "upstream is getting very heavy rain and water will flow down here")
    elif weighted >= warn_mm and (extra is None or extra > 10):
        level = "warning"
        verdict = tr("thượng nguồn mưa đáng kể, cần tính tới nước từ trên xuống",
                     "significant rain upstream — factor in water coming down")
    elif extra is not None and extra < -20:
        level = "safe"
        verdict = tr("thượng nguồn khô hơn tại chỗ — nước dồn về ít",
                     "upstream is drier than here — little water flowing down")
    else:
        level = "safe"
        verdict = tr("thượng nguồn không mưa bất thường", "no unusual rain upstream")

    up.sort(key=lambda u: u["w"], reverse=True)
    top = up[0]

    return {
        "available": True,
        "level": level,
        "verdict": verdict,
        "here_m": here,
        "relief_m": round(relief, 1),
        "upslope_points": counted,
        "total_points": len(ring),
        "upstream_rain_mm": round(weighted, 1),
        "local_rain_mm": round(local_mm, 1) if local_mm is not None else None,
        "extra_vs_local_mm": round(extra, 1) if extra is not None else None,
        "steepest": {"km": top["km"], "drop_m": top["drop_m"],
                     "rain_7d_mm": top.get("rain_7d_mm")},
        "calibrated": th is not None,
        "warn_mm": round(warn_mm, 1),
        "danger_mm": round(danger_mm, 1),
        "method": tr(
            f"Lấy mẫu {BEARINGS} hướng × {len(RADII_KM)} vòng "
            f"({', '.join(f'{r:.0f}' for r in RADII_KM)} km), giữ lại điểm cao "
            f"hơn thửa ≥{MIN_DROP_M:.0f} m, cân theo độ dốc về phía thửa "
            "(mét chênh cao trên mỗi km).",
            f"Samples {BEARINGS} bearings × {len(RADII_KM)} rings "
            f"({', '.join(f'{r:.0f}' for r in RADII_KM)} km), keeps points at "
            f"least {MIN_DROP_M:.0f} m higher than the plot, weighted by slope "
            "toward the plot (meters of drop per km).")
        + (tr(f" Ngưỡng theo khí hậu 10 năm tại chỗ (ERA5): cảnh báo từ {warn_mm:.0f} mm, nguy hiểm từ {danger_mm:.0f} mm "
              "mưa 7 ngày (P90/P97, không dưới 100/200 mm).",
              f" Thresholds from this spot's 10-year climate (ERA5): warning from {warn_mm:.0f} mm, danger from "
              f"{danger_mm:.0f} mm of 7-day rain (P90/P97, never below 100/200 mm).") if th else
           tr(" Chưa tải được khí hậu nền — dùng ngưỡng tuyệt đối 100/200 mm mưa 7 ngày.",
              " Baseline climate unavailable — using absolute thresholds of 100/200 mm of 7-day rain.")),
        "caveat": tr(
            "KHÔNG phải lưu vực được phân định đúng cách — là nan quạt lấy mẫu "
            "theo hướng dốc lên, giả định nước chảy thẳng xuống dốc. Bỏ qua "
            "lòng sông, đê bao, cống và hồ chứa. Dùng như một đối chứng, không "
            "thay cho cảnh báo của cơ quan thuỷ văn.",
            "NOT a properly delineated watershed — it's a fan sample uphill, "
            "assuming water flows straight downslope. Ignores riverbeds, dikes, "
            "culverts and reservoirs. Use as a cross-check, not a replacement "
            "for official hydrological warnings."),
    }


def _km(la1: float, lo1: float, la2: float, lo2: float) -> float:
    from app.services import datasources as ds
    return ds._haversine_km(la1, lo1, la2, lo2)
