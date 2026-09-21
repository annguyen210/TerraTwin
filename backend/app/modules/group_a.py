"""Nhóm A — quang học (Sentinel-2) + thời tiết. Hạn/cháy dùng dữ liệu THẬT."""
from __future__ import annotations

from app.modules.base import TwinModule
from app.modules.util import (
    _needs_sentinel, _next_sentinel, assessment_from_series, need_data_assessment,
)
from app.schemas import Assessment, Location
from app.services import datasources as ds
from app.services import hazard, optical, sentinel
from app.services.reqlang import tr


class DroughtModule(TwinModule):
    id = "drought"; name = "Cảnh báo hạn & thiếu nước"; name_en = "Drought & water-shortage alert"; group = "A"; icon = "🌾"; status = "active"
    data_sources = ["Open-Meteo: lượng mưa & ET₀"]
    data_sources_en = ["Open-Meteo: rainfall & ET₀"]
    users = ["Nông dân", "Đơn vị thủy lợi"]
    description = "Dự báo vùng ruộng sắp thiếu nước để chủ động điều tiết."

    def assess(self, loc: Location) -> Assessment:
        s, real, calibrated, source = hazard.module_series(self.id, loc.lat, loc.lon)

        def texts(lvl, pk, fd):
            if fd:
                return (tr(f"Thiếu nước NGHIÊM TRỌNG từ ~{fd.date} ({fd.value}%)",
                           f"SEVERE water shortage from ~{fd.date} ({fd.value}%)"),
                        tr("Ưu tiên tưới sớm, trữ nước; cân nhắc cây chịu hạn nếu kéo dài.",
                           "Irrigate early, store water; consider drought-tolerant crops if prolonged."))
            if lvl == "warning":
                return (tr(f"Nguy cơ thiếu nước — đỉnh {pk.value}%", f"Water-shortage risk — peak {pk.value}%"),
                        tr("Theo dõi độ ẩm, lên lịch tưới tiết kiệm.",
                           "Monitor moisture, schedule water-saving irrigation."))
            return (tr(f"Đủ ẩm trong 7 ngày — đỉnh {pk.value}%", f"Adequate moisture for 7 days — peak {pk.value}%"),
                    tr("Chưa cần can thiệp.", "No intervention needed."))

        detail = (tr("Chỉ số thiếu ẩm tính từ mưa & bốc thoát hơi ET₀ THẬT (Open-Meteo). ",
                     "Moisture-deficit index from REAL rainfall & ET₀ evapotranspiration (Open-Meteo). ")
                  if real else tr("Chỉ số thiếu ẩm (mẫu). ", "Moisture-deficit index (sample). ")) + hazard.scale_note(real, calibrated)
        src = [hazard.source_label(source, "lượng mưa & ET₀", "rainfall & ET₀")] if real else self.disp_data_sources()
        return assessment_from_series(self, loc, s, "%", 40, 70, texts, detail,
                                      confidence=0.78 if real else 0.6, is_real=real, data_sources=src)


class WildfireModule(TwinModule):
    id = "wildfire"; name = "Cảnh báo nguy cơ cháy rừng"; name_en = "Wildfire risk alert"; group = "A"; icon = "🔥"; status = "active"
    data_sources = ["Open-Meteo: nhiệt độ & lượng mưa", "NASA FIRMS (khi mở rộng)"]
    data_sources_en = ["Open-Meteo: temperature & rainfall", "NASA FIRMS (planned expansion)"]
    users = ["Kiểm lâm", "Chính quyền"]
    description = "Vùng khô dễ cháy + phát hiện điểm nóng sớm."

    def assess(self, loc: Location) -> Assessment:
        s, real, calibrated, source = hazard.module_series(self.id, loc.lat, loc.lon)

        def texts(lvl, pk, fd):
            if fd:
                return (tr(f"NGUY CƠ CHÁY CAO (chỉ số {pk.value})", f"HIGH FIRE RISK (index {pk.value})"),
                        tr("Cấm đốt, tăng tuần tra, sẵn sàng lực lượng chữa cháy.",
                           "Ban burning, increase patrols, ready firefighting crews."))
            if lvl == "warning":
                return (tr(f"Nguy cơ cháy trung bình (chỉ số {pk.value})", f"Moderate fire risk (index {pk.value})"),
                        tr("Cảnh báo người dân, hạn chế nguồn lửa.",
                           "Warn residents, limit fire sources."))
            return (tr(f"Nguy cơ cháy thấp (chỉ số {pk.value})", f"Low fire risk (index {pk.value})"),
                    tr("Duy trì theo dõi thường lệ.", "Keep routine monitoring."))

        detail = (tr("Chỉ số nguy cơ cháy từ nhiệt độ & khô hạn THẬT (Open-Meteo). ",
                     "Fire-risk index from REAL temperature & dryness (Open-Meteo). ")
                  if real else tr("Chỉ số nguy cơ cháy (mẫu). ", "Fire-risk index (sample). ")) + hazard.scale_note(real, calibrated)
        src = [hazard.source_label(source, "nhiệt độ & lượng mưa", "temperature & rainfall")] if real else self.disp_data_sources()
        return assessment_from_series(self, loc, s, tr("điểm", "pts"), 40, 70, texts, detail,
                                      confidence=0.75 if real else 0.6, is_real=real, data_sources=src)


