"""S07 — Causal Explain (XAI): VÌ SAO chỉ số lại cao?

Mô hình chỉ số của TerraTwin là HÀM THUẦN, nên không cần xấp xỉ kiểu SHAP:
ta tắt từng yếu tố rồi chạy lại đúng mô hình đó → phần chênh lệch CHÍNH LÀ
đóng góp thật của yếu tố ấy (leave-one-out chính xác, không phải ước lượng).

Trả về: đóng góp từng yếu tố + ngày mưa nào đẩy đỉnh lên cao nhất.
"""
from __future__ import annotations

from app.services import hazard
from app.services import realdata

# Cách "tắt" từng yếu tố cho mỗi module.
#   key  : tên yếu tố hiển thị
#   off  : hàm biến đổi rows để loại bỏ yếu tố đó
#   note : giải thích cho người dùng
_NO_RAIN = lambda r: {**r, "precip": 0.0}
_RAIN_MEETS_ET0 = lambda r: {**r, "precip": r["et0"]}   # mưa vừa đủ bù bốc hơi
_NO_ET0 = lambda r: {**r, "et0": 0.0}
_MILD_HEAT = lambda r: {**r, "tmax": min(r["tmax"], 30.0)}

_FACTORS = {
    "flood": [
        ("Lượng mưa dự báo", _NO_RAIN,
         "Nếu 7 ngày tới không mưa, chỉ số ngập còn lại là phần do địa hình."),
    ],
    "landslide": [
        ("Mưa tích lũy", _NO_RAIN,
         "Sạt lở cần nước làm bão hòa đất — bỏ mưa thì chỉ còn nền địa hình."),
    ],
    "drought": [
        ("Thiếu mưa", _RAIN_MEETS_ET0,
         "Nếu mưa đủ bù lượng bốc thoát hơi ET₀ thì không tích lũy thiếu ẩm."),
        ("Bốc thoát hơi ET₀", _NO_ET0,
         "ET₀ cao (nắng, gió, khô) rút ẩm khỏi ruộng nhanh hơn."),
    ],
    "wildfire": [
        ("Chuỗi ngày khô", _NO_RAIN,
         "Không mưa liên tiếp làm vật liệu cháy khô dần."),
        ("Nhiệt độ cao", _MILD_HEAT,
         "Phần nhiệt vượt 30°C cộng thẳng vào chỉ số nguy cơ cháy."),
    ],
}

# Yếu tố địa hình: tắt bằng cách thay giá trị địa hình sang mức "vô hại".
_TERRAIN = {
    "flood": ("Địa hình trũng", 60.0,
              "Nền càng thấp càng dễ đọng nước; giả sử nền cao 60 m thì hết yếu tố này."),
    "landslide": ("Độ dốc sườn", 0.0,
                  "Sạt lở nhân với độ dốc — địa hình phẳng thì rủi ro ~0 dù mưa lớn."),
}


def _terrain_off_series(module_id: str, rows, neutral: float):
    """Chạy lại mô hình với giá trị địa hình 'vô hại'."""
    from app.services import datasources as ds
    if module_id == "flood":
        return ds.flood_index(rows, neutral)
    if module_id == "landslide":
        return ds.landslide_index(rows, neutral)
    return []


def explain(module_id: str, lat: float, lon: float) -> dict | None:
    if not hazard.supports(module_id):
        return None
    name, unit = hazard.name_unit(module_id)

    rows = realdata.weather_7d(lat, lon)
    is_real = rows is not None
    if not rows:
        return {
            "module_id": module_id, "module_name": name, "unit": unit,
            "is_real": False, "available": False,
            "message": "Chưa lấy được dữ liệu thời tiết thật để giải thích "
                       "(kiểm tra kết nối). Không giải thích trên số liệu mẫu.",
            "factors": [], "peak": 0.0,
        }

    base_series = hazard.index_series(module_id, lat, lon, rows)
    base_peak = hazard.peak_of(base_series)
    _, terrain_note = hazard.terrain(module_id, lat, lon)

    factors: list[dict] = []

    # 1) Yếu tố thời tiết
    for label, off, note in _FACTORS.get(module_id, []):
        without = hazard.index_series(module_id, lat, lon, [off(r) for r in rows])
        peak_wo = hazard.peak_of(without)
        factors.append({
            "factor": label,
            "peak_without": round(peak_wo, 1),
            "contribution": round(base_peak - peak_wo, 1),
            "note": note,
        })

    # 2) Yếu tố địa hình (chỉ lũ & sạt lở)
    if module_id in _TERRAIN:
        label, neutral, note = _TERRAIN[module_id]
        peak_wo = hazard.peak_of(_terrain_off_series(module_id, rows, neutral))
        factors.append({
            "factor": label,
            "peak_without": round(peak_wo, 1),
            "contribution": round(base_peak - peak_wo, 1),
            "note": note,
        })

    # % đóng góp, chuẩn hóa trên tổng phần giải thích được (bỏ đóng góp âm)
    total = sum(f["contribution"] for f in factors if f["contribution"] > 0)
    for f in factors:
        f["share_pct"] = (round(100.0 * f["contribution"] / total, 1)
                          if total > 0 and f["contribution"] > 0 else 0.0)
    factors.sort(key=lambda f: f["contribution"], reverse=True)

    # 3) Ngày mưa nào nặng nhất trong cửa sổ
    wettest = max(rows, key=lambda r: r["precip"])
    peak_day = max(base_series, key=lambda s: s[2]) if base_series else None

    top = factors[0]["factor"] if factors and factors[0]["contribution"] > 0 else None
    if top:
        headline = (f"Chỉ số đỉnh {round(base_peak,1)} {unit} — chủ yếu do "
                    f"{top.lower()} ({factors[0]['share_pct']}%).")
    else:
        headline = f"Chỉ số đỉnh {round(base_peak,1)} {unit} — không có yếu tố nào nổi trội."

    return {
        "module_id": module_id, "module_name": name, "unit": unit,
        "is_real": is_real, "available": True,
        "peak": round(base_peak, 1),
        "peak_date": peak_day[1] if peak_day else None,
        "terrain": terrain_note,
        "headline": headline,
        "factors": factors,
        "wettest_day": {"date": wettest["date"], "precip_mm": round(wettest["precip"], 1)},
        "method": ("Leave-one-out CHÍNH XÁC: tắt từng yếu tố rồi chạy lại đúng mô "
                   "hình cảnh báo. Không phải xấp xỉ, không phải hộp đen."),
    }
