"""SÀNG LỌC PHÁ RỪNG SAU 31/12/2020 — cho từng ranh thửa, bằng dữ liệu ĐO, ai cũng
tính lại được.

EUDR chỉ hỏi một câu về đất: thửa này có bị phá rừng (hay suy thoái rừng, với gỗ)
SAU 31/12/2020 không? Doanh nghiệp xuất khẩu phải trả lời cho từng thửa trong tờ
khai thẩm định. TerraTwin không trả lời thay họ — TerraTwin SÀNG LỌC: thửa nào rõ
ràng không có rừng lúc đó, thửa nào cần người xem tận mắt, thửa nào có dấu hiệu
mất cây sau mốc. Đây không phải chứng nhận.

BA BẢN ĐỒ RỪNG QUANH NĂM 2020, ĐỘC LẬP NHAU, đều công khai, tính ngay trên ranh
thửa qua Microsoft Planetary Computer (không khoá, không tải tệp về máy chủ):
  · ESA WorldCover 2020 v100 — 10 m, quang học + radar Sentinel; lớp "Tán cây"
    và "Rừng ngập mặn".
  · JAXA ALOS PALSAR Forest/Non-Forest 2020 — 25 m, RADAR băng L (nhạy với thân
    gỗ cao, cách đo khác hẳn ảnh quang học); lớp rừng dày + rừng thưa.
  · Impact Observatory / Esri Annual Land Cover — có TỪNG NĂM 2017–2023. Lấy
    TRUNG BÌNH 2018–2020 cho mốc, 2022–2023 cho hiện tại: đo thật ở Vườn quốc
    gia Yok Đôn (3/10/2026) thấy bản đồ này nhảy "Cây" ↔ "Đồng cỏ" qua từng năm
    ở rừng khộp thưa (2017 cây, 2020 cỏ, 2022 cây, 2023 cỏ) — so một năm với một
    năm là sinh ra "mất rừng" giả.
Cộng ảnh Sentinel-2 cùng MÙA (tháng 11 – tháng 2) ngay quanh mốc 31/12/2020 và mùa
gần nhất: NDVI trong ranh + ảnh màu thật để người đọc tự nhìn. So khác mùa thì
rừng khộp rụng lá mùa khô cũng thành "mất cây".

BỎ PHIẾU, KHÔNG TIN MỘT BẢN ĐỒ. Đo thật (3/10/2026): vườn cà phê gần Buôn Ma Thuột
và vườn cây ăn trái Cần Thơ bị WorldCover vẽ 76–78% "tán cây", trong khi radar
ALOS và Impact Observatory đều 0% rừng. EUDR KHÔNG coi đất nông nghiệp có cây là
rừng (Điều 2(4)). Một bản đồ đơn lẻ nói "có cây" vì thế không đủ để gắn cờ.

KHÔNG dùng chênh lệch WorldCover 2020 → 2021 làm dấu hiệu mất rừng: ESA nói rõ
hai bản dùng thuật toán khác nhau, khác biệt chủ yếu do thuật toán, không phải
thay đổi thật. Bản 2021 chỉ hiện để tham khảo.

QUY TẮC (chốt TRƯỚC bài kiểm định độc lập, không chỉnh theo kết quả — xem
THRESHOLDS và data/eudr_validation.json). "Phiếu rừng" = bản đồ có ≥10% diện tích
thửa là rừng (ngưỡng tán 10% của định nghĩa rừng EU/FAO); "phiếu mạnh" = ≥30%.
"Mất cây" = tán cây Impact Observatory TB 2022–2023 thấp hơn TB 2018–2020 ≥20 điểm
%, HOẶC NDVI cùng mùa giảm ≥0,15 từ mức rừng ≥0,6.
  RỦI RO          ≥2 phiếu mạnh VÀ mất cây.
  CẦN XEM LẠI     ≥2 phiếu rừng; hoặc 1 phiếu rừng kèm mất cây; hoặc chỉ có 2 bản
                  đồ mà chúng bất đồng; hoặc tâm thửa trong khu bảo tồn (OSM).
  ĐẠT SÀNG LỌC    0 phiếu rừng, hoặc 1/3 phiếu (thường là cây lâu năm che bóng)
                  và không mất cây.
  CHƯA ĐỦ DỮ LIỆU lấy được dưới 2/3 bản đồ.
"""
from __future__ import annotations

import math
import urllib.parse
from datetime import date, datetime, timezone

from app.services import cache_store, eudr_geo, mpc
from app.services.reqlang import tr

RULES = {1: "terratwin.eudr-screen/1", 2: "terratwin.eudr-screen/2", 3: "terratwin.eudr-screen/3"}
# Quy tắc ĐANG DÙNG trên production. Chỉ đổi sang bản mới SAU KHI nó đạt kiểm định độc lập
# theo giao thức đặt trước (data/eudr_validation_protocol*.json). v2 chỉ NỚI "cần xem lại"
# thành "đạt" cho thửa có tán cây thưa không mất cây — không bao giờ làm kết luận xấu đi.
ACTIVE_RULE = 1
METHOD_VERSION = RULES[ACTIVE_RULE]
CUTOFF = date(2020, 12, 31)

THRESHOLDS = {
    "forest_vote_pct": 10.0,       # ngưỡng tán 10% của định nghĩa rừng EU/FAO
    "forest_strong_pct": 30.0,
    "forest_majority_pct": 50.0,   # v2: "phiếu rừng" để CẦN XEM LẠI khi không mất cây = ≥50% thửa
    # v3: ca tán dày, KHÔNG mất cây → hỏi mô hình "rừng hay vườn cây" (đã kiểm định riêng).
    # Chỉ hạ xuống ĐẠT khi xác suất rừng ≤ 0,2 — chọn trên tập KIỂM ĐỊNH của mô hình đó
    # (4,6% rừng bị gọi nhầm là vườn, nhận ra 72,7% vườn), KHÔNG trên mẫu kiểm định v3.
    "foc_crop_max_p": 0.2,
    "loss_pts": 20.0,              # tán cây TB 2022–23 thấp hơn TB 2018–20 ≥ 20 điểm %
    "ndvi_forest": 0.6,            # NDVI trước mốc đủ cao mới xét giảm NDVI
    "ndvi_drop": 0.15,
    "s2_clear_min_pct": 80.0,      # % điểm ảnh quang mây trong khung thửa
    "min_maps": 2,
}