class PestModule(TwinModule):
    """Stress cây nhìn từ vệ tinh, có phân biệt ĐỀU hay LOANG LỔ.

    Hạn làm cây yếu đều cả thửa; sâu bệnh làm yếu theo ổ. Module đo cả hai nên
    nói được 'bất thường này giống ổ bệnh' hay 'giống hạn toàn vùng' — thứ mà
    một bản tin cấp tỉnh không nói được cho riêng thửa của bạn.
    """
    id = "pest"; name = "Phát hiện sâu bệnh sớm"; name_en = "Early pest & disease detection"; group = "A"; icon = "🌾"
    # CHẠY NGAY, không cần khoá. Điều kiện cũ gắn trạng thái vào
    # sentinel.configured(), nên khi chưa có khoá Copernicus thì mũi nhọn này
    # tự khai là "preview" — trong khi nó đã chạy thật qua Planetary Computer,
    # cùng bộ ảnh Sentinel-2 L2A, không cần đăng ký. Phần mềm khai báo SAI về
    # chính năng lực của mình: /api/roadmap báo "chạy ngay 13/18" trong khi
    # thực tế là 18/18.
    status = "active"
    # NẶNG: cần ảnh vệ tinh, mà nguồn không khoá phải gọi riêng từng ảnh và dò
    # lớp SCL cho từng cảnh — đo được 60–370 giây. Để trong lượt quét nhanh thì
    # màn hình đầu từ 2,5 giây thành hơn một phút, và người dùng đóng app trước
    # khi thấy bất cứ thứ gì. Chạy riêng khi được yêu cầu, kết quả có cache.
    heavy = True
    data_sources = ["Sentinel-2 NDVI (Copernicus)", "Ảnh lá người dùng (lộ trình)"]
    data_sources_en = ["Sentinel-2 NDVI (Copernicus)", "User leaf photos (roadmap)"]
    users = ["Nông dân", "DN nông nghiệp"]
    description = "Khoanh vùng cây stress bất thường + phân biệt đều hay loang lổ."

    def assess(self, loc: Location) -> Assessment:
        r = optical.stress(loc.lat, loc.lon)
        if r is None:
            return need_data_assessment(
                self, loc,
                needs=_needs_sentinel(tr("ảnh Sentinel-2 (NDVI) cho thửa này",
                                         "Sentinel-2 (NDVI) imagery for this plot")),
                will_do=tr("so sức sống cây hiện tại với chính thửa này 4 tháng qua và "
                           "cho biết bất thường đang ĐỀU hay LOANG LỔ",
                           "compare current plant vigor with this same plot over the "
                           "past 4 months and say whether the anomaly is UNIFORM or "
                           "PATCHY"),
                next_step=_next_sentinel())

        metrics = {"ndvi_hien_tai": r["ndvi_now"], "ndvi_nen": r["ndvi_baseline"],
                   "thay_doi_pct": r["change_pct"], "z_score": r["z_score"]}
        if r["patchiness_ratio"] is not None:
            metrics["do_loang_lo"] = r["patchiness_ratio"]

        head = (f"{r['verdict'].capitalize()} — NDVI {r['ndvi_now']} "
                + tr(f"({r['change_pct']:+.1f}% so nền thửa), ảnh ngày {r['observed_on']}",
                     f"({r['change_pct']:+.1f}% vs plot baseline), image {r['observed_on']}"))
        rec = (r["cause_hint"] + tr(" Ra thăm đúng chỗ và chụp lá gửi lại qua Field Mode.",
                                    " Visit the exact spot and send a leaf photo via Field Mode.")
               if r["cause_hint"] else
               tr("Chưa cần hành động. Phần mềm tiếp tục theo dõi mỗi lần vệ tinh bay qua.",
                  "No action needed. The app keeps watching on each satellite pass."))
        return Assessment(
            module_id=self.id, module_name=self.disp_name(), location=loc, status="ok",
            risk_level=r["level"], headline=head,
            detail=(f"{r['cover'].capitalize()}. {r['method']} {r['caveat']}"),
            recommendation=rec, confidence=0.7, confidence_low=0.6,
            confidence_high=0.78, is_real=True, metrics=metrics,
            data_sources=[sentinel.source_note("NDVI")])


