"""KIỂM CHỨNG TIN ĐĂNG BÁN ĐẤT (GĐ3 kế hoạch tổng) — đối chiếu TỪNG CÂU KHẲNG ĐỊNH với số đo của thửa.

Người bán có động cơ giấu ("đất cao ráo, không bao giờ ngập"). TerraTwin không kết tội ai: mỗi câu khẳng
định được tách ra và đặt cạnh dữ liệu đo — Khớp / Mâu thuẫn / Không đủ dữ liệu — kèm con số, ngày, nguồn.

  · CHỈ nhận chữ người dùng tự dán vào — KHÔNG cào trang bất động sản (rủi ro pháp lý, xem kế hoạch).
  · KHÔNG lưu nội dung tin đăng.
  · Bước 1 (đây): luật từ khoá tiếng Việt có dấu và không dấu. Bước 2 (khi có ~1.000 câu gán nhãn + GPU):
    tinh chỉnh PhoBERT, chỉ thay luật khi F1 ≥ 0,8 trên tập giữ lại (ops/listing_gate.py đo trên tin thật).
  · Loại đất PHÁP LÝ (thổ cư, đất ở) chỉ có trên sổ đỏ — vệ tinh không kiểm được, nói thẳng như vậy.
"""
from __future__ import annotations

import re
import unicodedata

from app.services.reqlang import tr

# (loại, nhãn VI, nhãn EN, mẫu — viết KHÔNG DẤU, so trên văn bản đã bỏ dấu)
CLAIMS: list[tuple[str, str, str, list[str]]] = [
    ("no_flood", "Không ngập", "Never floods", [
        r"khong (bao gio |he |bi |lo )*ngap", r"chua (tung|bao gio) (bi )?ngap", r"khong (bi )?ung ngap",
        r"kho rao quanh nam", r"khong lo (bi )?ngap", r"ngap (lut )?(la )?khong (co|bao gio)"]),
    ("high_ground", "Đất cao ráo", "High ground", [
        r"cao rao", r"nen (dat )?cao", r"(the|vi tri) dat cao", r"dat cao\b", r"khong (bi )?trung",
        r"cao hon (mat )?(duong|khu vuc)"]),
    ("near_river", "Gần sông", "Near a river", [
        r"(gan|ven|giap|sat|view|mat tien|canh) song", r"(gan|ven|giap|sat|view|mat tien|canh) (kenh|rach)"]),
    ("near_sea", "Gần biển", "Near the sea", [
        r"(gan|ven|giap|sat|view|mat tien|canh) bien", r"cach bien \d"]),
    ("flat", "Bằng phẳng", "Flat", [r"bang phang", r"dat phang", r"khong (bi )?doc", r"mat bang (vuong|dep|phang)"]),
    ("no_landslide", "Không sạt lở", "No landslides", [r"khong (bi |lo )?sat lo", r"chua (tung )?sat lo"]),
    ("residential", "Đất ở / thổ cư", "Residential land", [r"tho cu", r"dat o\b", r"\bodt\b", r"\bont\b", r"len tho cu"]),
    ("fresh_water", "Nước ngọt", "Fresh water", [r"nuoc ngot", r"khong (bi )?(nhiem )?man", r"gieng ngot"]),
]


def fold(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower()).replace("đ", "d")
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?;\n])\s+|\n+|[•\-–]\s+", text)
    return [p.strip(" .;!?") for p in parts if p and len(p.strip()) >= 3]


def extract(text: str) -> list[dict]:
    """Câu khẳng định trong tin đăng → [{type, sentence}] (một câu có thể chứa nhiều loại)."""
    out, seen = [], set()
    for s in sentences(text[:5000]):
        f = fold(s)
        for typ, _vi, _en, pats in CLAIMS:
            if any(re.search(p, f) for p in pats) and (typ, s) not in seen:
                seen.add((typ, s))
                out.append({"type": typ, "sentence": s})
    return out


def _label(typ: str) -> str:
    for t, vi, en, _ in CLAIMS:
        if t == typ:
            return tr(vi, en)
    return typ


# ------------------------------------------------------------------ bằng chứng

def _water(lat: float, lon: float) -> dict | None:
    from app import routes_water
    from app.services import cache_store, water_history as wh
    if not routes_water.gate()["passed"]:
        return None
    r = cache_store.get(cache_store.make_key("water", round(lat, 4), round(lon, 4), int(wh.RADIUS_M)))
    return r if r and r.get("available") else None


