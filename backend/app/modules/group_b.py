"""Nhóm B — radar/địa hình + mưa. Lũ/sạt lở/rủi ro đất dùng dữ liệu THẬT."""
from __future__ import annotations

from app.modules.base import TwinModule
from app.modules.util import assessment_from_series, need_data_assessment
from app.schemas import Assessment, Location
from app.services import datasources as ds


class FloodModule(TwinModule):
    id = "flood"; name = "Cảnh báo lũ/ngập sớm"; group = "B"; icon = "🌊"; status = "active"
    data_sources = ["Open-Meteo: lượng mưa", "Cao độ DEM (Open-Meteo)",
                    "GloFAS: lưu lượng sông (Open-Meteo Flood API)"]
    users = ["Người dân", "Chính quyền", "Cứu hộ"]
    description = "Vùng dân cư nào sắp ngập, sâu bao nhiêu, khi nào."

    def assess(self, loc: Location) -> Assessment:
        s, real = ds.flood_series(loc.lat, loc.lon)
        elev = ds.elevation_proxy(loc.lat, loc.lon)
        river = ds.river_discharge_context(loc.lat, loc.lon)

        def texts(lvl, pk, fd):
            if fd:
                head = f"NGUY CƠ NGẬP CAO từ ~{fd.date} (chỉ số {fd.value})"
                rec = "Kê cao tài sản, sẵn sàng sơ tán; theo dõi thông báo địa phương."
            elif lvl == "warning":
                head = f"Có nguy cơ ngập (chỉ số {pk.value})"
                rec = "Chuẩn bị phương án thoát nước, theo dõi mưa."
            else:
                head = f"Ít nguy cơ ngập (chỉ số {pk.value})"
                rec = "Chưa cần hành động."
            # Đối chứng độc lập bằng lưu lượng sông thật
            if river and river["level"] != "safe":
                head += f" · lưu lượng sông gấp {river['ratio']}× bình thường"
                if river["level"] == "danger":
                    rec = ("Sông đang lên rất mạnh — " + rec[0].lower() + rec[1:])
            return head, rec

        base = (f"Chỉ số ngập từ lượng mưa THẬT (Open-Meteo), cao độ ~{elev} m." if real
                else f"Chỉ số ngập (mẫu), cao độ ~{elev} m.")
        if river:
            base += (f" Lưu lượng sông GloFAS: nay {river['now_m3s']} m³/s, đỉnh "
                     f"{river['peak_m3s']} m³/s ngày {river['peak_date']} — gấp "
                     f"{river['ratio']}× trung bình khí hậu ({river['mean_m3s']} m³/s).")
        detail = base + " <40 thấp · 40–70 cảnh báo · ≥70 cao."

        src = ["Open-Meteo: lượng mưa (thật)", f"Cao độ {elev} m (Open-Meteo)"] if real else list(self.data_sources)
        metrics: dict[str, float] = {}
        conf = 0.75 if real else 0.6
        if river:
            src.append("GloFAS: lưu lượng sông (thật)")
            metrics = {"luu_luong_hien_tai_m3s": river["now_m3s"],
                       "luu_luong_dinh_m3s": river["peak_m3s"],
                       "luu_luong_tb_m3s": river["mean_m3s"],
                       "ty_so_so_binh_thuong": river["ratio"]}
            # Hai nguồn độc lập cùng chỉ một hướng ⇒ tin cậy hơn.
            if real:
                conf = min(0.88, conf + 0.08)

        a = assessment_from_series(self, loc, s, "điểm", 40, 70, texts, detail,
                                   confidence=conf, is_real=real, data_sources=src)
        a.metrics = metrics
        return a


class LandslideModule(TwinModule):
    id = "landslide"; name = "Cảnh báo sạt lở"; group = "B"; icon = "⛰️"; status = "active"
    data_sources = ["Open-Meteo: lượng mưa", "Độ dốc (DEM ước lượng)"]
    users = ["Dân miền núi", "Chính quyền"]
    description = "Vùng núi có nguy cơ sạt lở sau mưa lớn."

    def assess(self, loc: Location) -> Assessment:
        s, real = ds.landslide_series(loc.lat, loc.lon)
        slope, slope_real = ds.slope_context(loc.lat, loc.lon)

        def texts(lvl, pk, fd):
            if fd:
                return (f"NGUY CƠ SẠT LỞ CAO (chỉ số {pk.value})",
                        "Tránh xa mái dốc khi mưa lớn; sẵn sàng sơ tán.")
            if lvl == "warning":
                return (f"Nguy cơ sạt lở trung bình (chỉ số {pk.value})",
                        "Theo dõi vết nứt, lượng mưa; cảnh giác ban đêm.")
            if slope < 3.0:
                return (f"Địa hình phẳng — hầu như không có nguy cơ sạt lở (chỉ số {pk.value})",
                        "Không cần lo sạt lở ở khu vực đồng bằng này.")
            return (f"Nguy cơ sạt lở thấp (chỉ số {pk.value})", "Duy trì theo dõi.")

        slope_txt = f"độ dốc THẬT ~{slope}° (DEM Open-Meteo)" if slope_real else f"độ dốc ~{slope}° (ước lượng)"
        detail = ((f"Kết hợp lượng mưa THẬT (Open-Meteo) + {slope_txt}." if real
                   else f"Chỉ số sạt lở (mẫu), {slope_txt}.")
                  + " Sạt lở cần địa hình dốc — đồng bằng phẳng gần như không rủi ro."
                  + " <40 thấp · 40–70 trung bình · ≥70 cao.")
        src = ["Open-Meteo: lượng mưa (thật)", slope_txt] if real else self.data_sources
        return assessment_from_series(self, loc, s, "điểm", 40, 70, texts, detail,
                                      confidence=0.7 if real else 0.6, is_real=real, data_sources=src)


