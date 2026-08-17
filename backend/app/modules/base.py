"""Khuôn module dùng chung — trái tim của kiến trúc '1 lõi + 14 module'.

Mỗi mũi nhọn là một lớp con của TwinModule, chỉ cần viết assess().
Module chưa có nguồn dữ liệu thật thì trả `util.need_data_assessment()` —
nói rõ cần nguồn gì, KHÔNG bịa số.
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
