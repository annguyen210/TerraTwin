"""Ảnh nền độ phân giải cao THẬT dưới thửa — ngày chụp, độ phân giải, nguồn (Esri World Imagery).

Bản đồ chính đã dùng ảnh vệ tinh thật (Esri World Imagery, ảnh Vantor/Maxar tới ~0,3–0,6 m) — đó là cách ĐÚNG để người dùng
thấy chi tiết dưới 10 m, thay cho "siêu phân giải" sinh bằng mô hình (TỪ CHỐI, roadmap S10). Nhưng ảnh nền KHÔNG phải ảnh
hôm nay: có nơi chụp cách đây nhiều năm. Không ghi ngày thì người xem tưởng đó là hiện trạng — nên đọc lớp siêu dữ liệu của
chính dịch vụ (World_Imagery/MapServer/identify: DATE, RESOLUTION, SOURCE) và hiện ngay dưới thửa.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import date

IDENTIFY = "https://services.arcgisonline.com/arcgis/rest/services/World_Imagery/MapServer/identify"
TTL = 30 * 86400


def _parse(attrs: dict) -> dict | None:
    raw = str(attrs.get("DATE (YYYYMMDD)") or attrs.get("SRC_DATE") or "")
    d = None
    if len(raw) == 8 and raw.isdigit() and raw != "99999999":
        try:
            d = date(int(raw[:4]), int(raw[4:6]), int(raw[6:8])).isoformat()
        except ValueError:
            d = None
    try:
        res = float(attrs.get("RESOLUTION (M)"))
    except (TypeError, ValueError):
        res = None
    if res is not None and res >= 99999:
        res = None
    src = attrs.get("SOURCE") or attrs.get("SOURCE_INFO")
    return {"date": d, "resolution_m": res, "source": None if src in (None, "Null", "") else src,
            "product": None if attrs.get("SOURCE_INFO") in (None, "Null") else attrs.get("SOURCE_INFO")}


def meta(lat: float, lon: float) -> dict | None:
    """Siêu dữ liệu ảnh nền tại điểm, hoặc None nếu dịch vụ không trả lời (KHÁC với 'không có ngày')."""
    from app.services import cache_store
    key = cache_store.make_key("basemap-meta", round(lat, 4), round(lon, 4))
    hit = cache_store.get(key)
    if hit is not None:
        return hit
    d = 0.0005
    q = urllib.parse.urlencode({"geometry": f"{lon},{lat}", "geometryType": "esriGeometryPoint", "sr": 4326, "layers": "all:0",
                                "tolerance": 1, "mapExtent": f"{lon - d},{lat - d},{lon + d},{lat + d}",
                                "imageDisplay": "400,400,96", "returnGeometry": "false", "f": "json"})
    try:
        req = urllib.request.Request(f"{IDENTIFY}?{q}", headers={"User-Agent": "TerraTwin"})
        with urllib.request.urlopen(req, timeout=20) as r:
            j = json.loads(r.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None
    res = (j.get("results") or [])
    if not res:
        out = {"available": False}
    else:
        p = _parse(res[0].get("attributes") or {})
        out = {"available": True, **p, "service": "Esri World Imagery"}
        if p["date"]:
            out["age_years"] = round((date.today() - date.fromisoformat(p["date"])).days / 365.25, 1)
    cache_store.put(key, out, ttl_seconds=TTL)
    return out