class StormDamageModule(TwinModule):
    id = "storm_damage"; name = "Bản đồ thiệt hại sau bão"; group = "B"; icon = "🌪️"; status = "preview"
    data_sources = ["Ảnh vệ tinh trước/sau (change detection, cần key)"]
    users = ["Cứu trợ", "Bảo hiểm", "Nhà nước"]
    description = "Khoanh vùng thiệt hại trong vài giờ để cứu trợ/bồi thường."

    def assess(self, loc: Location) -> Assessment:
        return need_data_assessment(
            self, loc,
            needs="ảnh vệ tinh trước & sau bão (change detection)",
            will_do="khoanh vùng thiệt hại và ước tính % diện tích ảnh hưởng phục vụ "
                    "cứu trợ/bồi thường",
            next_step="Đang trong lộ trình tích hợp ảnh Sentinel-1/2 hai kỳ.")


class LandRiskModule(TwinModule):
    id = "land_risk"; name = "Rủi ro trước khi mua đất"; group = "B"; icon = "🏘️"; status = "active"
    data_sources = ["Cao độ (Open-Meteo)", "Open-Meteo: lượng mưa", "Khoảng cách biển"]
    users = ["Người mua nhà đất", "Môi giới", "Ngân hàng"]
    description = "Nhập vị trí → lô này có ngập/sạt lở không, an toàn không."

    def assess(self, loc: Location) -> Assessment:
        elev = ds.elevation_proxy(loc.lat, loc.lon)          # thật (Open-Meteo)
        slope, slope_real = ds.slope_context(loc.lat, loc.lon)
        dist = ds.distance_to_coast_km(loc.lat, loc.lon)
        precip, has_rain = ds.recent_precip_total(loc.lat, loc.lon)

        flood_pen = max(0.0, 30.0 - elev * 1.2)
        if precip is not None:
            flood_pen = min(45.0, flood_pen + precip * 0.15)
        slide_pen = min(30.0, slope * 1.2)
        salt_pen = max(0.0, 20.0 - dist * 0.4)
        score = int(max(0.0, 100.0 - flood_pen - slide_pen - salt_pen))
        lvl = "safe" if score >= 75 else "warning" if score >= 50 else "danger"
        head = f"Điểm an toàn đất: {score}/100"
        rec = ("An toàn để mua/đầu tư." if lvl == "safe"
               else "Có rủi ro — thương lượng giá & kiểm tra kỹ." if lvl == "warning"
               else "Rủi ro cao — cân nhắc rất kỹ trước khi mua.")
        slope_lbl = "THẬT " if slope_real else ""
        detail = (f"Cao độ THẬT ~{elev} m · dốc {slope_lbl}~{slope}° · cách biển ~{round(dist,1)} km"
                  + (f" · mưa 7 ngày ~{precip} mm (Open-Meteo)." if has_rain else " (mưa: mẫu)."))
        metrics = {"diem": float(score), "cao_do_m": elev, "do_doc_deg": slope}
        if precip is not None:
            metrics["mua_7ngay_mm"] = precip
        return Assessment(
            module_id=self.id, module_name=self.name, location=loc, status="ok",
            risk_level=lvl, headline=head, score=float(score), detail=detail,
            recommendation=rec, confidence=0.68, confidence_low=0.55, confidence_high=0.78,
            is_real=bool(has_rain and slope_real), metrics=metrics, data_sources=self.data_sources)


class IllegalBuildModule(TwinModule):
    id = "illegal_build"; name = "Giám sát xây dựng trái phép"; group = "B"; icon = "🏗️"; status = "preview"
    data_sources = ["Change detection ảnh vệ tinh (cần key)"]
    users = ["Quản lý đô thị", "Địa chính"]
    description = "Tự phát hiện công trình mới bất thường / lấn chiếm."

    def assess(self, loc: Location) -> Assessment:
        return need_data_assessment(
            self, loc,
            needs="ảnh vệ tinh 2 kỳ (change detection)",
            will_do="phát hiện công trình/bề mặt mới xuất hiện giữa hai thời điểm để "
                    "đối chiếu giấy phép (kết quả có hệ quả pháp lý nên KHÔNG mô phỏng)",
            next_step="Đang trong lộ trình tích hợp change detection ảnh Sentinel.")
