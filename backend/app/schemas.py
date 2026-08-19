"""Kiểu dữ liệu dùng chung cho toàn bộ lõi + module."""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field, field_validator

# Khung phục vụ: lãnh thổ Việt Nam (đệm nhẹ để không chặn oan click sát biên giới).
VN_LAT_MIN, VN_LAT_MAX = 7.5, 24.0
VN_LON_MIN, VN_LON_MAX = 101.5, 112.5


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
            raise ValueError(
                "TerraTwin hiện phục vụ lãnh thổ Việt Nam "
                f"(vĩ độ {VN_LAT_MIN}–{VN_LAT_MAX}). Toạ độ ngoài vùng."
            )
        return v

    @field_validator("lon")
    @classmethod
    def _lon_in_vn(cls, v: float) -> float:
        if not (VN_LON_MIN <= v <= VN_LON_MAX):
            raise ValueError(
                "TerraTwin hiện phục vụ lãnh thổ Việt Nam "
                f"(kinh độ {VN_LON_MIN}–{VN_LON_MAX}). Toạ độ ngoài vùng."
            )
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
    is_real: bool = False
    score: Optional[float] = None


class ScanResult(BaseModel):
    location: Location
    terrascore: TerraScoreResult
    modules: list[ScanModule] = []
    alerts: list[ScanModule] = []      # chỉ module warning/danger, ưu tiên nguy hiểm trước
    real_data_ratio: float = 0.0
    generated_at: str


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
