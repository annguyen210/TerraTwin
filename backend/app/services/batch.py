"""THẨM ĐỊNH HÀNG LOẠT — một tệp CSV nhiều thửa → bảng rủi ro cả danh mục.

AI CẦN. Cán bộ tín dụng nông nghiệp có vài trăm khoản vay thế chấp bằng đất;
hợp tác xã có vài trăm thửa xã viên; công ty bảo hiểm có danh sách hợp đồng.
Họ không mở từng thửa trên bản đồ. Họ dán một bảng toạ độ và cần biết: thửa nào
là đất gì, thửa nào đang có mối đe doạ thật, mười năm qua chỗ nào ngập nhiều,
và bao nhiêu phần trăm diện tích danh mục đang chịu rủi ro.

KHÔNG MÔ HÌNH MỚI: mỗi dòng chạy đúng các dịch vụ đã có — loại đất ESA WorldCover
(landuse), quét 18 mô-đun (scan), mười năm hiểm hoạ ERA5 (passport). Mức rủi ro
của thửa dùng ĐÚNG quy tắc của danh mục đã lưu (portfolio.overview): chỉ tính
mô-đun có dữ liệu thật VÀ là mối đe doạ — điện mặt trời "kém" không phải rủi ro.

TRẦN 50 THỬA/LẦN (gói miễn phí, xem max_rows): mỗi thửa tốn vài lượt gọi nguồn
dữ liệu miễn phí (Open-Meteo, Planetary Computer). Vượt hạn mức nguồn là MỌI
người dùng mất dữ liệu, không riêng người chạy lô.

CHẠY TIẾP ĐƯỢC: kết quả ghi xuống bảng batch_runs SAU MỖI THỬA. Render free ngủ
sau 15 phút không có request → tiến trình chết giữa lô; lần khởi động sau,
jobs_db.requeue_running đưa việc về hàng đợi và hàm xử lý đi tiếp từ thửa dở.
"""
from __future__ import annotations

import csv
import io
import re

from app.services.reqlang import tr

# TRẦN + NHỊP (review 2/10/2026): 200 thửa × (quét 18 mô-đun + 10 năm ERA5 + loại
# đất) ≈ vài nghìn lượt gọi ra ngoài từ IP Render — IP mà Open-Meteo vốn đã từng
# chặn. Gói miễn phí: 50 thửa/lần, tuần tự, nghỉ giữa các thửa, gặp hạn mức thì
# TẠM DỪNG chứ không nã tiếp. Chỉnh được khi lên gói trả phí:
#   TERRATWIN_BATCH_MAX_ROWS   (mặc định 50)
#   TERRATWIN_BATCH_DELAY_S    (mặc định 3 giây giữa hai thửa)
#   TERRATWIN_BATCH_PAUSE_S    (mặc định 60 giây mỗi lần chờ hạn mức)
#   TERRATWIN_BATCH_MAX_PAUSES (mặc định 15 lần chờ ≈ 15 phút cho mỗi thửa)
def _env_num(name: str, default: float) -> float:
    import os
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


def max_rows() -> int:
    return int(_env_num("TERRATWIN_BATCH_MAX_ROWS", 50))


MAX_ROWS = 50   # giá trị mặc định, để hiển thị; dùng max_rows() khi chạy
_RANK = {"danger": 0, "warning": 1, "safe": 2, "unknown": 3}

# Tên cột chấp nhận (không phân biệt hoa thường, bỏ dấu cách/gạch).
_COLS = {
    "ref": ("ma", "mã", "ref", "id", "ten", "tên", "name", "so_thua", "sothua", "khoan_vay", "hop_dong"),
    "lat": ("lat", "latitude", "vi_do", "vĩ_độ", "vido", "vĩđộ"),
    "lon": ("lon", "lng", "long", "longitude", "kinh_do", "kinh_độ", "kinhdo", "kinhđộ"),
    "area_ha": ("area_ha", "area", "ha", "dien_tich", "diện_tích", "dientich", "dien_tich_ha"),
}

TEMPLATE = ("ma,lat,lon,area_ha\n"
            "KV-001,16.4600,107.5900,0.3\n"
            "KV-002,10.4000,105.2000,1.5\n"
            "KV-003,12.7500,108.1500,2\n")


def _norm(h: str) -> str:
    return re.sub(r"[\s\-]+", "_", h.strip().lower()).strip("_")


