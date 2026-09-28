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

SONG NGỮ: mọi chuỗi trả ra qua tr(vi, en). `priority` là NHÃN hiển thị (dịch
được); `priority_code` (high/medium/low) là khoá ổn định cho giao diện tô màu —
tách ra vì trước đây giao diện tô màu theo chính chữ "cao"/"thấp", dịch nhãn
là mất màu.
"""
from __future__ import annotations

from app.schemas import Location
from app.services.reqlang import tr

_NAMES = {   # (VI, EN, biểu tượng)
    "rice": ("Lúa nước", "Paddy rice", "🌾"),
    "shrimp": ("Tôm nước lợ", "Brackish-water shrimp", "🦐"),
    "rice_shrimp": ("Luân canh lúa – tôm", "Rice–shrimp rotation", "🌾"),
    "coconut": ("Dừa", "Coconut", "🥥"),
    "fruit": ("Cây ăn trái (xoài, mít)", "Fruit trees (mango, jackfruit)", "🥭"),
    "coffee": ("Cà phê", "Coffee", "☕"),
    "forest": ("Rừng phòng hộ / keo", "Protection forest / acacia", "🌲"),
}

_PRIORITY = {   # mã ổn định → (VI, EN)
    "high": ("cao", "high"),
    "medium": ("trung bình", "medium"),
    "low": ("thấp", "low"),
}


def _score_crops(elev, slope, sal, coast, rain, tmax) -> list[dict]:
    """Chấm điểm từng lựa chọn. Mỗi điểm cộng/trừ đều kèm lý do tra được."""
    out: list[dict] = []

    def add(code, score, reasons, warnings):
        vi, en, icon = _NAMES[code]
        out.append({"code": code, "name": tr(vi, en), "icon": icon,
                    "score": max(0, min(100, round(score))),
                    "reasons": reasons, "warnings": warnings})

    # Lúa nước
    s, r, w = 70, [], []
    if slope > 5:
        s -= 40
        w.append(tr(f"Độ dốc {slope}° quá lớn để làm ruộng nước.",
                    f"A {slope}° slope is too steep for paddy fields."))
    else:
        r.append(tr(f"Nền phẳng ({slope}°) phù hợp ruộng nước.",
                    f"Flat ground ({slope}°) suits paddy fields."))
    if sal is not None:
        if sal >= 4.0:
            s -= 45
            w.append(tr(f"Mặn đỉnh {sal} g/L vượt xa ngưỡng lúa (1 g/L).",
                        f"Peak salinity {sal} g/L is far above rice's limit (1 g/L)."))
        elif sal >= 1.0:
            s -= 20
            w.append(tr(f"Mặn đỉnh {sal} g/L trên ngưỡng an toàn của lúa.",
                        f"Peak salinity {sal} g/L is above rice's safe limit."))
        else:
            r.append(tr(f"Mặn đỉnh chỉ {sal} g/L, dưới ngưỡng lúa.",
                        f"Peak salinity only {sal} g/L, below rice's limit."))
    if rain and rain < 1200:
        s -= 15
        w.append(tr(f"Mưa {rain} mm/năm hơi ít cho lúa, cần chủ động tưới.",
                    f"{rain} mm/year of rain is a bit low for rice; plan irrigation."))
    add("rice", s, r, w)

    # Tôm nước lợ
    s, r, w = 40, [], []
    if coast <= 25 and elev <= 5:
        s += 35
        r.append(tr(f"Cách biển {coast} km, nền {elev} m — thuận lấy nước lợ.",
                    f"{coast} km from the sea, ground at {elev} m — easy access to brackish water."))
    else:
        s -= 25
        w.append(tr(f"Cách biển {coast} km, nền {elev} m — khó lấy nước lợ.",
                    f"{coast} km from the sea, ground at {elev} m — hard to get brackish water."))
    if sal is not None and sal >= 4.0:
        s += 20
        r.append(tr(f"Mặn đỉnh {sal} g/L là điều kiện tôm CẦN, không phải trở ngại.",
                    f"Peak salinity {sal} g/L is what shrimp NEED, not an obstacle."))
    if tmax and tmax > 33:
        s -= 10
        w.append(tr(f"Nhiệt tối đa {tmax}°C dễ gây stress nhiệt cho tôm.",
                    f"A {tmax}°C max temperature easily heat-stresses shrimp."))
    add("shrimp", s, r, w)

    # Luân canh lúa - tôm
    s, r, w = 45, [], []
    if sal is not None and 1.0 <= sal < 8.0 and elev <= 5 and slope <= 3:
        s += 40
        r.append(tr(f"Mặn theo mùa (đỉnh {sal} g/L) — mùa mưa cấy lúa, mùa khô nuôi tôm.",
                    f"Seasonal salinity (peak {sal} g/L) — rice in the wet season, shrimp in the dry season."))
        r.append(tr("Mô hình nhiều hộ ĐBSCL đã áp dụng ở điều kiện tương tự.",
                    "Many Mekong Delta farms use this model under similar conditions."))
    else:
        s -= 20
        w.append(tr("Mặn không dao động theo mùa rõ rệt nên luân canh ít lợi thế.",
                    "Salinity doesn't swing clearly by season, so rotation has little advantage."))
    add("rice_shrimp", s, r, w)

    # Dừa
    s, r, w = 55, [], []
    if sal is not None and sal <= 4.5:
        s += 20
        r.append(tr(f"Dừa chịu mặn tới ~4 g/L; đỉnh ở đây {sal} g/L.",
                    f"Coconut tolerates salinity up to ~4 g/L; the peak here is {sal} g/L."))
    elif sal is not None:
        s -= 15
        w.append(tr(f"Mặn đỉnh {sal} g/L cao cả với dừa.",
                    f"Peak salinity {sal} g/L is high even for coconut."))
    if elev <= 8:
        r.append(tr("Chịu được ngập nhẹ theo triều.", "Tolerates light tidal flooding."))
    if slope > 12:
        s -= 20
        w.append(tr(f"Độ dốc {slope}° không thuận cho dừa.",
                    f"A {slope}° slope is unfavorable for coconut."))
    add("coconut", s, r, w)

    # Cây ăn trái
    s, r, w = 60, [], []
    if elev < 3:
        s -= 35
        w.append(tr(f"Nền chỉ {elev} m — xoài/mít rất kém chịu ngập úng.",
                    f"Ground only {elev} m — mango/jackfruit tolerate waterlogging very poorly."))
    else:
        r.append(tr(f"Nền {elev} m đủ cao để thoát nước cho cây ăn trái.",
                    f"Ground at {elev} m is high enough to drain for fruit trees."))
    if sal is not None and sal >= 2.0:
        s -= 25
        w.append(tr(f"Mặn đỉnh {sal} g/L gây hại rễ cây ăn trái.",
                    f"Peak salinity {sal} g/L damages fruit-tree roots."))
    if 3 <= slope <= 15:
        s += 10
        r.append(tr(f"Độ dốc {slope}° giúp thoát nước tự nhiên.",
                    f"A {slope}° slope helps natural drainage."))
    add("fruit", s, r, w)

    # Cà phê
    s, r, w = 25, [], []
    if elev >= 500:
        s += 45
        r.append(tr(f"Cao độ {elev} m nằm trong dải cà phê cần (>500 m).",
                    f"Elevation {elev} m is within coffee's range (>500 m)."))
    else:
        s -= 20
        w.append(tr(f"Cao độ {elev} m quá thấp cho cà phê.",
                    f"Elevation {elev} m is too low for coffee."))
    if rain and 1500 <= rain <= 2500:
        s += 15
        r.append(tr(f"Mưa {rain} mm/năm nằm đúng dải cà phê ưa.",
                    f"{rain} mm/year of rain is right in coffee's preferred range."))
    if tmax and tmax > 32:
        s -= 15
        w.append(tr(f"Nhiệt tối đa {tmax}°C cao so với cà phê.",
                    f"A {tmax}°C max temperature is high for coffee."))
    add("coffee", s, r, w)

    # Rừng
    s, r, w = 30, [], []
    if slope >= 15:
        s += 50
        r.append(tr(f"Độ dốc {slope}° — trồng rừng là cách giữ đất hiệu quả nhất.",
                    f"A {slope}° slope — planting forest is the most effective way to hold the soil."))
    if sal is not None and sal >= 8.0:
        s += 15
        r.append(tr("Mặn quá cao cho cây trồng thường; rừng ngập mặn là lựa chọn đúng.",
                    "Too salty for ordinary crops; mangrove forest is the right choice."))
    if not r:
        w.append(tr(f"Đất phẳng ({slope}°) và không quá mặn — trồng rừng ở đây "
                    "phí tiềm năng canh tác, trừ khi bạn chủ đích làm phòng hộ.",
                    f"Flat ({slope}°) and not too salty — planting forest here wastes "
                    "farming potential, unless you specifically want a protective belt."))
    add("forest", s, r, w)

    # Chấm điểm mà không nói vì sao thì người dùng không kiểm chứng được —
    # đúng thứ dự án này đã mất nhiều đợt để loại bỏ.
    for c in out:
        if not c["reasons"] and not c["warnings"]:
            c["reasons"].append(tr(
                "Không có yếu tố nào ở thửa này đặc biệt thuận hay cản trở lựa "
                "chọn này; điểm số là mức nền.",
                "Nothing on this plot particularly favors or hinders this option; "
                "the score is the baseline."))
    out.sort(key=lambda c: c["score"], reverse=True)
    return out


def _item(code: str, item: str, why: str) -> dict:
    vi, en = _PRIORITY[code]
    return {"priority": tr(vi, en), "priority_code": code, "item": item, "why": why}


def _infrastructure(elev, slope, sal, flood_risk, coast) -> list[dict]:
    """Việc cần làm với đất, xếp theo mức ưu tiên."""
    items = []
    if flood_risk in ("warning", "danger"):
        items.append(_item("high", tr("Tôn nền hoặc đắp bờ bao", "Raise the ground or build a dike"),
                           tr(f"Module Lũ đang ở mức {flood_risk}; nền hiện {elev} m.",
                              f"The Flood module is at {flood_risk}; ground is now {elev} m.")))
        items.append(_item("high", tr("Kênh hoặc mương thoát nước", "Drainage canal or ditch"),
                           tr("Nước rút nhanh giảm thời gian ngập — thứ quyết định mất mùa.",
                              "Fast drainage shortens flooding — which decides whether the crop is lost.")))
    if sal is not None and sal >= 1.0:
        items.append(_item("high", tr("Cống ngăn mặn đóng chủ động được",
                                      "Salinity sluice gate you can close yourself"),
                           tr(f"Mặn đỉnh {sal} g/L vượt ngưỡng lúa.",
                              f"Peak salinity {sal} g/L exceeds rice's limit.")))
        items.append(_item("medium", tr("Ao hoặc bể trữ nước ngọt", "Freshwater pond or tank"),
                           tr("Trữ trước mùa khô để không phải lấy nước sông lúc mặn lên.",
                              "Store water before the dry season so you don't draw river water when salinity rises.")))
    if slope >= 15:
        items.append(_item("high", tr("Ruộng bậc thang hoặc băng chắn", "Terraces or contour barriers"),
                           tr(f"Độ dốc {slope}° gây xói mòn và nguy cơ sạt lở.",
                              f"A {slope}° slope causes erosion and landslide risk.")))
    if coast <= 5:
        items.append(_item("medium", tr("Băng cây chắn gió mặn", "Windbreak against salty wind"),
                           tr(f"Cách biển chỉ {coast} km — gió mang hơi mặn hại lá.",
                              f"Only {coast} km from the sea — salty wind damages leaves.")))
    if not items:
        items.append(_item("low", tr("Chưa cần hạ tầng đặc biệt", "No special infrastructure needed yet"),
                           tr("Các chỉ số hiện tại đều trong ngưỡng an toàn.",
                              "All current indicators are within safe thresholds.")))
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
        "headline": (tr(f"Phù hợp nhất: {best['icon']} {best['name']} ({best['score']}/100).",
                        f"Best fit: {best['icon']} {best['name']} ({best['score']}/100).")
                     + (" " + best["reasons"][0] if best["reasons"] else "")),
        "generative_note": tr(
            "Chữ 'generative' ở đây nghĩa là TỔNG HỢP phương án mới từ ràng buộc "
            "đo được, không phải model sinh ảnh. Mỗi điểm cộng/trừ đều kèm lý do "
            "truy được về đúng con số đã dẫn tới nó.",
            "'Generative' here means SYNTHESIZING new options from measured "
            "constraints, not an image-generation model. Every plus/minus comes "
            "with a reason traceable to the exact number behind it."),
        "caveat": tr(
            "Ngưỡng cây trồng mang tính ĐỊNH HƯỚNG, tổng hợp từ tài liệu nông học "
            "phổ thông. Trước khi xuống giống hãy đối chiếu khuyến cáo của Sở "
            "NN&PTNT địa phương và kinh nghiệm hộ lân cận — điều kiện thực tế còn "
            "phụ thuộc chất đất, giống và thị trường mà phần mềm chưa biết.",
            "Crop thresholds are INDICATIVE, compiled from general agronomy "
            "literature. Before planting, check the local agriculture department's "
            "guidance and neighbors' experience — real outcomes also depend on "
            "soil, variety and market, which the software doesn't know yet."),
    }
