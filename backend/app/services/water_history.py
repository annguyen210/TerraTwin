"""LỊCH SỬ NƯỚC NHÌN XUYÊN MÂY — Sentinel-1 (radar băng C) cho TỪNG THỬA, 2017 → nay (GĐ2 kế hoạch tổng).

ĐO THẬT, KHÔNG PHẢI DỰ BÁO. Mặt nước phẳng phản xạ radar ra xa vệ tinh → tán xạ ngược VV rất thấp
(≈ −20…−25 dB; đất, cây ≈ −5…−12 dB). Radar nhìn xuyên mây, kể cả giữa cơn bão khi ảnh quang học mù.
Đo 9/10/2026 trên đồng lúa Quảng Điền (Huế): trung vị VV từ ≈ −8 dB tụt còn −16,7 dB (10/10/2020) và
−18,3 dB (13/10/2020) — đúng tuần lũ lịch sử tháng 10/2020.

PHƯƠNG PHÁP (ngưỡng, có chủ đích đơn giản để kiểm được; GĐ5 cắm mô hình học sâu vào thay ĐÚNG hàm
`flag()` mà không đổi giao diện):
  · Chỉ MỘT quỹ đạo (cùng hướng bay + cùng quỹ đạo tương đối — cùng góc nhìn), cảnh RTC đã hiệu chỉnh địa hình.
  · Mỗi cảnh: phân vị 10/25/50/75 của VV (dB) trong khung thửa.
  · Nền của CHÍNH thửa = trung vị theo thời gian của từng phân vị → không nhầm ruộng lúa ngập theo vụ hay
    mặt nước thường trực là "đợt lũ".
  · Một cảnh có nước khi phân vị q < −18 dB VÀ thấp hơn nền cùng phân vị ≥ 3 dB.
    Mức phủ: q50 → "≥ 50% thửa", q25 → "25–50%", q10 → "10–25%".
  · Các cảnh có nước cách nhau ≤ 24 ngày ghép thành một ĐỢT.

GIỚI HẠN — NÓI RA: đô thị (phản xạ kép làm nước trông sáng), rừng rậm (tán che mặt nước), sườn dốc (bóng
radar), mặt cát/đường nhựa rất phẳng có thể tối như nước; chu kỳ chụp 6–12 ngày (2022–2024 chỉ còn
Sentinel-1A: 12 ngày) có thể lọt đợt ngập ngắn hơn chu kỳ.
"""
from __future__ import annotations

import statistics
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime

from app.services import cache_store, mpc
from app.services.reqlang import tr

COLLECTION = "sentinel-1-rtc"
START_YEAR = 2017
WATER_DB = -18.0
DROP_DB = 3.0
MERGE_GAP_DAYS = 24
RADIUS_M = 100.0
PCTS = (10, 25, 50, 75)
_SCENE_TTL = 400 * 24 * 3600          # cảnh cũ không đổi
_RESULT_TTL = 6 * 24 * 3600           # có cảnh mới mỗi 6–12 ngày
JOB_KIND = "water_history"


def _db(v):
    import math
    return round(10 * math.log10(v), 2) if v and v > 0 else None


def _items(box: list[float], until: date) -> list[dict]:
    out = []
    for y in range(START_YEAR, until.year + 1):
        r = mpc._call(mpc.STAC, {"collections": [COLLECTION], "bbox": box,
                                 "datetime": f"{y}-01-01/{min(date(y, 12, 31), until).isoformat()}", "limit": 250})
        out += (r or {}).get("features") or []
    return out


def pick_track(items: list[dict]) -> tuple[str | None, int | None, list[dict]]:
    """Quỹ đạo có nhiều cảnh nhất (cùng hướng bay + cùng quỹ đạo tương đối)."""
    from collections import Counter
    c = Counter((f["properties"].get("sat:orbit_state"), f["properties"].get("sat:relative_orbit")) for f in items)
    if not c:
        return None, None, []
    (orbit, rel), _ = c.most_common(1)[0]
    sel = [f for f in items if (f["properties"].get("sat:orbit_state"), f["properties"].get("sat:relative_orbit")) == (orbit, rel)]
    seen, uniq = set(), []
    for f in sorted(sel, key=lambda f: f["properties"]["datetime"]):
        d = f["properties"]["datetime"][:10]
        if d not in seen:                       # một cảnh mỗi ngày (hai mảnh liền nhau cùng ngày)
            seen.add(d)
            uniq.append(f)
    return orbit, rel, uniq


