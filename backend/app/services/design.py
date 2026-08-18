"""U03 — Generative Design Studio: sinh phương án canh tác cụ thể cho thửa đất.

Bản trong tầm nhìn dùng model sinh ảnh/thiết kế. Nhưng thứ nông dân cần không
phải ảnh render đẹp — mà là phương án nói rõ: TRỒNG GÌ, MÙA NÀO, LÀM GÌ TRƯỚC.
Cái đó sinh được từ dữ liệu đã có, và mỗi khuyến nghị truy được về đúng con số
đã dẫn tới nó.

Đây là "generative" theo nghĩa TỔNG HỢP phương án mới từ ràng buộc, không phải
theo nghĩa mô hình sinh. Kết quả ghi rõ điều đó, không để người đọc ngộ nhận.

CƠ SỞ NGƯỠNG (tổng hợp từ tài liệu nông học phổ thông, không phải bịa):
  Lúa      chịu mặn kém (<1 g/L), cần nhiều nước, nền phẳng
  Tôm      nước lợ, cần ao ven biển, nhiệt 28-32°C
  Dừa      chịu mặn tới ~4 g/L, chịu ngập nhẹ theo triều
  Xoài/mít chịu hạn khá nhưng RẤT kém chịu ngập úng
  Cà phê   cần cao độ >500 m, mát, mưa 1500-2500 mm
  Rừng     giữ đất trên sườn dốc >=15°
Ngưỡng mang tính định hướng — phải đối chiếu khuyến cáo Sở NN&PTNT địa phương.
"""
from __future__ import annotations

from app.schemas import Location

_NAMES = {
    "rice": ("Lúa nước", "🌾"),
    "shrimp": ("Tôm nước lợ", "🦐"),
    "rice_shrimp": ("Luân canh lúa – tôm", "🌾"),
    "coconut": ("Dừa", "🥥"),
    "fruit": ("Cây ăn trái (xoài, mít)", "🥭"),
    "coffee": ("Cà phê", "☕"),
    "forest": ("Rừng phòng hộ / keo", "🌲"),
}


