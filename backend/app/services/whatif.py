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
from app.services import hazard
from app.services import realdata

# Ngưỡng & metadata lấy từ lõi hiểm họa dùng chung (hazard.py)
SAFE, WARNING = hazard.SAFE, hazard.WARNING
_META = hazard.META

# Bốn tương lai song song. rain = nhân lượng mưa, temp = cộng vào nhiệt độ tối đa.
SCENARIOS = [
    ("Hiện tại (dữ liệu thật)", 1.0, 0.0),
    ("Mưa +50%", 1.5, 0.0),
    ("Mưa gấp đôi (cực đoan)", 2.0, 0.0),
    ("Khô hạn kéo dài (mưa −60%, +2°C)", 0.4, 2.0),
]


def available(module_id: str) -> bool:
    return hazard.supports(module_id)


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
        series = hazard.index_series(
            module_id, loc.lat, loc.lon, hazard.transform(rows, rain, temp))
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
