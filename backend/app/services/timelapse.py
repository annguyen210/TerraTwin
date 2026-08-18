"""C04 — Time-Lapse: rủi ro của thửa đất này đã đổi thế nào qua các năm.

Bản đầy đủ của C04 là phát hiện thay đổi trên ẢNH vệ tinh hai kỳ, và cái đó cần
ảnh Sentinel (chưa có). Nhưng "time-lapse" theo đúng nghĩa — xem một thứ biến
đổi theo thời gian — thì làm được ngay với ERA5: chạy chính mô hình cảnh báo
trên từng năm quá khứ và xem rủi ro đi lên hay đi xuống.

Điều này trả lời câu hỏi người mua đất và ngân hàng thực sự hỏi: "mảnh này ngày
càng rủi ro hơn, hay đang tốt lên?" — câu hỏi mà một tấm ảnh vệ tinh đơn lẻ
không trả lời được.

GIỚI HẠN ĐÃ GHI RÕ: đây là time-lapse của RỦI RO KHÍ HẬU, không phải phát hiện
thay đổi bề mặt (mất rừng, xây dựng mới). Cái sau cần ảnh Sentinel.
"""
from __future__ import annotations

from datetime import date, timedelta

from app.services import cache_store, hazard, realdata

_LAG_DAYS = 10
_TTL = 7 * 24 * 3600


def _year_peak(module_id: str, lat: float, lon: float, rows: list) -> tuple[float, str]:
    """Đỉnh chỉ số trong năm + ngày đạt đỉnh, dùng cửa sổ trượt 7 ngày."""
    best, best_date = 0.0, ""
    for i in range(0, max(0, len(rows) - 7), 3):     # bước 3 ngày cho nhanh
        w = [{**r, "day": j} for j, r in enumerate(rows[i:i + 7])]
        s = hazard.index_series(module_id, lat, lon, w)
        p = hazard.peak_of(s)
        if p > best:
            best, best_date = p, rows[i]["date"]
    return round(best, 1), best_date


def build(module_id: str, lat: float, lon: float, years: int = 10) -> dict | None:
    if not hazard.supports(module_id):
        return None
    name, unit = hazard.name_unit(module_id)
    years = max(3, min(int(years), 20))

    key = cache_store.make_key("timelapse", module_id, round(lat, 3),
                               round(lon, 3), years)
    hit = cache_store.get(key)
    if hit:
        hit["cached"] = True
        return hit

    last = (date.today() - timedelta(days=_LAG_DAYS)).year - 1
    first = last - years + 1
    rows = realdata.historical_weather(lat, lon, f"{first}-01-01", f"{last}-12-31")
    if not rows:
        return {"available": False, "module_id": module_id, "module_name": name,
                "message": "Chưa tải được dữ liệu lịch sử ERA5 (kiểm tra mạng)."}

    by_year: dict[int, list] = {}
    for r in rows:
        try:
            y = int(r["date"][:4])
        except (KeyError, ValueError):
            continue
        by_year.setdefault(y, []).append(r)

    frames = []
    for y in sorted(by_year):
        yr = by_year[y]
        if len(yr) < 60:            # năm thiếu dữ liệu thì bỏ
            continue
        peak, peak_date = _year_peak(module_id, lat, lon, yr)
        rain = round(sum(d.get("precip") or 0.0 for d in yr), 1)
        risk = ("danger" if peak >= hazard.WARNING
                else "warning" if peak >= hazard.SAFE else "safe")
        frames.append({"year": y, "peak": peak, "peak_date": peak_date,
                       "rain_annual_mm": rain, "risk_level": risk,
                       "days_covered": len(yr)})

    if len(frames) < 3:
        return {"available": False, "module_id": module_id, "module_name": name,
                "message": "Không đủ năm có dữ liệu để dựng time-lapse."}

    peaks = [f["peak"] for f in frames]
    n = len(peaks)
    # Hồi quy tuyến tính đơn giản trên chỉ số đỉnh theo năm.
    xs = list(range(n))
    mx, my = sum(xs) / n, sum(peaks) / n
    denom = sum((x - mx) ** 2 for x in xs)
    slope = (sum((x - mx) * (p - my) for x, p in zip(xs, peaks)) / denom
             if denom else 0.0)
    total_change = round(slope * (n - 1), 1)

    half = n // 2
    early = sum(peaks[:half]) / half
    late = sum(peaks[n - half:]) / half

    if abs(total_change) < 3.0:
        trend, trend_txt = "stable", "gần như không đổi"
    elif total_change > 0:
        trend, trend_txt = "worsening", "đang xấu đi"
    else:
        trend, trend_txt = "improving", "đang tốt lên"

    n_danger = sum(1 for f in frames if f["risk_level"] == "danger")
    worst = max(frames, key=lambda f: f["peak"])

    return_val = {
        "available": True, "module_id": module_id, "module_name": name,
        "unit": unit, "location": {"lat": lat, "lon": lon},
        "from_year": frames[0]["year"], "to_year": frames[-1]["year"],
        "frames": frames,
        "trend": trend,
        "trend_change": total_change,
        "early_mean": round(early, 1), "late_mean": round(late, 1),
        "danger_years": n_danger,
        "worst_year": worst,
        "safe": hazard.SAFE, "warning": hazard.WARNING,
        "headline": (
            f"{len(frames)} năm qua: rủi ro {trend_txt} "
            f"({'+' if total_change > 0 else ''}{total_change} {unit}). "
            f"{n_danger}/{len(frames)} năm chạm mức nguy hiểm; nặng nhất là "
            f"{worst['year']} ({worst['peak']} {unit})."),
        "cached": False,
        "caveat": (
            "Đây là time-lapse của RỦI RO KHÍ HẬU, chạy đúng mô hình cảnh báo "
            "trên ERA5 từng năm. KHÔNG phải phát hiện thay đổi bề mặt (mất "
            "rừng, xây dựng mới) — cái đó cần ảnh Sentinel hai kỳ, chưa tích hợp. "
            "Xu thế tính bằng hồi quy tuyến tính trên chuỗi ngắn nên là chỉ dấu, "
            "không phải kết luận khí hậu học."),
        "method": ("Chạy mô hình cảnh báo trên cửa sổ trượt 7 ngày suốt từng năm, "
                   "lấy đỉnh mỗi năm, rồi hồi quy tuyến tính để đo xu thế."),
    }
    cache_store.put(key, return_val, _TTL)
    return return_val