def _score_crops(elev, slope, sal, coast, rain, tmax) -> list[dict]:
    """Chấm điểm từng lựa chọn. Mỗi điểm cộng/trừ đều kèm lý do tra được."""
    out: list[dict] = []

    def add(code, score, reasons, warnings):
        name, icon = _NAMES[code]
        out.append({"code": code, "name": name, "icon": icon,
                    "score": max(0, min(100, round(score))),
                    "reasons": reasons, "warnings": warnings})

    # Lúa nước
    s, r, w = 70, [], []
    if slope > 5:
        s -= 40
        w.append(f"Độ dốc {slope}° quá lớn để làm ruộng nước.")
    else:
        r.append(f"Nền phẳng ({slope}°) phù hợp ruộng nước.")
    if sal is not None:
        if sal >= 4.0:
            s -= 45
            w.append(f"Mặn đỉnh {sal} g/L vượt xa ngưỡng lúa (1 g/L).")
        elif sal >= 1.0:
            s -= 20
            w.append(f"Mặn đỉnh {sal} g/L trên ngưỡng an toàn của lúa.")
        else:
            r.append(f"Mặn đỉnh chỉ {sal} g/L, dưới ngưỡng lúa.")
    if rain and rain < 1200:
        s -= 15
        w.append(f"Mưa {rain} mm/năm hơi ít cho lúa, cần chủ động tưới.")
    add("rice", s, r, w)

    # Tôm nước lợ
    s, r, w = 40, [], []
    if coast <= 25 and elev <= 5:
        s += 35
        r.append(f"Cách biển {coast} km, nền {elev} m — thuận lấy nước lợ.")
    else:
        s -= 25
        w.append(f"Cách biển {coast} km, nền {elev} m — khó lấy nước lợ.")
    if sal is not None and sal >= 4.0:
        s += 20
        r.append(f"Mặn đỉnh {sal} g/L là điều kiện tôm CẦN, không phải trở ngại.")
    if tmax and tmax > 33:
        s -= 10
        w.append(f"Nhiệt tối đa {tmax}°C dễ gây stress nhiệt cho tôm.")
    add("shrimp", s, r, w)

    # Luân canh lúa - tôm
    s, r, w = 45, [], []
    if sal is not None and 1.0 <= sal < 8.0 and elev <= 5 and slope <= 3:
        s += 40
        r.append(f"Mặn theo mùa (đỉnh {sal} g/L) — mùa mưa cấy lúa, mùa khô nuôi tôm.")
        r.append("Mô hình nhiều hộ ĐBSCL đã áp dụng ở điều kiện tương tự.")
    else:
        s -= 20
        w.append("Mặn không dao động theo mùa rõ rệt nên luân canh ít lợi thế.")
    add("rice_shrimp", s, r, w)

    # Dừa
    s, r, w = 55, [], []
    if sal is not None and sal <= 4.5:
        s += 20
        r.append(f"Dừa chịu mặn tới ~4 g/L; đỉnh ở đây {sal} g/L.")
    elif sal is not None:
        s -= 15
        w.append(f"Mặn đỉnh {sal} g/L cao cả với dừa.")
    if elev <= 8:
        r.append("Chịu được ngập nhẹ theo triều.")
    if slope > 12:
        s -= 20
        w.append(f"Độ dốc {slope}° không thuận cho dừa.")
    add("coconut", s, r, w)

    # Cây ăn trái
    s, r, w = 60, [], []
    if elev < 3:
        s -= 35
        w.append(f"Nền chỉ {elev} m — xoài/mít rất kém chịu ngập úng.")
    else:
        r.append(f"Nền {elev} m đủ cao để thoát nước cho cây ăn trái.")
    if sal is not None and sal >= 2.0:
        s -= 25
        w.append(f"Mặn đỉnh {sal} g/L gây hại rễ cây ăn trái.")
    if 3 <= slope <= 15:
        s += 10
        r.append(f"Độ dốc {slope}° giúp thoát nước tự nhiên.")
    add("fruit", s, r, w)

    # Cà phê
    s, r, w = 25, [], []
    if elev >= 500:
        s += 45
        r.append(f"Cao độ {elev} m nằm trong dải cà phê cần (>500 m).")
    else:
        s -= 20
        w.append(f"Cao độ {elev} m quá thấp cho cà phê.")
    if rain and 1500 <= rain <= 2500:
        s += 15
        r.append(f"Mưa {rain} mm/năm nằm đúng dải cà phê ưa.")
    if tmax and tmax > 32:
        s -= 15
        w.append(f"Nhiệt tối đa {tmax}°C cao so với cà phê.")
    add("coffee", s, r, w)

    # Rừng
    s, r, w = 30, [], []
    if slope >= 15:
        s += 50
        r.append(f"Độ dốc {slope}° — trồng rừng là cách giữ đất hiệu quả nhất.")
    if sal is not None and sal >= 8.0:
        s += 15
        r.append("Mặn quá cao cho cây trồng thường; rừng ngập mặn là lựa chọn đúng.")
    if not r:
        w.append(f"Đất phẳng ({slope}°) và không quá mặn — trồng rừng ở đây "
                 "phí tiềm năng canh tác, trừ khi bạn chủ đích làm phòng hộ.")
    add("forest", s, r, w)

    # Chấm điểm mà không nói vì sao thì người dùng không kiểm chứng được —
    # đúng thứ dự án này đã mất nhiều đợt để loại bỏ.
    for c in out:
        if not c["reasons"] and not c["warnings"]:
            c["reasons"].append(
                "Không có yếu tố nào ở thửa này đặc biệt thuận hay cản trở lựa "
                "chọn này; điểm số là mức nền.")
    out.sort(key=lambda c: c["score"], reverse=True)
    return out


