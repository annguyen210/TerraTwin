"""Module MẶN — mũi nhọn khởi đầu, hoạt động đầy đủ end-to-end.

Đây là 'khuôn mẫu' để nhân bản cho 13 module còn lại.

PHẠM VI: xâm nhập mặn NÔNG NGHIỆP ở vùng đồng bằng (ĐBSCL, ĐB sông Hồng).
Ngoài vùng này, ở gần biển là nước mặn tự nhiên — KHÔNG áp ngưỡng lúa
(nếu không thì trung tâm Đà Nẵng cũng bị khuyên "đóng cống").

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


def _season_label(factor: float) -> str:
    """Diễn giải hệ số mùa vụ cho người dùng."""
    if factor >= 0.75:
        return "ĐỈNH mùa mặn (mùa khô, sông cạn)"
    if factor >= 0.40:
        return "chuyển mùa — mặn đang lên/xuống"
    return "mùa mưa lũ — nước ngọt đẩy mặn ra biển"


class SalinityModule(TwinModule):
    id = "salinity"
    name = "Cảnh báo xâm nhập mặn"
    group = "A"
    icon = "🌾"
    status = "active"
    data_sources = ["Đường bờ biển VN", "Cao độ DEM (Open-Meteo)",
                    "Chu kỳ mùa khô/mùa lũ", "Bảng thủy triều",
                    "Dữ liệu mặn Ủy hội Mekong (chờ tích hợp)"]
    users = ["Nông dân lúa ĐBSCL", "Hợp tác xã", "Sở NN&PTNT"]
    description = "Báo trước 5–7 ngày khi nước mặn sắp tới ruộng, kèm việc nên làm."

    def assess(self, location: Location) -> Assessment:
        ctx = get_salinity_context(location.lat, location.lon)
        zone = ctx["zone"]

        # --- Ngoài vùng đồng bằng nhiễm mặn: nói thật, không áp ngưỡng lúa ---
        if zone is None:
            dist = ctx["distance_to_coast_km"]
            near_sea = dist < 10.0
            detail = (
                f"Vị trí cách bờ biển ~{dist} km, cao độ ~{ctx['elevation_m']} m. "
                "Module này phục vụ xâm nhập mặn NÔNG NGHIỆP ở vùng đồng bằng "
                "(ĐBSCL, ĐB sông Hồng) — nơi nước mặn theo sông vào ruộng lúa "
                "trong mùa khô. Vị trí này nằm ngoài hai vùng đó nên KHÔNG áp "
                "ngưỡng mặn của cây lúa để tránh kết luận sai."
            )
            headline = (
                "Ngoài vùng xâm nhập mặn nông nghiệp — sát biển nên nước lợ/mặn tự nhiên"
                if near_sea else
                "Ngoài vùng xâm nhập mặn nông nghiệp"
            )
            return Assessment(
                module_id=self.id, module_name=self.name, location=location,
                status="out_of_scope", risk_level="unknown", is_real=False,
                headline=headline, detail=detail,
                recommendation=("Dùng các mô-đun Lũ/Ngập, Hạn hoặc Rủi ro mua đất "
                                "cho vị trí này."),
                confidence=None, data_sources=self.data_sources,
            )

        # --- Trong vùng đồng bằng: đánh giá đầy đủ ---
        forecast = [
            ForecastPoint(day=d, date=dt, value=v, unit="g/L", risk=_risk(v))
            for (d, dt, v) in ctx["series"]
        ]
        peak = max(forecast, key=lambda f: f.value)
        first_danger = next((f for f in forecast if f.risk == "danger"), None)
        level = _risk(peak.value)
        season = ctx["season_factor"]
        season_txt = _season_label(season)

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
            rec = ("Chưa cần hành động. Hệ thống sẽ tự cảnh báo khi vào mùa khô."
                   if season < 0.4 else
                   "Chưa cần hành động. Hệ thống sẽ tự cảnh báo nếu tình hình đổi.")

        detail = (
            f"{zone} · cách bờ biển gần nhất ~{ctx['distance_to_coast_km']} km · "
            f"cao độ ~{ctx['elevation_m']} m · hệ số mùa {season} ({season_txt}). "
            f"Ngưỡng lúa: an toàn <{SAFE}, cảnh báo {SAFE}–{WARNING}, "
            f"nguy hiểm ≥{WARNING} g/L. ƯỚC LƯỢNG VẬT LÝ (bờ biển + cao độ + "
            "mùa vụ + triều) — CHỜ hiệu chỉnh bằng số đo mặn MRC/trạm tỉnh."
        )

        return Assessment(
            module_id=self.id, module_name=self.name, location=location,
            status="ok", risk_level=level, headline=headline, detail=detail,
            recommendation=rec, confidence=0.55, confidence_low=0.4, confidence_high=0.7,
            is_real=False, forecast=forecast, data_sources=self.data_sources,
        )
