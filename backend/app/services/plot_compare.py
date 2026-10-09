"""GĐ6 · NĂNG LỰC 7 — SO SÁNH 2–4 THỬA TRÊN MỘT MÀN.

Người phân vân giữa hai mảnh đất nghĩ đúng như thế này: mảnh nào từng ngập nhiều hơn, cao hơn, xa sông
hơn, có nằm vùng mặn không, mười năm qua lũ/sạt lở bao nhiêu đợt, đất đang là gì. Chỉ ghép dịch vụ SẴN
CÓ, cùng nguồn với Hồ sơ đất số. Không chấm điểm tổng, không khuyên mua: mỗi hàng chỉ đánh dấu giá trị
thuận lợi nhất THEO RIÊNG tiêu chí đó.
"""
from __future__ import annotations

from app.services import cache_store
from app.services.reqlang import tr

_TTL = 6 * 3600


def one(lat: float, lon: float) -> dict:
    """Một cột so sánh. Mục nào hỏng ghi None (giao diện ghi "không lấy được"), không đoán."""
    from app.services import datasources as ds, jobs, landuse, listing_check as lc, passport
    key = cache_store.make_key("compare", round(lat, 5), round(lon, 5))
    hit = cache_store.get(key)
    if hit is not None:
        return hit
    water, terr, hist, land, river = jobs.gather([
        lambda: lc._water(lat, lon), lambda: passport.terrain(lat, lon), lambda: passport.history(lat, lon),
        lambda: landuse.composition(lat, lon), lambda: lc._nearest_river_km(lat, lon, 5000.0)], timeout=60)
    hist = hist or {}
    out = {
        "lat": lat, "lon": lon,
        "water_events": (water or {}).get("n_events"),
        "water_scenes": (water or {}).get("n_scenes"),
        "water_last": ((water or {}).get("events") or [{}])[-1].get("start") if water and water.get("events") else None,
        "elevation_m": (terr or {}).get("elevation_m"),
        "lower_than_pct": (terr or {}).get("lower_than_pct"),
        "slope_deg": (terr or {}).get("slope_deg"),
        # Không có sông/kênh nào trong 5 km → chuỗi "> 5" (inf không hợp lệ trong JSON, và 0 hay None đều sai nghĩa).
        "river_km": "> 5 km" if river == float("inf") else river,
        "coast_km": ds.distance_to_coast_km(lat, lon),
        "salinity_zone": ds.salinity_zone(lat, lon),
        "flood_10y": (hist.get("flood") or {}).get("events"),
        "landslide_10y": (hist.get("landslide") or {}).get("events"),
        "drought_10y": (hist.get("drought") or {}).get("events"),
        "land": (f"{land['classes'][0]['name']} {land['classes'][0]['pct']:.0f}%" if land and land.get("classes") else None),
    }
    # Chỉ cache khi các nguồn chính đều có — đừng giữ một cột thiếu suốt 6 giờ.
    if terr is not None and hist:
        cache_store.put(key, out, _TTL)
    return out


# hàng → (nhãn VI, nhãn EN, đơn vị, hướng thuận lợi: "low" | "high" | None, nguồn)
ROWS = [
    ("water_events", "Số đợt nước phủ (radar, 2017→nay)", "Water events (radar, 2017→now)", "", "low", "Sentinel-1 RTC"),
    ("elevation_m", "Cao độ", "Elevation", " m", "high", "Copernicus DEM"),
    ("lower_than_pct", "Thấp hơn % đất trong 5 km", "Lower than % of land within 5 km", "%", "low", "Copernicus DEM"),
    ("slope_deg", "Độ dốc", "Slope", "°", "low", "Copernicus DEM"),
    ("river_km", "Tới sông/kênh gần nhất", "To nearest river/canal", " km", None, "OpenStreetMap"),   # gần sông: dễ ngập NHƯNG có nước tưới — không chấm
    ("coast_km", "Tới bờ biển", "To the coast", " km", "high", "TerraTwin coastline"),
    ("salinity_zone", "Vùng nhiễm mặn nông nghiệp", "Agricultural salinity zone", "", None, "TerraTwin"),
    ("flood_10y", "Đợt lũ vượt ngưỡng (10 năm)", "Flood episodes over threshold (10 y)", "", "low", "ERA5"),
    ("landslide_10y", "Đợt sạt lở vượt ngưỡng (10 năm)", "Landslide episodes over threshold (10 y)", "", "low", "ERA5"),
    ("drought_10y", "Đợt hạn vượt ngưỡng (10 năm)", "Drought episodes over threshold (10 y)", "", "low", "ERA5"),
    ("land", "Loại đất (ESA WorldCover)", "Land cover (ESA WorldCover)", "", None, "ESA WorldCover 2021"),
]


def compare(points: list[dict]) -> dict:
    from app.services import jobs
    cols = jobs.gather([lambda p=p: one(p["lat"], p["lon"]) for p in points], timeout=120)
    cols = [{**(c or {"lat": p["lat"], "lon": p["lon"]}), "name": p.get("name") or f"{p['lat']:.4f}, {p['lon']:.4f}"}
            for p, c in zip(points, cols)]
    rows = []
    for k, vi, en, unit, better, src in ROWS:
        vals = [c.get(k) for c in cols]
        best = None
        nums = [v for v in vals if isinstance(v, (int, float))]
        if better and len(nums) >= 2 and len(set(nums)) > 1:
            target = min(nums) if better == "low" else max(nums)
            best = [i for i, v in enumerate(vals) if v == target]
        if k == "salinity_zone":
            vals = [v or tr("ngoài vùng", "outside") for v in vals]
        rows.append({"key": k, "label": tr(vi, en), "unit": unit, "values": vals, "best": best, "source": src})
    return {
        "columns": [{"name": c["name"], "lat": c["lat"], "lon": c["lon"], "water_read": c.get("water_events") is not None}
                    for c in cols],
        "rows": rows,
        "note": tr("Đánh dấu giá trị thuận lợi nhất theo RIÊNG từng tiêu chí — không phải điểm tổng, không phải lời khuyên mua. "
                   "Số đợt nước phủ chỉ có khi đã đọc lịch sử nước radar của thửa (~2 phút mỗi thửa).",
                   "Highlights the most favourable value for EACH criterion alone — not an overall score, not buying advice. "
                   "Water events appear only once the plot's radar water history has been read (~2 min per plot)."),
    }
