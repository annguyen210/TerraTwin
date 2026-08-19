"""OpenStreetMap qua Overpass API — hạ tầng do con người dựng, miễn phí, không key.

VÌ SAO CẦN NGUỒN NÀY: ba ngành còn trống trong bản thiết kế (Đô thị & Quy hoạch,
Khai khoáng & Hạ tầng, Chuỗi cung ứng) đều hỏi về thứ VỆ TINH VÀ KHÍ TƯỢNG KHÔNG
TRẢ LỜI ĐƯỢC: ở đây có bao nhiêu nhà, bao nhiêu đường, có mỏ nào không, đi ra
quốc lộ mất bao xa. Đó là dữ liệu hạ tầng, và OSM là nguồn mở tốt nhất cho nó ở
Việt Nam.

Ảnh vệ tinh nhìn thấy "bề mặt cứng"; OSM nói cho biết bề mặt cứng đó LÀ GÌ —
nhà ở, nhà máy, mỏ đá, hay đường cao tốc. Hai nguồn bổ sung nhau chứ không thay
nhau.

GIỚI HẠN PHẢI BIẾT VÀ PHẢI NÓI RA:
  · OSM do tình nguyện viên vẽ. Thành phố lớn ở VN khá đầy đủ; nông thôn và
    miền núi thì thưa. "Không có nhà nào trong OSM" KHÔNG có nghĩa là không có
    nhà — nên mọi kết quả đều kèm mức độ đầy đủ của dữ liệu.
  · Overpass công cộng có hạn mức và hay chậm. Timeout ngắn, cache 7 ngày (hạ
    tầng không đổi theo giờ), hỏng thì trả None chứ không đoán.
"""
from __future__ import annotations

import json
import math
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

# Overpass công cộng chỉ cho MỖI IP 2 slot chạy cùng lúc; quá thì trả 429 hoặc
# 504. Trần chung của phần mềm là 6 lượt gọi ra ngoài, nên nếu không có cổng
# riêng cho OSM thì chính phần mềm tự làm hỏng lời gọi của mình — đúng lỗi đã
# gặp: mô-đun mỏ hỏng ba lần liên tiếp chỉ vì chạy ngay sau mấy lượt OSM khác.
_GATE = threading.BoundedSemaphore(1)

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",   # gương, dùng khi cái đầu nghẽn
]
ENDPOINT = ENDPOINTS[0]
# Overpass yêu cầu User-Agent nhận dạng được. Phải THUẦN ASCII — header HTTP
# mã hoá latin-1, một chữ tiếng Việt có dấu ở đây là hỏng cả lời gọi.
USER_AGENT = "TerraTwin/0.6 (Vietnam land digital twin; contact via repo)"
TIMEOUT = 60.0            # Overpass công cộng hay chậm; quận nội thành ~20 s
_TTL = 7 * 86400          # hạ tầng không đổi theo giờ

# Diện tích sàn trung bình một công trình ở VN khi OSM không vẽ đường bao (chỉ
# đánh dấu điểm). Con số thô, chỉ dùng để ước lượng bậc độ lớn — luôn công bố.
_ASSUMED_BUILDING_M2 = 90.0

# Giá trị thẻ highway KHÔNG dành cho xe cơ giới.
_FOOT_ONLY = {"footway", "path", "steps", "pedestrian", "cycleway",
              "bridleway", "corridor", "track"}


