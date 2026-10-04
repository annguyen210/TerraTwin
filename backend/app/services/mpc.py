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
import math
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

from app.services.reqlang import tr

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
# Ngưỡng cho thống kê ĐÃ CHE MÂY TỪNG ĐIỂM ẢNH (masked_stats). Trung bình chỉ tính trên
# điểm ảnh quang nên không còn bị mây kéo lệch; ngưỡng chỉ còn giữ cho phần nhìn thấy
# đủ đại diện cho thửa (40% của ô 600 m ≈ 1.400 điểm ảnh 10 m).
CLEAR_MIN_MASKED = 40.0
_SCL_MASK = "(" + "|".join(f"(SCL=={c})" for c in SCL_CLEAR) + ")"
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


def masked_stats(item_id: str, box: list[float], index: str) -> dict | None:
    """Thống kê chỉ số CHỈ trên điểm ảnh quang mây (lớp SCL), một lượt gọi.

    Bản cũ lấy trung bình MỌI điểm ảnh của cảnh đã qua ngưỡng 70% quang: tới 30%
    điểm ảnh còn lại là mây (NDVI ≈ 0) vẫn bị cộng vào. Đo thật 18/9/2026 ở Lâm Đồng,
    cảnh quang 66%: trung bình cũ 0,358, chỉ trên điểm quang 0,411 — lệch 13%, đủ để
    "phát hiện sâu bệnh" báo cây yếu đi chỉ vì trời có mây.

    Data API không nhận nodata tuỳ ý cho biểu thức, nên xin 5 băng trong cùng một
    lượt gọi rồi tính đúng: tổng có che, số điểm quang, tổng bình phương có che, min
    và max có che. Lượt gọi này cũng cho luôn % quang — thay cho lượt dò SCL riêng.
    """
    v, m = EXPR[index], _SCL_MASK
    expr = ";".join([f"where({m},{v},0)", f"where({m},1,0)", f"where({m},({v})*({v}),0)",
                     f"where({m},{v},2)", f"where({m},{v},-2)"])
    q = urllib.parse.urlencode({"collection": COLLECTION, "item": item_id,
                                "expression": expr, "asset_as_band": "true"})
    r = _call(f"{DATA}?{q}", _poly(box))
    if not r:
        return None
    try:
        a, b, c, mn, mx = list(r["properties"]["statistics"].values())[:5]
        n, f = float(a["count"]), float(b["mean"])
    except (KeyError, ValueError, TypeError):
        return None
    if not n or not math.isfinite(f) or f <= 0:
        return {"clear_pct": 0.0, "count": 0}
    mean = a["mean"] / f
    if not math.isfinite(mean):
        return None
    return {"mean": mean, "std": math.sqrt(max(0.0, c["mean"] / f - mean * mean)),
            "min": mn["min"], "max": mx["max"], "count": int(round(n * f)),
            "clear_pct": 100.0 * f}


