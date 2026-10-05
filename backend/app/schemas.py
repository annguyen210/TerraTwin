"""Kiểu dữ liệu dùng chung cho toàn bộ lõi + module."""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field, field_validator

# Hộp toạ độ THÔ — chỉ là cửa chặn nhanh cho dữ liệu rác (lat=999), KHÔNG phải
# ranh giới Việt Nam. Hộp này bao cả Lào, Campuchia, nam Trung Quốc và Biển
# Đông; việc phân biệt đất liền Việt Nam / mặt biển / nước khác do
# services/region.py làm bằng cao độ DEM và tra cứu quốc gia.
#
# Kinh độ nới tới 115,0 có chủ đích: mốc cũ 112,5 khiến Trường Sa bị từ chối
# kèm câu "ngoài lãnh thổ Việt Nam" — phần mềm không nên tự phát ngôn về chủ
# quyền, và càng không nên phát ngôn sai. Nay điểm đó đi qua được cửa này rồi
# được region.py trả lời trung thực là "mặt nước, ngoài phạm vi phục vụ".
VN_LAT_MIN, VN_LAT_MAX = 7.5, 24.0
VN_LON_MIN, VN_LON_MAX = 101.5, 115.0


class Location(BaseModel):
    # Ràng buộc cứng theo toạ độ Trái Đất — chặn lat=999, lon=9999…
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)
    name: Optional[str] = None
    # Diện tích không âm và có trần hợp lý (10 triệu ha ~ lớn hơn mọi thửa/nông trường).
    area_ha: Optional[float] = Field(default=None, ge=0.0, le=1.0e7)

    @field_validator("lat")
    @classmethod
    def _lat_in_vn(cls, v: float) -> float:
        if not (VN_LAT_MIN <= v <= VN_LAT_MAX):
            from app.services.reqlang import tr
            # Nói rõ GIÁ TRỊ đã nhận: lỗi thật 4/10/2026 — trình duyệt máy tính đoán vị trí
            # theo mạng ra Singapore (vĩ độ ~1,3); câu cũ không cho người dùng biết vì sao.
            raise ValueError(tr(
                f"Vĩ độ nhận được là {v:g} — ngoài khung Việt Nam ({VN_LAT_MIN}–{VN_LAT_MAX}). "
                "Nếu bạn dùng nút định vị trên máy tính, trình duyệt có thể đoán sai vị trí theo "
                "mạng; hãy gõ tên xã hoặc dán toạ độ từ Google Maps.",
                f"Received latitude {v:g} — outside Vietnam's box ({VN_LAT_MIN}–{VN_LAT_MAX}). "
                "If you used the locate button on a computer, the browser may have guessed your "
                "location from the network; type a commune name or paste coordinates from Google Maps."
            ))
        return v

    @field_validator("lon")
    @classmethod
    def _lon_in_vn(cls, v: float) -> float:
        if not (VN_LON_MIN <= v <= VN_LON_MAX):
            from app.services.reqlang import tr
            raise ValueError(tr(
                f"Kinh độ nhận được là {v:g} — ngoài khung Việt Nam ({VN_LON_MIN}–{VN_LON_MAX}). "
                "Kiểm tra lại thứ tự: vĩ độ trước, kinh độ sau (vd 21.18, 106.07).",
                f"Received longitude {v:g} — outside Vietnam's box ({VN_LON_MIN}–{VN_LON_MAX}). "
                "Check the order: latitude first, then longitude (e.g. 21.18, 106.07)."
            ))
        return v


class ModuleInfo(BaseModel):
    id: str
    name: str
    group: str          # A (quang học) | B (radar/địa hình) | C (chỉ số)
    status: str         # active | planned
    icon: str
    data_sources: list[str]
    users: list[str]
    description: str
    heavy: bool = False
    threat: bool = True


class ForecastPoint(BaseModel):
    day: int
    date: str
    value: float
    unit: str
    risk: str           # safe | warning | danger


