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
    name_en: str = ""      # song ngữ: tên tiếng Anh (reqlang chọn theo request)
    group: str = ""
    icon: str = ""
    data_sources: list[str] = []
    data_sources_en: list[str] = []  # song ngữ tuỳ chọn cho data_sources (xem disp_data_sources)
    users: list[str] = []
    description: str = ""
    status: str = "planned"

    # Mô-đun "nặng": tốn nhiều lượt gọi ra ngoài (vd. quét cả một lưới điểm,
    # mỗi điểm cần khí hậu nền riêng). Lượt QUÉT TOÀN CẢNH bỏ qua những mô-đun
    # này — người dùng bấm một điểm trên bản đồ thì chờ vài giây là hợp lý,
    # chờ mười lăm giây thì không, và một mô-đun vùng không nên bắt cả mười
    # sáu mô-đun kia đợi nó.
    heavy: bool = False

    # Mô-đun này có mô tả một MỐI ĐE DOẠ không?
    #
    # `risk_level` chỉ là "mức trên thang của chính mô-đun đó". Với hiểm họa,
    # danger nghĩa là sắp có chuyện xấu. Với mô-đun cơ hội hay đánh giá, danger
    # nghĩa hoàn toàn khác: điện mặt trời "danger" = bức xạ trung bình, hoàn
    # toàn không phải nguy hiểm.
    #
    # Trộn hai loại đó vào cùng một danh sách cảnh báo là lý do rà soát nền có
    # thể gửi email lúc ba giờ sáng báo "điện mặt trời: nguy hiểm". Người nhận
    # cái đó vài lần sẽ tắt thông báo, và lần thứ mười hai — lần lũ thật — họ
    # không còn nhận được nữa. Đây chính là thứ phá tỉ lệ báo động giả 3%.
    threat: bool = True

    def disp_name(self) -> str:
        """Tên hiển thị theo ngôn ngữ request (mặc định VI). Dùng cho info() và
        module_name trong Assessment để lưới 18 mũi nhọn hiện đúng ngữ."""
        from app.services.reqlang import tr
        return tr(self.name, self.name_en or self.name)

    def disp_data_sources(self) -> list[str]:
        """data_sources theo ngôn ngữ request nếu module khai báo data_sources_en."""
        from app.services.reqlang import tr
        return tr(self.data_sources, self.data_sources_en or self.data_sources)

    def info(self) -> ModuleInfo:
        return ModuleInfo(
            id=self.id, name=self.disp_name(), group=self.group, status=self.status,
            icon=self.icon, data_sources=self.disp_data_sources(), users=self.users,
            description=self.description, heavy=self.heavy, threat=self.threat,
        )

    @abstractmethod
    def assess(self, location: Location) -> Assessment:
        ...
