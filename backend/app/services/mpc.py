"""Ảnh Sentinel-2 KHÔNG CẦN KHOÁ, qua Microsoft Planetary Computer.

VÌ SAO CÓ TỆP NÀY. Năm mũi nhọn quang học (sâu bệnh, sinh trưởng, carbon, thiệt
hại sau bão, xây dựng trái phép) đã viết xong từ lâu nhưng nằm im vì chờ một
khoá Copernicus. Người dùng mở app lên thấy "5 mục chưa đủ dữ liệu" và kết luận
phần mềm sơ sài — họ kết luận đúng với thứ họ được cho xem.

Planetary Computer phục vụ ĐÚNG bộ dữ liệu Sentinel-2 L2A đó, công khai, không
đăng ký, và có sẵn dịch vụ tính thống kê ngay trên máy chủ. Nghĩa là chất lượng
dữ liệu KHÔNG đổi — chỉ đổi chỗ lấy. Không có sự đánh đổi nào bị giấu ở đây.

ĐÃ KIỂM CHỨNG BẰNG SỐ trước khi tin, vì một API trả về 200 chưa có nghĩa là nó
trả về đúng:
    ruộng Bến Tre   NDVI 0,441   ✓ hợp lý cho đất nông nghiệp
    đô thị TP.HCM   NDVI 0,129   ✓ hợp lý cho bê tông dày đặc
Lần thử đầu ra 0,015 và tôi suýt kết luận API hỏng — hoá ra toạ độ tôi chọn rơi
đúng giữa sông Hàm Luông. API đúng, phép thử của tôi sai.

ĐÁNH ĐỔI THẬT, nói ra chứ không giấu:
  · Copernicus Statistics API gộp cả chuỗi thời gian vào MỘT lời gọi. Ở đây
    phải gọi riêng từng ảnh, nên chậm hơn — bù lại bằng chạy song song và cache.
  · Che mây: máy chủ này không nhận biểu thức lồng điều kiện, nên không lọc
    được từng điểm ảnh ngay trong công thức. Thay vào đó dò lớp SCL riêng cho
    ĐÚNG THỬA rồi mới quyết nhận hay bỏ cả ảnh. Tốn hai lời gọi mỗi ảnh, nhưng
    lọc chính xác hơn hẳn cách nhìn độ mây cả cảnh — đo được ở Bến Tre: cảnh
    46,6% mây cho NDVI 0,498 dùng tốt, còn cảnh 55,4% mây cho 0,136 toàn rác.
    Độ quang tại thửa được ghi vào từng kết quả (`coverage_pct`).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
DATA = "https://planetarycomputer.microsoft.com/api/data/v1/item/statistics"
COLLECTION = "sentinel-2-l2a"
USER_AGENT = "TerraTwin/0.7 (Vietnam land digital twin; contact via repo)"

TIMEOUT = 60.0
# Ngưỡng mây của CẢ CẢNH, để rộng có chủ ý. Độ mây cảnh tính trên ô ảnh 110 km
# nên gần như không nói gì về một thửa 600 m: đo thật ở Bến Tre thấy cảnh 46,6%
# mây cho NDVI 0,498 hoàn hảo, còn cảnh 55,4% mây cho 0,136 toàn rác. Lọc thật
# nằm ở CLEAR_MIN bên dưới. Để ngưỡng này chặt (40%) làm mất 25/26 ảnh trong
# mùa mưa — đó chính là lý do năm mũi nhọn quang học tưởng như không có dữ liệu.
MAX_CLOUD = 95.0
MAX_SCENES = 6            # trần số ảnh mỗi chuỗi — giữ độ trễ trong tầm kiểm soát
CLEAR_MIN = 70.0          # % điểm ảnh quang mây TRONG THỬA thì mới nhận
MAX_PROBE = 24            # số ảnh dò lớp SCL trước khi bỏ cuộc

# Lớp phân loại cảnh SCL được coi là nhìn thấy mặt đất/nước:
#   4 thực vật · 5 đất trần · 6 nước · 7 chưa phân loại · 11 tuyết
# Bỏ: 3 bóng mây · 8,9 mây · 10 mây ti
SCL_CLEAR = (4, 5, 6, 7, 11)
_TTL_RECENT = 12 * 3600
_TTL_CLOSED = 7 * 86400   # cửa sổ quá khứ đã đóng thì không bao giờ đổi nữa

# Cùng bộ chỉ số với lớp Copernicus, viết theo cú pháp biểu thức của máy chủ này.
EXPR = {
    "NDVI": "(B08-B04)/(B08+B04)",
    "NDWI": "(B03-B08)/(B03+B08)",
    "NDMI": "(B08-B11)/(B08+B11)",
    "NDBI": "(B11-B08)/(B11+B08)",
}


def available() -> bool:
    """Luôn sẵn sàng — không cần khoá. Vẫn có thể hỏng lúc gọi, và khi đó trả None."""
    return True


def _call(url: str, payload: dict | None = None, timeout: float = TIMEOUT):
    from app.services import jobs

    with jobs.upstream() as allowed:
        if not allowed:
            return None
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8") if payload else None,
                headers={"User-Agent": USER_AGENT,
                         "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            return None


def bbox_around(lat: float, lon: float, buffer_m: float = 300.0) -> list[float]:
    dlat = buffer_m / 111_320.0
    dlon = buffer_m / (111_320.0 * max(0.2, abs(__import__("math").cos(
        __import__("math").radians(lat)))))
    return [lon - dlon, lat - dlat, lon + dlon, lat + dlat]


def _poly(box: list[float]) -> dict:
    x0, y0, x1, y1 = box
    return {"type": "Feature", "properties": {},
            "geometry": {"type": "Polygon",
                         "coordinates": [[[x0, y0], [x1, y0], [x1, y1],
                                          [x0, y1], [x0, y0]]]}}


def search(box: list[float], start: date, end: date,
           max_cloud: float = MAX_CLOUD, limit: int = 40) -> list[dict] | None:
    """Tìm ảnh Sentinel-2 phủ vùng này. Trả None nếu gọi hỏng (KHÁC với rỗng)."""
    r = _call(STAC, {
        "collections": [COLLECTION],
        "bbox": box,
        "datetime": f"{start.isoformat()}/{end.isoformat()}",
        "query": {"eo:cloud_cover": {"lt": max_cloud}},
        "limit": limit,
        "sortby": [{"field": "datetime", "direction": "desc"}],
    })
    if r is None or "features" not in r:
        return None
    return r["features"]


def clear_fraction(item_id: str, box: list[float]) -> float | None:
    """% điểm ảnh trong THỬA thật sự nhìn thấy mặt đất, theo lớp SCL.

    Đây là phép lọc thật, thay cho độ mây của cả cảnh. Đo được ở Bến Tre:
        cảnh 46,6% mây → thửa quang 100%  → NDVI 0,498  (dùng được)
        cảnh 69,9% mây → thửa quang   0%  → NDVI 0,027  (rác, phải bỏ)
    Hai cảnh có độ mây gần nhau nhưng một cái dùng được một cái không — chỉ
    nhìn ở mức thửa mới phân biệt nổi.
    """
    q = urllib.parse.urlencode({
        "collection": COLLECTION, "item": item_id,
        "expression": "SCL", "asset_as_band": "true",
        "histogram_bins": "12", "histogram_range": "0,12",
    })
    r = _call(f"{DATA}?{q}", _poly(box))
    if not r:
        return None
    try:
        st = list(r["properties"]["statistics"].values())[0]
        counts, edges = st["histogram"][0], st["histogram"][1]
    except (KeyError, IndexError, TypeError):
        return None
    total = sum(counts)
    if total <= 0:
        return None
    clear = sum(n for n, lo in zip(counts, edges) if int(lo) in SCL_CLEAR)
    return 100.0 * clear / total


def _stats_one(item_id: str, box: list[float], index: str) -> dict | None:
    q = urllib.parse.urlencode({
        "collection": COLLECTION, "item": item_id,
        "expression": EXPR[index], "asset_as_band": "true",
    })
    r = _call(f"{DATA}?{q}", _poly(box))
    if not r:
        return None
    try:
        st = list(r["properties"]["statistics"].values())[0]
    except (KeyError, IndexError, TypeError):
        return None
    if not st or st.get("count", 0) < 1:
        return None
    return st


def _spread(items: list[dict], n: int) -> list[dict]:
    """Chọn n ảnh TRẢI ĐỀU theo thời gian, không phải n ảnh mới nhất.

    Lấy n ảnh mới nhất thì cả chuỗi có thể dồn vào một tuần, và mọi so sánh
    "trước / sau" mất nghĩa. Trải đều giữ được hình dạng diễn biến.
    """
    if len(items) <= n:
        return items
    step = len(items) / n
    return [items[int(i * step)] for i in range(n)]


def index_series(lat: float, lon: float, index: str = "NDVI",
                 days: int = 90, buffer_m: float = 300.0,
                 end: date | None = None,
                 max_scenes: int = MAX_SCENES) -> list[dict] | None:
    """Chuỗi thống kê chỉ số quang học. Cùng dạng trả về với lớp Copernicus.

    Mỗi phần tử: date, mean, std, min, max, valid_px, total_px, coverage_pct,
    cloud_pct. Trả None khi không lấy được — người gọi PHẢI phân biệt "không có
    dữ liệu" với "có dữ liệu và nó bằng 0".
    """
    if index not in EXPR:
        raise ValueError(f"Chỉ số không hỗ trợ: {index}")

    end = end or date.today()
    start = end - timedelta(days=int(days))
    box = bbox_around(lat, lon, buffer_m)

    from app.services import cache_store, jobs
    key = cache_store.make_key("mpc-series", index, round(lat, 4), round(lon, 4),
                               int(days), int(buffer_m), end.isoformat(),
                               int(buffer_m), max_scenes)
    hit = cache_store.get(key)
    if hit is not None:
        return hit

    items = search(box, start, end)
    if items is None:
        return None
    if not items:
        return []

    # HAI BƯỚC: dò lớp SCL trước (rẻ) để loại ảnh bị mây che tại chính thửa
    # này, rồi mới lấy chỉ số cho những ảnh sống sót. Làm ngược lại thì vừa tốn
    # gấp đôi vừa cho ra những con số trông như dữ liệu nhưng thực chất là mây.
    probe = _spread(items, min(MAX_PROBE, len(items)))
    fracs = jobs.gather([lambda it=it: (it, clear_fraction(it["id"], box))
                         for it in probe])
    good = [(it, f) for it, f in fracs if f is not None and f >= CLEAR_MIN]
    if not good:
        return []
    chosen = [(it, f) for it, f in good[:max_scenes]]

    span_m = buffer_m * 2.0
    expect = max(1.0, (span_m / 10.0) ** 2)

    def one(pair):
        it, frac = pair
        st = _stats_one(it["id"], box, index)
        if st is None:
            return None
        cov = frac
        return {
            "date": it["properties"]["datetime"][:10],
            "mean": round(st["mean"], 4),
            "std": round(st.get("std", 0.0), 4),
            "min": round(st.get("min", 0.0), 4),
            "max": round(st.get("max", 0.0), 4),
            "valid_px": int(st.get("count", 0)),
            "total_px": int(expect),
            "coverage_pct": round(cov, 1),
            "cloud_pct": round(float(it["properties"].get("eo:cloud_cover") or 0.0), 1),
            "scene": it["id"],
        }

    rows = [r for r in jobs.gather([lambda p=p: one(p) for p in chosen]) if r]
    rows.sort(key=lambda r: r["date"])
    if not rows:
        return None

    closed = end < date.today() - timedelta(days=14)
    cache_store.put(key, rows, ttl_seconds=_TTL_CLOSED if closed else _TTL_RECENT)
    return rows


def index_distribution(lat: float, lon: float, index: str = "NDVI",
                       days: int = 60, buffer_m: float = 600.0,
                       bins: int = 20, end: date | None = None) -> dict | None:
    """PHÂN BỐ giá trị trên toàn ô, không chỉ trung bình.

    Cần cho việc đo che phủ: một ô nửa rừng già nửa đất trống và một ô toàn cây
    bụi thưa cho cùng NDVI trung bình, nhưng trữ lượng carbon khác hẳn nhau.
    """
    if index not in EXPR:
        raise ValueError(f"Chỉ số không hỗ trợ: {index}")

    end = end or date.today()
    start = end - timedelta(days=int(days))
    box = bbox_around(lat, lon, buffer_m)

    from app.services import cache_store
    key = cache_store.make_key("mpc-hist", index, round(lat, 4), round(lon, 4),
                               int(days), int(buffer_m), bins, end.isoformat())
    hit = cache_store.get(key)
    if hit is not None:
        return hit

    items = search(box, start, end, max_cloud=MAX_CLOUD, limit=30)
    if not items:
        return None

    # Ảnh ít mây nhất trong cửa sổ — histogram chỉ có nghĩa khi nhìn thấy đất.
    # Chọn ảnh QUANG NHẤT TẠI THỬA, không phải ảnh có độ mây cảnh thấp nhất.
    probe = _spread(items, min(8, len(items)))
    from app.services import jobs as _j
    fr = _j.gather([lambda it=it: (it, clear_fraction(it["id"], box)) for it in probe])
    ok = [(it, f) for it, f in fr if f is not None and f >= CLEAR_MIN]
    if not ok:
        return None
    ok.sort(key=lambda p: -p[1])
    it = ok[0][0]

    q = urllib.parse.urlencode({
        "collection": COLLECTION, "item": it["id"],
        "expression": EXPR[index], "asset_as_band": "true",
        "histogram_bins": str(int(bins)),
    })
    r = _call(f"{DATA}?{q}", _poly(box))
    if not r:
        return None
    try:
        st = list(r["properties"]["statistics"].values())[0]
        counts, edges = st["histogram"][0], st["histogram"][1]
    except (KeyError, IndexError, TypeError):
        return None

    # ĐỦ MỌI TRƯỜNG mà bản Copernicus trả về. Thiếu một cái là hàm dùng nó nổ
    # KeyError hoặc trả None, và triệu chứng lộ ra ở tận mô-đun carbon dưới dạng
    # "không dựng được phân bố" — nghe như thiếu ảnh, trong khi ảnh đã có sẵn.
    # Đã sập hai lần liên tiếp (thiếu `bins`, rồi thiếu `area_ha`), nên lần này
    # đối chiếu thẳng danh sách trường mà mrv.py thật sự đọc.
    px = 10.0
    valid = int(st.get("count", 0))
    tong = max(1, int((buffer_m * 2 / px) ** 2))
    out = {
        "date": it["properties"]["datetime"][:10],
        "observed_window": [start.isoformat(), end.isoformat()],
        "pixel_m": px,
        "area_ha": round((buffer_m * 2) ** 2 / 10_000.0, 3),
        "valid_px": valid,
        "total_px": tong,
        "coverage_pct": round(100.0 * valid / tong, 1),
        "index": index,
        "mean": round(st["mean"], 4),
        "std": round(st.get("std", 0.0), 4),
        "valid_px": int(st.get("count", 0)),
        # ĐÚNG DẠNG mà sentinel.fraction_above() mong đợi: danh sách bin có
        # low/high/count. Bản đầu trả {counts, edges} theo dạng thô của máy chủ,
        # nên fraction_above() trả None và mô-đun carbon báo "không dựng được
        # phân bố" — trong khi ảnh vốn đã lấy được. Lệch hợp đồng giữa bản dự
        # phòng và bản gốc, không phải thiếu dữ liệu.
        "bins": [{"low": float(edges[i]), "high": float(edges[i + 1]),
                  "count": int(counts[i])}
                 for i in range(min(len(counts), len(edges) - 1))],
        "histogram": {"counts": counts, "edges": edges},
        "cloud_pct": round(float(it["properties"].get("eo:cloud_cover") or 0.0), 1),
        "scene": it["id"],
        "source": "Microsoft Planetary Computer · Sentinel-2 L2A (không cần khoá)",
    }
    closed = end < date.today() - timedelta(days=14)
    cache_store.put(key, out, ttl_seconds=_TTL_CLOSED if closed else _TTL_RECENT)
    return out