def _one_per_date(items: list[dict]) -> list[dict]:
    """Mỗi ngày bay MỘT cảnh (độ mây cảnh thấp nhất), giữ thứ tự mới → cũ.

    Thửa nằm ở mép hai ô lưới MGRS thì mỗi lần bay có HAI cảnh trùng ngày: chúng ăn
    gấp đôi suất dò và làm chuỗi đếm một ngày thành hai quan sát.
    """
    best: dict[str, dict] = {}
    for it in items:
        d = it["properties"]["datetime"][:10]
        cc = float(it["properties"].get("eo:cloud_cover") or 100.0)
        if d not in best or cc < float(best[d]["properties"].get("eo:cloud_cover") or 100.0):
            best[d] = it
    return sorted(best.values(), key=lambda it: it["properties"]["datetime"], reverse=True)


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
    key = cache_store.make_key("mpc-series-m3", index, round(lat, 4), round(lon, 4),
                               int(days), int(buffer_m), end.isoformat(),
                               int(buffer_m), max_scenes)
    hit = cache_store.get(key)
    if hit is not None:
        return hit

    # limit đủ cho cả cửa sổ: mặc định 40 cảnh (mới → cũ, hai ô lưới mỗi ngày) chỉ phủ
    # ~100 ngày, nên chuỗi "180 ngày" của mô-đun năng suất âm thầm mất nửa đầu.
    items = search(box, start, end, limit=400)
    if items is None:
        return None
    if not items:
        return []

    # MỘT lượt gọi mỗi cảnh: thống kê đã che mây từng điểm ảnh, kèm luôn % quang.
    probe = _spread(_one_per_date(items), min(MAX_PROBE, len(items)))
    got = [g for g in jobs.gather([lambda it=it: (it, masked_stats(it["id"], box, index))
                                   for it in probe]) if g is not None]
    if not any(st is not None for _, st in got):
        return None                      # mọi lượt gọi đều hỏng — KHÁC với "toàn mây"
    good = [(it, st) for it, st in got
            if st is not None and st.get("clear_pct", 0.0) >= CLEAR_MIN_MASKED and "mean" in st]
    if not good:
        return []
    # Không còn cắt ở max_scenes: trần đó để tiết kiệm lượt gọi thống kê thứ hai, mà
    # nay mỗi cảnh chỉ một lượt — bỏ đi cảnh quang đã trả tiền gọi là phí dữ liệu thật
    # (mùa mưa, "năng suất" cần 5 điểm trong 180 ngày; trần 6 làm hụt).
    chosen = good

    span_m = buffer_m * 2.0
    expect = max(1.0, (span_m / 10.0) ** 2)

    def one(pair):
        it, st = pair
        cov = st["clear_pct"]
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

    rows = [one(p) for p in chosen]
    rows.sort(key=lambda r: r["date"])
    if not rows:
        return None

    closed = end < date.today() - timedelta(days=14)
    cache_store.put(key, rows, ttl_seconds=_TTL_CLOSED if closed else _TTL_RECENT)
    return rows


def _add_months(d: date, delta: int) -> date:
    m = d.month - 1 + delta
    y = d.year + m // 12
    return date(y, m % 12 + 1, 1)


MONTHLY_MAX_PER_MONTH = 2   # trần số cảnh dò mỗi tháng — giữ tổng lời gọi trong tầm