def _infrastructure(elev, slope, sal, flood_risk, coast) -> list[dict]:
    """Việc cần làm với đất, xếp theo mức ưu tiên."""
    items = []
    if flood_risk in ("warning", "danger"):
        items.append({"priority": "cao", "item": "Tôn nền hoặc đắp bờ bao",
                      "why": f"Module Lũ đang ở mức {flood_risk}; nền hiện {elev} m."})
        items.append({"priority": "cao", "item": "Kênh hoặc mương thoát nước",
                      "why": "Nước rút nhanh giảm thời gian ngập — thứ quyết định mất mùa."})
    if sal is not None and sal >= 1.0:
        items.append({"priority": "cao", "item": "Cống ngăn mặn đóng chủ động được",
                      "why": f"Mặn đỉnh {sal} g/L vượt ngưỡng lúa."})
        items.append({"priority": "trung bình", "item": "Ao hoặc bể trữ nước ngọt",
                      "why": "Trữ trước mùa khô để không phải lấy nước sông lúc mặn lên."})
    if slope >= 15:
        items.append({"priority": "cao", "item": "Ruộng bậc thang hoặc băng chắn",
                      "why": f"Độ dốc {slope}° gây xói mòn và nguy cơ sạt lở."})
    if coast <= 5:
        items.append({"priority": "trung bình", "item": "Băng cây chắn gió mặn",
                      "why": f"Cách biển chỉ {coast} km — gió mang hơi mặn hại lá."})
    if not items:
        items.append({"priority": "thấp", "item": "Chưa cần hạ tầng đặc biệt",
                      "why": "Các chỉ số hiện tại đều trong ngưỡng an toàn."})
    return items


def generate(loc: Location) -> dict:
    """Sinh phương án canh tác từ Twin của thửa đất."""
    from app.modules.registry import get_module
    from app.services import datasources as ds

    elev = ds.elevation_proxy(loc.lat, loc.lon)
    slope, _ = ds.slope_context(loc.lat, loc.lon)
    coast = ds.distance_to_coast_km(loc.lat, loc.lon)
    zone = ds.salinity_zone(loc.lat, loc.lon)

    sal_a = get_module("salinity").assess(loc)
    sal = max((f.value for f in sal_a.forecast), default=None) if sal_a.forecast else None
    flood = get_module("flood").assess(loc)
    drought = get_module("drought").assess(loc)

    gen = None
    try:
        from app.services import genome
        gen = genome.genome_of(loc.lat, loc.lon)
    except Exception:
        pass
    rain = gen["rain_annual"] if gen else None
    tmax = gen["tmax_mean"] if gen else None

    crops = _score_crops(elev, slope, sal, coast, rain, tmax)
    infra = _infrastructure(elev, slope, sal, flood.risk_level, coast)
    best = crops[0]

    return {
        "location": loc.model_dump(),
        "site": {
            "elevation_m": elev, "slope_deg": slope, "coast_km": coast,
            "salinity_zone": zone, "salinity_peak_gl": sal,
            "rain_annual_mm": rain, "tmax_mean_c": tmax,
            "flood_risk": flood.risk_level, "drought_risk": drought.risk_level,
        },
        "recommended": best,
        "options": crops,
        "infrastructure": infra,
        "headline": (f"Phù hợp nhất: {best['icon']} {best['name']} "
                     f"({best['score']}/100)."
                     + (" " + best["reasons"][0] if best["reasons"] else "")),
        "generative_note": (
            "Chữ 'generative' ở đây nghĩa là TỔNG HỢP phương án mới từ ràng buộc "
            "đo được, không phải model sinh ảnh. Mỗi điểm cộng/trừ đều kèm lý do "
            "truy được về đúng con số đã dẫn tới nó."),
        "caveat": (
            "Ngưỡng cây trồng mang tính ĐỊNH HƯỚNG, tổng hợp từ tài liệu nông học "
            "phổ thông. Trước khi xuống giống hãy đối chiếu khuyến cáo của Sở "
            "NN&PTNT địa phương và kinh nghiệm hộ lân cận — điều kiện thực tế còn "
            "phụ thuộc chất đất, giống và thị trường mà phần mềm chưa biết."),
    }
