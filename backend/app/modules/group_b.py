"""Nhóm B — radar/địa hình + mưa. Lũ/sạt lở/rủi ro đất dùng dữ liệu THẬT."""
from __future__ import annotations

from app.modules.base import TwinModule
from app.modules.util import (
    _needs_sentinel, _next_sentinel, assessment_from_series, need_data_assessment,
)
from app.schemas import Assessment, Location
from app.services import datasources as ds
from app.services import hazard, optical, sentinel
from app.services.reqlang import tr


class FloodModule(TwinModule):
    id = "flood"; name = "Cảnh báo lũ/ngập sớm"; name_en = "Early flood warning"; group = "B"; icon = "🌊"; status = "active"
    data_sources = ["Open-Meteo: lượng mưa", "Cao độ DEM (Open-Meteo)",
                    "GloFAS: lưu lượng sông (Open-Meteo Flood API)"]
    data_sources_en = ["Open-Meteo: rainfall", "DEM elevation (Open-Meteo)",
                       "GloFAS: river discharge (Open-Meteo Flood API)"]
    users = ["Người dân", "Chính quyền", "Cứu hộ"]
    description = "Vùng dân cư nào sắp ngập, sâu bao nhiêu, khi nào."

    def assess(self, loc: Location) -> Assessment:
        s, real, calibrated, source = hazard.module_series(self.id, loc.lat, loc.lon)
        elev = ds.elevation_proxy(loc.lat, loc.lon)

        # Mưa THƯỢNG NGUỒN cố ý KHÔNG nằm ở đây mà tách thành mô-đun riêng
        # (upstream_flood, nhóm B, đánh dấu nặng). Nó cần lấy mẫu cả một nan
        # quạt địa hình nên tốn ~10 giây; nhét vào đây thì lượt quét toàn cảnh
        # từ 2,5 s vọt lên 82 s — đo được, không phải phỏng đoán. Rà soát nền
        # vẫn chạy nó vì ở đó chờ lâu không sao.
        river = ds.river_discharge_context(loc.lat, loc.lon)

        def texts(lvl, pk, fd):
            if fd:
                head = tr(f"NGUY CƠ NGẬP CAO từ ~{fd.date} (chỉ số {fd.value})",
                          f"HIGH FLOOD RISK from ~{fd.date} (index {fd.value})")
                rec = tr("Kê cao tài sản, sẵn sàng sơ tán; theo dõi thông báo địa phương.",
                         "Raise belongings, be ready to evacuate; follow local announcements.")
            elif lvl == "warning":
                head = tr(f"Có nguy cơ ngập (chỉ số {pk.value})", f"Flood risk present (index {pk.value})")
                rec = tr("Chuẩn bị phương án thoát nước, theo dõi mưa.",
                         "Prepare drainage, watch the rain.")
            else:
                head = tr(f"Ít nguy cơ ngập (chỉ số {pk.value})", f"Low flood risk (index {pk.value})")
                rec = tr("Chưa cần hành động.", "No action needed.")
            # Đối chứng độc lập bằng lưu lượng sông thật
            if river and river["level"] != "safe":
                head += tr(f" · lưu lượng sông gấp {river['ratio']}× bình thường",
                           f" · river discharge {river['ratio']}× normal")
                if river["level"] == "danger":
                    rec = tr("Sông đang lên rất mạnh — ", "River rising fast — ") + rec
            return head, rec

        base = (tr(f"Chỉ số ngập từ lượng mưa THẬT (Open-Meteo), cao độ ~{elev} m.",
                   f"Flood index from REAL rainfall (Open-Meteo), elevation ~{elev} m.") if real
                else tr(f"Chỉ số ngập (mẫu), cao độ ~{elev} m.",
                        f"Flood index (sample), elevation ~{elev} m."))
        if river:
            base += tr(f" Lưu lượng sông GloFAS: nay {river['now_m3s']} m³/s, đỉnh "
                       f"{river['peak_m3s']} m³/s ngày {river['peak_date']} — gấp "
                       f"{river['ratio']}× trung bình khí hậu ({river['mean_m3s']} m³/s).",
                       f" GloFAS river discharge: now {river['now_m3s']} m³/s, peak "
                       f"{river['peak_m3s']} m³/s on {river['peak_date']} — "
                       f"{river['ratio']}× climatic mean ({river['mean_m3s']} m³/s).")
        detail = base + " " + hazard.scale_note(real, calibrated)

        src = [hazard.source_label(source, "lượng mưa", "rainfall"),
               tr(f"Cao độ {elev} m (Open-Meteo)", f"Elevation {elev} m (Open-Meteo)")] \
            if real else list(self.disp_data_sources())
        metrics: dict[str, float] = {}
        conf = 0.75 if real else 0.6
        if river:
            src.append(tr("GloFAS: lưu lượng sông (thật)", "GloFAS: river discharge (real)"))
            metrics = {"luu_luong_hien_tai_m3s": river["now_m3s"],
                       "luu_luong_dinh_m3s": river["peak_m3s"],
                       "luu_luong_tb_m3s": river["mean_m3s"],
                       "ty_so_so_binh_thuong": river["ratio"]}
            # Hai nguồn độc lập cùng chỉ một hướng ⇒ tin cậy hơn.
            if real:
                conf = min(0.88, conf + 0.08)
        a = assessment_from_series(self, loc, s, tr("điểm", "pts"), 40, 70, texts, detail,
                                   confidence=conf, is_real=real, data_sources=src)
        a.metrics = metrics
        return a