class Assessment(BaseModel):
    module_id: str
    module_name: str
    location: Location
    status: str
    risk_level: str
    headline: str
    detail: str
    recommendation: str
    confidence: Optional[float] = None
    confidence_low: Optional[float] = None   # cận dưới khoảng tin cậy
    confidence_high: Optional[float] = None  # cận trên khoảng tin cậy
    is_real: bool = False                    # True = dữ liệu vệ tinh/thời tiết thật
    score: Optional[float] = None
    metrics: dict[str, float] = {}
    forecast: list[ForecastPoint] = []
    data_sources: list[str] = []


class TerraScoreResult(BaseModel):
    location: Location
    score: int
    grade: str
    summary: str
    breakdown: dict[str, int] = {}
    real_data_ratio: float = 0.0   # tỉ lệ hiểm họa được đánh giá bằng dữ liệu thật
    region: dict = {}


class KnowledgeCitation(BaseModel):
    """Một ghi chép thực địa đã được dùng làm ngữ cảnh cho câu trả lời."""
    id: int
    title: str
    author_name: str
    similarity_pct: float
    distance_km: float


class CopilotAnswer(BaseModel):
    answer: str
    used_modules: list[str] = []
    llm: bool = False
    knowledge_used: list[KnowledgeCitation] = []


class ScanModule(BaseModel):
    id: str
    name: str
    icon: str
    group: str
    risk_level: str
    headline: str
    recommendation: str
    is_real: bool
    # BỐN TRẠNG THÁI, không phải hai. Gộp chúng lại là vừa thiệt cho sản phẩm
    # vừa sai với người dùng:
    #   status="ok"  + is_real=True   → ĐO ĐƯỢC
    #   status="ok"  + is_real=False  → ƯỚC LƯỢNG (có kết luận, có độ tin cậy)
    #   status="need_data"            → THIẾU DỮ LIỆU (thật sự chưa biết)
    #   status="out_of_scope"         → KHÔNG ÁP DỤNG ở đây (cũng là câu trả lời)
    # Trước đây "mặn Bến Tre 0,27 g/L" và "chưa có ảnh vệ tinh" đều hiện ra như
    # nhau, nên màn hình đầu báo "7/16 mục thiếu dữ liệu" trong khi thực tế chỉ
    # 5 mục là thiếu thật.
    status: str = "ok"
    confidence: Optional[float] = None
    score: Optional[float] = None
    threat: bool = True
    # Đủ để vẽ chi tiết NGAY trong lưới, không phải bấm vào mới thấy:
    spark: list[float] = []          # giá trị dự báo 7 ngày (vẽ sparkline)
    unit: Optional[str] = None       # đơn vị của spark
    peak: Optional[float] = None     # đỉnh 7 ngày (con số đập vào mắt)
    # Timing — để "Kế hoạch thửa" biết VIỆC CẦN LÀM rơi vào NGÀY nào, không chỉ
    # "có rủi ro". Một cảnh báo không kèm ngày thì người dùng vẫn phải tự đoán.
    peak_date: Optional[str] = None      # ngày đạt đỉnh trong 7 ngày tới
    risk_dates: list[str] = []           # các ngày có cảnh báo (warning/danger)


class ScanResult(BaseModel):
    location: Location
    terrascore: TerraScoreResult
    modules: list[ScanModule] = []
    alerts: list[ScanModule] = []      # chỉ module warning/danger, ưu tiên nguy hiểm trước
    real_data_ratio: float = 0.0
    generated_at: str
    skipped_heavy: list[str] = []
    region: dict = {}


class ScenarioPoint(BaseModel):
    day: int
    date: str
    value: float
    risk: str


class ScenarioResult(BaseModel):
    label: str
    rain_mult: float
    temp_delta: float
    peak: float
    first_danger_date: Optional[str] = None
    series: list[ScenarioPoint] = []


class WhatIfResult(BaseModel):
    module_id: str
    module_name: str
    location: Location
    unit: str
    safe: float
    warning: float
    is_real: bool = False
    note: str
    scenarios: list[ScenarioResult] = []