def _query(q: str) -> dict | None:
    from app.services import cache_store, jobs

    key = cache_store.make_key("osm", q)
    hit = cache_store.get(key)
    if hit is not None:
        return hit

    def _work():
        h = cache_store.get(key)
        if h is not None:
            return h
        d = None
        # CHỈ dùng cổng riêng của OSM, KHÔNG lấy thêm suất của jobs.upstream().
        #
        # Lý do phải nói rõ, vì đây là một lần treo thật: ban đầu hàm này giữ
        # một suất gọi-ra-ngoài toàn cục RỒI mới xếp hàng ở cổng OSM. Overpass
        # công cộng chậm 10–60 giây và chỉ chạy một truy vấn một lúc, nên vài
        # luồng OSM giữ hết suất toàn cục trong lúc chờ nhau — Open-Meteo không
        # xin được suất nào và cả bộ test đứng im. Cổng 1 slot ở đây đã chặt hơn
        # trần toàn cục rồi, nên chồng thêm chỉ có hại.
        # Thử lần lượt các máy chủ. 429/504 nghĩa là "đang bận, quay lại sau"
        # chứ không phải "không có dữ liệu" — bỏ cuộc ngay ở đó là biến một lần
        # nghẽn tạm thời thành câu "chưa đủ dữ liệu" gửi tới người dùng.
        with _GATE:
            data = urllib.parse.urlencode({"data": q}).encode()
            for attempt, url in enumerate(ENDPOINTS):
                try:
                    # Header HTTP mã hoá latin-1. Một chữ tiếng Việt có dấu
                    # trong User-Agent là hỏng cả lời gọi — giữ THUẦN ASCII.
                    req = urllib.request.Request(
                        url, data=data,
                        headers={"User-Agent": USER_AGENT,
                                 "Content-Type":
                                     "application/x-www-form-urlencoded"})
                    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                        d = json.loads(r.read().decode("utf-8"))
                    break
                except urllib.error.HTTPError as e:
                    if e.code in (429, 504) and attempt < len(ENDPOINTS) - 1:
                        time.sleep(2.0)
                        continue
                    return None
                except Exception:
                    if attempt < len(ENDPOINTS) - 1:
                        continue
                    return None
        if d is None:
            return None
        cache_store.put(key, d, _TTL)
        return d

    return jobs.single_flight(f"osm:{key}", _work)


def _bbox(lat: float, lon: float, radius_m: float) -> tuple[float, float, float, float]:
    dlat = radius_m / 111_320.0
    dlon = radius_m / (111_320.0 * max(0.2, math.cos(math.radians(lat))))
    return (lat - dlat, lon - dlon, lat + dlat, lon + dlon)