class LandslideModule(TwinModule):
    id = "landslide"; name = "Cảnh báo sạt lở"; name_en = "Landslide alert"; group = "B"; icon = "⛰️"; status = "active"
    data_sources = ["Open-Meteo: lượng mưa", "Độ dốc (DEM ước lượng)"]
    data_sources_en = ["Open-Meteo: rainfall", "Slope (DEM estimated)"]
    users = ["Dân miền núi", "Chính quyền"]
    description = "Vùng núi có nguy cơ sạt lở sau mưa lớn."

    def assess(self, loc: Location) -> Assessment:
        s, real, calibrated, source = hazard.module_series(self.id, loc.lat, loc.lon)
        slope, slope_real = ds.slope_context(loc.lat, loc.lon)

        def texts(lvl, pk, fd):
            if fd:
                return (tr(f"NGUY CƠ SẠT LỞ CAO (chỉ số {pk.value})", f"HIGH LANDSLIDE RISK (index {pk.value})"),
                        tr("Tránh xa mái dốc khi mưa lớn; sẵn sàng sơ tán.",
                           "Stay away from slopes in heavy rain; be ready to evacuate."))
            if lvl == "warning":
                return (tr(f"Nguy cơ sạt lở trung bình (chỉ số {pk.value})", f"Moderate landslide risk (index {pk.value})"),
                        tr("Theo dõi vết nứt, lượng mưa; cảnh giác ban đêm.",
                           "Watch for cracks and rainfall; stay alert at night."))
            if slope < 3.0:
                return (tr(f"Địa hình phẳng — hầu như không có nguy cơ sạt lở (chỉ số {pk.value})",
                           f"Flat terrain — virtually no landslide risk (index {pk.value})"),
                        tr("Không cần lo sạt lở ở khu vực đồng bằng này.",
                           "No need to worry about landslides in this flatland."))
            return (tr(f"Nguy cơ sạt lở thấp (chỉ số {pk.value})", f"Low landslide risk (index {pk.value})"),
                    tr("Duy trì theo dõi.", "Keep monitoring."))

        slope_txt = (tr(f"độ dốc THẬT ~{slope}° (DEM Open-Meteo)", f"REAL slope ~{slope}° (Open-Meteo DEM)") if slope_real
                     else tr(f"độ dốc ~{slope}° (ước lượng)", f"slope ~{slope}° (estimated)"))
        detail = ((tr(f"Kết hợp lượng mưa THẬT (Open-Meteo) + {slope_txt}.",
                      f"Combines REAL rainfall (Open-Meteo) + {slope_txt}.") if real
                   else tr(f"Chỉ số sạt lở (mẫu), {slope_txt}.", f"Landslide index (sample), {slope_txt}."))
                  + tr(" Sạt lở cần địa hình dốc — đồng bằng phẳng gần như không rủi ro. ",
                       " Landslides need steep terrain — flat deltas have almost no risk. ")
                  + hazard.scale_note(real, calibrated))
        src = [hazard.source_label(source, "lượng mưa", "rainfall"), slope_txt] \
            if real else self.disp_data_sources()
        return assessment_from_series(self, loc, s, tr("điểm", "pts"), 40, 70, texts, detail,
                                      confidence=0.7 if real else 0.6, is_real=real, data_sources=src)