def _num(s: str, decimal_comma: bool) -> float | None:
    s = (s or "").strip()
    if not s:
        return None
    if decimal_comma:
        s = s.replace(".", "").replace(",", ".") if s.count(",") == 1 and s.count(".") >= 1 \
            else s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def parse_csv(text: str) -> tuple[list[dict], list[dict]]:
    """→ (dòng hợp lệ, lỗi [{line, message}]). Chấp nhận dấu phân cách , ; tab;
    Excel tiếng Việt hay xuất ';' kèm dấu phẩy thập phân ("16,46")."""
    text = (text or "").lstrip("\ufeff").strip()
    if not text:
        return [], [{"line": 0, "message": tr("Tệp rỗng.", "Empty file.")}]
    first = text.splitlines()[0]
    delim = max((";", ",", "\t"), key=first.count)
    decimal_comma = delim != ","
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    header = [_norm(h) for h in next(reader, [])]
    idx = {}
    for key, names in _COLS.items():
        for i, h in enumerate(header):
            if h in {_norm(n) for n in names}:
                idx[key] = i
                break
    if "lat" not in idx or "lon" not in idx:
        return [], [{"line": 1, "message": tr(
            "Thiếu cột toạ độ. Dòng đầu phải có cột lat và lon (hoặc vi_do, kinh_do).",
            "Missing coordinate columns. The header must have lat and lon.")}]

    rows, errors = [], []
    for n, rec in enumerate(reader, start=2):
        if not any(c.strip() for c in rec):
            continue
        get = lambda k: rec[idx[k]] if k in idx and idx[k] < len(rec) else ""
        lat, lon = _num(get("lat"), decimal_comma), _num(get("lon"), decimal_comma)
        ref = (get("ref") or f"#{n - 1}").strip()[:60]
        if lat is None or lon is None:
            errors.append({"line": n, "message": tr(f"{ref}: toạ độ không phải số.",
                                                    f"{ref}: coordinates are not numbers.")})
            continue
        if not (8.0 <= lat <= 23.6 and 102.0 <= lon <= 110.0):
            hint = tr(" (có thể đã đảo lat/lon)", " (lat/lon may be swapped)") \
                if (8.0 <= lon <= 23.6 and 102.0 <= lat <= 110.0) else ""
            errors.append({"line": n, "message": tr(f"{ref}: ngoài lãnh thổ Việt Nam{hint}.",
                                                    f"{ref}: outside Vietnam{hint}.")})
            continue
        area = _num(get("area_ha"), decimal_comma)
        rows.append({"ref": ref, "lat": round(lat, 6), "lon": round(lon, 6),
                     "area_ha": area if area and area > 0 else None})
        if len(rows) > max_rows():
            errors.append({"line": n, "message": tr(
                f"Quá {max_rows()} thửa — chỉ lấy {max_rows()} thửa đầu; chia phần còn lại "
                "thành lần chạy khác (trần bảo vệ hạn mức nguồn dữ liệu miễn phí).",
                f"More than {max_rows()} plots — only the first {max_rows()} are kept; split "
                "the rest into another run (protects the free data sources' quota).")})
            rows = rows[:max_rows()]
            break
    return rows, errors


def appraise(row: dict) -> dict:
    """Thẩm định MỘT thửa từ dịch vụ sẵn có. Không ném lỗi: hỏng thì ghi error."""
    from app.schemas import Location
    from app.services import jobs, landuse, passport, scan

    loc = Location(lat=row["lat"], lon=row["lon"], area_ha=row["area_ha"])
    sc, lu, pp = jobs.gather([lambda: scan.scan(loc),
                              lambda: landuse.composition(row["lat"], row["lon"]),
                              lambda: passport.build(row["lat"], row["lon"])])
    out = {**row, "land_group": None, "land_label": None, "risk_level": "unknown",
           "score": None, "grade": None, "drivers": [], "history_10y": {},
           "real_data_ratio": None, "error": None}
    if lu:
        out["land_group"], out["land_label"] = lu["dominant_group"], lu["label"]
    if sc is not None:
        real = [m for m in sc.modules if m.is_real and m.threat]
        out["risk_level"] = min((m.risk_level for m in real),
                                key=lambda r: _RANK.get(r, 9), default="unknown")
        out["drivers"] = [m.name for m in sorted(
            (m for m in real if m.risk_level in ("danger", "warning")),
            key=lambda m: _RANK.get(m.risk_level, 9))][:3]
        out["score"], out["grade"] = sc.terrascore.score, sc.terrascore.grade
        out["real_data_ratio"] = round(sc.real_data_ratio, 2)
    if pp and pp.get("available") and pp.get("history"):
        out["history_10y"] = {mid: h.get("events", 0) for mid, h in pp["history"].items()}
    if sc is None and lu is None:
        out["error"] = tr("Không lấy được dữ liệu cho thửa này.",
                          "No data could be fetched for this plot.")
    return out