def _scene(item_id: str, box: list[float]) -> dict | None:
    key = cache_store.make_key("s1vv", item_id, [round(v, 5) for v in box])
    hit = cache_store.get(key)
    if hit is not None:
        return hit or None
    q = urllib.parse.urlencode([("collection", COLLECTION), ("item", item_id), ("assets", "vv")] + [("p", p) for p in PCTS])
    r = mpc._call(f"{mpc.DATA}?{q}", mpc._poly(box))
    try:
        st = list(r["properties"]["statistics"].values())[0]
        out = {f"p{p}": _db(st.get(f"percentile_{p}")) for p in PCTS}
        out["mean"] = _db(st.get("mean"))
        if any(v is None for v in out.values()):
            out = {}
    except (KeyError, IndexError, TypeError):
        return None                             # lỗi mạng: không cache, lần sau thử lại
    cache_store.put(key, out, ttl_seconds=_SCENE_TTL)
    return out or None


def baseline(rows: list[dict]) -> dict:
    return {f"p{p}": round(statistics.median(r[f"p{p}"] for r in rows), 2) for p in PCTS}


def flag(row: dict, base: dict) -> str | None:
    """Mức phủ nước của một cảnh, hoặc None. GĐ5 thay hàm này bằng mô hình học sâu khi vượt cổng."""
    for p, label in ((50, "≥50%"), (25, "25–50%"), (10, "10–25%")):
        v = row[f"p{p}"]
        if v < WATER_DB and v <= base[f"p{p}"] - DROP_DB:
            return label
    return None


def events(rows: list[dict], base: dict) -> list[dict]:
    order = {"10–25%": 1, "25–50%": 2, "≥50%": 3}
    out: list[dict] = []
    for r in rows:
        f = flag(r, base)
        if not f:
            continue
        d = date.fromisoformat(r["date"])
        if out and (d - date.fromisoformat(out[-1]["end"])).days <= MERGE_GAP_DAYS:
            e = out[-1]
            e["end"] = r["date"]
            e["n_scenes"] += 1
            e["dates"].append(r["date"])
            if order[f] > order[e["peak_cover"]]:
                e["peak_cover"] = f
            e["min_p50_db"] = min(e["min_p50_db"], r["p50"])
        else:
            out.append({"start": r["date"], "end": r["date"], "n_scenes": 1, "dates": [r["date"]],
                        "peak_cover": f, "min_p50_db": r["p50"]})
    return out


