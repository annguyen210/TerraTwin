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


def index_series(module_id: str, lat: float, lon: float, rows):
    """Chạy đúng mô hình chỉ số của module trên chuỗi rows đã cho."""
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
