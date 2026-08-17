"""What-If / Parallel Futures — mô phỏng nhiều 'tương lai song song' cho 1 thửa đất.

Cách làm TRUNG THỰC: lấy nền dữ liệu thời tiết THẬT 7 ngày (Open-Meteo), rồi biến
đổi minh bạch theo kịch bản (nhân lượng mưa, cộng nhiệt độ) và chạy ĐÚNG mô hình
chỉ số đang dùng cho dự báo. Đây là mô phỏng tham số công khai — KHÔNG phải AI hộp đen.

Chỉ áp dụng cho 4 module hiểm họa do thời tiết chi phối:
  drought · flood · wildfire · landslide
"""
from __future__ import annotations

from app.modules.util import risk_of
from app.schemas import (
    Location, ScenarioPoint, ScenarioResult, WhatIfResult,
)
from app.services import datasources as ds
from app.services import realdata

# safe/warning dùng chung cho 4 module chỉ số (0–100)
SAFE, WARNING = 40.0, 70.0

_META = {
    "drought": ("Cảnh báo hạn & thiếu nước", "%"),
    "flood": ("Cảnh báo lũ/ngập sớm", "điểm"),
    "wildfire": ("Cảnh báo nguy cơ cháy rừng", "điểm"),
    "landslide": ("Cảnh báo sạt lở", "điểm"),
}

# Bốn tương lai song song. rain = nhân lượng mưa, temp = cộng vào nhiệt độ tối đa.
SCENARIOS = [
    ("Hiện tại (dữ liệu thật)", 1.0, 0.0),
    ("Mưa +50%", 1.5, 0.0),
    ("Mưa gấp đôi (cực đoan)", 2.0, 0.0),
    ("Khô hạn kéo dài (mưa −60%, +2°C)", 0.4, 2.0),
]


def _transform(rows, rain_mult: float, temp_delta: float):
    out = []
    for r in rows:
        out.append({
            "day": r["day"], "date": r["date"],
            "precip": max(0.0, r["precip"] * rain_mult),
            "et0": r["et0"],
            "tmax": r["tmax"] + temp_delta,
        })
    return out


def _index(module_id: str, lat: float, lon: float, rows):
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


def available(module_id: str) -> bool:
    return module_id in _META


def run(module_id: str, loc: Location) -> WhatIfResult | None:
    if module_id not in _META:
        return None
    name, unit = _META[module_id]

    rows = realdata.weather_7d(loc.lat, loc.lon)
    is_real = rows is not None
    if not rows:
        # fallback: dựng nền mẫu từ chuỗi hiện có để app vẫn chạy offline
        base_series, _ = {
            "drought": ds.drought_series, "flood": ds.flood_series,
            "wildfire": ds.wildfire_series, "landslide": ds.landslide_series,
        }[module_id](loc.lat, loc.lon)
        rows = [{"day": d, "date": dt, "precip": max(0.0, v * 0.2),
                 "et0": 3.0, "tmax": 32.0} for (d, dt, v) in base_series]

    scenarios: list[ScenarioResult] = []
    for label, rain, temp in SCENARIOS:
        series = _index(module_id, loc.lat, loc.lon, _transform(rows, rain, temp))
        pts = [ScenarioPoint(day=d, date=dt, value=v, risk=risk_of(v, SAFE, WARNING))
               for (d, dt, v) in series]
        peak = max((p.value for p in pts), default=0.0)
        first_danger = next((p.date for p in pts if p.risk == "danger"), None)
        scenarios.append(ScenarioResult(
            label=label, rain_mult=rain, temp_delta=temp, peak=round(peak, 1),
            first_danger_date=first_danger, series=pts,
        ))

    note = ("Mô phỏng tham số minh bạch trên nền thời tiết THẬT 7 ngày (Open-Meteo): "
            "điều chỉnh lượng mưa/nhiệt rồi chạy đúng mô hình cảnh báo."
            if is_real else
            "Nền dữ liệu thật không sẵn (offline) — đang mô phỏng trên chuỗi mẫu.")
    return WhatIfResult(
        module_id=module_id, module_name=name, location=loc, unit=unit,
        safe=SAFE, warning=WARNING, is_real=is_real, note=note, scenarios=scenarios,
    )