def _nearest_river_km(lat: float, lon: float, radius_m: float = 3000.0) -> float | None:
    """Khoảng cách tới ĐIỂM GẦN NHẤT trên sông/kênh (không phải tâm đường — sông dài có tâm rất xa)."""
    from app.services import datasources as ds, osm
    s, w, n, e = osm._bbox(lat, lon, radius_m)
    d = osm._query(f'[out:json][timeout:30];way["waterway"~"river|canal"]({s:.5f},{w:.5f},{n:.5f},{e:.5f});out geom;')
    if d is None or "elements" not in d:
        return None
    best = None
    for el in d["elements"]:
        for p in el.get("geometry") or []:
            km = ds._haversine_km(lat, lon, p["lat"], p["lon"])
            best = km if best is None or km < best else best
    return round(best, 2) if best is not None else float("inf")


def evidence(lat: float, lon: float, types: set[str]) -> dict:
    """Chỉ lấy nguồn mà các câu cần — không gọi mạng thừa."""
    from app.services import datasources as ds, passport
    ev: dict = {}
    if types & {"no_flood", "high_ground"}:
        ev["water"] = _water(lat, lon)
    if types & {"high_ground", "flat", "no_landslide"}:
        try:
            ev["terrain"] = passport.terrain(lat, lon)
        except Exception:               # noqa: BLE001
            ev["terrain"] = None
    if "near_sea" in types:
        ev["coast_km"] = ds.distance_to_coast_km(lat, lon)
    if "near_river" in types:
        try:
            ev["river_km"] = _nearest_river_km(lat, lon)
        except Exception:               # noqa: BLE001
            ev["river_km"] = None
    return ev