# Quá mốc này thì coi là trong đất liền — đo được, không phải đoán: ven biển
# 15,7 km và cửa sông 22,2 km đều có dữ liệu biển; 43 km thì không.
_INLAND_KM = 30.0


class AquacultureModule(TwinModule):
    """Ngưỡng nhiệt cho tôm sú/thẻ chân trắng ĐBSCL:
    tối ưu 28–32°C · >33°C stress nhiệt (giảm ăn, dễ bệnh) · <25°C chậm lớn.
    Sóng lớn đe dọa lồng bè và làm xáo trộn tầng nước ao ven biển.
    """
    id = "aquaculture"; name = "Cảnh báo môi trường ao nuôi"; name_en = "Aquaculture environment alert"; group = "A"; icon = "🦐"; status = "active"
    data_sources = ["Open-Meteo Marine: nhiệt mặt nước & sóng",
                    "Open-Meteo: nhiệt không khí",
                    "Sentinel-2 độ đục/tảo (cần key — lộ trình)"]
    data_sources_en = ["Open-Meteo Marine: sea-surface temp & waves",
                       "Open-Meteo: air temperature",
                       "Sentinel-2 turbidity/algae (needs key — roadmap)"]
    users = ["Hộ/DN nuôi thủy sản"]
    description = "Nhiệt nước/sóng ảnh hưởng tôm cá → cảnh báo sớm."

    HOT, VERY_HOT, COLD = 32.0, 33.5, 25.0

    def assess(self, loc: Location) -> Assessment:
        marine = ds.marine_context(loc.lat, loc.lon)
        if marine is None:
            # PHÂN BIỆT "KHÔNG ÁP DỤNG" VỚI "THIẾU DỮ LIỆU".
            #
            # Trước đây cả hai đều trả need_data, nên một thửa lúa giữa đồng
            # bằng bị đếm là "thiếu dữ liệu ao nuôi" — làm màn hình đầu báo
            # thiếu 6 mục trong khi thực tế chỉ 5. Nhưng "ở đây không nuôi biển
            # được" là một CÂU TRẢ LỜI đúng và dứt khoát, không phải một lỗ hổng.
            #
            # Ranh giới lấy theo ĐO ĐƯỢC chứ không đoán: thử thật thì Cần Giờ
            # (15,7 km) và cửa sông (22,2 km) đều có đủ 7 ngày dữ liệu biển,
            # còn điểm cách bờ 43 km thì không có ô lưới biển nào gần.
            km = ds.distance_to_coast_km(loc.lat, loc.lon)
            if km > _INLAND_KM:
                return Assessment(
                    module_id=self.id, module_name=self.disp_name(), location=loc,
                    status="out_of_scope", risk_level="unknown", is_real=False,
                    headline=tr(f"Không áp dụng — cách biển ~{round(km)} km",
                                f"Not applicable — ~{round(km)} km from the sea"),
                    detail=tr(
                        f"Vị trí này nằm sâu trong đất liền (~{round(km)} km từ "
                        "bờ), nên không có dữ liệu nhiệt mặt nước hay sóng. Đây "
                        "không phải thiếu sót của phần mềm: nuôi trồng ven biển "
                        "không diễn ra ở đây. Với ao nội đồng thì yếu tố quyết "
                        "định là nhiệt và ôxy TẠI AO, phải đo bằng cảm biến đặt "
                        "tại chỗ — vệ tinh không nhìn thấy được.",
                        f"This location is well inland (~{round(km)} km from the "
                        "coast), so there's no sea-surface temperature or wave "
                        "data. This is not a software gap: coastal aquaculture "
                        "doesn't happen here. For inland ponds, the deciding "
                        "factors are IN-POND temperature and oxygen, which need "
                        "on-site sensors — satellites can't see them."),
                    recommendation="",
                    data_sources=self.disp_data_sources())
            return need_data_assessment(
                self, loc,
                needs=tr("dữ liệu nhiệt mặt nước cho đúng toạ độ này",
                         "sea-surface temperature data for this exact coordinate"),
                will_do=tr("theo dõi nhiệt nước, sóng và độ đục để cảnh báo môi trường ao xấu",
                           "monitor water temperature, waves and turbidity to warn of "
                           "bad pond conditions"),
                next_step=tr(
                    f"Điểm này chỉ cách bờ ~{round(km)} km nên lẽ ra phải "
                    "có dữ liệu biển. Nguồn đang không trả về — thử lại sau.",
                    f"This point is only ~{round(km)} km from the coast, so sea "
                    "data should exist. The source isn't responding — try again "
                    "later."))

        sst, wave = marine["sst_max"], marine["wave_max"]
        if sst >= self.VERY_HOT:
            lvl = "danger"
            head = tr(f"Nước quá NÓNG — đỉnh {sst}°C (ngưỡng stress {self.VERY_HOT}°C)",
                      f"Water too HOT — peak {sst}°C (stress threshold {self.VERY_HOT}°C)")
            rec = tr("Giảm cho ăn, tăng sục khí, nâng mực nước ao; hoãn thả giống "
                     "tới khi nhiệt hạ.",
                     "Reduce feeding, increase aeration, raise pond water level; delay "
                     "stocking until it cools.")
        elif sst >= self.HOT:
            lvl = "warning"
            head = tr(f"Nước ấm cần chú ý — đỉnh {sst}°C", f"Warm water to watch — peak {sst}°C")
            rec = tr("Theo dõi oxy hòa tan lúc rạng sáng, chuẩn bị quạt nước.",
                     "Watch dissolved oxygen at dawn, ready the paddlewheels.")
        elif sst <= self.COLD:
            lvl = "warning"
            head = tr(f"Nước lạnh — chỉ {sst}°C, tôm chậm lớn", f"Cold water — only {sst}°C, slow shrimp growth")
            rec = tr("Giữ mực nước sâu, giảm thay nước, cân nhắc lùi lịch thả giống.",
                     "Keep water deep, reduce water changes, consider delaying stocking.")
        else:
            lvl = "safe"
            head = tr(f"Nhiệt nước thuận lợi — đỉnh {sst}°C (tối ưu 28–32°C)",
                      f"Favorable water temp — peak {sst}°C (optimal 28–32°C)")
            rec = tr("Duy trì chăm sóc bình thường.", "Continue normal care.")

        if wave is not None and wave >= 2.0:
            head += tr(f" · sóng cao {wave} m", f" · waves up to {wave} m")
            rec += tr(" Sóng lớn — gia cố lồng bè, kiểm tra bờ ao.",
                      " High waves — reinforce cages, check pond banks.")
            if lvl == "safe":
                lvl = "warning"

        metrics = {"nhiet_mat_nuoc_max_c": sst}
        if wave is not None:
            metrics["song_cao_max_m"] = wave

        return Assessment(
            module_id=self.id, module_name=self.disp_name(), location=loc, status="ok",
            risk_level=lvl, headline=head,
            detail=tr(f"Nhiệt mặt nước & sóng THẬT 7 ngày (Open-Meteo Marine). "
                      f"Ngưỡng tôm: tối ưu 28–32°C, stress ≥{self.VERY_HOT}°C, "
                      f"chậm lớn ≤{self.COLD}°C. Độ đục/tảo cần ảnh Sentinel — "
                      "chưa tích hợp nên chưa đưa vào đánh giá.",
                      f"REAL 7-day sea-surface temp & waves (Open-Meteo Marine). "
                      f"Shrimp thresholds: optimal 28–32°C, stress ≥{self.VERY_HOT}°C, "
                      f"slow growth ≤{self.COLD}°C. Turbidity/algae need Sentinel "
                      "imagery — not yet integrated, so not included in the assessment."),
            recommendation=rec, confidence=0.72, confidence_low=0.64,
            confidence_high=0.8, is_real=True, metrics=metrics,
            forecast=marine["forecast"],
            data_sources=[tr("Open-Meteo Marine: nhiệt mặt nước & sóng (thật)",
                             "Open-Meteo Marine: sea-surface temp & waves (real)")])


