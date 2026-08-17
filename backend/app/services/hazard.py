"""Lõi hiểm họa dùng chung — 4 module do thời tiết chi phối.

Gộp phần trước đây bị lặp ở whatif.py và backtest.py: cùng một bảng metadata,
cùng một cách chạy mô hình chỉ số trên chuỗi thời tiết. Mọi tính năng mới
(explain / goal-seek / Monte Carlo / anomaly) đều đi qua đây nên chắc chắn
dùng ĐÚNG mô hình đang chạy cho dự báo — không có model thứ hai lệch pha.
"""
from __future__ import annotations

from app.services import datasources as ds

# Ngưỡng dùng chung cho 4 chỉ số 0–100
SAFE, WARNING = 40.0, 70.0

# id -> (tên hiển thị, đơn vị)
META = {
    "drought": ("Cảnh báo hạn & thiếu nước", "%"),
    "flood": ("Cảnh báo lũ/ngập sớm", "điểm"),
    "wildfire": ("Cảnh báo nguy cơ cháy rừng", "điểm"),
    "landslide": ("Cảnh báo sạt lở", "điểm"),
}

IDS = tuple(META)


def supports(module_id: str) -> bool:
    return module_id in META


def name_unit(module_id: str) -> tuple[str, str]:
    return META[module_id]


def terrain(module_id: str, lat: float, lon: float) -> tuple[float | None, str]:
    """(giá trị địa hình, mô tả). Lũ dùng cao độ, sạt lở dùng độ dốc."""
    if module_id == "flood":
        elev = ds.elevation_proxy(lat, lon)
        return elev, f"cao độ ~{elev} m"
    if module_id == "landslide":
        slope, _ = ds.slope_context(lat, lon)
        return slope, f"độ dốc ~{slope}°"
    if module_id == "drought":
        return None, "chỉ số thiếu ẩm (ET₀ − mưa)"
    return None, "nhiệt & khô hạn"


def index_series_absolute(module_id: str, lat: float, lon: float, rows):
    """Thang TUYỆT ĐỐI (bản gốc). Bão hòa ở vùng mưa nhiều → chỉ dùng làm
    phương án lùi khi không lấy được khí hậu nền. Giữ lại để so sánh & test."""
    if module_id == "drought":
        return ds.drought_index(rows)
    if module_id == "flood":
        return ds.flood_index(rows, ds.elevation_proxy(lat, lon))
    if module_id == "wildfire":
        return ds.wildfire_index(rows)
    if module_id == "landslide":
        slope, _ = ds.slope_context(lat, lon)
        return ds.landslide_index(rows, slope)
    return []


def index_series_calibrated(module_id: str, lat: float, lon: float, rows):
    """(series, is_calibrated). Ưu tiên thang ĐÃ HIỆU CHUẨN theo khí hậu điểm đó;
    tự lùi về thang tuyệt đối khi offline."""
    from app.services import calibration     # tránh import vòng
    s, ok = calibration.calibrated_series(module_id, lat, lon, rows)
    if ok and s:
        return s, True
    return index_series_absolute(module_id, lat, lon, rows), False


def index_series(module_id: str, lat: float, lon: float, rows):
    """Chỉ số dùng chung cho mọi luồng — đã hiệu chuẩn nếu có thể."""
    return index_series_calibrated(module_id, lat, lon, rows)[0]


# Chuỗi MẪU khi offline — chỉ để app không chết, luôn kèm cờ is_real=False.
_FALLBACK = {
    "drought": lambda la, lo: ds.drought_series(la, lo),
    "flood": lambda la, lo: ds.flood_series(la, lo),
    "wildfire": lambda la, lo: ds.wildfire_series(la, lo),
    "landslide": lambda la, lo: ds.landslide_series(la, lo),
}


def module_series(module_id: str, lat: float, lon: float):
    """(series, is_real, is_calibrated) — điểm vào DUY NHẤT cho 4 module hiểm họa.

    Trước đây các module gọi thẳng ds.*_series() nên vẫn chạy thang TUYỆT ĐỐI,
    trong khi explain/goal-seek/heatmap/backtest đã dùng thang ĐÃ HIỆU CHUẨN.
    Hậu quả: cùng một toạ độ, thẻ module báo "nguy hiểm 74.5" còn bản đồ nhiệt
    báo an toàn. Hàm này buộc mọi nơi dùng chung một thang.
    """
    from app.services import realdata

    rows = realdata.weather_7d(lat, lon)
    if rows:
        series, calibrated = index_series_calibrated(module_id, lat, lon, rows)
        return series, True, calibrated
    fb = _FALLBACK.get(module_id)
    if fb is None:
        return [], False, False
    series, _ = fb(lat, lon)
    return series, False, False


def scale_note(is_real: bool, is_calibrated: bool) -> str:
    """Câu mô tả thang đo — người dùng phải biết con số này nghĩa là gì."""
    if not is_real:
        return ("Số liệu MẪU (không lấy được dữ liệu thật) — chỉ minh họa luồng, "
                "không dùng để ra quyết định.")
    if is_calibrated:
        return ("Thang ĐÃ HIỆU CHUẨN theo khí hậu 10 năm của chính điểm này: "
                "<40 an toàn (dưới phân vi 90) · 40–70 cảnh báo (P90–P97) · "
                "≥70 nguy hiểm (trên P97, chỉ ~3% số ngày trong năm).")
    return ("Thang tuyệt đối CHƯA hiệu chuẩn (không tải được khí hậu nền) — "
            "ở vùng mưa nhiều có thể báo động nhiều hơn thực tế. "
            "<40 thấp · 40–70 cảnh báo · ≥70 cao.")


def peak_of(series) -> float:
    return max((v for _, _, v in series), default=0.0)


def transform(rows, rain_mult: float = 1.0, temp_delta: float = 0.0):
    """Biến đổi chuỗi thời tiết theo kịch bản — minh bạch, không hộp đen."""
    return [
        {
            "day": r["day"], "date": r["date"],
            "precip": max(0.0, r["precip"] * rain_mult),
            "et0": r["et0"],
            "tmax": r["tmax"] + temp_delta,
        }
        for r in rows
    ]