class StormDamageModule(TwinModule):
    id = "storm_damage"; name = "Bản đồ thiệt hại sau bão"; name_en = "Post-storm damage map"; group = "B"; icon = "🌪️"
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
    data_sources = ["Sentinel-2 NDVI hai kỳ (Copernicus)"]
    data_sources_en = ["Sentinel-2 NDVI two-date pair (Copernicus)"]
    users = ["Cứu trợ", "Bảo hiểm", "Nhà nước"]
    description = "So ảnh hai kỳ để đo mất thảm thực vật đột ngột."

    def assess(self, loc: Location) -> Assessment:
        r = optical.vegetation_loss(loc.lat, loc.lon)
        if r is None:
            return need_data_assessment(
                self, loc,
                needs=_needs_sentinel(tr("ảnh Sentinel-2 hai kỳ trước & sau",
                                         "before-and-after Sentinel-2 image pair")),
                will_do=tr("đo mức mất thảm thực vật giữa hai kỳ để làm căn cứ cứu trợ "
                           "và hồ sơ bồi thường",
                           "measure vegetation loss between the two dates as evidence "
                           "for relief and compensation claims"),
                next_step=_next_sentinel())

        head = (f"{r['verdict'].capitalize()} — NDVI {r['before']['mean']} → "
                f"{r['after']['mean']} ({r['delta']:+.3f})")
        if r["possible_causes"]:
            rec = (tr("Đối chiếu với việc bạn biết đã xảy ra trên thửa (",
                      "Compare with what you know happened on the plot (")
                   + ", ".join(r["possible_causes"]) + tr("). Nếu là thiên tai, ảnh "
                     "hai kỳ này dùng được làm chứng cứ ban đầu cho hồ sơ bồi thường.",
                     "). If it's a disaster, this two-date pair works as initial "
                     "evidence for a compensation claim."))
        else:
            rec = tr("Chưa thấy mất thảm thực vật bất thường giữa hai kỳ.",
                     "No unusual vegetation loss between the two dates.")
        return Assessment(
            module_id=self.id, module_name=self.disp_name(), location=loc, status="ok",
            risk_level=r["level"], headline=head,
            detail=tr(f"Trước: {r['before_cover']}. Sau: {r['after_cover']}. "
                      f"{r['method']} {r['caveat']}",
                      f"Before: {r['before_cover']}. After: {r['after_cover']}. "
                      f"{r['method']} {r['caveat']}"),
            recommendation=rec, confidence=0.72, confidence_low=0.62,
            confidence_high=0.8, is_real=True,
            metrics={"ndvi_truoc": r["before"]["mean"],
                     "ndvi_sau": r["after"]["mean"],
                     "thay_doi": r["delta"]},
            data_sources=[sentinel.source_note("NDVI")])