# id → (collection, năm, asset, mã lớp rừng/tán cây, độ phân giải m, tên)
DIRECT_2020 = {
    "wc2020": ("esa-worldcover", 2020, "map", (10, 95), 10, "ESA WorldCover 2020 v100 (10 m)"),
    "alos2020": ("alos-fnf-mosaic", 2020, "C", (1, 2), 25,
                 "JAXA ALOS PALSAR Forest/Non-Forest 2020 (radar, 25 m)"),
}
IO_NAME = "Impact Observatory/Esri Annual Land Cover (10 m), TB 2018–2020"
WC2021 = ("esa-worldcover", 2021, "map", (10, 95), 10, "ESA WorldCover 2021 v200 (10 m)")
IO = ("io-lulc-annual-v02", "data", (2,), 10)
IO_YEARS = (2017, 2018, 2019, 2020, 2021, 2022, 2023)
IO_BEFORE = (2018, 2019, 2020)
IO_AFTER = (2022, 2023)
MAP_IDS = ("wc2020", "alos2020", "io")

IMG_URL = "https://planetarycomputer.microsoft.com/api/data/v1/item/bbox"
_TTL_MAP = 180 * 86400            # bản đồ năm cũ không bao giờ đổi
_TTL_RESULT = 7 * 86400           # ảnh mùa mới nhất thì đổi — kết quả giữ 7 ngày
_CACHE_V = 2


def s2_windows(today: date | None = None) -> tuple[tuple[date, date, date], tuple[date, date, date]]:
    """(trước, sau) — mỗi cái (từ, đến, ngày ưu tiên). Cùng MÙA tháng 11 – tháng 2:
    mùa khô Tây Nguyên, ít mây nhất, và so cùng mùa thì lá rụng theo mùa không bị
    tưởng là mất cây. "Sau" = mùa ĐÃ KẾT THÚC gần nhất."""
    today = today or date.today()
    y = today.year - 1 if today >= date(today.year, 3, 1) else today.year - 2
    return ((date(2020, 11, 1), date(2021, 2, 28), CUTOFF),
            (date(y, 11, 1), date(y + 1, 2, 28), date(y, 12, 31)))


# ------------------------------------------------------------------ bản đồ lớp phủ

def _items(collection: str, year: int, bbox: tuple) -> list[str]:
    key = cache_store.make_key("eudr-items", _CACHE_V, collection, year, *[round(v, 3) for v in bbox])
    hit = cache_store.get(key)
    if hit is not None:
        return hit
    r = None
    for _ in range(3):
        r = mpc._call(mpc.STAC, {"collections": [collection], "bbox": list(bbox),
                                 "datetime": f"{year}-01-01T00:00:00Z/{year}-12-31T23:59:59Z",
                                 "limit": 10})
        if r is not None:
            break
    if r is None:
        return []
    ids = []
    for f in r.get("features") or []:
        p = f.get("properties") or {}
        if (p.get("start_datetime") or p.get("datetime") or "")[:4] == str(year):
            ids.append(f["id"])
    if ids:
        cache_store.put(key, ids, ttl_seconds=_TTL_MAP)
    return ids


def _hist(collection: str, item: str, asset: str, feature: dict) -> dict[int, float] | None:
    q = urllib.parse.urlencode({"collection": collection, "item": item, "assets": asset,
                                "categorical": "true"})
    for _ in range(3):                       # ALOS trên PC thỉnh thoảng trả 500/504
        r = mpc._call(f"{mpc.DATA}?{q}", feature)
        if r:
            try:
                st = list(r["properties"]["statistics"].values())[0]
                out: dict[int, float] = {}
                for n, c in zip(st["histogram"][0], st["histogram"][1]):
                    if n:
                        k = int(round(float(c)))
                        out[k] = out.get(k, 0.0) + float(n)
                return out
            except (KeyError, IndexError, TypeError, ValueError):
                return None
    return None


def _feature(geom) -> dict:
    return {"type": "Feature", "properties": {}, "geometry": eudr_geo.geojson_of(geom)}


def class_share(collection: str, year: int, asset: str, codes: tuple, res_m: float,
                geom, nodata: tuple = (0,)) -> dict | None:
    """% diện tích thửa thuộc các lớp `codes` trên bản đồ (collection, year).

    Thửa nhỏ hơn vài điểm ảnh: mở rộng ranh thêm 1,5 điểm ảnh rồi tính lại, ghi rõ
    `buffered_m` — thà nói "đo trên vùng rộng hơn một chút" còn hơn trả rỗng."""
    key = cache_store.make_key("eudr-share", _CACHE_V, collection, year, eudr_geo.geojson_of(geom))
    hit = cache_store.get(key)
    if hit is not None:
        return hit
    items = _items(collection, year, geom.bounds)
    if not items:
        return None
    buffered, px, valid = 0.0, 0.0, {}
    for attempt in range(2):
        g = geom
        if attempt:
            lon0 = geom.centroid.x
            buffered = round(res_m * 1.5, 1)
            g = eudr_geo.from_metric(eudr_geo.to_metric(geom, lon0).buffer(buffered), lon0)
        total: dict[int, float] = {}
        got = False
        for it in items:
            h = _hist(collection, it, asset, _feature(g))
            if h is None:
                continue
            got = True
            for k, v in h.items():
                total[k] = total.get(k, 0.0) + v
        if not got:
            return None
        valid = {k: v for k, v in total.items() if k not in nodata}
        px = sum(valid.values())
        if px >= 3:
            break
    if px <= 0:
        return None
    pct = 100.0 * sum(v for k, v in valid.items() if k in codes) / px
    out = {"pct": round(pct, 1), "pixels": int(px), "items": items, "buffered_m": buffered,
           "classes": {str(k): int(v) for k, v in sorted(valid.items())}}
    cache_store.put(key, out, ttl_seconds=_TTL_MAP)
    return out


