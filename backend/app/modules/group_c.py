"""Nhóm C — chỉ số & thời tiết. Điện mặt trời & bảo hiểm dùng dữ liệu THẬT."""
from __future__ import annotations

from app.modules.base import TwinModule
from app.schemas import Assessment, Location
from app.services import datasources as ds
from app.services.reqlang import tr


class ParametricInsuranceModule(TwinModule):
    id = "parametric_insurance"; name = "Bảo hiểm nông nghiệp tham số"; name_en = "Parametric crop insurance"; group = "C"; icon = "🛡️"; status = "active"
    # "danger" ở đây = ĐÃ KÍCH HOẠT CHI TRẢ, tức tin tốt cho nông dân, và nó
    # suy ra từ chính chỉ số hạn nên module Hạn đã cảnh báo rồi. Đưa vào danh
    # sách cảnh báo là báo hai lần cùng một sự việc.
    threat = False
    data_sources = ["Open-Meteo: chỉ số hạn (mưa & ET₀)"]
    data_sources_en = ["Open-Meteo: drought index (rain & ET₀)"]
    users = ["Nông dân", "Công ty bảo hiểm"]
    description = "Tự chi trả khi hạn/lũ vượt ngưỡng đo bằng vệ tinh."

    def assess(self, loc: Location) -> Assessment:
        s, real = ds.drought_series(loc.lat, loc.lon)  # dùng chỉ số hạn làm trigger
        idx = round(max(v for (_, _, v) in s), 1)
        threshold = 70.0
        triggered = idx >= threshold
        # KHÔNG bịa số tiền chi trả. Trước đây ở đây có một hằng số 5_000_000 viết
        # cứng, không hợp đồng, không phí bảo hiểm, không đơn vị bảo hiểm — mà lại
        # hiện ra như "đã chi trả ~X đồng". Số tiền phụ thuộc hợp đồng thật; chỉ
        # số kích hoạt mới là thứ TerraTwin đo được và trả lời trung thực.
        over = round(idx - threshold, 1) if triggered else 0.0
        lvl = "danger" if triggered else "safe"
        head = (tr(f"Đã đạt ngưỡng kích hoạt (chỉ số hạn {idx} ≥ ngưỡng {threshold:.0f})",
                   f"Payout threshold reached (drought index {idx} ≥ threshold {threshold:.0f})")
                if triggered else tr(f"Chưa kích hoạt (chỉ số hạn {idx} < ngưỡng {threshold:.0f})",
                                     f"Not triggered (drought index {idx} < threshold {threshold:.0f})"))
        rec = (tr("Đủ điều kiện lập hồ sơ chi trả tự động. Số tiền chi trả tuỳ HỢP "
                  "ĐỒNG với đơn vị bảo hiểm — TerraTwin chỉ cung cấp chỉ số kích hoạt, "
                  "không định giá bồi thường.",
                  "Eligible to file an automatic payout claim. The amount depends on "
                  "your CONTRACT with the insurer — TerraTwin only provides the trigger "
                  "index, it doesn't price claims.") if triggered
               else tr("Chưa đạt ngưỡng bồi thường; tiếp tục theo dõi.",
                       "Payout threshold not reached; keep monitoring."))
        detail = (tr("Trigger dựa trên chỉ số hạn THẬT (Open-Meteo).", "Trigger based on REAL drought index (Open-Meteo).") if real
                  else tr("Trigger dựa trên chỉ số hạn (mẫu).", "Trigger based on drought index (sample).")) + \
            tr(" Kích hoạt tự động khi vượt ngưỡng; số tiền do hợp đồng bảo hiểm quy định.",
               " Auto-triggers when the threshold is exceeded; the amount is set by the insurance contract.")
        return Assessment(
            module_id=self.id, module_name=self.disp_name(), location=loc, status="ok",
            risk_level=lvl, headline=head, detail=detail, recommendation=rec,
            confidence=0.75 if real else 0.6, is_real=real,
            metrics={"chi_so": idx, "nguong": threshold, "vuot_nguong": over},
            data_sources=[tr("Open-Meteo (thật)", "Open-Meteo (real)")] if real else self.disp_data_sources())


class SolarModule(TwinModule):
    id = "solar"; name = "Chọn vị trí & dự báo điện mặt trời"; name_en = "Solar siting & output forecast"; group = "C"; icon = "☀️"; status = "active"
    # "danger" = bức xạ trung bình, sản lượng hạn chế. Đó là thông tin đầu tư,
    # tuyệt đối không phải mối đe doạ với mảnh đất.
    threat = False
    data_sources = ["NASA POWER: bức xạ mặt trời"]
    data_sources_en = ["NASA POWER: solar irradiance"]
    users = ["Nhà đầu tư điện mặt trời", "Hộ lắp mái"]
    description = "Bức xạ/che khuất của mái/khu đất → sản lượng dự kiến."

    def assess(self, loc: Location) -> Assessment:
        rad, real = ds.solar_radiation(loc.lat, loc.lon)
        annual = round(rad * 365 * 0.8, 0)
        lvl = "safe" if rad >= 4.8 else "warning" if rad >= 4.3 else "danger"
        quality = (tr("Rất tốt", "Very good") if lvl == "safe"
                   else tr("Khá", "Fair") if lvl == "warning" else tr("Trung bình", "Average"))
        head = tr(f"{quality} — bức xạ ~{rad} kWh/m²/ngày → ~{annual:,.0f} kWh/kWp/năm",
                  f"{quality} — irradiance ~{rad} kWh/m²/day → ~{annual:,.0f} kWh/kWp/yr")
        rec = (tr("Vị trí tốt để lắp điện mặt trời.", "Good location for solar panels.") if lvl == "safe"
               else tr("Chấp nhận được; tối ưu góc lắp & tránh che khuất.", "Acceptable; optimize tilt & avoid shading.") if lvl == "warning"
               else tr("Sản lượng hạn chế; cân nhắc kỹ hiệu quả đầu tư.", "Limited output; weigh the investment carefully."))
        detail = (tr("Bức xạ THẬT từ NASA POWER (climatology).", "REAL irradiance from NASA POWER (climatology).") if real
                  else tr("Bức xạ (mẫu).", "Irradiance (sample).")) + tr(" Hệ số hiệu suất ~0.8.", " Performance ratio ~0.8.")
        return Assessment(
            module_id=self.id, module_name=self.disp_name(), location=loc, status="ok",
            risk_level=lvl, headline=head, detail=detail, recommendation=rec,
            confidence=0.8 if real else 0.6, is_real=real,
            metrics={"buc_xa_kwh_m2_ngay": rad, "san_luong_kwh_kwp_nam": annual},
            data_sources=[tr("NASA POWER (thật)", "NASA POWER (real)")] if real else self.disp_data_sources())