def summarize(results: list[dict]) -> dict:
    ok = [r for r in results if not r.get("error")]
    by_risk = {k: 0 for k in ("danger", "warning", "safe", "unknown")}
    by_land: dict[str, int] = {}
    grades: dict[str, int] = {}
    drivers: dict[str, int] = {}
    hist_any: dict[str, int] = {}
    total_ha = at_risk_ha = 0.0
    for r in ok:
        by_risk[r["risk_level"]] = by_risk.get(r["risk_level"], 0) + 1
        g = r.get("land_group") or "unknown"
        by_land[g] = by_land.get(g, 0) + 1
        if r.get("grade"):
            grades[r["grade"]] = grades.get(r["grade"], 0) + 1
        for d in r.get("drivers") or []:
            drivers[d] = drivers.get(d, 0) + 1
        for mid, n in (r.get("history_10y") or {}).items():
            if n:
                hist_any[mid] = hist_any.get(mid, 0) + 1
        ha = float(r.get("area_ha") or 0)
        total_ha += ha
        if r["risk_level"] in ("danger", "warning"):
            at_risk_ha += ha
    watch = sorted(ok, key=lambda r: (_RANK.get(r["risk_level"], 9), r.get("score") or 999))
    n = len(ok)
    at_risk = by_risk["danger"] + by_risk["warning"]
    return {
        "n": len(results), "n_ok": n, "n_failed": len(results) - n,
        "by_risk": by_risk, "by_land": by_land, "grades": grades,
        "top_drivers": sorted(drivers.items(), key=lambda kv: -kv[1])[:5],
        "history_10y_plots": hist_any,
        "total_ha": round(total_ha, 2), "at_risk_ha": round(at_risk_ha, 2),
        "at_risk_pct": round(100 * at_risk / n, 1) if n else None,
        "watchlist": [r["ref"] for r in watch if r["risk_level"] in ("danger", "warning")][:10],
        "headline": (tr(f"{at_risk}/{n} thửa đang có mối đe doạ thật"
                        + (f" ({round(at_risk_ha, 1)}/{round(total_ha, 1)} ha)" if total_ha else "")
                        + f"; {by_land.get('built', 0)} thửa là đất xây dựng.",
                        f"{at_risk}/{n} plots face a real threat"
                        + (f" ({round(at_risk_ha, 1)}/{round(total_ha, 1)} ha)" if total_ha else "")
                        + f"; {by_land.get('built', 0)} plots are built-up land.")
                     if n else tr("Không thẩm định được thửa nào.", "No plot could be appraised.")),
    }


def run(rows: list[dict], on_progress=None) -> dict:
    """Thẩm định lần lượt (không song song nhiều thửa: mỗi thửa đã gọi song song
    bên trong; chạy nhiều thửa cùng lúc chỉ dồn ép nguồn dữ liệu miễn phí)."""
    results = []
    for i, r in enumerate(rows):
        if on_progress:
            on_progress(i, len(rows), r["ref"])
        try:
            results.append(appraise(r))
        except Exception:
            results.append({**r, "risk_level": "unknown", "error": tr(
                "Lỗi khi thẩm định thửa này.", "Error appraising this plot.")})
    if on_progress:
        on_progress(len(rows), len(rows), "")
    return {"rows": results, "summary": summarize(results)}


CSV_COLUMNS = ["ref", "lat", "lon", "area_ha", "land_group", "land_label", "risk_level",
               "score", "grade", "drivers", "flood_10y", "drought_10y", "landslide_10y",
               "wildfire_10y", "real_data_ratio", "error"]