def io_mean(traj: dict[int, float | None], years: tuple[int, ...]) -> float | None:
    vals = [traj[y] for y in years if traj.get(y) is not None]
    return round(sum(vals) / len(vals), 1) if len(vals) >= max(1, len(years) - 1) else None


# ------------------------------------------------------------------ ảnh Sentinel-2

def _image_box(geom) -> list[float]:
    """Khung ảnh vuông quanh thửa, rộng gấp ~1,8 lần thửa, tối thiểu 600 m."""
    x0, y0, x1, y1 = geom.bounds
    lat = (y0 + y1) / 2
    mx = 111_320.0 * max(0.2, math.cos(math.radians(lat)))
    half = max(max((x1 - x0) * mx, (y1 - y0) * 111_320.0) * 1.8, 600.0) / 2
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return [round(cx - half / mx, 6), round(cy - half / 111_320.0, 6),
            round(cx + half / mx, 6), round(cy + half / 111_320.0, 6)]


def _ndvi(item: str, baseline: str | None, feature: dict) -> float | None:
    try:
        off = float(baseline) >= 4.0 if baseline else False
    except ValueError:
        off = False
    # Baseline ≥ 04.00 cộng 1000 vào MỌI kênh (xem landchange.py): không trừ thì
    # NDVI sau 2022 bị kéo xuống một cách im lặng và "mất cây" giả xuất hiện.
    expr = "(B08-B04)/(B08+B04-2000)" if off else "(B08-B04)/(B08+B04)"
    q = urllib.parse.urlencode({"collection": mpc.COLLECTION, "item": item,
                                "expression": expr, "asset_as_band": "true"})
    r = mpc._call(f"{mpc.DATA}?{q}", feature)
    try:
        st = list(r["properties"]["statistics"].values())[0]
        return round(float(st["mean"]), 3) if st.get("count", 0) >= 1 else None
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def s2_scene(geom, start: date, end: date, prefer: date | None = None) -> dict | None:
    """Ảnh quang mây TẠI THỬA trong [start, end], gần ngày `prefer` nhất."""
    bounds = list(geom.bounds)
    items = mpc.search(bounds, start, end, max_cloud=70.0, limit=40)
    if not items:
        return None
    if prefer is not None:
        items = sorted(items, key=lambda it: abs((date.fromisoformat(
            (it.get("properties", {}).get("datetime") or "1970-01-01")[:10]) - prefer).days))
    feat = _feature(geom)
    for it in items[:10]:
        clear = mpc.clear_fraction(it["id"], bounds)
        if clear is None or clear < THRESHOLDS["s2_clear_min_pct"]:
            continue
        props = it.get("properties", {})
        baseline = props.get("s2:processing_baseline")
        nd = _ndvi(it["id"], baseline, feat)
        if nd is None:
            continue
        ib = _image_box(geom)
        q = urllib.parse.urlencode({"collection": mpc.COLLECTION, "item": it["id"],
                                    "assets": "visual", "asset_bidx": "visual|1,2,3"})
        return {"item": it["id"], "date": (props.get("datetime") or "")[:10],
                "clear_pct": round(clear, 1), "ndvi_mean": nd, "processing_baseline": baseline,
                "image": {"url": f"{IMG_URL}/{ib[0]},{ib[1]},{ib[2]},{ib[3]}/512x512.png?{q}",
                          "bbox": ib}}
    return None


# ------------------------------------------------------------------ khu bảo tồn

def protected_areas(lat: float, lon: float) -> dict:
    """Tâm thửa có nằm trong khu bảo tồn / vườn quốc gia theo OpenStreetMap không.
    OSM không phải bản đồ pháp lý — "không thấy" KHÁC "chắc chắn ngoài".

    Kiểm A–Z 24/11/2026: tra TẠI CHỖ ranh OSM tải sẵn (services/protected_areas.py) — hỏi Overpass mỗi lần thường ra
    "Chưa kiểm được khu bảo tồn". Overpass chỉ còn là dự phòng khi tệp thiếu/hỏng."""
    from app.services import osm, protected_areas as pa
    local = pa.inside(lat, lon)
    if local is not None:
        return {"checked": True, "inside": local, "source": f"OpenStreetMap (ranh tải {pa.fetched()})"}
    q = (f"[out:json][timeout:25];is_in({lat:.6f},{lon:.6f})->.a;"
         '(area.a["boundary"="protected_area"];area.a["boundary"="national_park"];'
         'area.a["leisure"="nature_reserve"];);out tags;')
    d = osm._query(q)
    if d is None:
        return {"checked": False, "inside": [], "source": "OpenStreetMap"}
    names = []
    for el in d.get("elements") or []:
        t = el.get("tags") or {}
        nm = t.get("name:vi") or t.get("name") or t.get("name:en")
        if nm and nm not in names:
            names.append(nm)
    return {"checked": True, "inside": names, "source": "OpenStreetMap"}


# ------------------------------------------------------------------ kết luận

LEVELS = ("low", "review", "high", "unknown")
LABELS = {
    "low": ("Đạt sàng lọc", "Passed screening"),
    "review": ("Cần xem lại", "Needs review"),
    "high": ("Rủi ro phá rừng", "Deforestation risk"),
    "unknown": ("Chưa đủ dữ liệu", "Insufficient data"),
}
_MAP_SHORT = {"wc2020": "WorldCover", "alos2020": "ALOS radar", "io": "Impact Observatory"}


def label(level: str) -> str:
    vi, en = LABELS.get(level, LABELS["unknown"])
    return tr(vi, en)


