"""S02 — Counterfactual Time Machine: xác suất từ những năm CÓ THẬT.

Thay vì Monte Carlo với phân phối tự bịa, ta dùng ANALOG ENSEMBLE:
lấy đúng cửa sổ lịch này (cùng ngày/tháng) của N năm gần nhất từ ERA5 —
mỗi năm là một "tương lai đã từng xảy ra" ở CHÍNH mảnh đất này — rồi chạy
đúng mô hình cảnh báo trên từng năm.

Kết quả: "3/10 năm cùng kỳ sẽ vượt ngưỡng nguy hiểm → xác suất ~30%",
kèm P10/P50/P90. Mọi con số truy ngược được về một năm thật, kiểm chứng được.
"""
from __future__ import annotations

from datetime import date, timedelta

from app.services import hazard
from app.services import realdata

_WINDOW = 7          # số ngày mô phỏng, khớp dự báo 7 ngày
_LAG_DAYS = 10       # ERA5 trễ vài ngày → lùi an toàn


def _percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    i = p / 100.0 * (len(sorted_vals) - 1)
    lo, hi = int(i), min(int(i) + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (i - lo)


def run(module_id: str, lat: float, lon: float, years: int = 10,
        today: date | None = None) -> dict | None:
    if not hazard.supports(module_id):
        return None
    name, unit = hazard.name_unit(module_id)
    today = today or date.today()

    # Cửa sổ lịch: cùng ngày/tháng, N năm gần nhất (bỏ năm hiện tại vì ERA5 trễ).
    last_year = (today - timedelta(days=_LAG_DAYS)).year - 1
    first_year = last_year - years + 1

    start = date(first_year, 1, 1).isoformat()
    end = date(last_year, 12, 31).isoformat()
    rows = realdata.historical_weather(lat, lon, start, end)
    if not rows:
        return {
            "module_id": module_id, "module_name": name, "unit": unit,
            "available": False,
            "message": "Chưa tải được dữ liệu lịch sử ERA5 (kiểm tra kết nối mạng).",
            "members": [],
        }

    by_date = {r["date"]: r for r in rows}
    members = []
    for y in range(first_year, last_year + 1):
        try:
            anchor = date(y, today.month, today.day)
        except ValueError:            # 29/2 ở năm không nhuận
            anchor = date(y, today.month, 28)
        window = []
        for d in range(_WINDOW):
            key = (anchor + timedelta(days=d)).isoformat()
            r = by_date.get(key)
            if r is None:
                break
            window.append({**r, "day": d})
        if len(window) < _WINDOW:
            continue
        series = hazard.index_series(module_id, lat, lon, window)
        peak = hazard.peak_of(series)
        members.append({
            "year": y,
            "peak": round(peak, 1),
            "rain_total_mm": round(sum(w["precip"] for w in window), 1),
            "danger": peak >= hazard.WARNING,
            "warning": peak >= hazard.SAFE,
            "series": [{"day": d, "date": dt, "value": v} for d, dt, v in series],
        })

    if not members:
        return {
            "module_id": module_id, "module_name": name, "unit": unit,
            "available": False,
            "message": "Không đủ dữ liệu lịch sử cho cửa sổ ngày này.",
            "members": [],
        }

    peaks = sorted(m["peak"] for m in members)
    n = len(members)
    n_danger = sum(1 for m in members if m["danger"])
    n_warning = sum(1 for m in members if m["warning"])
    worst = max(members, key=lambda m: m["peak"])
    best = min(members, key=lambda m: m["peak"])

    # Dự báo hiện tại đặt cạnh phân phối lịch sử → "năm nay đứng ở đâu".
    now_rows = realdata.weather_7d(lat, lon)
    now_peak = None
    now_rank_pct = None
    if now_rows:
        now_peak = round(hazard.peak_of(hazard.index_series(module_id, lat, lon, now_rows)), 1)
        n_below = sum(1 for p in peaks if p < now_peak)
        now_rank_pct = round(100.0 * n_below / n)

    p_danger = round(100.0 * n_danger / n)
    headline = (
        f"Cùng kỳ {n} năm qua tại đây: {n_danger}/{n} năm vượt ngưỡng nguy hiểm "
        f"→ xác suất ~{p_danger}%."
    )
    if now_peak is not None:
        headline += (f" Dự báo năm nay ({now_peak} {unit}) cao hơn "
                     f"{now_rank_pct}% số năm đó.")

    return {
        "module_id": module_id, "module_name": name, "unit": unit,
        "available": True, "is_real": True,
        "window_days": _WINDOW,
        "years": n, "from_year": first_year, "to_year": last_year,
        "prob_danger_pct": p_danger,
        "prob_warning_pct": round(100.0 * n_warning / n),
        "p10": round(_percentile(peaks, 10), 1),
        "p50": round(_percentile(peaks, 50), 1),
        "p90": round(_percentile(peaks, 90), 1),
        "current_peak": now_peak,
        "current_rank_pct": now_rank_pct,
        "worst_year": {"year": worst["year"], "peak": worst["peak"],
                       "rain_total_mm": worst["rain_total_mm"]},
        "best_year": {"year": best["year"], "peak": best["peak"],
                      "rain_total_mm": best["rain_total_mm"]},
        "headline": headline,
        "members": members,
        "threshold_warning": hazard.WARNING,
        "threshold_safe": hazard.SAFE,
        "method": ("Analog ensemble: mỗi thành viên là thời tiết THẬT (ERA5) cùng "
                   "ngày/tháng của một năm đã qua tại chính toạ độ này, chạy qua "
                   "đúng mô hình cảnh báo. Không có phân phối giả định."),
        "data_source": "Open-Meteo Archive (ERA5) — thời tiết lịch sử thật",
    }