class YieldModule(TwinModule):
    id = "yield"; name = "Dự báo năng suất & thu hoạch"; name_en = "Yield & harvest forecast"; group = "A"; icon = "🌾"
    # CHẠY NGAY, không cần khoá. Điều kiện cũ gắn trạng thái vào
    # sentinel.configured(), nên khi chưa có khoá Copernicus thì mũi nhọn này
    # tự khai là "preview" — trong khi nó đã chạy thật qua Planetary Computer,
    # cùng bộ ảnh Sentinel-2 L2A, không cần đăng ký. Phần mềm khai báo SAI về
    # chính năng lực của mình: /api/roadmap báo "chạy ngay 13/18" trong khi
    # thực tế là 18/18.
    status = "active"
    # NẶNG: cần ảnh vệ tinh, mà nguồn không khoá phải gọi riêng từng ảnh và dò
    # lớp SCL cho từng cảnh — đo được 60–370 giây. Để trong lượt quét nhanh thì
    # màn hình đầu từ 2,5 giây thành hơn một phút, và người dùng đóng app trước
    # khi thấy bất cứ thứ gì. Chạy riêng khi được yêu cầu, kết quả có cache.
    heavy = True
    # Giai đoạn sinh trưởng là THÔNG TIN, không phải đe doạ: "đang chín" và
    # "vừa thu hoạch xong nên đất trống" đều làm chỉ số tụt mà chẳng có gì xấu.
    # Việc bắt cây suy bất thường là của module Sâu bệnh — nó so với chính nền
    # của thửa nên không nhầm thu hoạch thành thảm hoạ.
    threat = False
    data_sources = ["Chuỗi NDVI Sentinel-2 180 ngày (Copernicus)"]
    data_sources_en = ["180-day Sentinel-2 NDVI series (Copernicus)"]
    users = ["Nông dân", "Thương lái", "DN xuất khẩu"]
    description = "Cây đang ở giai đoạn nào, đỉnh sinh trưởng khi nào, còn bao lâu tới thu."

    def assess(self, loc: Location) -> Assessment:
        r = optical.growth(loc.lat, loc.lon)
        if r is None:
            return need_data_assessment(
                self, loc,
                needs=_needs_sentinel(tr("chuỗi ảnh Sentinel-2 180 ngày",
                                         "180-day Sentinel-2 image series")),
                will_do=tr("dựng đường cong sinh trưởng NDVI của thửa và cho biết cây "
                           "đang lên hay đang chín, đỉnh rơi vào ngày nào",
                           "build the plot's NDVI growth curve and say whether the "
                           "crop is growing or ripening, and when it peaks"),
                next_step=_next_sentinel())

        # Giai đoạn sinh trưởng KHÔNG phải hiểm họa: cây chín không phải rủi ro.
        # Chỉ báo động khi thửa mất thảm thực vật ngoài dự kiến.
        lvl = "danger" if r["ndvi_now"] < optical.NDVI_BARE else "safe"
        head = (f"{r['stage'].capitalize()} — NDVI {r['ndvi_now']}, "
                + tr(f"đỉnh {r['ndvi_peak']} ngày {r['peak_date']}",
                     f"peak {r['ndvi_peak']} on {r['peak_date']}"))
        return Assessment(
            module_id=self.id, module_name=self.disp_name(), location=loc, status="ok",
            risk_level=lvl, headline=head,
            detail=f"{r['method']} {r['caveat']}",
            recommendation=r["advice"], confidence=0.68, confidence_low=0.58,
            confidence_high=0.76, is_real=True,
            metrics={"ndvi_hien_tai": r["ndvi_now"], "ndvi_dinh": r["ndvi_peak"],
                     "ngay_qua_dinh": float(r["days_since_peak"]),
                     "tich_phan_ndvi": r["ndvi_integral"],
                     "suc_song_so_dinh_pct": r["vigor_vs_peak_pct"] or 0.0},
            data_sources=[sentinel.source_note("NDVI")])


