"""Đăng ký toàn bộ mũi nhọn — tất cả dùng chung lõi Twin.

14 mũi nhọn trong bản thiết kế gốc, cộng 3 mũi nhọn nhóm D phủ nốt ba ngành
còn trống của danh sách 12 ngành (Đô thị & Quy hoạch · Khai khoáng & Hạ tầng ·
Chuỗi cung ứng). Bản thiết kế liệt kê 14 mũi nhọn nhưng lại hứa 12 ngành — hai
con số đó không khớp nhau, và phủ đủ 12 ngành thì phải là 17.

Thêm module mới = tạo lớp con TwinModule + thêm vào danh sách _CLASSES.
"""
from __future__ import annotations

from app.modules.base import TwinModule
from app.modules.group_a import (
    AquacultureModule, CarbonModule, DroughtModule, PestModule,
    WildfireModule, YieldModule,
)
from app.modules.group_b import (
    FloodModule, IllegalBuildModule, LandRiskModule, LandslideModule,
    StormDamageModule,
)
from app.modules.group_c import ParametricInsuranceModule, SolarModule
from app.modules.group_d import (
    MiningModule, SupplyChainModule, UrbanModule,
)
from app.modules.salinity import SalinityModule

_CLASSES = [
    # Nhóm A — quang học
    SalinityModule, DroughtModule, PestModule, YieldModule,
    CarbonModule, WildfireModule, AquacultureModule,
    # Nhóm B — radar/địa hình
    FloodModule, LandslideModule, StormDamageModule,
    LandRiskModule, IllegalBuildModule,
    # Nhóm C — chỉ số
    ParametricInsuranceModule, SolarModule,
    # Nhóm D — hạ tầng & chuỗi (OpenStreetMap + khí tượng)
    UrbanModule, MiningModule, SupplyChainModule,
]

_MODULES: dict[str, TwinModule] = {cls().id: cls() for cls in _CLASSES}


def list_modules() -> list:
    return [m.info() for m in _MODULES.values()]


def get_module(module_id: str) -> TwinModule | None:
    return _MODULES.get(module_id)