class LandRiskModule(TwinModule):
    id = "land_risk"; name = "Rủi ro trước khi mua đất"; name_en = "Pre-purchase land risk"; group = "B"; icon = "🏘️"; status = "active"
    # Đây là điểm thẩm định MỘT LẦN trước khi mua, không phải sự việc sắp xảy
    # ra. Với thửa đã sở hữu, nhắc lại mỗi sáu giờ rằng "đất này trũng" là phiền
    # chứ không phải cảnh báo — nền đất không đổi từ hôm qua.
    threat = False
    data_sources = ["Cao độ (Open-Meteo)", "Open-Meteo: lượng mưa", "Khoảng cách biển"]
    data_sources_en = ["Elevation (Open-Meteo)", "Open-Meteo: rainfall", "Distance to coast"]
    users = ["Người mua nhà đất", "Môi giới", "Ngân hàng"]
    description = "Nhập vị trí → lô này có ngập/sạt lở không, an toàn không."

    def assess(self, loc: Location) -> Assessment:
        elev = ds.elevation_proxy(loc.lat, loc.lon)          # thật (Open-Meteo)
        slope, slope_real = ds.slope_context(loc.lat, loc.lon)
        dist = ds.distance_to_coast_km(loc.lat, loc.lon)
        precip, has_rain = ds.forecast_precip_7d_total(loc.lat, loc.lon)

        flood_pen = max(0.0, 30.0 - elev * 1.2)
        if precip is not None:
            flood_pen = min(45.0, flood_pen + precip * 0.15)
        slide_pen = min(30.0, slope * 1.2)
        salt_pen = max(0.0, 20.0 - dist * 0.4)
        score = int(max(0.0, 100.0 - flood_pen - slide_pen - salt_pen))
        lvl = "safe" if score >= 75 else "warning" if score >= 50 else "danger"
        head = tr(f"Điểm an toàn đất: {score}/100", f"Land safety score: {score}/100")
        rec = (tr("An toàn để mua/đầu tư.", "Safe to buy/invest.") if lvl == "safe"
               else tr("Có rủi ro — thương lượng giá & kiểm tra kỹ.", "Some risk — negotiate price & inspect carefully.") if lvl == "warning"
               else tr("Rủi ro cao — cân nhắc rất kỹ trước khi mua.", "High risk — consider very carefully before buying."))
        slope_lbl = "THẬT " if slope_real else ""
        detail = (tr(f"Cao độ THẬT ~{elev} m · dốc {slope_lbl}~{slope}° · cách biển ~{round(dist,1)} km",
                     f"REAL elevation ~{elev} m · slope ~{slope}° · {round(dist,1)} km from coast")
                  + (tr(f" · mưa dự báo 7 ngày tới ~{precip} mm (Open-Meteo).", f" · 7-day rain forecast ~{precip} mm (Open-Meteo).") if has_rain
                     else tr(" (mưa: mẫu).", " (rain: sample).")))
        metrics = {"diem": float(score), "cao_do_m": elev, "do_doc_deg": slope}
        if precip is not None:
            metrics["mua_7ngay_mm"] = precip
        return Assessment(
            module_id=self.id, module_name=self.disp_name(), location=loc, status="ok",
            risk_level=lvl, headline=head, score=float(score), detail=detail,
            recommendation=rec, confidence=0.68, confidence_low=0.55, confidence_high=0.78,
            is_real=bool(has_rain and slope_real), metrics=metrics, data_sources=self.disp_data_sources())


class IllegalBuildModule(TwinModule):
    id = "illegal_build"; name = "Giám sát xây dựng trái phép"; name_en = "Illegal-construction watch"; group = "B"; icon = "🏗️"
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
    data_sources = ["Sentinel-2 NDBI + NDVI, hai kỳ cách nhau 1 năm (Copernicus)"]
    data_sources_en = ["Sentinel-2 NDBI + NDVI, two dates one year apart (Copernicus)"]
    users = ["Quản lý đô thị", "Địa chính"]
    description = "Bề mặt cứng mới xuất hiện so với cùng kỳ năm trước."

    def assess(self, loc: Location) -> Assessment:
        r = optical.new_construction(loc.lat, loc.lon)
        if r is None:
            return need_data_assessment(
                self, loc,
                needs=_needs_sentinel(tr("ảnh Sentinel-2 hai kỳ cách nhau một năm",
                                         "Sentinel-2 images one year apart")),
                will_do=tr("đối chiếu NDBI và NDVI giữa hai kỳ để chỉ ra chỗ có bề mặt "
                           "cứng mới, làm đầu mối đi kiểm tra hồ sơ",
                           "compare NDBI and NDVI between the two dates to flag new "
                           "hard surfaces, as a lead for a records check"),
                next_step=_next_sentinel())

        head = (f"{r['verdict'].capitalize()} — NDBI {r['ndbi']['delta']:+.3f}, "
                + tr(f"NDVI {r['ndvi']['delta']:+.3f} so cùng kỳ năm trước",
                     f"NDVI {r['ndvi']['delta']:+.3f} vs same period last year"))
        rec = (tr("Có đầu mối để đi kiểm tra thực địa và tra hồ sơ địa chính. "
                  "Phần mềm KHÔNG kết luận công trình có phép hay không.",
                  "A lead worth checking on the ground and against cadastral records. "
                  "The software does NOT conclude whether the construction is licensed.")
               if r["both_signals"] else
               tr("Chưa có đầu mối đủ mạnh để đi kiểm tra.",
                  "No strong enough lead to warrant an inspection."))
        return Assessment(
            module_id=self.id, module_name=self.disp_name(), location=loc, status="ok",
            risk_level=r["level"], headline=head,
            detail=f"{r['method']} {r['caveat']}",
            recommendation=rec, confidence=0.65, confidence_low=0.54,
            confidence_high=0.74, is_real=True,
            metrics={"ndbi_thay_doi": r["ndbi"]["delta"],
                     "ndvi_thay_doi": r["ndvi"]["delta"]},
            data_sources=[sentinel.source_note("NDBI"), sentinel.source_note("NDVI")])