def verdict(f2020: dict, io_traj: dict, ndvi_before: float | None, ndvi_after: float | None,
            protected: list[str], rule: int | None = None,
            p_forest: float | None = None) -> tuple[str, list[str], dict]:
    """Quy tắc sàng lọc THUẦN (không mạng) — xem đầu tệp. Trả (mức, lý do, tín hiệu).

    f2020: {"wc2020": %, "alos2020": %, "io": % (TB 2018–2020)} — None nếu thiếu.
    p_forest: xác suất "rừng" của mô hình rừng-hay-vườn (chỉ quy tắc 3 dùng; None = không có
    → quy tắc 3 cư xử y như quy tắc 2, tức là luôn THẬN TRỌNG khi thiếu mô hình)."""
    T = THRESHOLDS
    rule = rule or ACTIVE_RULE
    avail = {k: v for k, v in f2020.items() if v is not None}
    votes = [k for k, v in avail.items() if v >= T["forest_vote_pct"]]
    strong = [k for k, v in avail.items() if v >= T["forest_strong_pct"]]
    majority = [k for k, v in avail.items() if v >= T["forest_majority_pct"]]
    io_b, io_a = io_mean(io_traj, IO_BEFORE), io_mean(io_traj, IO_AFTER)
    io_drop = (io_b - io_a) if io_b is not None and io_a is not None else None
    nd_drop = (ndvi_before - ndvi_after) if ndvi_before is not None and ndvi_after is not None else None
    loss_io = io_drop is not None and io_drop >= T["loss_pts"]
    loss_nd = nd_drop is not None and ndvi_before >= T["ndvi_forest"] and nd_drop >= T["ndvi_drop"]
    loss = loss_io or loss_nd
    signals = {"votes": votes, "strong": strong, "majority": majority, "rule": RULES[rule],
               "io_before_pct": io_b, "io_after_pct": io_a,
               "io_drop_pts": None if io_drop is None else round(io_drop, 1),
               "ndvi_drop": None if nd_drop is None else round(nd_drop, 3),
               "loss": loss, "loss_by": [n for n, b in (("io", loss_io), ("ndvi", loss_nd)) if b],
               "p_forest": p_forest}

    if len(avail) < T["min_maps"]:
        return "unknown", [tr(f"Chỉ lấy được {len(avail)}/3 bản đồ rừng quanh năm 2020 — cần ít nhất 2.",
                              f"Only {len(avail)}/3 forest maps around 2020 could be read — at least 2 are needed.")], signals

    def names(ids):
        return ", ".join(f"{_MAP_SHORT[i]} {avail[i]:.0f}%" for i in ids)
    loss_txt = []
    if loss_io:
        loss_txt.append(tr(f"tán cây (Impact Observatory) từ TB {io_b:.0f}% (2018–2020) xuống {io_a:.0f}% (2022–2023)",
                           f"tree cover (Impact Observatory) from avg {io_b:.0f}% (2018–2020) to {io_a:.0f}% (2022–2023)"))
    if loss_nd:
        loss_txt.append(tr(f"NDVI cùng mùa trong ranh giảm từ {ndvi_before:.2f} xuống {ndvi_after:.2f}",
                           f"same-season NDVI inside the boundary fell from {ndvi_before:.2f} to {ndvi_after:.2f}"))
    loss_s = "; ".join(loss_txt)
    reasons: list[str] = []
    if len(strong) >= 2 and loss:
        level = "high"
        reasons.append(tr(f"{len(strong)}/{len(avail)} bản đồ cho thấy ≥30% thửa là rừng năm 2020 ({names(strong)}), "
                          f"và có dấu hiệu mất cây sau mốc: {loss_s}.",
                          f"{len(strong)}/{len(avail)} maps show ≥30% of the plot as forest in 2020 ({names(strong)}), "
                          f"and there are signs of tree loss after the cutoff: {loss_s}."))
    elif (rule >= 3 and len(majority) >= 2 and not loss and p_forest is not None
          and p_forest <= T["foc_crop_max_p"]):
        # v3 — ba bản đồ chỉ thấy "tán dày", không phân biệt rừng với cao su/cà phê/điều trồng
        # sau 2000 (kiểm định v2: 12/16 ô sai là loại này). Mô hình đọc NHỊP SINH TRƯỞNG 12
        # tháng (vườn cây có mùa thu hoạch, tỉa cành, tưới; rừng thì không) mới tách được.
        level = "low"
        reasons.append(tr(f"{len(majority)}/{len(avail)} bản đồ thấy tán cây dày năm 2020 ({names(majority)}), "
                          f"nhưng mô hình rừng-hay-vườn (đọc nhịp sinh trưởng 12 tháng Sentinel-2) chỉ cho "
                          f"{p_forest * 100:.0f}% khả năng là rừng, và không có dấu hiệu mất cây sau mốc — "
                          "nhiều khả năng là vườn cây lâu năm.",
                          f"{len(majority)}/{len(avail)} maps show dense tree cover in 2020 ({names(majority)}), "
                          f"but the forest-or-crop model (12-month Sentinel-2 growth rhythm) gives only "
                          f"{p_forest * 100:.0f}% chance of forest, and there are no tree-loss signs — most likely a tree crop."))
    elif rule >= 2 and len(majority) >= 2:
        # v2 — rừng thật gần như luôn ≥50% trên cả ba bản đồ; vườn cây lâu năm (cà phê, cao su,
        # cây ăn quả) thường chỉ 10–45% "tán cây" ở WorldCover/IO dù ALOS xếp là rừng.
        level = "review"
        reasons.append(tr(f"{len(majority)}/{len(avail)} bản đồ cho thấy PHẦN LỚN thửa (≥50%) là rừng năm 2020 "
                          f"({names(majority)}). Cần người xem ảnh, giấy tờ để phân biệt rừng với cây lâu năm.",
                          f"{len(majority)}/{len(avail)} maps show MOST of the plot (≥50%) as forest in 2020 "
                          f"({names(majority)}). A person must check imagery and documents to tell forest from tree crops."))
        if loss_txt:
            reasons.append(tr(f"Dấu hiệu mất cây sau mốc: {loss_s}.", f"Signs of tree loss after the cutoff: {loss_s}."))
    elif rule >= 2 and len(votes) >= 1 and loss:
        level = "review"
        reasons.append(tr(f"Bản đồ thấy có rừng năm 2020 ({names(votes)}) và có dấu hiệu mất cây sau mốc: {loss_s}.",
                          f"Maps show some forest in 2020 ({names(votes)}) and there are signs of tree loss: {loss_s}."))
    elif rule == 1 and len(votes) >= 2:
        level = "review"
        reasons.append(tr(f"{len(votes)}/{len(avail)} bản đồ cho thấy có rừng ≥10% diện tích năm 2020 ({names(votes)}). "
                          "Cần người xem ảnh, giấy tờ để phân biệt rừng với cây lâu năm (cao su, cà phê che bóng).",
                          f"{len(votes)}/{len(avail)} maps show ≥10% forest in 2020 ({names(votes)}). A person must "
                          "check imagery and documents to tell forest from tree crops (rubber, shaded coffee)."))
        if loss_txt:
            reasons.append(tr(f"Dấu hiệu mất cây sau mốc: {loss_s}.", f"Signs of tree loss after the cutoff: {loss_s}."))
    elif len(votes) == 1 and loss:
        level = "review"
        reasons.append(tr(f"Một bản đồ thấy rừng năm 2020 ({names(votes)}) và có dấu hiệu mất cây sau mốc: {loss_s}.",
                          f"One map shows forest in 2020 ({names(votes)}) and there are signs of tree loss: {loss_s}."))
    elif len(votes) == 1 and len(avail) < 3:
        level = "review"
        reasons.append(tr(f"Chỉ có {len(avail)} bản đồ và chúng bất đồng ({names(list(avail))}) — chưa đủ để kết luận.",
                          f"Only {len(avail)} maps and they disagree ({names(list(avail))}) — not enough to conclude."))
    else:
        level = "low"
        if rule >= 2 and len(votes) >= 2:
            reasons.append(tr(f"{len(votes)}/{len(avail)} bản đồ thấy tán cây nhưng dưới 50% diện tích thửa "
                              f"({names(list(avail))}), và không có dấu hiệu mất cây sau mốc — thường là vườn cây "
                              "lâu năm (cà phê, cao su, cây ăn quả), không phải rừng.",
                              f"{len(votes)}/{len(avail)} maps show tree cover but under 50% of the plot "
                              f"({names(list(avail))}), and no tree-loss signs after the cutoff — usually tree crops "
                              "(coffee, rubber, orchards), not forest."))
        elif votes:
            reasons.append(tr(f"Chỉ 1/3 bản đồ thấy tán cây ({names(votes)}); hai bản đồ còn lại "
                              f"({names([k for k in avail if k not in votes])}) không thấy rừng năm 2020 — thường là "
                              "cây lâu năm che bóng hoặc cây rải rác, không phải rừng.",
                              f"Only 1/3 maps shows tree cover ({names(votes)}); the other two "
                              f"({names([k for k in avail if k not in votes])}) show no forest in 2020 — usually shaded tree "
                              "crops or scattered trees, not forest."))
        else:
            reasons.append(tr(f"Cả {len(avail)} bản đồ quanh năm 2020 đều cho thấy dưới 10% thửa là rừng "
                              f"({names(list(avail))}).",
                              f"All {len(avail)} maps around 2020 show under 10% of the plot as forest "
                              f"({names(list(avail))})."))
        if nd_drop is not None and nd_drop >= T["ndvi_drop"]:
            reasons.append(tr(f"NDVI cùng mùa giảm {nd_drop:.2f} — thửa không phải rừng lúc mốc nên thường là tái "
                              "canh, thu hoạch.",
                              f"Same-season NDVI fell {nd_drop:.2f} — the plot was not forest at the cutoff, so "
                              "usually replanting or harvest."))
    if protected:
        if level == "low":
            level = "review"
        reasons.append(tr("Tâm thửa nằm trong khu bảo vệ theo OpenStreetMap: " + ", ".join(protected) +
                          " — cần kiểm tính hợp pháp của việc sản xuất ở đây.",
                          "The plot centre lies in a protected area per OpenStreetMap: " + ", ".join(protected) +
                          " — the legality of production here must be checked."))
    return level, reasons, signals


