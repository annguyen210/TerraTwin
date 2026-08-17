"""Khuôn module dùng chung — trái tim của kiến trúc '1 lõi + 14 module'.

Mỗi mũi nhọn là một lớp con của TwinModule, chỉ cần viết assess().
PlannedModule = module đã đăng ký (có metadata) nhưng chưa bật logic.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas import Assessment, Location, ModuleInfo


class TwinModule(ABC):
    id: str = ""
    name: str = ""
    group: str = ""
    icon: str = ""
    data_sources: list[str] = []
    users: list[str] = []
    description: str = ""
    status: str = "planned"

    def info(self) -> ModuleInfo:
        return ModuleInfo(
            id=self.id, name=self.name, group=self.group, status=self.status,
            icon=self.icon, data_sources=self.data_sources, users=self.users,
            description=self.description,
        )

    @abstractmethod
    def assess(self, location: Location) -> Assessment:
        ...


class PlannedModule(TwinModule):
    """Một trong 13 mũi nhọn đã thiết kế, dùng chung lõi, sẽ bật sau Phase 0."""

    status = "planned"

    def __init__(self, id, name, group, icon, data_sources, users, description):
        self.id = id
        self.name = name
        self.group = group
        self.icon = icon
        self.data_sources = data_sources
        self.users = users
        self.description = description

    def assess(self, location: Location) -> Assessment:
        return Assessment(
            module_id=self.id, module_name=self.name, location=location,
            status="not_implemented", risk_level="unknown",
            headline="Mô-đun đang trong lộ trình",
            detail=(f"'{self.name}' đã được thiết kế và dùng chung lõi Twin — "
                    "sẽ bật sau khi hoàn thiện module Mặn (Phase 0)."),
            recommendation="Nhân khuôn từ module Mặn sang mô-đun này.",
            data_sources=self.data_sources,
        )
