"""A3 — DỰ BÁO XÁC SUẤT từ tổ hợp vật lý.

"Chỉ số 72 điểm" không giúp nông dân quyết định gặt sớm hay không. "70% khả năng
chạm ngưỡng nguy hiểm trong 7 ngày tới" thì có — và đó là chuẩn của mọi cơ quan
khí tượng nghiệp vụ.

Cách làm rẻ mà THẬT: chạy đúng chỉ số hiểm hoạ trên từng thành viên của tổ hợp
dự báo (ensemble-api.open-meteo.com, không cần khoá), rồi lấy phân vị thực
nghiệm. Xác suất ở đây là ĐẾM số kịch bản vượt ngưỡng trên tổng số thành viên —
không bịa ra từ một con số điểm.
"""
from __future__ import annotations

ENS_URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
_VARS = "precipitation_sum,et0_fao_evapotranspiration,temperature_2m_max"
_MODEL = "gfs_seamless"


def summarize(peaks: list[float]) -> dict:
    """Từ đỉnh chỉ số của các thành viên → phân vị P10/P50/P90 + xác suất vượt
    ngưỡng + một câu tiếng người. Ít hơn 5 thành viên thì nói thẳng chưa đủ."""
    import numpy as np
    from app.services import hazard

    vals = [float(p) for p in peaks if p is not None]
    n = len(vals)
    if n < 5:
        return {"available": False, "members": n,
                "message": "Chưa đủ thành viên tổ hợp để cho xác suất."}
    arr = np.asarray(vals, dtype=float)
    p10, p50, p90 = (round(float(np.percentile(arr, q)), 1) for q in (10, 50, 90))
    prob_warn = int(round(100.0 * float(np.mean(arr >= hazard.WARNING))))
    prob_watch = int(round(100.0 * float(np.mean(arr >= hazard.SAFE))))
    return {
        "available": True, "members": n,
        "p10": p10, "p50": p50, "p90": p90,
        "prob_exceed_warning": prob_warn,   # % thành viên ≥ ngưỡng NGUY HIỂM (70)
        "prob_exceed_watch": prob_watch,    # % thành viên ≥ ngưỡng ĐÁNG CHÚ Ý (40)
        "sentence": _sentence(prob_warn, prob_watch),
    }


def _sentence(prob_warn: int, prob_watch: int) -> str:
    if prob_warn >= 50:
        return f"{prob_warn}% khả năng chạm mức NGUY HIỂM trong 7 ngày tới."
    if prob_watch >= 50:
        return (f"{prob_watch}% khả năng chạm mức đáng chú ý trong 7 ngày tới "
                f"({prob_warn}% tới mức nguy hiểm).")
    return f"Phần lớn kịch bản an toàn — chỉ {prob_warn}% chạm mức nguy hiểm."


def _member_rows(daily: dict, i: int):
    """Dựng rows cho thành viên thứ i từ khối daily của ensemble-api. Thiếu biến
    của thành viên thì lùi về cột control (không có member) — vẫn chạy được."""
    from app.services import realdata

    def col(base: str):
        return daily.get(f"{base}_member{i:02d}") or daily.get(base) or []

    item = {"daily": {
        "time": daily.get("time") or [],
        "precipitation_sum": col("precipitation_sum"),
        "et0_fao_evapotranspiration": col("et0_fao_evapotranspiration"),
        "temperature_2m_max": col("temperature_2m_max"),
    }}
    return realdata._rows_from_daily(item)


def forecast(module_id: str, lat: float, lon: float) -> dict:
    """Xác suất vượt ngưỡng cho 7 ngày tới, từ tổ hợp vật lý. Best-effort: gọi
    mạng ra ngoài, hỏng thì nói thẳng chưa đủ dữ liệu chứ không đoán."""
    from app.services import hazard, realdata

    if not hazard.supports(module_id):
        return {"available": False,
                "message": "Mô-đun này chưa tính xác suất theo tổ hợp."}
    try:
        url = (f"{ENS_URL}?latitude={lat:.4f}&longitude={lon:.4f}"
               f"&daily={_VARS}&models={_MODEL}&forecast_days=7")
        d = realdata._get(url)
        daily = (d or {}).get("daily")
        if not daily:
            return {"available": False, "message": "Chưa lấy được tổ hợp dự báo."}
        members = sorted({int(k.rsplit("member", 1)[1])
                          for k in daily if "member" in k
                          and k.rsplit("member", 1)[1].isdigit()})
        peaks: list[float] = []
        for i in members:
            rows = _member_rows(daily, i)
            if rows:
                peaks.append(hazard.peak_of(
                    hazard.index_series(module_id, lat, lon, rows)))
        out = summarize(peaks)
        out["module_id"] = module_id
        return out
    except Exception as e:      # noqa: BLE001
        return {"available": False,
                "message": f"Chưa tính được xác suất: {type(e).__name__}."}