def judge(typ: str, ev: dict) -> tuple[str, str, str]:
    """(verdict, bằng chứng, nguồn). verdict ∈ consistent | contradicted | insufficient."""
    w, terr = ev.get("water"), ev.get("terrain")
    if typ == "no_flood":
        if not w:
            return "insufficient", tr("Chưa đọc lịch sử nước radar cho thửa này — bấm \"Xem lịch sử nước\" (~2 phút) rồi kiểm lại.",
                                      "Radar water history not read for this plot yet — click \"Show water history\" (~2 min) and re-check."), "Sentinel-1"
        if w["n_events"] > 0:
            dates = ", ".join(e["start"] for e in w["events"][-3:])
            return "contradicted", tr(f"Radar ghi nhận nước phủ {w['n_events']} đợt từ {w['first'][:4]} (gần nhất: {dates}).",
                                      f"Radar recorded water {w['n_events']} times since {w['first'][:4]} (latest: {dates})."), "Sentinel-1 RTC"
        return "consistent", tr(f"Không thấy đợt nước phủ nào trong {w['n_scenes']} cảnh radar từ {w['first'][:4]}.",
                                f"No water events in {w['n_scenes']} radar scenes since {w['first'][:4]}."), "Sentinel-1 RTC"
    if typ == "high_ground":
        if not terr:
            return "insufficient", tr("Không lấy được địa hình lúc này.", "Terrain unavailable right now."), "DEM"
        low = terr["lower_than_pct"]
        wet = (w or {}).get("n_events", 0)
        if low >= 70 or wet >= 2:
            msg = tr(f"Thửa thấp hơn {low}% đất trong bán kính khảo sát", f"The plot is lower than {low}% of surrounding land")
            if wet:
                msg += tr(f"; radar ghi nhận nước phủ {wet} đợt", f"; radar recorded water {wet} times")
            return "contradicted", msg + ".", "DEM + Sentinel-1"
        if low <= 30 and not wet:
            return "consistent", tr(f"Thửa cao hơn {100 - low}% đất xung quanh (cao độ {terr['elevation_m']} m).",
                                    f"The plot is higher than {100 - low}% of surrounding land (elevation {terr['elevation_m']} m)."), "DEM"
        return "insufficient", tr(f"Thửa ở mức trung bình so với xung quanh (thấp hơn {low}%) — không đủ để nói là cao ráo hay trũng.",
                                  f"The plot sits mid-level (lower than {low}% of surroundings) — not enough to call it high or low."), "DEM"
    if typ == "flat":
        if not terr or terr.get("slope_deg") is None:
            return "insufficient", tr("Không lấy được độ dốc.", "Slope unavailable."), "DEM"
        sl = terr["slope_deg"]
        if sl <= 5:
            return "consistent", tr(f"Độ dốc {sl}°.", f"Slope {sl}°."), "DEM 90 m"
        if sl >= 15:
            return "contradicted", tr(f"Độ dốc {sl}° — không phải đất bằng.", f"Slope {sl}° — not flat."), "DEM 90 m"
        return "insufficient", tr(f"Độ dốc {sl}° — dốc nhẹ, DEM 90 m không đủ chi tiết để kết luận.",
                                  f"Slope {sl}° — gentle; a 90 m DEM is too coarse to conclude."), "DEM 90 m"
    if typ == "no_landslide":
        if not terr or terr.get("slope_deg") is None:
            return "insufficient", tr("Không lấy được độ dốc.", "Slope unavailable."), "DEM"
        sl = terr["slope_deg"]
        if sl >= 25:
            return "contradicted", tr(f"Độ dốc {sl}° — sườn dốc thuộc nhóm có nguy cơ sạt lở khi mưa lớn.",
                                      f"Slope {sl}° — a steep slope in the landslide-prone range in heavy rain."), "DEM 90 m"
        if sl < 10:
            return "consistent", tr(f"Độ dốc {sl}° — địa hình thoải.", f"Slope {sl}° — gentle terrain."), "DEM 90 m"
        return "insufficient", tr(f"Độ dốc {sl}° — cần khảo sát thực địa.", f"Slope {sl}° — needs a field survey."), "DEM 90 m"
    if typ == "near_sea":
        km = ev.get("coast_km")
        if km is None:
            return "insufficient", tr("Không tính được khoảng cách tới biển.", "Couldn't compute distance to the sea."), ""
        if km <= 5:
            return "consistent", tr(f"Cách bờ biển khoảng {km:.1f} km.", f"About {km:.1f} km from the coast."), tr("đường bờ biển xấp xỉ", "approximate coastline")
        if km >= 20:
            return "contradicted", tr(f"Cách bờ biển khoảng {km:.0f} km.", f"About {km:.0f} km from the coast."), tr("đường bờ biển xấp xỉ", "approximate coastline")
        return "insufficient", tr(f"Cách bờ biển khoảng {km:.0f} km — \"gần\" tuỳ cách hiểu.", f"About {km:.0f} km from the coast — \"near\" is subjective."), tr("đường bờ biển xấp xỉ", "approximate coastline")
    if typ == "near_river":
        km = ev.get("river_km")
        if km is None:
            return "insufficient", tr("Không tra được sông/kênh từ OpenStreetMap lúc này.", "Couldn't query rivers/canals from OpenStreetMap now."), "OpenStreetMap"
        if km == float("inf"):
            return "contradicted", tr("Không có sông/kênh nào trong 3 km theo OpenStreetMap.", "No river/canal within 3 km per OpenStreetMap."), "OpenStreetMap"
        if km <= 1:
            return "consistent", tr(f"Sông/kênh gần nhất cách khoảng {km * 1000:.0f} m.", f"Nearest river/canal about {km * 1000:.0f} m away."), "OpenStreetMap"
        return "insufficient", tr(f"Sông/kênh gần nhất cách khoảng {km:.1f} km.", f"Nearest river/canal about {km:.1f} km away."), "OpenStreetMap"
    if typ == "residential":
        return "insufficient", tr("Loại đất PHÁP LÝ (thổ cư, đất ở) chỉ có trên giấy chứng nhận — ảnh vệ tinh không kiểm được. Hãy xem sổ đỏ và tra quy hoạch.",
                                  "LEGAL land category (residential) is only on the land certificate — satellites can't verify it. Check the certificate and zoning."), ""
    if typ == "fresh_water":
        return "insufficient", tr("Chưa có số đo độ mặn tại chỗ — TerraTwin chỉ có ước lượng mô hình, không đủ để xác nhận \"nước ngọt\". Thử nước giếng thực tế.",
                                  "No on-site salinity measurement — TerraTwin only has a model estimate, not enough to confirm \"fresh water\". Test the well water."), ""
    return "insufficient", "", ""


def check(text: str, lat: float, lon: float) -> dict:
    claims = extract(text)
    ev = evidence(lat, lon, {c["type"] for c in claims}) if claims else {}
    rows = []
    for c in claims:
        verdict, msg, src = judge(c["type"], ev)
        rows.append({**c, "label": _label(c["type"]), "verdict": verdict, "evidence": msg, "source": src})
    count = {v: sum(1 for r in rows if r["verdict"] == v) for v in ("consistent", "contradicted", "insufficient")}
    return {"claims": rows, "counts": count, "location": {"lat": lat, "lon": lon},
            "note": tr("Đối chiếu từ dữ liệu đo, lời văn trung lập — không phải kết luận pháp lý về người bán. "
                       "Nội dung tin đăng không được lưu.",
                       "Compared against measured data, in neutral wording — not a legal finding about the seller. "
                       "The listing text is not stored.")}