def _poly_area_m2(geom: list[dict]) -> float:
    """Diện tích đa giác từ toạ độ độ, xấp xỉ phẳng cục bộ (đủ cho quy mô km)."""
    if not geom or len(geom) < 3:
        return 0.0
    lat0 = sum(p["lat"] for p in geom) / len(geom)
    k = math.cos(math.radians(lat0))
    pts = [((p["lon"] * k) * 111_320.0, p["lat"] * 111_320.0) for p in geom]
    s = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def built_environment(lat: float, lon: float, radius_m: float = 1000.0) -> dict | None:
    """Mật độ xây dựng, đường sá và loại đất sử dụng quanh một điểm.

    Trả None khi Overpass không phản hồi — người gọi PHẢI phân biệt "không hỏi
    được" với "hỏi được và không có gì".
    """
    s, w, n, e = _bbox(lat, lon, radius_m)
    bb = f"{s:.5f},{w:.5f},{n:.5f},{e:.5f}"
    q = f"""[out:json][timeout:35];
(
  way["building"]({bb});
  way["highway"]({bb});
  way["landuse"~"quarry|industrial|residential|commercial|forest|farmland"]({bb});
  way["waterway"]({bb});
  node["amenity"~"marketplace|hospital|school"]({bb});
);
out geom;"""
    d = _query(q)
    if d is None or "elements" not in d:
        return None

    area_m2 = math.pi * radius_m * radius_m
    buildings = 0
    roads_m = paths_m = 0.0
    building_m2 = 0.0
    landuse: dict[str, float] = {}
    waterways = 0
    amenities: dict[str, int] = {}

    for el in d["elements"]:
        tags = el.get("tags") or {}
        geom = el.get("geometry") or []
        if "building" in tags:
            buildings += 1
            a = _poly_area_m2(geom)
            building_m2 += a if a > 0 else _ASSUMED_BUILDING_M2
        elif "highway" in tags:
            length = 0.0
            for i in range(len(geom) - 1):
                p, qq = geom[i], geom[i + 1]
                dy = (qq["lat"] - p["lat"]) * 111_320.0
                dx = ((qq["lon"] - p["lon"]) * 111_320.0
                      * math.cos(math.radians(p["lat"])))
                length += math.hypot(dx, dy)
            # OSM gắn thẻ highway cho CẢ lối đi bộ, bậc thang, đường mòn. Gộp
            # tất cả vào "đường" cho ra mật độ 48 km/km² ở quận nội thành —
            # con số vô nghĩa. Tách xe cơ giới ra khỏi lối đi bộ.
            if tags["highway"] in _FOOT_ONLY:
                paths_m += length
            else:
                roads_m += length
        elif "landuse" in tags:
            landuse[tags["landuse"]] = landuse.get(tags["landuse"], 0.0) + \
                _poly_area_m2(geom)
        elif "waterway" in tags:
            waterways += 1
        elif tags.get("amenity"):
            amenities[tags["amenity"]] = amenities.get(tags["amenity"], 0) + 1

    built_frac = min(1.0, building_m2 / area_m2) if area_m2 else 0.0

    # Mức đầy đủ của dữ liệu. OSM thưa ở nông thôn VN, nên phải nói rõ độ tin
    # cậy thay vì để người đọc tưởng "0 nhà" nghĩa là đất trống.
    # NHÀ là tín hiệu chính, đường chỉ là phụ. Chấm theo "nhà HOẶC đường" cho ra
    # nghịch lý đã gặp: một điểm ven biển Cà Mau có 0 nhà nhưng 20 km đường vẫn
    # được xếp "đầy đủ" — trong khi 0 nhà chính là bằng chứng rõ nhất rằng chưa
    # ai vẽ nhà ở đó.
    if buildings == 0:
        completeness, comp_note = "thưa", (
            "OSM chưa vẽ công trình nào ở đây. Gần như chắc chắn là CHƯA AI VẼ "
            "chứ không phải thực địa trống — không được đọc con số này như bằng "
            "chứng vắng công trình.")
    elif buildings >= 200 and roads_m >= 10_000:
        completeness, comp_note = "tốt", "OSM ở đây được vẽ khá đầy đủ."
    elif buildings >= 20:
        completeness, comp_note = "vừa", (
            "OSM ở đây vẽ ở mức trung bình; số nhà thực tế có thể cao hơn.")
    else:
        completeness, comp_note = "thưa", (
            "OSM ở đây rất thưa. Con số thấp có thể do CHƯA AI VẼ chứ không phải "
            "do thực địa trống — đừng đọc là bằng chứng vắng công trình.")

    return {
        "radius_m": radius_m,
        "area_ha": round(area_m2 / 10_000.0, 1),
        "buildings": buildings,
        "building_area_m2": round(building_m2),
        "built_fraction": round(built_frac, 4),
        "built_pct": round(built_frac * 100, 2),
        "road_km": round(roads_m / 1000.0, 2),
        "path_km": round(paths_m / 1000.0, 2),
        "road_density_km_per_km2": round(
            (roads_m / 1000.0) / max(0.01, area_m2 / 1_000_000.0), 2),
        "landuse_ha": {k: round(v / 10_000.0, 2) for k, v in sorted(
            landuse.items(), key=lambda kv: kv[1], reverse=True)},
        "waterways": waterways,
        "amenities": amenities,
        "completeness": completeness,
        "completeness_note": comp_note,
        "source": "OpenStreetMap qua Overpass API (dữ liệu mở, cộng đồng đóng góp)",
    }


def nearest(lat: float, lon: float, selector: str, radius_m: float = 25_000.0,
            limit: int = 5) -> list[dict] | None:
    """Các đối tượng gần nhất khớp một selector Overpass, kèm khoảng cách.

    `selector` ví dụ: '["highway"~"trunk|primary"]' hoặc '["landuse"="quarry"]'.
    """
    from app.services import datasources as ds

    s, w, n, e = _bbox(lat, lon, radius_m)
    bb = f"{s:.5f},{w:.5f},{n:.5f},{e:.5f}"
    q = f"""[out:json][timeout:35];
(
  node{selector}({bb});
  way{selector}({bb});
);
out center;"""
    d = _query(q)
    if d is None or "elements" not in d:
        return None

    out = []
    for el in d["elements"]:
        c = el.get("center") or ({"lat": el.get("lat"), "lon": el.get("lon")})
        if c.get("lat") is None or c.get("lon") is None:
            continue
        km = ds._haversine_km(lat, lon, c["lat"], c["lon"])
        tags = el.get("tags") or {}
        out.append({"lat": c["lat"], "lon": c["lon"], "km": round(km, 2),
                    "name": tags.get("name") or "(không tên)",
                    "tags": {k: v for k, v in tags.items()
                             if k in ("highway", "landuse", "man_made",
                                      "industrial", "amenity", "name")}})
    out.sort(key=lambda r: r["km"])
    return out[:limit]