def _cell(v) -> str:
    """Chống CSV injection: ô chữ do người dùng nhập bắt đầu bằng = + - @ (hay
    tab/CR) thì Excel chạy như CÔNG THỨC — có thể gọi lệnh ra ngoài. Thêm dấu '
    phía trước để Excel coi là chữ. Số thì để nguyên."""
    if v is None:
        return ""
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def to_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_COLUMNS)
    for r in rows:
        h = r.get("history_10y") or {}
        w.writerow([_cell(x) for x in (
            r.get("ref"), r.get("lat"), r.get("lon"), r.get("area_ha"),
            r.get("land_group"), r.get("land_label"), r.get("risk_level"),
            r.get("score"), r.get("grade"), "; ".join(r.get("drivers") or []),
            h.get("flood"), h.get("drought"), h.get("landslide"), h.get("wildfire"),
            r.get("real_data_ratio"), r.get("error"))])
    # BOM để Excel trên Windows mở đúng tiếng Việt.
    return "\ufeff" + buf.getvalue()


# ------------------------------------------------------------------ việc nền

JOB_KIND = "batch_appraisal"


def _wait_for_quota(report) -> bool:
    """Nguồn dữ liệu đang bị chặn vì quá hạn mức (429)? Chờ — không nã tiếp.
    True nếu đã thông; False nếu chờ đủ trần mà vẫn bị chặn (chạy tiếp, dòng
    nào thiếu dữ liệu sẽ tự ghi thiếu)."""
    import time

    from app.services import realdata
    pauses = int(_env_num("TERRATWIN_BATCH_MAX_PAUSES", 15))
    for k in range(pauses):
        ex = realdata.quota_status().get("exhausted") or []
        if not ex:
            return True
        report("paused_quota", ex)
        time.sleep(_env_num("TERRATWIN_BATCH_PAUSE_S", 60))
    return not (realdata.quota_status().get("exhausted") or [])


def _register() -> None:
    import json
    import time

    from app.services import jobs_db, reqlang

    @jobs_db.register(JOB_KIND)
    def _job(args: dict) -> dict:
        from app import db as _db
        from app.db import BatchRun

        reqlang.set_lang(args.get("lang"))
        job_id = args.get("_job_id")
        rows = args["rows"]

        from sqlalchemy import select

        def _still_there(s) -> bool:
            # Hỏi THẲNG CSDL — s.get() trả lại đối tượng đang giữ trong phiên này
            # nên không bao giờ thấy được việc người dùng xoá lô từ phiên khác.
            return s.execute(select(BatchRun.id).where(BatchRun.id == job_id)).first() is not None

        with _db.SessionLocal() as s:
            run_row = s.get(BatchRun, job_id)
            if run_row is None and args.get("run_created"):
                return {"run_id": job_id, "cancelled": True}   # đã xoá trước khi chạy
            if run_row is None:                      # lô gửi từ bản cũ chưa tạo sẵn
                run_row = BatchRun(id=job_id, user_id=int(args["user_id"]),
                                   title=str(args.get("title") or "")[:200],
                                   n_rows=len(rows), rows_json="[]", state="queued")
                s.add(run_row)
            done = json.loads(run_row.rows_json or "[]")   # chạy TIẾP từ thửa dở
            run_row.state = "running"
            s.commit()

            def report(phase: str, extra=None) -> None:
                jobs_db.report_progress(job_id, {"done": len(done), "total": len(rows),
                                                 "current": rows[len(done)]["ref"]
                                                 if len(done) < len(rows) else "",
                                                 "phase": phase, "detail": extra})

            for i in range(len(done), len(rows)):
                _wait_for_quota(report)
                report("running")
                try:
                    done.append(appraise(rows[i]))
                except Exception:
                    done.append({**rows[i], "risk_level": "unknown", "error": tr(
                        "Lỗi khi thẩm định thửa này.", "Error appraising this plot.")})
                # Ghi SAU MỖI THỬA: máy chủ chết lúc này thì lần sau đi tiếp từ i+1.
                if not _still_there(s):              # người dùng đã xoá lô
                    return {"run_id": job_id, "cancelled": True}
                run_row.rows_json = json.dumps(done, ensure_ascii=False)
                s.commit()
                if i < len(rows) - 1:
                    time.sleep(_env_num("TERRATWIN_BATCH_DELAY_S", 3))

            summary = summarize(done)
            run_row.summary_json = json.dumps(summary, ensure_ascii=False)
            run_row.state = "done"
            s.commit()
        report("done")
        return {"run_id": job_id, "summary": summary}


_register()