class UpstreamFloodModule(TwinModule):
    """Lũ đến từ mưa rơi Ở TRÊN CAO, không phải mưa rơi trên thửa.

    Vì sao phải là một mô-đun riêng chứ không gộp vào module Lũ: nó cảnh báo
    được ngay cả khi TẠI CHỖ chưa mưa giọt nào — Trà Leng 2020 không sập vì mưa
    tại chỗ mà vì cả sườn núi phía trên đã ngậm nước. Gộp vào chỉ số ngập tại
    chỗ sẽ làm loãng đúng cái tín hiệu quan trọng nhất của nó.

    Đánh dấu NẶNG vì phải lấy mẫu địa hình cả một nan quạt: đo được là lượt quét
    toàn cảnh từ 2,5 s vọt lên 82 s nếu để chung. Rà soát nền vẫn chạy nó — ở đó
    chờ mười giây không ai thấy, mà đó lại đúng là lúc cảnh báo có giá trị nhất.
    """

    id = "upstream_flood"; name = "Lũ từ thượng nguồn"; name_en = "Upstream flood"; group = "B"; icon = "🏔️"
    status = "active"
    heavy = True
    data_sources = ["DEM: nan quạt cao độ 8 hướng × 3 vòng (Open-Meteo)",
                    "Open-Meteo: mưa dự báo trên lưới thượng nguồn"]
    data_sources_en = ["DEM: 8-bearing × 3-ring elevation fan (Open-Meteo)",
                       "Open-Meteo: rain forecast on the upstream grid"]
    users = ["Dân vùng núi và hạ lưu", "Chính quyền", "Cứu hộ"]
    description = "Trên cao có đang mưa không, và nước đó có dồn về phía bạn không."

    def assess(self, loc: Location) -> Assessment:
        from app.services import catchment

        r = catchment.upstream(loc.lat, loc.lon)
        if r is None:
            return need_data_assessment(
                self, loc,
                needs=tr("cao độ và mưa dự báo cho vùng quanh thửa",
                         "elevation and rain forecast for the area around the plot"),
                will_do=tr("đo lượng mưa rơi trên phần đất cao hơn rồi cân theo độ "
                           "dốc về phía thửa, để cảnh báo nước dồn xuống",
                           "measure rain falling on higher ground and weight it by slope "
                           "toward the plot, to warn of water flowing down"),
                next_step=tr("Nguồn dữ liệu đang không phản hồi. Thử lại sau ít phút.",
                             "The data source isn't responding. Try again in a few minutes."))

        # Địa hình phẳng hoặc thửa nằm ở chỗ cao: KHÔNG phải "chưa đủ dữ liệu" —
        # là một câu trả lời đầy đủ, và với người dùng còn là tin tốt.
        if not r["available"]:
            binh_yen = r["reason"] == "no_upslope"
            return Assessment(
                module_id=self.id, module_name=self.disp_name(), location=loc,
                status="ok", risk_level="safe",
                headline=(tr("Không có sườn nào đổ nước về thửa này",
                             "No slope drains toward this plot")
                          if binh_yen else
                          tr(f"Địa hình quá phẳng để nói chuyện thượng nguồn "
                             f"(chênh cao {r['relief_m']} m)",
                             f"Terrain too flat to talk about upstream "
                             f"(relief {r['relief_m']} m)")),
                detail=r["message"],
                recommendation=(
                    tr("Nguy cơ nước từ trên dồn xuống gần như không có. Vẫn theo "
                       "dõi module Lũ cho mưa tại chỗ.",
                       "Risk of water flowing down from above is nearly zero. Still "
                       "watch the Flood module for local rain.")
                    if binh_yen else
                    tr("Ở đồng bằng, hãy theo dõi module Lũ (mưa tại chỗ + lưu "
                       "lượng sông GloFAS) và thông báo đóng/mở cống của địa phương.",
                       "On flat delta terrain, watch the Flood module (local rain + "
                       "GloFAS river discharge) and local sluice-gate announcements.")),
                confidence=0.6, confidence_low=0.5, confidence_high=0.7,
                is_real=True,
                metrics={"cao_do_m": r["here_m"], "chenh_cao_m": r["relief_m"]},
                data_sources=[tr("DEM cao độ (Open-Meteo)", "DEM elevation (Open-Meteo)")])

        rec = {
            "danger": tr("Trên cao đang mưa rất lớn và nước sẽ dồn xuống. Nguy cơ "
                        "đến NGAY CẢ KHI ở đây chưa mưa — kê cao tài sản, tránh "
                        "lòng suối và chân mái dốc, sẵn sàng di dời.",
                        "Heavy rain upstream and water will flow down. The risk "
                        "exists EVEN IF it hasn't rained here yet — raise "
                        "belongings, stay away from streambeds and slope toes, "
                        "be ready to move."),
            "warning": tr("Thượng nguồn mưa đáng kể. Theo dõi mực nước suối và "
                         "tránh qua ngầm tràn khi nước lên.",
                         "Significant rain upstream. Watch stream levels and avoid "
                         "low-water crossings when the water rises."),
            "safe": tr("Chưa thấy nước bất thường dồn về từ phía trên.",
                      "No unusual water flowing down from above yet."),
        }[r["level"]]

        return Assessment(
            module_id=self.id, module_name=self.disp_name(), location=loc, status="ok",
            risk_level=r["level"],
            headline=tr(
                f"{r['verdict'].capitalize()} — mưa thượng nguồn "
                f"{r['upstream_rain_mm']} mm so với {r['local_rain_mm']} mm "
                f"tại chỗ ({r['extra_vs_local_mm']:+} mm)",
                f"{r['verdict'].capitalize()} — upstream rain "
                f"{r['upstream_rain_mm']} mm vs {r['local_rain_mm']} mm "
                f"locally ({r['extra_vs_local_mm']:+} mm)"),
            detail=tr(
                f"{r['upslope_points']}/{r['total_points']} điểm quanh thửa "
                f"cao hơn, chênh cao {r['relief_m']} m. Sườn dốc nhất: cách "
                f"{r['steepest']['km']} km, cao hơn {r['steepest']['drop_m']} m, "
                f"mưa {r['steepest']['rain_7d_mm']} mm. {r['method']} "
                f"{r['caveat']}",
                f"{r['upslope_points']}/{r['total_points']} points around the plot "
                f"are higher, relief {r['relief_m']} m. Steepest slope: "
                f"{r['steepest']['km']} km away, {r['steepest']['drop_m']} m higher, "
                f"{r['steepest']['rain_7d_mm']} mm rain. {r['method']} "
                f"{r['caveat']}"),
            recommendation=rec, confidence=0.6, confidence_low=0.48,
            confidence_high=0.7, is_real=True,
            metrics={"mua_thuong_nguon_mm": r["upstream_rain_mm"],
                     "mua_tai_cho_mm": r["local_rain_mm"] or 0.0,
                     "lech_mm": r["extra_vs_local_mm"] or 0.0,
                     "diem_cao_hon": float(r["upslope_points"]),
                     "chenh_cao_m": r["relief_m"]},
            data_sources=[tr("DEM nan quạt cao độ (thật)", "DEM elevation fan (real)"),
                          tr("Open-Meteo: mưa trên lưới thượng nguồn (thật)",
                             "Open-Meteo: rain on upstream grid (real)")])
