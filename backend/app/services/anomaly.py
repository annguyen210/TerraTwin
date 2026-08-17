"""C10 — Anomaly Detection: tuần này có BẤT THƯỜNG so với mọi năm không?

Một con số tuyệt đối ("180 mm") không nói lên điều gì cho nông dân. Điều đáng
báo là ĐỘ LỆCH so với bình thường của CHÍNH mảnh đất đó vào CHÍNH thời điểm
này trong năm.

Ta lấy khí hậu nền từ ERA5 (cùng ngày/tháng, N năm), tính trung bình & độ lệch
chuẩn, rồi so dự báo 7 ngày tới → z-score + thứ hạng phần trăm.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

from app.services import realdata

_WINDOW = 7
_LAG_DAYS = 10

# (khóa, nhãn, đơn vị, hàm gộp 7 ngày, ngưỡng z đáng báo, hướng "cao là bất lợi")
_METRICS = [
    ("precip", "Tổng lượng mưa 7 ngày", "mm", sum, 1.5, True),
    ("tmax", "Nhiệt độ tối đa trung bình", "°C",
     lambda xs: sum(xs) / len(xs) if xs else 0.0, 1.5, True),
    ("et0", "Tổng bốc thoát hơi ET₀", "mm", sum, 1.5, True),
]


def _mean_std(xs: list[float]) -> tuple[float, float]:
    if not xs:
        return 0.0, 0.0
    m = sum(xs) / len(xs)
    if len(xs) < 2:
        return m, 0.0
    var = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    return m, math.sqrt(var)


def _verdict(z: float, high_is_bad: bool) -> tuple[str, str]:
    a = abs(z)
    if a < 1.0:
        return "normal", "trong mức bình thường"
    if a < 1.5:
        return "notable", "hơi lệch so với bình thường"
    direction = "CAO" if z > 0 else "THẤP"
    if a < 2.5:
        return "anomaly", f"BẤT THƯỜNG — {direction} rõ rệt so với cùng kỳ mọi năm"
    return "extreme", f"CỰC ĐOAN — {direction} hiếm gặp trong lịch sử cùng kỳ"


def _verdict_flat(cur: float, mean: float) -> tuple[float | None, str, str]:
    """Khí hậu nền gần như không đổi (std≈0) → z-score không xác định.

    Không được im lặng trả 'bình thường': nếu hiện tại lệch hẳn khỏi nền phẳng
    thì đó chính là bất thường rõ nhất. Trả z=None và kết luận theo tỉ lệ.
    """
    delta = abs(cur - mean)
    scale = max(abs(mean), 1.0)
    if delta <= 0.1 * scale:
        return 0.0, "normal", "trong mức bình thường"
    direction = "CAO" if cur > mean else "THẤP"
    return None, "extreme", (f"CỰC ĐOAN — {direction} hẳn so với nền lịch sử gần như "
                             "không đổi ở cùng kỳ")


def run(lat: float, lon: float, years: int = 10,
        today: date | None = None) -> dict:
    today = today or date.today()
    last_year = (today - timedelta(days=_LAG_DAYS)).year - 1
    first_year = last_year - years + 1

    hist = realdata.historical_weather(
        lat, lon, date(first_year, 1, 1).isoformat(), date(last_year, 12, 31).isoformat())
    now = realdata.weather_7d(lat, lon)

    if not hist or not now:
        return {
            "available": False,
            "message": ("Cần cả dữ liệu lịch sử ERA5 và dự báo hiện tại để so sánh "
                        "(kiểm tra kết nối mạng)."),
            "metrics": [],
        }

    by_date = {r["date"]: r for r in hist}

    # Gom cửa sổ 7 ngày cùng ngày/tháng của từng năm quá khứ
    windows: list[list[dict]] = []
    for y in range(first_year, last_year + 1):
        try:
            anchor = date(y, today.month, today.day)
        except ValueError:
            anchor = date(y, today.month, 28)
        w = []
        for d in range(_WINDOW):
            r = by_date.get((anchor + timedelta(days=d)).isoformat())
            if r is None:
                break
            w.append(r)
        if len(w) == _WINDOW:
            windows.append(w)

    if not windows:
        return {"available": False,
                "message": "Không đủ dữ liệu lịch sử cho cửa sổ ngày này.",
                "metrics": []}

    metrics = []
    for key, label, unit, agg, z_alert, high_bad in _METRICS:
        hist_vals = sorted(agg([r[key] for r in w]) for w in windows)
        cur = agg([r[key] for r in now])
        mean, std = _mean_std(hist_vals)
        rank = round(100.0 * sum(1 for v in hist_vals if v < cur) / len(hist_vals))
        if std > 1e-9:
            z = (cur - mean) / std
            level, text = _verdict(z, high_bad)
            alert = abs(z) >= z_alert
        else:
            z, level, text = _verdict_flat(cur, mean)
            alert = level == "extreme"
        metrics.append({
            "key": key, "label": label, "unit": unit,
            "current": round(cur, 1),
            "normal_mean": round(mean, 1),
            "normal_std": round(std, 1),
            "z_score": round(z, 2) if z is not None else None,
            "percentile": rank,
            "level": level,
            "verdict": f"{round(cur,1)} {unit} — {text} (TB cùng kỳ {round(mean,1)} {unit}).",
            "alert": alert,
        })

    alerts = [m for m in metrics if m["alert"]]
    if alerts:
        top = max(alerts, key=lambda m: abs(m["z_score"]) if m["z_score"] is not None else 99.0)
        headline = (f"⚠️ {len(alerts)} chỉ số bất thường — nổi bật: "
                    f"{top['label'].lower()} {top['current']} {top['unit']}, "
                    f"cao hơn {top['percentile']}% số năm cùng kỳ.")
    else:
        headline = "✅ Tuần tới trong mức bình thường so với cùng kỳ nhiều năm."

    return {
        "available": True, "is_real": True,
        "years": len(windows), "from_year": first_year, "to_year": last_year,
        "window_days": _WINDOW,
        "headline": headline,
        "metrics": metrics,
        "method": ("So dự báo 7 ngày với khí hậu nền ERA5 cùng ngày/tháng tại chính "
                   "toạ độ này; z-score = (hiện tại − trung bình) / độ lệch chuẩn."),
        "data_source": "Open-Meteo Archive (ERA5) + dự báo Open-Meteo",
    }