def screen(plot: dict) -> dict:
    """Sàng lọc MỘT thửa đã chuẩn hoá (eudr_geo). Không ném lỗi: nguồn nào hỏng
    thì ghi thiếu, và thiếu quá nhiều thì kết luận "chưa đủ dữ liệu"."""
    from app.services import jobs

    geom = eudr_geo.shapely_geom(plot)
    gj = eudr_geo.geojson_of(geom)
    (b0, b1, bp), (a0, a1, ap) = s2_windows()
    # Khoá cache theo SỐ ĐO (không theo quy tắc): kết luận tính lại lúc đọc (_localize), nên
    # đổi quy tắc không bắt đo lại vệ tinh.
    # raw2 (24/11/2026): số đo có thêm bản đồ rừng 2020 của EU (JRC GFC2020 v4) — kết quả nhớ đệm cũ không có.
    key = cache_store.make_key("eudr-screen", _CACHE_V, "raw2", gj, a0.isoformat())
    hit = cache_store.get(key)
    if hit is not None:
        if "loss_reference" not in hit:
            # Kết quả nhớ đệm trước 25/11/2026 chưa có hai bản đồ mất rừng — đọc thêm (mỗi bản đồ có nhớ đệm riêng 1
            # năm), KHÔNG đo lại cả 14 nguồn và không kéo dài hạn của kết quả cũ.
            hit["loss_reference"] = loss_reference(geom)
        return _localize(hit)

    tasks = [lambda d=d: class_share(d[0], d[1], d[2], d[3], d[4], geom) for d in DIRECT_2020.values()]
    tasks.append(lambda: class_share(WC2021[0], WC2021[1], WC2021[2], WC2021[3], WC2021[4], geom))
    tasks += [lambda y=y: class_share(IO[0], y, IO[1], IO[2], IO[3], geom) for y in IO_YEARS]
    tasks += [lambda: s2_scene(geom, b0, b1, prefer=bp), lambda: s2_scene(geom, a0, a1, prefer=ap)]
    c = geom.centroid
    from app.services import hansen_gfc, jrc_gfc, jrc_tmf
    tasks.append(lambda: jrc_gfc.forest_share(geom))
    tasks.append(lambda: protected_areas(c.y, c.x))
    tasks += [lambda: jrc_tmf.change(geom), lambda: hansen_gfc.loss(geom)]
    got = jobs.gather(tasks, timeout=240.0)
    tmf, hansen = got[-2], got[-1]
    got = got[:-2]

    nd = len(DIRECT_2020)
    direct = dict(zip(DIRECT_2020.keys(), got[:nd]))
    wc2021 = got[nd]
    io_raw = dict(zip(IO_YEARS, got[nd + 1: nd + 1 + len(IO_YEARS)]))
    s2_before, s2_after, eu_ref, prot = got[-4], got[-3], got[-2], got[-1] or {"checked": False, "inside": []}
    traj = {y: (v or {}).get("pct") for y, v in io_raw.items()}
    io_b = io_mean(traj, IO_BEFORE)

    forest = [{"id": k, "name": DIRECT_2020[k][5], "collection": DIRECT_2020[k][0], "res_m": DIRECT_2020[k][4],
               **(v or {"pct": None})} for k, v in direct.items()]
    forest.append({"id": "io", "name": IO_NAME, "collection": IO[0], "res_m": IO[3], "pct": io_b,
                   "years": list(IO_BEFORE),
                   "items": [it for y in IO_BEFORE for it in ((io_raw.get(y) or {}).get("items") or [])],
                   "pixels": (io_raw.get(2020) or {}).get("pixels"),
                   "buffered_m": (io_raw.get(2020) or {}).get("buffered_m", 0.0)})
    raw = {
        "method": METHOD_VERSION, "cutoff": CUTOFF.isoformat(),
        "computed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "plot": {"area_ha": plot.get("area_ha"), "kind": plot.get("kind"),
                 "geometry_used": "polygon" if plot.get("kind") == "polygon" else "circle_from_point",
                 "centroid": plot.get("centroid")},
        "forest_2020": forest,
        "wc2021": ({"name": WC2021[5], **wc2021} if wc2021 else None),
        "io_trajectory": [{"year": y, "tree_pct": traj.get(y),
                           "item": ((io_raw.get(y) or {}).get("items") or [None])[0]} for y in IO_YEARS],
        "s2": {"before": s2_before, "after": s2_after,
               "windows": {"before": [b0.isoformat(), b1.isoformat()], "after": [a0.isoformat(), a1.isoformat()]}},
        "protected": prot, "thresholds": THRESHOLDS,
        # Bản đồ THAM CHIẾU — không phải phiếu của quy tắc v1 (xem eu_reference_note).
        "eu_reference": ({"id": "jrc2020", "name": jrc_gfc.NAME, "name_en": jrc_gfc.NAME_EN,
                          "source": "European Commission, Joint Research Centre — GFC2020 v4", **eu_ref}
                         if eu_ref else None),
        # Hai bản đồ MẤT RỪNG SAU MỐC theo năm (25/11/2026) — cũng là tham chiếu, xem loss_reference_note.
        "loss_reference": loss_reference(geom, (tmf, hansen)),
    }
    if sum(f.get("pct") is not None for f in forest) >= THRESHOLDS["min_maps"]:
        cache_store.put(key, raw, ttl_seconds=_TTL_RESULT)
    return _localize(raw)


