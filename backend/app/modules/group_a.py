"""Nhóm A — quang học (Sentinel-2) + thời tiết. Hạn/cháy dùng dữ liệu THẬT."""
from __future__ import annotations

from app.modules.base import TwinModule
from app.modules.util import assessment_from_series, need_data_assessment
from app.schemas import Assessment, Location
from app.services import datasources as ds


class DroughtModule(TwinModule):
    id = "drought"; name = "Cảnh báo hạn & thiếu nước"; group = "A"; icon = "🌾"; status = "active"
    data_sources = ["Open-Meteo: lượng mưa & ET₀"]
    users = ["Nông dân", "Đơn vị thủy lợi"]
    description = "Dự báo vùng ruộng sắp thiếu nước để chủ động điều tiết."

    def assess(self, loc: Location) -> Assessment:
        s, real = ds.drought_series(loc.lat, loc.lon)

        def texts(lvl, pk, fd):
            if fd:
                return (f"Thiếu nước NGHIÊM TRỌNG từ ~{fd.date} ({fd.value}%)",
                        "Ưu tiên tưới sớm, trữ nước; cân nhắc cây chịu hạn nếu kéo dài.")
            if lvl == "warning":
                return (f"Nguy cơ thiếu nước — đỉnh {pk.value}%",
                        "Theo dõi độ ẩm, lên lịch tưới tiết kiệm.")
            return (f"Đủ ẩm trong 7 ngày — đỉnh {pk.value}%", "Chưa cần can thiệp.")

        detail = ("Chỉ số thiếu ẩm tính từ mưa & bốc thoát hơi ET₀ THẬT (Open-Meteo)."
                  if real else "Chỉ số thiếu ẩm (mẫu).") + " <40 an toàn · 40–70 cảnh báo · ≥70 nghiêm trọng."
        src = ["Open-Meteo: lượng mưa & ET₀ (dữ liệu thật)"] if real else self.data_sources
        return assessment_from_series(self, loc, s, "%", 40, 70, texts, detail,
                                      confidence=0.78 if real else 0.6, is_real=real, data_sources=src)


class WildfireModule(TwinModule):
    id = "wildfire"; name = "Cảnh báo nguy cơ cháy rừng"; group = "A"; icon = "🔥"; status = "active"
    data_sources = ["Open-Meteo: nhiệt độ & lượng mưa", "NASA FIRMS (khi mở rộng)"]
    users = ["Kiểm lâm", "Chính quyền"]
    description = "Vùng khô dễ cháy + phát hiện điểm nóng sớm."

    def assess(self, loc: Location) -> Assessment:
        s, real = ds.wildfire_series(loc.lat, loc.lon)

        def texts(lvl, pk, fd):
            if fd:
                return (f"NGUY CƠ CHÁY CAO (chỉ số {pk.value})",
                        "Cấm đốt, tăng tuần tra, sẵn sàng lực lượng chữa cháy.")
            if lvl == "warning":
                return (f"Nguy cơ cháy trung bình (chỉ số {pk.value})",
                        "Cảnh báo người dân, hạn chế nguồn lửa.")
            return (f"Nguy cơ cháy thấp (chỉ số {pk.value})", "Duy trì theo dõi thường lệ.")

        detail = ("Chỉ số nguy cơ cháy từ nhiệt độ & khô hạn THẬT (Open-Meteo)."
                  if real else "Chỉ số nguy cơ cháy (mẫu).") + " <40 thấp · 40–70 trung bình · ≥70 cao."
        src = ["Open-Meteo: nhiệt độ & lượng mưa (dữ liệu thật)"] if real else self.data_sources
        return assessment_from_series(self, loc, s, "điểm", 40, 70, texts, detail,
                                      confidence=0.75 if real else 0.6, is_real=real, data_sources=src)


class PestModule(TwinModule):
    id = "pest"; name = "Phát hiện sâu bệnh sớm"; group = "A"; icon = "🌾"; status = "preview"
    data_sources = ["Sentinel-2 NDVI (cần key)", "Ảnh người dùng (CV)"]
    users = ["Nông dân", "DN nông nghiệp"]
    description = "Khoanh vùng cây stress bất thường + xác nhận qua ảnh lá."

    def assess(self, loc: Location) -> Assessment:
        return need_data_assessment(
            self, loc,
            needs="ảnh vệ tinh Sentinel-2 (NDVI)",
            will_do="khoanh vùng cây bị stress bất thường theo chỉ số thực vật NDVI "
                    "và so sánh với nền khỏe mạnh của cùng loại cây",
            next_step="Có thể chụp ảnh lá qua Field Mode để AI kiểm tra cục bộ (lộ trình).")


class AquacultureModule(TwinModule):
    id = "aquaculture"; name = "Cảnh báo môi trường ao nuôi"; group = "A"; icon = "🦐"; status = "preview"
    data_sources = ["Sentinel-2 (chỉ số nước, cần key)", "Thời tiết"]
    users = ["Hộ/DN nuôi thủy sản"]
    description = "Chất lượng nước/thời tiết ảnh hưởng tôm cá → cảnh báo sớm."

    def assess(self, loc: Location) -> Assessment:
        return need_data_assessment(
            self, loc,
            needs="chỉ số chất lượng nước từ Sentinel-2",
            will_do="theo dõi độ đục/tảo/nhiệt mặt nước ao nuôi để cảnh báo môi trường xấu",
            next_step="Đang trong lộ trình tích hợp ảnh Sentinel-2.")


class YieldModule(TwinModule):
    id = "yield"; name = "Dự báo năng suất & thu hoạch"; group = "A"; icon = "🌾"; status = "preview"
    data_sources = ["Chuỗi ảnh vệ tinh (cần key)", "Thời tiết"]
    users = ["Nông dân", "Thương lái", "DN xuất khẩu"]
    description = "Ước lượng sản lượng theo vùng & thời điểm thu tối ưu."

    def assess(self, loc: Location) -> Assessment:
        return need_data_assessment(
            self, loc,
            needs="chuỗi ảnh vệ tinh NDVI theo mùa vụ",
            will_do="ước lượng năng suất (tấn/ha) và thời điểm thu hoạch tối ưu từ đường "
                    "cong sinh trưởng NDVI + thời tiết",
            next_step="Đang trong lộ trình tích hợp chuỗi ảnh Sentinel.")


class CarbonModule(TwinModule):
    id = "carbon"; name = "Đo & bán tín chỉ carbon rừng"; group = "A"; icon = "🌲"; status = "preview"
    data_sources = ["Sentinel-2 (cần key)", "Mô hình sinh khối", "Đối chiếu thực địa"]
    users = ["Chủ rừng", "DN", "Quỹ carbon"]
    description = "Đo trữ lượng carbon xác thực được để bán tín chỉ."

    def assess(self, loc: Location) -> Assessment:
        return need_data_assessment(
            self, loc,
            needs="ảnh Sentinel-2 + khảo sát thực địa",
            will_do="ước lượng sinh khối & trữ lượng carbon (tCO₂/ha) để lập hồ sơ MRV "
                    "bán tín chỉ — con số này cần xác thực nên KHÔNG mô phỏng",
            next_step="Đang trong lộ trình tích hợp ảnh vệ tinh + quy trình đo thực địa.")
