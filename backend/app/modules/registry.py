"""Đăng ký toàn bộ 14 mũi nhọn — tất cả đã bật (active), dùng chung lõi Twin.

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
]

_MODULES: dict[str, TwinModule] = {cls().id: cls() for cls in _CLASSES}


def list_modules() -> list:
    return [m.info() for m in _MODULES.values()]


def get_module(module_id: str) -> TwinModule | None:
    return _MODULES.get(module_id)
