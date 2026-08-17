"""Nhóm A — quang học (Sentinel-2) + thời tiết. Hạn/cháy dùng dữ liệu THẬT."""
from __future__ import annotations

from app.modules.base import TwinModule
from app.modules.util import assessment_from_series, need_data_assessment
from app.schemas import Assessment, Location
from app.services import datasources as ds
from app.services import hazard


class DroughtModule(TwinModule):
    id = "drought"; name = "Cảnh báo hạn & thiếu nước"; group = "A"; icon = "🌾"; status = "active"
    data_sources = ["Open-Meteo: lượng mưa & ET₀"]
    users = ["Nông dân", "Đơn vị thủy lợi"]
    description = "Dự báo vùng ruộng sắp thiếu nước để chủ động điều tiết."

    def assess(self, loc: Location) -> Assessment:
        s, real, calibrated = hazard.module_series(self.id, loc.lat, loc.lon)

        def texts(lvl, pk, fd):
            if fd:
                return (f"Thiếu nước NGHIÊM TRỌNG từ ~{fd.date} ({fd.value}%)",
                        "Ưu tiên tưới sớm, trữ nước; cân nhắc cây chịu hạn nếu kéo dài.")
            if lvl == "warning":
                return (f"Nguy cơ thiếu nước — đỉnh {pk.value}%",
                        "Theo dõi độ ẩm, lên lịch tưới tiết kiệm.")
            return (f"Đủ ẩm trong 7 ngày — đỉnh {pk.value}%", "Chưa cần can thiệp.")

        detail = ("Chỉ số thiếu ẩm tính từ mưa & bốc thoát hơi ET₀ THẬT (Open-Meteo). "
                  if real else "Chỉ số thiếu ẩm (mẫu). ") + hazard.scale_note(real, calibrated)
        src = ["Open-Meteo: lượng mưa & ET₀ (dữ liệu thật)"] if real else self.data_sources
        return assessment_from_series(self, loc, s, "%", 40, 70, texts, detail,
                                      confidence=0.78 if real else 0.6, is_real=real, data_sources=src)


class WildfireModule(TwinModule):
    id = "wildfire"; name = "Cảnh báo nguy cơ cháy rừng"; group = "A"; icon = "🔥"; status = "active"
    data_sources = ["Open-Meteo: nhiệt độ & lượng mưa", "NASA FIRMS (khi mở rộng)"]
    users = ["Kiểm lâm", "Chính quyền"]
    description = "Vùng khô dễ cháy + phát hiện điểm nóng sớm."

    def assess(self, loc: Location) -> Assessment:
        s, real, calibrated = hazard.module_series(self.id, loc.lat, loc.lon)

        def texts(lvl, pk, fd):
            if fd:
                return (f"NGUY CƠ CHÁY CAO (chỉ số {pk.value})",
                        "Cấm đốt, tăng tuần tra, sẵn sàng lực lượng chữa cháy.")
            if lvl == "warning":
                return (f"Nguy cơ cháy trung bình (chỉ số {pk.value})",
                        "Cảnh báo người dân, hạn chế nguồn lửa.")
            return (f"Nguy cơ cháy thấp (chỉ số {pk.value})", "Duy trì theo dõi thường lệ.")

        detail = ("Chỉ số nguy cơ cháy từ nhiệt độ & khô hạn THẬT (Open-Meteo). "
                  if real else "Chỉ số nguy cơ cháy (mẫu). ") + hazard.scale_note(real, calibrated)
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
    """Ngưỡng nhiệt cho tôm sú/thẻ chân trắng ĐBSCL:
    tối ưu 28–32°C · >33°C stress nhiệt (giảm ăn, dễ bệnh) · <25°C chậm lớn.
    Sóng lớn đe dọa lồng bè và làm xáo trộn tầng nước ao ven biển.
    """
    id = "aquaculture"; name = "Cảnh báo môi trường ao nuôi"; group = "A"; icon = "🦐"; status = "active"
    data_sources = ["Open-Meteo Marine: nhiệt mặt nước & sóng",
                    "Open-Meteo: nhiệt không khí",
                    "Sentinel-2 độ đục/tảo (cần key — lộ trình)"]
    users = ["Hộ/DN nuôi thủy sản"]
    description = "Nhiệt nước/sóng ảnh hưởng tôm cá → cảnh báo sớm."

    HOT, VERY_HOT, COLD = 32.0, 33.5, 25.0

    def assess(self, loc: Location) -> Assessment:
        marine = ds.marine_context(loc.lat, loc.lon)
        if marine is None:
            return need_data_assessment(
                self, loc,
                needs="dữ liệu nhiệt mặt nước (chỉ có ở vùng biển/ven biển)",
                will_do="theo dõi nhiệt nước, sóng và độ đục để cảnh báo môi trường ao xấu",
                next_step=("Vị trí này nằm sâu trong đất liền nên không có dữ liệu "
                           "biển. Với ao nội đồng cần cảm biến tại ao (lộ trình)."))

        sst, wave = marine["sst_max"], marine["wave_max"]
        if sst >= self.VERY_HOT:
            lvl = "danger"
            head = f"Nước quá NÓNG — đỉnh {sst}°C (ngưỡng stress {self.VERY_HOT}°C)"
            rec = ("Giảm cho ăn, tăng sục khí, nâng mực nước ao; hoãn thả giống "
                   "tới khi nhiệt hạ.")
        elif sst >= self.HOT:
            lvl = "warning"
            head = f"Nước ấm cần chú ý — đỉnh {sst}°C"
            rec = "Theo dõi oxy hòa tan lúc rạng sáng, chuẩn bị quạt nước."
        elif sst <= self.COLD:
            lvl = "warning"
            head = f"Nước lạnh — chỉ {sst}°C, tôm chậm lớn"
            rec = "Giữ mực nước sâu, giảm thay nước, cân nhắc lùi lịch thả giống."
        else:
            lvl = "safe"
            head = f"Nhiệt nước thuận lợi — đỉnh {sst}°C (tối ưu 28–32°C)"
            rec = "Duy trì chăm sóc bình thường."

        if wave is not None and wave >= 2.0:
            head += f" · sóng cao {wave} m"
            rec += " Sóng lớn — gia cố lồng bè, kiểm tra bờ ao."
            if lvl == "safe":
                lvl = "warning"

        metrics = {"nhiet_mat_nuoc_max_c": sst}
        if wave is not None:
            metrics["song_cao_max_m"] = wave

        return Assessment(
            module_id=self.id, module_name=self.name, location=loc, status="ok",
            risk_level=lvl, headline=head,
            detail=(f"Nhiệt mặt nước & sóng THẬT 7 ngày (Open-Meteo Marine). "
                    f"Ngưỡng tôm: tối ưu 28–32°C, stress ≥{self.VERY_HOT}°C, "
                    f"chậm lớn ≤{self.COLD}°C. Độ đục/tảo cần ảnh Sentinel — "
                    "chưa tích hợp nên chưa đưa vào đánh giá."),
            recommendation=rec, confidence=0.72, confidence_low=0.64,
            confidence_high=0.8, is_real=True, metrics=metrics,
            forecast=marine["forecast"],
            data_sources=["Open-Meteo Marine: nhiệt mặt nước & sóng (thật)"])


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