def loss_reference(geom, got: tuple | None = None) -> dict:
    """JRC TMF (rừng ẩm 2020 → mất/suy thoái theo năm) + Hansen/GFW (năm mất tán cây). Mỗi bên None nếu chưa đọc được."""
    from app.services import hansen_gfc, jobs, jrc_tmf
    if got is None:
        got = jobs.gather([lambda: jrc_tmf.change(geom), lambda: hansen_gfc.loss(geom)], timeout=180.0)
    tmf, han = got
    return {
        "tmf": ({"id": "jrc_tmf", "name": jrc_tmf.NAME, "name_en": jrc_tmf.NAME_EN,
                 "source": "European Commission, Joint Research Centre — Tropical Moist Forest (Vancutsem et al. 2021)",
                 **tmf} if tmf else None),
        "hansen": ({"id": "hansen_gfc", "name": hansen_gfc.NAME, "name_en": hansen_gfc.NAME_EN,
                    "source": "Hansen et al. 2013, University of Maryland — Global Forest Change " + hansen_gfc.VERSION,
                    **han} if han else None),
    }


def _localize(raw: dict, rule: int | None = None, p_forest: float | None = None) -> dict:
    """Mức, lý do, chú thích tính lại lúc ĐỌC từ số đo (cache dùng chung hai ngôn ngữ,
    và ai cầm số đo cũng tự tính lại ra đúng kết luận này)."""
    f2020 = {f["id"]: f.get("pct") for f in raw["forest_2020"]}
    traj = {r["year"]: r["tree_pct"] for r in raw["io_trajectory"]}
    s2 = raw.get("s2") or {}
    level, reasons, signals = verdict(f2020, traj, (s2.get("before") or {}).get("ndvi_mean"),
                                      (s2.get("after") or {}).get("ndvi_mean"),
                                      (raw.get("protected") or {}).get("inside") or [], rule=rule,
                                      p_forest=p_forest)
    eu = raw.get("eu_reference")
    note = eu_reference_note(level, eu.get("pct") if eu else None)
    if note:
        reasons = [*reasons, note]
    lr = raw.get("loss_reference")
    lnote = loss_reference_note(level, lr)
    if lnote:
        reasons = [*reasons, lnote]
    tmf, han = (lr or {}).get("tmf"), (lr or {}).get("hansen")
    signals = {**signals, "eu_reference_pct": eu.get("pct") if eu else None,
               "tmf_lost_after_2020_pct": tmf.get("lost_after_2020_pct") if tmf else None,
               "hansen_loss_after_2020_pct": han.get("loss_after_2020_pct") if han else None}
    out = dict(raw)
    out.update(level=level, label=label(level), reasons=reasons, signals=signals, caveats=caveats(raw),
               method=RULES[rule or ACTIVE_RULE])
    return out


