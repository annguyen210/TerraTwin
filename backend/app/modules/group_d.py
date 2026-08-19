"""Nhóm D — ba ngành còn trống trong bản thiết kế.

  URB-09  Đô thị & Quy hoạch          → UrbanModule
  INF-11  Khai khoáng & Hạ tầng       → MiningModule
  SUP-12  Chuỗi cung ứng nông–lâm sản → SupplyChainModule

Cả ba đều hỏi những câu mà VỆ TINH VÀ KHÍ TƯỢNG MỘT MÌNH KHÔNG TRẢ LỜI ĐƯỢC:
ở đây có bao nhiêu nhà, quanh đây có mỏ nào không, vùng nguyên liệu quanh nhà
máy đang ra sao. Vì vậy nhóm này dựng trên OpenStreetMap (miễn phí, không key)
ghép với mưa/địa hình đã có, và ghép thêm ảnh Sentinel khi có khóa.

Điểm khác nhóm A/B/C: nhóm này nhìn ra XUNG QUANH chứ không chỉ nhìn xuống thửa.
Một khu đô thị ngập vì bê tông hoá cả lưu vực, không vì riêng mảnh đất đó; một
nhà máy thiếu nguyên liệu vì cả vùng trồng gặp hạn, không vì riêng kho của nó.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

from app.modules.base import TwinModule
from app.modules.util import need_data_assessment
from app.schemas import Assessment, Location
from app.services import datasources as ds
from app.services import osm

# ---------------------------------------------------------------- URB-09

# Số hiệu đường cong dòng chảy (SCS Curve Number, USDA-NRCS TR-55) cho nhóm đất
# thấm trung bình (HSG B/C — phù hợp phần lớn đồng bằng VN). CN càng cao thì
# nước mưa càng chảy tràn thay vì thấm xuống.
CN_IMPERVIOUS = 98.0      # mái, bê tông, nhựa đường
CN_PERVIOUS = 74.0        # đất, cỏ, vườn — nhóm B/C, che phủ trung bình


def _runoff_mm(rain_mm: float, cn: float) -> float:
    """Lượng nước chảy tràn theo phương pháp SCS Curve Number.

    S = 25400/CN − 254 (mm) · Ia = 0,2·S · Q = (P−Ia)² / (P−Ia+S) khi P > Ia.
    Đây là phương pháp thuỷ văn tiêu chuẩn, không phải hệ số tự nghĩ ra.
    """
    if rain_mm <= 0 or cn <= 0:
        return 0.0
    s = 25400.0 / cn - 254.0
    ia = 0.2 * s
    if rain_mm <= ia:
        return 0.0
    return (rain_mm - ia) ** 2 / (rain_mm - ia + s)


class UrbanModule(TwinModule):
    """Đô thị hoá làm ngập nặng thêm bao nhiêu — đo được, không phán chung chung.

    Câu hỏi thật của người quy hoạch và của người mua nhà trong đô thị không
    phải "trời mưa bao nhiêu" mà là "cùng trận mưa đó, khu này chảy tràn nhiều
    hơn khu chưa bê tông hoá bao nhiêu lần". Đó là thứ tính được: đo tỉ lệ bê
    tông hoá từ OSM rồi chạy đường cong dòng chảy SCS cho hai kịch bản.
    """

    id = "urban"; name = "Ngập úng & mảng xanh đô thị"; group = "D"; icon = "🏙️"
    status = "active"
    data_sources = ["OpenStreetMap: nhà, đường, loại đất sử dụng",
                    "Open-Meteo: mưa dự báo 7 ngày tới", "Cao độ DEM",
                    "Sentinel-2 NDVI cho mảng xanh (khi có khóa)"]
    users = ["Quản lý đô thị", "Nhà quy hoạch", "Người mua nhà trong đô thị"]
    description = "Bê tông hoá làm nước chảy tràn tăng bao nhiêu, mảng xanh còn bao nhiêu."

    def assess(self, loc: Location) -> Assessment:
        env = osm.built_environment(loc.lat, loc.lon, radius_m=1000.0)
        if env is None:
            return need_data_assessment(
                self, loc,
                needs="dữ liệu hạ tầng OpenStreetMap cho vùng này",
                will_do="đo tỉ lệ bê tông hoá rồi tính nước mưa chảy tràn tăng "
                        "thêm bao nhiêu so với khi chưa đô thị hoá",
                next_step=("Overpass API đang không phản hồi (dịch vụ công cộng "
                           "hay quá tải). Thử lại sau vài phút."))

        precip, has_rain = ds.forecast_precip_7d_total(loc.lat, loc.lon)
        rain = precip if has_rain else 0.0
        elev = ds.elevation_proxy(loc.lat, loc.lon)

        imp = env["built_fraction"]
        # CN pha trộn theo diện tích: phần bê tông và phần còn thấm được.
        cn_now = imp * CN_IMPERVIOUS + (1 - imp) * CN_PERVIOUS
        q_now = _runoff_mm(rain, cn_now)
        q_natural = _runoff_mm(rain, CN_PERVIOUS)
        extra = q_now - q_natural
        ratio = (q_now / q_natural) if q_natural > 0.5 else None

        # Mức rủi ro: bê tông hoá cao + nền thấp + mưa lớn. Ba yếu tố cùng lúc
        # mới thành ngập đô thị; một mình bê tông hoá không phải hiểm họa.
        score = 0.0
        score += min(45.0, imp * 150.0)          # bê tông hoá
        score += max(0.0, 25.0 - elev * 1.5)     # nền thấp, thoát chậm
        score += min(30.0, extra * 1.2)          # phần chảy tràn tăng thêm
        lvl = "danger" if score >= 70 else "warning" if score >= 40 else "safe"

        green_ha = env["landuse_ha"].get("forest", 0.0) + \
            env["landuse_ha"].get("farmland", 0.0)
        green_pct = round(100.0 * green_ha / max(0.1, env["area_ha"]), 1)

        head = (f"Bê tông hoá {env['built_pct']}% trong bán kính 1 km"
                + (f" — cùng trận mưa {rain} mm, nước chảy tràn "
                   f"{q_now:.0f} mm so với {q_natural:.0f} mm nếu chưa đô thị hoá"
                   f"{f' (gấp {ratio:.1f} lần)' if ratio else ''}"
                   if rain > 5 else " — 7 ngày tới chưa dự báo mưa đáng kể để so"))

        if lvl == "danger":
            rec = ("Vùng này bê tông hoá cao trên nền thấp. Ưu tiên hồ điều hoà, "
                   "mặt thấm nước và giữ lại mảng xanh còn sót — trồng cây ven "
                   "đường không đủ, phải có chỗ cho nước đi.")
        elif lvl == "warning":
            rec = ("Cần chú ý thoát nước khi mưa lớn. Giữ mảng xanh hiện có và "
                   "kiểm tra cống rãnh trước mùa mưa.")
        else:
            rec = "Mức bê tông hoá và địa hình hiện chưa tạo áp lực ngập rõ rệt."

        return Assessment(
            module_id=self.id, module_name=self.name, location=loc, status="ok",
            risk_level=lvl, headline=head, score=round(score, 1),
            detail=(f"{env['buildings']} công trình · đường xe cơ giới "
                    f"{env['road_density_km_per_km2']} km/km² · mảng xanh/nông "
                    f"nghiệp {green_pct}% · nền {elev} m. Dòng chảy tính bằng "
                    f"phương pháp SCS Curve Number (USDA TR-55), CN pha trộn "
                    f"{cn_now:.0f}. Độ đầy đủ dữ liệu OSM: {env['completeness']} — "
                    f"{env['completeness_note']}"),
            recommendation=rec, confidence=0.62, confidence_low=0.5,
            confidence_high=0.72, is_real=True,
            metrics={"be_tong_hoa_pct": env["built_pct"],
                     "cong_trinh": float(env["buildings"]),
                     "mat_do_duong_km_km2": env["road_density_km_per_km2"],
                     "mang_xanh_pct": green_pct,
                     "chay_tran_mm": round(q_now, 1),
                     "chay_tran_tu_nhien_mm": round(q_natural, 1),
                     "cao_do_m": elev},
            data_sources=[env["source"],
                          "Open-Meteo: mưa dự báo 7 ngày tới" if has_rain else "Mưa: chưa lấy được",
                          "SCS Curve Number (USDA-NRCS TR-55)"])


# ---------------------------------------------------------------- INF-11

class MiningModule(TwinModule):
    """Ổn định mái dốc ở nơi đất đã bị xáo trộn.

    Mỏ và công trường tạo ra mái dốc nhân tạo dựng đứng hơn tự nhiên, trên nền
    đất đã mất kết cấu. Đó là lý do các vụ sạt lở bãi thải và moong khai thác
    thường xảy ra sau mưa lớn chứ không phải giữa mùa khô. Module ghép ba thứ:
    có hoạt động đào bới quanh đây không (OSM), độ dốc thật (DEM), và mưa dồn
    (Open-Meteo). Có ảnh Sentinel thì thêm được đất trần đang mở rộng hay không.
    """

    id = "mining"; name = "An toàn mỏ & công trường"; group = "D"; icon = "⛏️"
    status = "active"
    data_sources = ["OpenStreetMap: mỏ, khu công nghiệp, công trường",
                    "DEM: độ dốc thật 4 hướng", "Open-Meteo: mưa dự báo 7 ngày tới",
                    "Sentinel-2: đất trần mở rộng (khi có khóa)"]
    users = ["Chủ mỏ", "Nhà thầu hạ tầng", "Cơ quan an toàn lao động",
             "Dân cư quanh mỏ"]
    description = "Nguy cơ mất ổn định mái dốc trên đất đã bị đào bới, sau mưa."

    _SELECTOR = '["landuse"~"quarry|industrial"]'

    def assess(self, loc: Location) -> Assessment:
        sites = osm.nearest(loc.lat, loc.lon, self._SELECTOR,
                            radius_m=15_000.0, limit=5)
        if sites is None:
            return need_data_assessment(
                self, loc,
                needs="dữ liệu OpenStreetMap về mỏ và khu công nghiệp quanh đây",
                will_do="ghép vị trí khai thác với độ dốc và mưa dồn để cảnh báo "
                        "nguy cơ mất ổn định mái dốc",
                next_step="Overpass API đang không phản hồi. Thử lại sau vài phút.")

        slope, slope_real = ds.slope_context(loc.lat, loc.lon)
        precip, has_rain = ds.forecast_precip_7d_total(loc.lat, loc.lon)
        rain = precip if has_rain else 0.0
        elev = ds.elevation_proxy(loc.lat, loc.lon)

        near = [s for s in sites if s["km"] <= 5.0]
        nearest_km = sites[0]["km"] if sites else None

        # Đất trần mở rộng — chỉ có khi đã cắm khóa Sentinel.
        bare = None
        try:
            from app.services import optical
            v = optical.vegetation_loss(loc.lat, loc.lon, gap_days=365, window=45)
            if v is not None:
                bare = v
        except Exception:
            bare = None

        # Điểm rủi ro. Dốc là yếu tố nền, mưa là ngòi nổ, hoạt động đào bới là
        # thứ biến một sườn ổn định thành sườn nhân tạo.
        score = 0.0
        score += min(40.0, slope * 2.0)
        score += min(35.0, rain * 0.18)      # mưa DỰ BÁO — ngòi nổ, nhìn về phía trước
        if near:
            score += 20.0
        elif nearest_km is not None and nearest_km <= 10.0:
            score += 8.0
        if bare is not None and bare["delta"] <= -0.15:
            score += 15.0

        lvl = "danger" if score >= 70 else "warning" if score >= 45 else "safe"

        if not near and (nearest_km is None or nearest_km > 10.0):
            head = (f"Không thấy mỏ hay khu công nghiệp nào trong 10 km "
                    f"(OSM) — độ dốc {slope}°, mưa dự báo 7 ngày tới {rain} mm")
            rec = ("Vị trí này không nằm gần khu vực đào bới theo dữ liệu OSM. "
                   "Nếu thực tế có công trường chưa được vẽ lên bản đồ, hãy "
                   "dùng module Sạt lở để đánh giá theo địa hình và mưa.")
        else:
            what = near[0] if near else sites[0]
            head = (f"{'Có' if near else 'Gần nhất'} khu khai thác/công nghiệp "
                    f"cách {what['km']} km ({what['name']}) — độ dốc {slope}°, "
                    f"mưa dự báo 7 ngày tới {rain} mm")
            if lvl == "danger":
                rec = ("Dốc lớn + mưa dồn + đất đã bị xáo trộn: đây đúng là tổ "
                       "hợp gây trượt bãi thải. Dừng hoạt động trên mái dốc, "
                       "kiểm tra rãnh thoát nước đỉnh tầng và di dời lán trại "
                       "khỏi chân mái.")
            elif lvl == "warning":
                rec = ("Theo dõi mái dốc và rãnh thoát nước trong đợt mưa này. "
                       "Ghi nhận vết nứt mới ở đỉnh tầng nếu có.")
            else:
                rec = "Điều kiện hiện tại chưa đến ngưỡng cảnh báo mái dốc."

        detail = (f"Độ dốc {'THẬT ' if slope_real else 'ước lượng '}{slope}° · "
                  f"nền {elev} m · {len(sites)} khu khai thác/công nghiệp trong "
                  f"15 km theo OSM. ")
        if bare is not None:
            detail += (f"Ảnh Sentinel: thảm thực vật đổi {bare['delta']:+.3f} so "
                       f"cùng kỳ năm trước ({bare['verdict']}). ")
        else:
            detail += ("Chưa ghép được ảnh Sentinel nên chưa biết diện đất trần "
                       "có đang mở rộng hay không. ")
        detail += ("OSM chỉ có những mỏ đã được cộng đồng vẽ; mỏ nhỏ và công "
                   "trường tạm thường chưa có trên bản đồ.")

        metrics = {"do_doc_deg": slope, "mua_7ngay_mm": rain,
                   "cao_do_m": elev, "so_khu_khai_thac_15km": float(len(sites))}
        if nearest_km is not None:
            metrics["khu_gan_nhat_km"] = nearest_km
        if bare is not None:
            metrics["thay_doi_tham_thuc_vat"] = bare["delta"]

        return Assessment(
            module_id=self.id, module_name=self.name, location=loc, status="ok",
            risk_level=lvl, headline=head, score=round(score, 1), detail=detail,
            recommendation=rec, confidence=0.6, confidence_low=0.48,
            confidence_high=0.7, is_real=True, metrics=metrics,
            data_sources=["OpenStreetMap: mỏ & khu công nghiệp",
                          "DEM: độ dốc 4 hướng", "Open-Meteo: mưa dự báo 7 ngày tới"]
            + (["Sentinel-2: biến động thảm thực vật"] if bare else []))


# ---------------------------------------------------------------- SUP-12

class SupplyChainModule(TwinModule):
    """Rủi ro NGUỒN CUNG của cả vùng nguyên liệu, không phải của một thửa.

    Nhà máy, hợp tác xã và thương lái không quan tâm một mảnh ruộng — họ quan
    tâm "vụ này vùng thu mua của tôi có gãy không". Câu đó trả lời được bằng
    cách chạy chính mô hình hiểm họa đã có trên MỘT LƯỚI điểm phủ bán kính thu
    mua, rồi đếm bao nhiêu phần diện tích đang ở mức cảnh báo.

    Kèm theo là HỒ SƠ TRUY XUẤT: điều kiện môi trường thật trong cả vụ tại đúng
    toạ độ đó, có mã băm để bên mua kiểm được hồ sơ chưa bị sửa. Đây là thứ nhà
    nhập khẩu và kiểm toán ESG hỏi, và là thứ dữ liệu ERA5 trả lời được ngay.
    """

    id = "supply_chain"; name = "Rủi ro vùng nguyên liệu"; group = "D"; icon = "🔗"
    status = "active"
    # Nặng: 25 điểm × 2 hiểm họa, mỗi điểm cần khí hậu nền 10 năm riêng để hiệu
    # chuẩn. Chạy song song rồi vẫn ~10 giây lượt đầu, nên không nhét vào lượt
    # quét toàn cảnh.
    heavy = True
    data_sources = ["Open-Meteo: dự báo 7 ngày trên lưới vùng thu mua",
                    "Open-Meteo ERA5: lịch sử cả vụ cho hồ sơ truy xuất",
                    "OpenStreetMap: đường trục & chợ đầu mối"]
    users = ["Nhà máy chế biến", "Hợp tác xã", "Thương lái", "DN xuất khẩu"]
    description = "Bao nhiêu phần vùng thu mua đang gặp rủi ro, và hồ sơ truy xuất nguồn gốc."

    RADIUS_KM = 25.0
    SIDE = 5              # lưới 5×5 = 25 điểm, một lượt gọi Open-Meteo

    def assess(self, loc: Location) -> Assessment:
        from app.services import hazard

        # Lưới phủ bán kính thu mua.
        dlat = self.RADIUS_KM / 111.0
        dlon = self.RADIUS_KM / (111.0 * max(0.2, math.cos(math.radians(loc.lat))))
        half = (self.SIDE - 1) / 2.0
        pts = [(round(loc.lat + (r - half) / half * dlat, 4),
                round(loc.lon + (c - half) / half * dlon, 4))
               for r in range(self.SIDE) for c in range(self.SIDE)]

        from app.services import realdata
        weather = realdata.weather_multi(pts)
        if not any(weather):
            return need_data_assessment(
                self, loc,
                needs="dự báo thời tiết cho lưới vùng thu mua",
                will_do="đếm bao nhiêu phần vùng nguyên liệu đang ở mức cảnh báo",
                next_step="Nguồn thời tiết đang không phản hồi. Thử lại sau ít phút.")

        # Chạy hai hiểm họa nặng nhất với nông sản trên từng điểm của lưới.
        #
        # PHẢI chạy song song: mỗi điểm cần khí hậu nền 10 năm của CHÍNH nó để
        # hiệu chuẩn, tức một lượt gọi ERA5 riêng. 25 điểm × 2 hiểm họa = 50
        # lượt. Nối tiếp mất hơn 100 giây — không ai chờ ngần ấy để xem một
        # bảng, và Render sẽ cắt kết nối trước khi xong.
        from app.services import jobs

        work = [(la, lo, rows, mid)
                for (la, lo), rows in zip(pts, weather) if rows
                for mid in ("flood", "drought")]

        def _task(la, lo, rows, mid):
            def run():
                series, _ = hazard.index_series_calibrated(mid, la, lo, rows)
                return bool(series
                            and max(v for _, _, v in series) >= hazard.SAFE)
            return run

        flags = jobs.gather([_task(*w) for w in work])

        at_risk = {"flood": 0, "drought": 0}
        counted = sum(1 for rows in weather if rows)
        for (_, _, _, mid), hit in zip(work, flags):
            if hit:
                at_risk[mid] += 1

        if counted == 0:
            return need_data_assessment(
                self, loc, needs="dữ liệu thời tiết cho vùng thu mua",
                will_do="đo tỉ lệ diện tích vùng nguyên liệu đang gặp rủi ro",
                next_step="Thử lại sau ít phút.")

        worst_id, worst_n = max(at_risk.items(), key=lambda kv: kv[1])
        pct = round(100.0 * worst_n / counted, 1)
        names = {"flood": "lũ/ngập", "drought": "hạn"}

        lvl = "danger" if pct >= 50 else "warning" if pct >= 20 else "safe"

        # Đường trục gần nhất — logistics là nửa còn lại của chuỗi cung ứng.
        road = osm.nearest(loc.lat, loc.lon,
                           '["highway"~"^(motorway|trunk|primary)$"]',
                           radius_m=30_000.0, limit=1)
        road_km = road[0]["km"] if road else None

        head = (f"{pct}% vùng thu mua bán kính {self.RADIUS_KM:.0f} km đang ở mức "
                f"cảnh báo {names[worst_id]}"
                if pct > 0 else
                f"Cả {counted} điểm trong vùng thu mua đều an toàn 7 ngày tới")

        if lvl == "danger":
            rec = (f"Quá nửa vùng nguyên liệu gặp {names[worst_id]}. Cân nhắc "
                   "chốt hợp đồng nguồn thay thế ngoài vùng, giãn lịch giao và "
                   "báo trước cho khách hàng cuối — báo sớm rẻ hơn bồi thường muộn.")
        elif lvl == "warning":
            rec = (f"Một phần vùng nguyên liệu đang gặp {names[worst_id]}. Theo "
                   "dõi sát các hộ ở vùng trũng/khô nhất và chuẩn bị phương án "
                   "thu mua bù.")
        else:
            rec = "Nguồn cung 7 ngày tới chưa thấy rủi ro thời tiết đáng kể."

        metrics = {
            "diem_kiem_tra": float(counted),
            "ban_kinh_km": self.RADIUS_KM,
            "ty_le_rui_ro_pct": pct,
            "diem_canh_bao_lu": float(at_risk["flood"]),
            "diem_canh_bao_han": float(at_risk["drought"]),
        }
        if road_km is not None:
            metrics["duong_truc_gan_nhat_km"] = road_km

        detail = (f"Chạy mô hình hiểm họa trên lưới {self.SIDE}×{self.SIDE} phủ "
                  f"bán kính {self.RADIUS_KM:.0f} km ({counted} điểm có dữ liệu). "
                  f"Lũ: {at_risk['flood']}/{counted} điểm · hạn: "
                  f"{at_risk['drought']}/{counted} điểm.")
        if road_km is not None:
            detail += f" Đường trục gần nhất cách {road_km} km."
        detail += (" Đây là rủi ro THỜI TIẾT của vùng nguyên liệu, chưa tính giá "
                   "thị trường, hợp đồng hay năng lực kho vận — những thứ phần "
                   "mềm không có dữ liệu.")

        return Assessment(
            module_id=self.id, module_name=self.name, location=loc, status="ok",
            risk_level=lvl, headline=head, score=pct, detail=detail,
            recommendation=rec, confidence=0.66, confidence_low=0.55,
            confidence_high=0.75, is_real=True, metrics=metrics,
            data_sources=["Open-Meteo: dự báo 7 ngày trên lưới vùng thu mua"]
            + (["OpenStreetMap: đường trục"] if road_km is not None else []))


def provenance(loc: Location, start: str, end: str,
               product: str = "", grower: str = "") -> dict:
    """Hồ sơ truy xuất: điều kiện môi trường THẬT suốt vụ tại đúng toạ độ này.

    Nhà nhập khẩu và kiểm toán ESG hỏi "lô hàng này lớn lên trong điều kiện
    nào" — câu đó ERA5 trả lời được cho bất kỳ toạ độ nào ở Việt Nam, từ 1940
    tới nay. Kèm mã băm để bên mua kiểm hồ sơ chưa bị sửa sau khi lập.

    KHÔNG chứng minh nông sản thật sự đến từ đây — đó là việc của chuỗi ký gửi
    vật lý. Nó chứng minh: NẾU đến từ toạ độ này trong khoảng thời gian này thì
    điều kiện môi trường đúng là như thế này.
    """
    import hashlib
    import json
    from datetime import datetime, timezone

    from app.services import realdata

    try:
        d0 = date.fromisoformat(start)
        d1 = date.fromisoformat(end)
    except ValueError:
        return {"available": False,
                "message": "Ngày phải theo dạng YYYY-MM-DD."}
    if d1 <= d0:
        return {"available": False, "message": "Ngày kết thúc phải sau ngày bắt đầu."}
    if (d1 - d0).days > 400:
        return {"available": False,
                "message": "Khoảng thời gian tối đa 400 ngày cho một vụ."}
    if d1 >= date.today() - timedelta(days=6):
        return {"available": False,
                "message": ("ERA5 công bố chậm khoảng 5–7 ngày. Chọn ngày kết "
                            "thúc cách hôm nay ít nhất một tuần.")}

    rows = realdata.historical_weather_multi([(loc.lat, loc.lon)], start, end)
    series = rows[0] if rows else None
    if not series:
        return {"available": False,
                "message": "Chưa lấy được dữ liệu lịch sử cho toạ độ này."}

    rain = [r["precip"] for r in series if r.get("precip") is not None]
    tmax = [r["tmax"] for r in series if r.get("tmax") is not None]
    et0 = [r["et0"] for r in series if r.get("et0") is not None]

    measured = {
        "location": {"lat": loc.lat, "lon": loc.lon},
        "period": {"from": start, "to": end, "days": len(series)},
        "rain_total_mm": round(sum(rain), 1) if rain else None,
        "rain_max_day_mm": round(max(rain), 1) if rain else None,
        "dry_days": sum(1 for v in rain if v < 1.0) if rain else None,
        "tmax_mean_c": round(sum(tmax) / len(tmax), 1) if tmax else None,
        "tmax_peak_c": round(max(tmax), 1) if tmax else None,
        "et0_total_mm": round(sum(et0), 1) if et0 else None,
        "source": "Open-Meteo Archive (ERA5, ECMWF)",
    }

    context = {
        "elevation_m": ds.elevation_proxy(loc.lat, loc.lon),
        "coast_km": round(ds.distance_to_coast_km(loc.lat, loc.lon), 1),
        "salinity_zone": ds.salinity_zone(loc.lat, loc.lon),
    }

    payload = json.dumps({"measured": measured, "context": context,
                          "product": product, "grower": grower},
                         sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    return {
        "available": True,
        "product": product or "(chưa ghi tên sản phẩm)",
        "grower": grower or "(chưa ghi tên người trồng)",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "measured": measured,
        "context": context,
        "headline": (
            f"Vụ {start} → {end} tại {loc.lat:.4f}, {loc.lon:.4f}: mưa "
            f"{measured['rain_total_mm']} mm trong {measured['period']['days']} "
            f"ngày, {measured['dry_days']} ngày khô, nhiệt tối đa trung bình "
            f"{measured['tmax_mean_c']}°C."),
        "integrity": {
            "algorithm": "SHA-256", "hash": digest, "short": digest[:16],
            "note": ("Băm trên đúng bộ số liệu ở trên. Bên mua băm lại và so — "
                     "khác một con số là mã băm khác."),
        },
        "scope": (
            "Hồ sơ này chứng minh ĐIỀU KIỆN MÔI TRƯỜNG tại toạ độ và khoảng thời "
            "gian đã nêu, lấy từ ERA5 — ai cũng tra lại được từ nguồn gốc. Nó "
            "KHÔNG chứng minh lô hàng thật sự đến từ đây; việc đó thuộc về chuỗi "
            "ký gửi vật lý và giấy tờ, phần mềm không thay thế được."),
    }