def history(lat: float, lon: float, radius_m: float = RADIUS_M, today: date | None = None,
            progress=None, use_cache: bool = True) -> dict:
    today = today or date.today()
    key = cache_store.make_key("water", round(lat, 4), round(lon, 4), int(radius_m))
    if use_cache:
        hit = cache_store.get(key)
        if hit is not None:
            return hit
    box = mpc.bbox_around(lat, lon, radius_m)
    orbit, rel, items = pick_track(_items(box, today))
    if not items:
        return {"available": False, "message": tr("Không tìm thấy cảnh Sentinel-1 nào trên thửa này.",
                                                  "No Sentinel-1 scenes found over this plot.")}
    rows, done = [], 0

    def one(f):
        return f["properties"]["datetime"][:10], _scene(f["id"], box)
    with ThreadPoolExecutor(max_workers=4) as ex:
        for d, s in ex.map(one, items):
            done += 1
            if s:
                rows.append({"date": d, **s})
            if progress and done % 20 == 0:
                progress({"done": done, "total": len(items)})
    rows.sort(key=lambda r: r["date"])
    if len(rows) < 10:
        return {"available": False, "message": tr("Quá ít cảnh radar đọc được để dựng nền của thửa.",
                                                  "Too few readable radar scenes to build the plot baseline.")}
    base = baseline(rows)
    ev = events(rows, base)
    out = {
        "available": True, "evidence_class": "measured",
        "center": {"lat": lat, "lon": lon}, "radius_m": radius_m,
        "track": {"orbit": orbit, "relative_orbit": rel, "collection": COLLECTION},
        "n_scenes": len(rows), "first": rows[0]["date"], "last": rows[-1]["date"],
        "baseline_db": base, "events": ev, "n_events": len(ev),
        "series": [[r["date"], r["p50"], r["p25"]] for r in rows],
        "method": tr(
            f"Cảnh có nước khi phân vị VV < {WATER_DB:g} dB VÀ thấp hơn nền của chính thửa ≥ {DROP_DB:g} dB; "
            f"các cảnh cách nhau ≤ {MERGE_GAP_DAYS} ngày ghép thành một đợt. Một quỹ đạo cố định, ảnh RTC "
            "Sentinel-1 qua Microsoft Planetary Computer.",
            f"A scene has water when a VV percentile < {WATER_DB:g} dB AND ≥ {DROP_DB:g} dB below the plot's own "
            f"baseline; scenes ≤ {MERGE_GAP_DAYS} days apart merge into one event. One fixed orbit track, "
            "Sentinel-1 RTC via Microsoft Planetary Computer."),
        "limits": tr(
            "Đô thị (phản xạ kép), rừng rậm, sườn dốc và mặt rất phẳng có thể làm sai; chu kỳ chụp 6–12 ngày "
            "có thể lọt đợt ngập ngắn. Đây là số đo radar, không phải số liệu ngập chính thức.",
            "Urban areas (double bounce), dense forest, steep slopes and very smooth surfaces can mislead; the "
            "6–12 day revisit can miss short floods. These are radar measurements, not official flood records."),
        "computed": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    cache_store.put(key, out, ttl_seconds=_RESULT_TTL)
    return out


TILER = "https://planetarycomputer.microsoft.com/api/data/v1/item/tiles/WebMercatorQuad/{z}/{x}/{y}@1x"
# Mặt nạ hiển thị: điểm ảnh VV < −18 dB (tuyến tính 10^-1.8 ≈ 0,0158), bỏ điểm ngoài dải quét (VV = 0).
_MASK_EXPR = "where((vv>0)&(vv<0.0158),1,0)"
_MASK_COLOR = '{"1":[29,120,200,215]}'


def scene(lat: float, lon: float, day: str) -> dict | None:
    """Cảnh Sentinel-1 RTC chụp thửa ngày `day` (ưu tiên đúng quỹ đạo của lịch sử nước đã đọc) + mẫu URL
    ô ảnh để vẽ lên bản đồ: ảnh radar xám và mặt nạ nước. Trình duyệt tải ô thẳng từ Planetary Computer."""
    d = date.fromisoformat(day)
    key = cache_store.make_key("s1scene", round(lat, 4), round(lon, 4), d.isoformat())
    hit = cache_store.get(key)
    if hit is not None:
        return hit or None
    box = mpc.bbox_around(lat, lon, RADIUS_M)
    r = mpc._call(mpc.STAC, {"collections": [COLLECTION], "bbox": box,
                             "datetime": f"{d.isoformat()}T00:00:00Z/{d.isoformat()}T23:59:59Z", "limit": 10})
    if r is None:
        return None                                   # lỗi mạng: không cache
    feats = r.get("features") or []
    hist = cache_store.get(cache_store.make_key("water", round(lat, 4), round(lon, 4), int(RADIUS_M)))
    if hist and hist.get("available"):
        tr_ = (hist["track"]["orbit"], hist["track"]["relative_orbit"])
        feats = sorted(feats, key=lambda f: (f["properties"].get("sat:orbit_state"),
                                             f["properties"].get("sat:relative_orbit")) != tr_)
    if not feats:
        cache_store.put(key, {}, 86400)
        return None
    f = feats[0]
    q = urllib.parse.urlencode
    out = {
        "item": f["id"], "date": f["properties"]["datetime"][:10],
        "orbit": f["properties"].get("sat:orbit_state"), "relative_orbit": f["properties"].get("sat:relative_orbit"),
        "radar_tiles": TILER + "?" + q({"collection": COLLECTION, "item": f["id"], "assets": "vv",
                                       "rescale": "0,0.25", "colormap_name": "greys_r"}),
        "water_tiles": TILER + "?" + q({"collection": COLLECTION, "item": f["id"], "expression": _MASK_EXPR,
                                       "asset_as_band": "True", "colormap": _MASK_COLOR, "nodata": "0"}),
        "legend": tr("Xanh: điểm ảnh VV < −18 dB — mặt nước lúc chụp, GỒM CẢ sông, hồ, đầm thường trực. "
                     "Đợt nước của thửa được tính so với nền của chính thửa, không phải lớp này.",
                     "Blue: pixels with VV < −18 dB — water at capture time, INCLUDING permanent rivers, lakes and lagoons. "
                     "The plot's water events are computed against its own baseline, not this layer."),
        "attribution": "Copernicus Sentinel-1 RTC · Microsoft Planetary Computer",
    }
    cache_store.put(key, out, 30 * 86400)
    return out


def _register() -> None:
    from app.services import jobs_db

    @jobs_db.register(JOB_KIND)
    def _handle(args: dict) -> dict:
        jid = args.get("_job_id")
        return history(float(args["lat"]), float(args["lon"]),
                       progress=lambda p: jobs_db.report_progress(jid, p))


_register()