def monthly_index_series(lat: float, lon: float, index: str = "NDVI",
                         months: int = 24, buffer_m: float = 300.0,
                         end: date | None = None,
                         max_per_month: int = MONTHLY_MAX_PER_MONTH) -> list[dict] | None:
    """Chuỗi THÁNG cho A7 (change_detect) — mỗi điểm là TRUNG VỊ của các cảnh
    quang mây trong đúng tháng đó, không phải một cảnh đơn lẻ hay N cảnh sạch
    tuyệt đối rải khắp cả cửa sổ.

    VÌ SAO: Sentinel-2 bay qua vị trí bất kỳ ở Việt Nam ~5 ngày/lần (hai vệ
    tinh chồng quỹ đạo có nơi dày hơn), nên 24 tháng thường có trên trăm cảnh
    thô. index_series() ở trên đòi MAX_SCENES cảnh "sạch tuyệt đối" xếp hạng
    theo độ quang toàn chuỗi — với ngưỡng CLEAR_MIN=70% tại đúng thửa, mùa mưa
    có thể chỉ còn 5-6 cảnh sống sót cho CẢ HAI NĂM, dưới hẳn MIN_POINTS=8 mà
    change_detect.detect_from_series() cần. Gộp trung vị theo tháng khoan
    dung hơn: chỉ cần MỘT cảnh quang mây trong một tháng là tháng đó có điểm,
    và trung vị của vài cảnh (khi tháng đó có nhiều) khử nhiễu tốt hơn hẳn một
    cảnh đơn lẻ xui gặp mây rìa.
    """
    if index not in EXPR:
        raise ValueError(f"Chỉ số không hỗ trợ: {index}")

    end = end or date.today()
    end_month = date(end.year, end.month, 1)
    start = _add_months(end_month, -(months - 1))
    box = bbox_around(lat, lon, buffer_m)

    from app.services import cache_store, jobs

    key = cache_store.make_key("mpc-monthly-m2", index, round(lat, 4), round(lon, 4),
                               months, int(buffer_m), end.isoformat())
    hit = cache_store.get(key)
    if hit is not None:
        return hit

    items = search(box, start, end, max_cloud=MAX_CLOUD, limit=400)
    if items is None:
        return None
    if not items:
        return []

    buckets: dict[tuple[int, int], list[dict]] = {}
    for it in _one_per_date(items):
        d = date.fromisoformat(it["properties"]["datetime"][:10])
        if d < start:
            continue
        mk = (d.year, d.month)
        buckets.setdefault(mk, []).append(it)

    probe_pairs: list[tuple[tuple[int, int], dict]] = []
    for mk, its in buckets.items():
        chosen_probe = _spread(sorted(its, key=lambda x: x["properties"]["datetime"]),
                               min(max_per_month, len(its)))
        probe_pairs.extend((mk, it) for it in chosen_probe)

    got = jobs.gather([lambda p=p: (p[0], masked_stats(p[1]["id"], box, index))
                       for p in probe_pairs])
    vals_by_month: dict[tuple[int, int], list[float]] = {}
    for res in got:
        if res is None:
            continue
        mk, st = res
        if st is not None and st.get("clear_pct", 0.0) >= CLEAR_MIN_MASKED and "mean" in st:
            vals_by_month.setdefault(mk, []).append(st["mean"])

    rows: list[dict] = []
    for mk in sorted(vals_by_month):
        vals = sorted(vals_by_month[mk])
        n = len(vals)
        median = vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2.0
        rows.append({
            "date": date(mk[0], mk[1], 15).isoformat(),
            "mean": round(median, 4),
            "n_scenes": n,
        })

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
    key = cache_store.make_key("mpc-hist-m2", index, round(lat, 4), round(lon, 4),
                               int(days), int(buffer_m), bins, end.isoformat())
    hit = cache_store.get(key)
    if hit is not None:
        return hit

    items = search(box, start, end, max_cloud=MAX_CLOUD, limit=200)
    if not items:
        return None

    # Ảnh QUANG NHẤT TẠI THỬA (một cảnh mỗi ngày bay), đo bằng chính lượt thống kê đã
    # che mây — cùng cách với index_series. Bản cũ đòi 70% quang và vẽ histogram trên
    # MỌI điểm ảnh: mùa mưa thường không có cảnh nào đạt (carbon "thiếu ảnh"), còn khi
    # đạt thì mây (NDVI ≈ 0) vẫn nằm trong phân bố, kéo lệch tỉ lệ che phủ.
    probe = _spread(_one_per_date(items), min(12, len(items)))
    from app.services import jobs as _j
    fr = [g for g in _j.gather([lambda it=it: (it, masked_stats(it["id"], box, index))
                                for it in probe]) if g is not None]
    ok = [(it, st_) for it, st_ in fr
          if st_ is not None and st_.get("clear_pct", 0.0) >= CLEAR_MIN_MASKED and "mean" in st_]
    if not ok:
        return None
    ok.sort(key=lambda p: -p[1]["clear_pct"])
    it, mst = ok[0]

    # Điểm ảnh mây nhận giá trị -2, nằm NGOÀI khoảng histogram [-1, 1] nên bị loại khỏi
    # phân bố; trung bình/độ lệch lấy từ masked_stats (chỉ điểm ảnh quang).
    q = urllib.parse.urlencode({
        "collection": COLLECTION, "item": it["id"],
        "expression": f"where({_SCL_MASK},{EXPR[index]},-2)", "asset_as_band": "true",
        "histogram_bins": str(int(bins)), "histogram_range": "-1,1",
    })
    r = _call(f"{DATA}?{q}", _poly(box))
    if not r:
        return None
    try:
        st = dict(list(r["properties"]["statistics"].values())[0])
        counts, edges = st["histogram"][0], st["histogram"][1]
    except (KeyError, IndexError, TypeError):
        return None
    st.update({"mean": mst["mean"], "std": mst["std"], "count": mst["count"]})

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
        "source": tr("Microsoft Planetary Computer · Sentinel-2 L2A (không cần khoá)",
                     "Microsoft Planetary Computer · Sentinel-2 L2A (no key needed)"),
    }
    closed = end < date.today() - timedelta(days=14)
    cache_store.put(key, out, ttl_seconds=_TTL_CLOSED if closed else _TTL_RECENT)
    return out
