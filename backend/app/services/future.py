"""S10 ③ — Ảnh 'TƯƠNG LAI' theo kịch bản. Bản TRUNG THỰC, KHÔNG cần model sinh.

Ghép hai thứ đã có: ẢNH VỆ TINH THẬT của thửa (imagery.plot_view, có ngày chụp)
và KỊCH BẢN từ C02 Parallel Futures (whatif). Nền là ảnh thật; lớp phủ là dự
phóng, vẽ như một lớp RIÊNG có nhãn + mức tin cậy — không hoà vào điểm ảnh.

HAI HÀNG RÀO (đúng điều kiện đặc tả gốc tự đặt ra):
  1. Nền LUÔN là ảnh vệ tinh thật có ngày chụp; lớp phủ không bao giờ trộn vào
     pixel — frontend vẽ nó như overlay trong suốt.
  2. Nhãn 'DỰ PHÓNG' + mức tin cậy hiện NGAY trên ảnh, không giấu ở chú thích.

KHÔNG có điểm ảnh nào do model tưởng tượng: nền là quan sát thật, lớp phủ là con
số dự phóng từ mô hình đã hiệu chuẩn + backtest — thứ người xem phân biệt được.
"""
from __future__ import annotations

from app.schemas import Location
from app.services import hazard, imagery, whatif

# (màu lớp phủ, nhãn lớp) theo từng hiểm họa thời tiết.
_OVERLAY = {
    "flood": ("#2E6BB0", "Vùng ngập dự phóng"),
    "drought": ("#C08A2E", "Mức khô hạn dự phóng"),
    "wildfire": ("#C2412E", "Nguy cơ cháy dự phóng"),
    "landslide": ("#8A5A2B", "Nguy cơ sạt lở dự phóng"),
}

_RISK_VI = {"safe": "an toàn", "warning": "cảnh báo", "danger": "nguy hiểm"}


def _risk_of(peak: float, safe: float, warning: float) -> str:
    if peak >= warning:
        return "danger"
    if peak >= safe:
        return "warning"
    return "safe"


def build(module_id: str, lat: float, lon: float) -> dict:
    """Ảnh tương lai cho 1 thửa + 1 hiểm họa thời tiết. Luôn trả dict."""
    if not hazard.supports(module_id):
        return {"available": False, "reason": "unsupported",
                "message": ("Ảnh tương lai chỉ áp dụng cho hiểm họa thời tiết: "
                            + ", ".join(hazard.IDS) + ".")}

    loc = Location(lat=lat, lon=lon)
    wi = whatif.run(module_id, loc)
    if wi is None:
        return {"available": False, "reason": "unsupported",
                "message": "Module không hỗ trợ kịch bản."}

    color, layer_label = _OVERLAY.get(module_id, ("#2E6BB0", "Vùng dự phóng"))

    scenarios = []
    for s in wi.scenarios:
        risk = _risk_of(s.peak, wi.safe, wi.warning)
        intensity = round(min(1.0, s.peak / 100.0), 3)
        # Độ mờ lớp phủ: đủ để thấy mức độ, đủ trong để vẫn nhìn xuyên tới ảnh
        # thật bên dưới (hàng rào 1 — không che mất quan sát).
        opacity = round(0.12 + 0.48 * intensity, 2)
        danger_txt = (f" · vượt ngưỡng từ {s.first_danger_date[5:]}"
                      if s.first_danger_date else "")
        scenarios.append({
            "label": s.label,
            "rain_mult": s.rain_mult,
            "temp_delta": s.temp_delta,
            "peak": s.peak,
            "risk": risk,
            "risk_vi": _RISK_VI[risk],
            "first_danger_date": s.first_danger_date,
            "intensity": intensity,
            "opacity": opacity,
            "caption": (f"Kịch bản '{s.label}': chỉ số đỉnh {s.peak}"
                        f"{'%' if wi.unit == '%' else ' điểm'} — {_RISK_VI[risk]}"
                        f"{danger_txt}."),
        })

    # Ảnh nền thật (có thể bị mây che → available=False, khi đó vẫn trả kịch bản
    # dạng chữ + nói rõ vì sao chưa có ảnh).
    img = imagery.plot_view(lat, lon)
    confidence = 0.75 if wi.is_real else 0.55

    out = {
        "available": True,
        "module_id": module_id,
        "module_name": wi.module_name,
        "unit": wi.unit,
        "safe": wi.safe,
        "warning": wi.warning,
        "is_real": wi.is_real,
        "confidence": confidence,
        "confidence_low": round(max(0.0, confidence - 0.1), 2),
        "confidence_high": round(min(1.0, confidence + 0.1), 2),
        "overlay_color": color,
        "layer_label": layer_label,
        "scenarios": scenarios,
        "is_projection": True,
        "disclaimer": (
            "DỰ PHÓNG, KHÔNG phải ảnh chụp tương lai. Nền là ảnh vệ tinh THẬT; "
            "lớp phủ màu là kết quả mô phỏng kịch bản (đã hiệu chuẩn + backtest), "
            "vẽ tách khỏi ảnh để bạn luôn phân biệt được quan sát với dự đoán."),
        "note": wi.note,
    }

    if img.get("available"):
        out["base_image"] = {
            "true_color": img["now"]["true_color"],
            "date": img["now"]["date"],
            "cloud_scene_pct": img["now"].get("cloud_scene_pct"),
        }
        out["span_m"] = img.get("span_m")
        out["resolution_m"] = img.get("resolution_m")
        out["source"] = img.get("source")
    else:
        out["base_image"] = None
        out["base_message"] = img.get(
            "message", "Chưa có ảnh quang mây cho thửa này.")
        out["source"] = ("Sentinel-2 L2A · Microsoft Planetary Computer "
                         "(không cần khoá)")

    return out