def eu_reference_note(level: str, eu_pct: float | None) -> str | None:
    """Câu đối chiếu với bản đồ rừng 2020 của EU (JRC GFC2020 v4). KHÔNG đổi mức kết luận: quy tắc đang dùng (v1) chốt
    trước kiểm định với ba bản đồ; muốn cho bản đồ EU bỏ phiếu phải qua giao thức kiểm định như v2/v3. Chỉ nói rõ khi
    hai bên bất đồng — đó đúng là chỗ người giải trình cần (cà phê, cao su bị ba bản đồ kia vẽ thành rừng)."""
    if eu_pct is None or level == "unknown":
        return None
    T = THRESHOLDS["forest_vote_pct"]
    if level in ("high", "review") and eu_pct < T:
        return tr(f"Bản đồ rừng 2020 của chính EU (JRC GFC2020 v4) chỉ thấy {eu_pct:g}% rừng trong ranh — trái với các bản "
                  "đồ trên. Thường gặp ở cà phê, cao su, cây ăn quả, thứ EU không coi là rừng. Kèm đối chiếu này khi giải "
                  "trình; mức kết luận CHƯA đổi vì quy tắc đang dùng chưa tính bản đồ này.",
                  f"The EU's own 2020 forest map (JRC GFC2020 v4) sees only {eu_pct:g}% forest inside the boundary — "
                  "contradicting the maps above. Typical of coffee, rubber and orchards, which the EU does not count as "
                  "forest. Attach this when justifying; the level is NOT changed because the active rule does not use "
                  "this map yet.")
    if level == "low" and eu_pct >= T:
        return tr(f"Bản đồ rừng 2020 của chính EU (JRC GFC2020 v4) thấy {eu_pct:g}% rừng trong ranh — nên xem lại ảnh và "
                  "giấy tờ trước khi nộp tờ khai.",
                  f"The EU's own 2020 forest map (JRC GFC2020 v4) sees {eu_pct:g}% forest inside the boundary — review the "
                  "imagery and papers before filing the statement.")
    return tr(f"Bản đồ rừng 2020 của chính EU (JRC GFC2020 v4) cùng chiều: {eu_pct:g}% rừng trong ranh.",
              f"The EU's own 2020 forest map (JRC GFC2020 v4) agrees: {eu_pct:g}% forest inside the boundary.")


# Phần thửa (%) mất sau mốc để câu đối chiếu nói thành lời — dưới mức này là nhiễu mép ranh/điểm ảnh lẻ. Chốt TRƯỚC khi
# chạy trên mẫu nào (25/11/2026) và chỉ quyết định CÂU CHỮ, không quyết định mức kết luận.
LOSS_NOTE_PCT = 1.0


def _years(by_year: dict | None) -> str:
    return ", ".join(sorted((by_year or {}).keys()))


def _ha(v: float) -> str:
    return f"{v:.3g}"


def loss_reference_note(level: str, lr: dict | None) -> str | None:
    """Câu đối chiếu với hai bản đồ mất rừng theo năm. Như eu_reference_note: KHÔNG đổi mức (quy tắc v1 chốt trước
    kiểm định với ba bản đồ), chỉ nói rõ hai bản đồ thấy gì — nhất là khi trái với kết luận. "Mất" (TMF rời lớp rừng,
    Hansen mất cả tán) và "suy thoái" (TMF: rừng nguyên vẹn → suy thoái) là hai chuyện khác nhau, nói riêng."""
    if not lr or level == "unknown":
        return None
    tmf, han = lr.get("tmf"), lr.get("hansen")
    if not tmf and not han:
        return None
    T = LOSS_NOTE_PCT
    t_lost = bool(tmf) and tmf.get("lost_after_2020_pct", 0) >= T
    h_lost = bool(han) and han.get("loss_after_2020_pct", 0) >= T
    deg = bool(tmf) and tmf.get("degraded_after_2020_pct", 0) >= T
    names = " và ".join(n for n, x in (("JRC TMF", tmf), ("Hansen/GFW", han)) if x)
    names_en = " and ".join(n for n, x in (("JRC TMF", tmf), ("Hansen/GFW", han)) if x)
    deg_vi = deg_en = ""
    if deg:
        deg_vi = (f"JRC TMF thấy {tmf['degraded_after_2020_pct']:g}% thửa là rừng nguyên vẹn năm 2020 bị suy thoái (chặt "
                  f"chọn, cháy) sau mốc (năm {_years(tmf.get('degraded_by_year'))})")
        deg_en = (f"JRC TMF sees {tmf['degraded_after_2020_pct']:g}% of the plot as undisturbed 2020 forest degraded "
                  f"(selective logging, fire) after the cutoff (year {_years(tmf.get('degraded_by_year'))})")
    vi, en = [], []
    if t_lost:
        vi.append(f"JRC TMF của EU thấy {tmf['lost_after_2020_pct']:g}% thửa (~{_ha(tmf['lost_after_2020_ha'])} ha) là "
                  f"rừng ẩm năm 2020 đã bị mất sau mốc (năm {_years(tmf.get('lost_by_year'))})")
        en.append(f"the EU's JRC TMF sees {tmf['lost_after_2020_pct']:g}% of the plot (~{_ha(tmf['lost_after_2020_ha'])} "
                  f"ha) as 2020 moist forest lost after the cutoff (year {_years(tmf.get('lost_by_year'))})")
    if h_lost:
        vi.append(f"Hansen/GFW thấy {han['loss_after_2020_pct']:g}% thửa (~{_ha(han['loss_after_2020_ha'])} ha) mất tán "
                  f"cây trong 2021–{han.get('last_year', 2024)} (năm {_years(han.get('loss_by_year'))})")
        en.append(f"Hansen/GFW sees {han['loss_after_2020_pct']:g}% of the plot (~{_ha(han['loss_after_2020_ha'])} ha) "
                  f"losing tree cover in 2021–{han.get('last_year', 2024)} (year {_years(han.get('loss_by_year'))})")
    keep_vi = " Mức kết luận CHƯA đổi vì quy tắc đang dùng chưa tính hai bản đồ này."
    keep_en = " The level is NOT changed because the active rule does not use these maps yet."
    if vi:
        harvest_vi = (" Mất tán cây theo Hansen cũng có thể là thu hoạch rừng trồng hoặc tái canh vườn." if h_lost else "")
        harvest_en = (" Hansen tree-cover loss can also be a plantation harvest or orchard replanting." if h_lost else "")
        more_vi, more_en = (f" Ngoài ra, {deg_vi}.", f" Also, {deg_en}.") if deg else ("", "")
        if level == "low":
            return tr(f"Bản đồ mất rừng theo năm: {'; '.join(vi)} — trái với kết luận trên.{more_vi}{harvest_vi} Xem hai "
                      f"ảnh Sentinel-2 bên dưới và giấy tờ trước khi nộp tờ khai.{keep_vi}",
                      f"Annual forest-loss maps: {'; '.join(en)} — contradicting the conclusion above.{more_en}"
                      f"{harvest_en} Check the two Sentinel-2 images below and the papers before filing.{keep_en}")
        return tr(f"Bản đồ mất rừng theo năm: {'; '.join(vi)}.{more_vi}{harvest_vi} Đối chiếu ảnh và giấy tờ.",
                  f"Annual forest-loss maps: {'; '.join(en)}.{more_en}{harvest_en} Compare with imagery and papers.")
    agree = level == "low"                    # "Đạt" + không thấy mất = cùng chiều
    none_vi = (f"{names} {'cùng ' if agree else ''}không thấy mất rừng hay mất tán cây đáng kể (dưới {T:g}% thửa) sau "
               "31/12/2020 trong ranh")
    none_en = (f"{names_en} {'also ' if agree else ''}see no significant forest or tree-cover loss (under {T:g}% of the "
               "plot) after 31/12/2020 inside the boundary")
    if deg:
        none_vi += f"; riêng {deg_vi}"
        none_en += f"; however, {deg_en}"
    if level in ("high", "review"):
        return tr(f"{none_vi} — kèm đối chiếu này khi giải trình.{keep_vi}", f"{none_en} — attach this when justifying.{keep_en}")
    if deg:
        return tr(f"{none_vi} — nên xem ảnh trước khi nộp tờ khai.{keep_vi}",
                  f"{none_en} — review the imagery before filing.{keep_en}")
    return tr(f"{none_vi}.", f"{none_en}.")