class CarbonModule(TwinModule):
    id = "carbon"; name = "Đo & bán tín chỉ carbon rừng"; name_en = "Forest carbon credits (MRV)"; group = "A"; icon = "🌲"
    # CHẠY NGAY, không cần khoá. Điều kiện cũ gắn trạng thái vào
    # sentinel.configured(), nên khi chưa có khoá Copernicus thì mũi nhọn này
    # tự khai là "preview" — trong khi nó đã chạy thật qua Planetary Computer,
    # cùng bộ ảnh Sentinel-2 L2A, không cần đăng ký. Phần mềm khai báo SAI về
    # chính năng lực của mình: /api/roadmap báo "chạy ngay 13/18" trong khi
    # thực tế là 18/18.
    status = "active"
    # NẶNG: cần ảnh vệ tinh, mà nguồn không khoá phải gọi riêng từng ảnh và dò
    # lớp SCL cho từng cảnh — đo được 60–370 giây. Để trong lượt quét nhanh thì
    # màn hình đầu từ 2,5 giây thành hơn một phút, và người dùng đóng app trước
    # khi thấy bất cứ thứ gì. Chạy riêng khi được yêu cầu, kết quả có cache.
    heavy = True
    data_sources = ["Sentinel-2 NDVI theo pixel (Copernicus)",
                    "Hệ số IPCC 2006 Tier 1 (AFOLU Ch.4)"]
    data_sources_en = ["Sentinel-2 per-pixel NDVI (Copernicus)",
                       "IPCC 2006 Tier 1 factors (AFOLU Ch.4)"]
    users = ["Chủ rừng", "DN", "Quỹ carbon"]
    description = "Đo che phủ tán thật + ước lượng trữ lượng có công bố bậc và sai số."

    def assess(self, loc: Location) -> Assessment:
        from app.services import mrv

        r = mrv.build(loc.lat, loc.lon)
        if not r.get("available"):
            return need_data_assessment(
                self, loc,
                needs=_needs_sentinel(tr("ảnh Sentinel-2 để đo che phủ tán",
                                         "Sentinel-2 imagery to measure canopy cover")),
                will_do=tr("đo che phủ tán thật rồi ước lượng trữ lượng tCO₂ theo hệ số "
                           "IPCC Tier 1, kèm dải sai số và mã băm chống sửa",
                           "measure real canopy cover, then estimate tCO₂ stock using "
                           "IPCC Tier 1 factors, with an uncertainty range and a "
                           "tamper-evident hash"),
                next_step=_next_sentinel())

        m, e = r["measured"], r["estimated"]
        # Che phủ giảm so với năm ngoái là RỦI RO (mất rừng); trữ lượng cao
        # không phải rủi ro. Đừng để module carbon báo động vì có nhiều cây.
        ch = r.get("change_vs_last_year")
        if ch and ch["delta_ha"] <= -0.5:
            lvl = "danger"
        elif ch and ch["delta_ha"] < -0.2:
            lvl = "warning"
        else:
            lvl = "safe"

        return Assessment(
            module_id=self.id, module_name=self.disp_name(), location=loc, status="ok",
            risk_level=lvl, headline=r["headline"],
            detail=(f"{r['methodology']['measured_by']} "
                    f"{r['methodology']['not_measured']} "
                    f"{r['limitations'][0]}"),
            recommendation=(tr("Che phủ đang giảm — kiểm tra thực địa ngay, đây là "
                               "thứ trực tiếp làm mất tín chỉ.",
                               "Canopy is declining — inspect on the ground now; this "
                               "directly costs credits.")
                            if lvl != "safe" else
                            tr("Muốn lên chuẩn phát hành tín chỉ: ",
                               "To reach credit-issuance grade: ") +
                            r["to_reach_credit_grade"][0]),
            confidence=0.6, confidence_low=0.45, confidence_high=0.72,
            is_real=True,
            metrics={"che_phu_tan_pct": m["canopy_pct"],
                     "dien_tich_rung_ha": m["forest_ha"],
                     "tru_luong_tco2": e["stock_tco2"],
                     "sai_so_pct": e["uncertainty_pct"]},
            data_sources=[m["source"], r["methodology"]["estimated_by"]])
