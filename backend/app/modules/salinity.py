"""Module MẶN — mũi nhọn khởi đầu, hoạt động đầy đủ end-to-end.

Đây là 'khuôn mẫu' để nhân bản cho 13 module còn lại.
Ngưỡng mặn cho lúa mang tính minh họa; hiệu chỉnh theo giống & giai đoạn thật.
"""
from __future__ import annotations

from app.modules.base import TwinModule
from app.schemas import Assessment, ForecastPoint, Location
from app.services.datasources import get_salinity_context

SAFE = 1.0     # g/L
WARNING = 4.0  # g/L


def _risk(v: float) -> str:
    if v >= WARNING:
        return "danger"
    if v >= SAFE:
        return "warning"
    return "safe"


class SalinityModule(TwinModule):
    id = "salinity"
    name = "Cảnh báo xâm nhập mặn"
    group = "A"
    icon = "🌾"
    status = "active"
    data_sources = ["Sentinel-1/2", "Dữ liệu mặn Ủy hội Mekong",
                    "Thủy văn tỉnh", "Bảng thủy triều"]
    users = ["Nông dân lúa ĐBSCL", "Hợp tác xã", "Sở NN&PTNT"]
    description = "Báo trước 5–7 ngày khi nước mặn sắp tới ruộng, kèm việc nên làm."

    def assess(self, location: Location) -> Assessment:
        ctx = get_salinity_context(location.lat, location.lon)
        forecast = [
            ForecastPoint(day=d, date=dt, value=v, unit="g/L", risk=_risk(v))
            for (d, dt, v) in ctx["series"]
        ]
        peak = max(forecast, key=lambda f: f.value)
        first_danger = next((f for f in forecast if f.risk == "danger"), None)
        level = _risk(peak.value)

        if first_danger:
            headline = (f"Nguy cơ mặn CAO — vượt ngưỡng ngày {first_danger.date} "
                        f"(~{first_danger.value} g/L)")
            rec = (f"Trữ nước ngọt và ĐÓNG CỐNG trước ngày {first_danger.date}. "
                   "Không lấy nước sông 3–4 ngày tới. Báo hợp tác xã.")
        elif level == "warning":
            headline = f"Mặn mức CẢNH BÁO — đỉnh ~{peak.value} g/L ngày {peak.date}"
            rec = ("Theo dõi sát, chuẩn bị trữ nước ngọt; "
                   "hạn chế lấy nước lúc triều cường.")
        else:
            headline = f"An toàn trong 7 ngày tới — đỉnh chỉ ~{peak.value} g/L"
            rec = "Chưa cần hành động. Hệ thống sẽ tự cảnh báo nếu tình hình đổi."

        detail = (f"Cách bờ biển gần nhất ~{ctx['distance_to_coast_km']} km. "
                  f"Ngưỡng lúa: an toàn <{SAFE}, cảnh báo {SAFE}–{WARNING}, "
                  f"nguy hiểm ≥{WARNING} g/L. ƯỚC LƯỢNG VẬT LÝ theo khoảng cách bờ "
                  "biển & triều — CHỜ hiệu chỉnh bằng dữ liệu đo mặn MRC/trạm tỉnh.")

        return Assessment(
            module_id=self.id, module_name=self.name, location=location,
            status="ok", risk_level=level, headline=headline, detail=detail,
            recommendation=rec, confidence=0.55, confidence_low=0.4, confidence_high=0.7,
            is_real=False, forecast=forecast, data_sources=self.data_sources,
        )