def caveats(raw: dict) -> list[str]:
    out = [tr("Đây là SÀNG LỌC từ bản đồ vệ tinh công khai, không phải chứng nhận tuân thủ EUDR. Định nghĩa "
              "rừng của EU loại trừ đất nông nghiệp có cây (cà phê che bóng, cao su) — bản đồ không phân biệt "
              "được hết. Kết luận cuối cùng thuộc về người nộp tờ khai thẩm định.",
              "This is SCREENING from public satellite maps, not EUDR compliance certification. The EU forest "
              "definition excludes agricultural land with trees (shaded coffee, rubber) — maps cannot always "
              "tell them apart. The final call rests with whoever files the due diligence statement.")]
    if (raw.get("plot") or {}).get("geometry_used") == "circle_from_point":
        out.append(tr("Thửa khai bằng MỘT ĐIỂM: đã sàng lọc trên hình tròn đúng diện tích khai quanh điểm đó "
                      "(4 ha nếu không khai) — ranh thật có thể khác. Đo ranh để kết quả sát hơn.",
                      "Plot declared as a POINT: screened on a circle of the declared area around it (4 ha if "
                      "none) — the real boundary may differ. Measure the boundary for a closer result."))
    if any((f.get("buffered_m") or 0) > 0 for f in raw.get("forest_2020") or []):
        out.append(tr("Thửa nhỏ hơn vài điểm ảnh bản đồ: đã đo trên ranh nới rộng thêm 15–40 m.",
                      "Plot smaller than a few map pixels: measured on the boundary widened by 15–40 m."))
    s2 = raw.get("s2") or {}
    if not s2.get("before") or not s2.get("after"):
        out.append(tr("Thiếu ảnh Sentinel-2 quang mây cùng mùa (tháng 11 – tháng 2) cho một trong hai mốc — chỉ "
                      "dùng bản đồ.",
                      "No cloud-free same-season (Nov–Feb) Sentinel-2 image for one of the two dates — maps only."))
    if "eu_reference" in raw and raw["eu_reference"] is None:
        out.append(tr("Chưa đọc được bản đồ rừng 2020 của EU (JRC GFC2020) lúc này — dịch vụ của JRC không phản hồi.",
                      "Could not read the EU's 2020 forest map (JRC GFC2020) right now — the JRC service did not respond."))
    if "loss_reference" in raw:
        lr = raw.get("loss_reference") or {}
        miss = [n for n, k in (("JRC TMF", "tmf"), ("Hansen/GFW", "hansen")) if not lr.get(k)]
        if miss:
            out.append(tr(f"Chưa đọc được bản đồ mất rừng theo năm ({', '.join(miss)}) lúc này — nguồn không phản hồi.",
                          f"Could not read the annual forest-loss map ({', '.join(miss)}) right now — the source did not "
                          "respond."))
        tmf = lr.get("tmf")
        if tmf and tmf.get("forest2020_pct", 0) < LOSS_NOTE_PCT:
            out.append(tr("JRC TMF chỉ vẽ rừng ẨM nhiệt đới: rừng khộp khô (Tây Nguyên) thường bị xếp “đất khác” — 0% rừng "
                          "ẩm ở đây không có nghĩa là không có rừng.",
                          "JRC TMF maps only MOIST tropical forest: dry dipterocarp forest (Central Highlands) is often "
                          "classed as “other land” — 0% moist forest here does not mean no forest."))
    if not ((raw.get("protected") or {}).get("checked")):
        out.append(tr("Chưa kiểm được khu bảo tồn (OpenStreetMap không phản hồi).",
                      "Protected areas could not be checked (OpenStreetMap did not respond)."))
    return out


def sources() -> list[str]:
    from app.services import jrc_gfc
    from app.services import hansen_gfc, jrc_tmf
    return [DIRECT_2020[k][5] for k in DIRECT_2020] + [jrc_gfc.NAME + " — tham chiếu, không bỏ phiếu",
                                                       jrc_tmf.NAME + " — tham chiếu, không bỏ phiếu",
                                                       hansen_gfc.NAME + " — tham chiếu, không bỏ phiếu"] + [
        "Impact Observatory/Esri Annual Land Cover 2017–2023 (10 m)", WC2021[5],
        "Copernicus Sentinel-2 L2A — Microsoft Planetary Computer",
        "OpenStreetMap — khu bảo tồn, vườn quốc gia",
    ]
