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

import os
import statistics
import time
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
_PARTIAL_TTL = 6 * 3600                # còn cảnh lỗi mạng → đọc lại sớm (cảnh đã đọc nằm trong cache, chỉ đọc phần thiếu)
# Số lượt đọc song song tới Planetary Computer. Thời gian chủ yếu là CHỜ mạng (~1,3 s/cảnh), không phải CPU.
# Đo 18/10/2026 — local: 4 luồng 3,0 cảnh/s · 8 luồng 5,3 · 12 luồng 6,5. Production (Render gói miễn phí, ít CPU):
# 4 luồng ~181 s · 8 luồng 459 cảnh / 71,6 s · 12 luồng 459 cảnh / 77,7 s — quá 8 thì CPU là nút thắt, chỉ thêm tải lên
# nguồn. Giữ 8. 0 cảnh lỗi ở mọi lượt đo; cảnh lỗi (nếu có) được thử lại và ghi số thiếu.
S1_WORKERS = max(1, int(os.environ.get("TERRATWIN_S1_WORKERS", "8")))
RETRY_ROUNDS = 2
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


def _scene_status(item_id: str, box: list[float]) -> tuple[str, dict | None]:
    """("ok", số đo) · ("empty", None) = cảnh không có điểm ảnh hợp lệ trong khung (đã cache) · ("error", None) = lỗi
    mạng / máy chủ — KHÔNG cache, phải thử lại. Trước 18/10/2026 hai trường hợp sau lẫn nhau: cảnh lỗi mạng bị bỏ im lặng."""
    key = cache_store.make_key("s1vv", item_id, [round(v, 5) for v in box])
    hit = cache_store.get(key)
    if hit is not None:
        return ("ok", hit) if hit else ("empty", None)
    q = urllib.parse.urlencode([("collection", COLLECTION), ("item", item_id), ("assets", "vv")] + [("p", p) for p in PCTS])
    r = mpc._call(f"{mpc.DATA}?{q}", mpc._poly(box))
    try:
        st = list(r["properties"]["statistics"].values())[0]
        out = {f"p{p}": _db(st.get(f"percentile_{p}")) for p in PCTS}
        out["mean"] = _db(st.get("mean"))
        if any(v is None for v in out.values()):
            out = {}
    except (KeyError, IndexError, TypeError):
        return ("error", None)                  # lỗi mạng: không cache, lần sau thử lại
    cache_store.put(key, out, ttl_seconds=_SCENE_TTL)
    return ("ok", out) if out else ("empty", None)


def _scene(item_id: str, box: list[float]) -> dict | None:
    return _scene_status(item_id, box)[1]


def baseline(rows: list[dict]) -> dict:
    return {f"p{p}": round(statistics.median(r[f"p{p}"] for r in rows), 2) for p in PCTS}


def cache_key(lat: float, lon: float, radius_m: float = RADIUS_M) -> str:
    """Khoá cache kết quả lịch sử nước của thửa — MỘT chỗ duy nhất cho mọi nơi đọc (hồ sơ, tin đăng, sổ tay,
    so sánh). v2 (12/10/2026): mỗi đợt có thêm phân vị quyết định — kết quả cũ thiếu trường đó nên bỏ."""
    return cache_store.make_key("water", round(lat, 4), round(lon, 4), int(radius_m), "v2")


def flag_detail(row: dict, base: dict) -> tuple[str, int, float] | None:
    """(mức phủ, phân vị đã quyết định, giá trị dB của phân vị đó) — hoặc None nếu cảnh không có nước."""
    for p, label in ((50, "≥50%"), (25, "25–50%"), (10, "10–25%")):
        v = row[f"p{p}"]
        if v < WATER_DB and v <= base[f"p{p}"] - DROP_DB:
            return label, p, v
    return None


def flag(row: dict, base: dict) -> str | None:
    """Mức phủ nước của một cảnh, hoặc None. GĐ5 thay hàm này bằng mô hình học sâu khi vượt cổng."""
    d = flag_detail(row, base)
    return d[0] if d else None


def events(rows: list[dict], base: dict) -> list[dict]:
    order = {"10–25%": 1, "25–50%": 2, "≥50%": 3}
    out: list[dict] = []
    # Mỗi đợt ghi ĐÚNG đại lượng đã quyết định (báo cáo kiểm toàn bộ 12/10/2026, mục 6): trước đây chỉ in trung vị
    # (vd −14,48 dB) trong khi quy tắc bắt nước ở phân vị 10/25 < −18 dB — người đọc thấy "−14 mà gọi là nước?".
    # flag_pct = phân vị của mức phủ cao nhất trong đợt; min_flag_db = giá trị thấp nhất của phân vị đó trong đợt.
    for r in rows:
        det = flag_detail(r, base)
        if not det:
            continue
        f, pct, v = det
        d = date.fromisoformat(r["date"])
        if out and (d - date.fromisoformat(out[-1]["end"])).days <= MERGE_GAP_DAYS:
            e = out[-1]
            e["end"] = r["date"]
            e["n_scenes"] += 1
            e["dates"].append(r["date"])
            if order[f] > order[e["peak_cover"]]:
                e.update(peak_cover=f, flag_pct=pct, min_flag_db=v, flag_date=r["date"])
            elif f == e["peak_cover"] and v < e["min_flag_db"]:
                e.update(min_flag_db=v, flag_date=r["date"])
            e["min_p50_db"] = min(e["min_p50_db"], r["p50"])
        else:
            out.append({"start": r["date"], "end": r["date"], "n_scenes": 1, "dates": [r["date"]],
                        "peak_cover": f, "flag_pct": pct, "min_flag_db": v, "flag_date": r["date"],
                        "min_p50_db": r["p50"]})
    return out


def water_surface(base: dict | None) -> dict | None:
    """Khung đo có MẶT NƯỚC THƯỜNG XUYÊN không (theo nền của chính thửa)?

    Nền một phân vị dưới ngưỡng nước nghĩa là phần khung đó là nước ở HẦU HẾT các lần chụp — nước quanh năm thì
    không bao giờ "thấp hơn nền ≥ 3 dB", nên "0 đợt nước" ở phần đó KHÔNG có nghĩa là không ngập (16/10/2026,
    giữa sông Thu Bồn: nền p10 −19,1 dB, 0 đợt). Trả mức ≥ 10% / ≥ 25% / ≥ 50% khung, hoặc None."""
    if not base:
        return None
    for p, share in ((50, "≥50%"), (25, "≥25%"), (10, "≥10%")):
        v = base.get(f"p{p}")
        if v is not None and v < WATER_DB:
            return {"share": share, "pct": p, "baseline_db": v,
                    "note": tr(f"{share} khung đo 200 m là MẶT NƯỚC THƯỜNG XUYÊN (nền p{p} = {v:g} dB < {WATER_DB:g} dB). "
                               "Phần đó nước có sẵn quanh năm nên không đếm được \"đợt nước\" — \"0 đợt\" không có nghĩa là không ngập. "
                               "Kiểm lại ô ngắm có nằm đúng thửa đất không.",
                               f"{share} of the 200 m frame is PERMANENT WATER (baseline p{p} = {v:g} dB < {WATER_DB:g} dB). "
                               "That part holds water all year, so no \"water events\" can be counted there — \"0 events\" does not mean no flooding. "
                               "Check that the crosshair is on the actual plot.")}
    return None


URBAN_BUILT_PCT = 40.0      # WorldCover "Bề mặt xây dựng" (mã 50) trong khung đo → khu đô thị


CANOPY_PCT = 60.0          # WorldCover Tán cây (10) + Rừng ngập mặn (95) trong khung đo → tán dày che mặt nước
CROP_PCT = 50.0            # WorldCover Đất trồng trọt (40) → nhắc: nước tưới theo vụ cũng hiện thành "đợt nước"


def _frame_pct(lat: float, lon: float) -> dict[int, float] | None:
    """Tỉ lệ % từng mã WorldCover trong ĐÚNG khung đo radar (bán kính RADIUS_M), hoặc None nếu không đọc được."""
    from app.services import landuse
    try:
        raw = landuse.fetch_raw(lat, lon, RADIUS_M)
    except Exception:  # noqa: BLE001
        return None
    if not raw or not raw.get("hist"):
        return None
    hist = {int(k): float(v) for k, v in raw["hist"].items()}
    tot = sum(hist.values()) or 1.0
    return {k: 100.0 * v / tot for k, v in hist.items()}


def canopy(lat: float, lon: float) -> dict | None:
    """Khung đo dưới TÁN CÂY DÀY (rừng, vườn dừa, cà phê, rừng ngập mặn): sóng radar băng C không xuyên tán dày nên
    không thấy nước bên dưới — "0 đợt" ở đây cũng KHÔNG có nghĩa là không ngập (cùng loại sai với đô thị, 17/10/2026)."""
    f = _frame_pct(lat, lon)
    if not f:
        return None
    pct = round(f.get(10, 0.0) + f.get(95, 0.0), 1)
    if pct < CANOPY_PCT:
        return None
    return {"tree_pct": pct,
            "note": tr(f"Tán cây dày (ESA WorldCover: {pct:g}% khung đo là tán cây/rừng ngập mặn): radar KHÔNG nhìn thấy được nước "
                       "dưới tán — \"0 đợt\" ở đây KHÔNG có nghĩa là không ngập.",
                       f"Dense tree canopy (ESA WorldCover: {pct:g}% of the frame is tree cover/mangrove): radar CANNOT see water "
                       "beneath the canopy — \"0 events\" here does NOT mean no flooding.")}


def cropland(lat: float, lon: float) -> dict | None:
    """Khung đo là ruộng: nước TƯỚI theo vụ (cho nước vào ruộng lúa) cũng làm VV tụt như lũ, nên một phần "đợt nước phủ"
    có thể là nước tưới. Đo 17/10/2026: ruộng phía đông Huế 16.43, 107.65 có đợt tháng 5–6 và 9–10 hằng năm (lịch cho
    nước), trong khi đồng lúa Quảng Điền 7 đợt đều rơi vào mùa lũ 10–1. Chỉ là LỜI NHẮC — không đổi quy tắc đã qua cổng."""
    f = _frame_pct(lat, lon)
    if not f or f.get(40, 0.0) < CROP_PCT:
        return None
    pct = round(f.get(40, 0.0), 1)
    return {"crop_pct": pct,
            "note": tr(f"Ruộng (ESA WorldCover: {pct:g}% khung đo là đất trồng trọt): nước tưới theo vụ cũng làm radar thấy \"nước phủ\" — "
                       "đối chiếu tháng của từng đợt với mùa lũ địa phương trước khi kết luận là lũ.",
                       f"Cropland (ESA WorldCover: {pct:g}% of the frame): seasonal irrigation also shows up as \"water cover\" — "
                       "compare each event's month with the local flood season before calling it a flood.")}


def urban(lat: float, lon: float) -> dict | None:
    """Khung đo radar (bán kính 100 m) có phải KHU ĐÔ THỊ không — nơi radar KHÔNG nhìn thấy được ngập.

    Giữa nhà cửa, sóng radar dội hai lần (mặt nước → tường → vệ tinh) nên vùng ngập trông SÁNG chứ không tối; "0 đợt
    nước" ở đó không có nghĩa là không ngập. Đo 17/10/2026 trên production, tin "Nhà phố không bao giờ ngập nước" bị
    chấm Khớp ở Hoàn Kiếm (0 đợt/284 cảnh), TP Bến Tre (0/451), TP Cà Mau (0/440). FAIL-OPEN: không đọc được
    WorldCover → None (không suy diễn là đô thị)."""
    f = _frame_pct(lat, lon)
    if not f:
        return None
    pct = round(f.get(50, 0.0), 1)
    if pct < URBAN_BUILT_PCT:
        return None
    return {"built_pct": pct,
            "note": tr(f"Khu đô thị (ESA WorldCover: {pct:g}% khung đo là bề mặt xây dựng): radar KHÔNG nhìn thấy được ngập giữa "
                       "nhà cửa — sóng dội vào tường làm nước trông sáng như đất. \"0 đợt\" ở đây KHÔNG có nghĩa là không ngập; "
                       "hỏi người dân, chính quyền địa phương hoặc bản đồ điểm ngập của đô thị.",
                       f"Urban area (ESA WorldCover: {pct:g}% of the frame is built-up): radar CANNOT see flooding between "
                       "buildings — the signal bounces off walls, making water look as bright as land. \"0 events\" here does NOT "
                       "mean no flooding; ask residents, local authorities or the city's flood-spot map.")}


def _annotate(r: dict, lat: float | None = None, lon: float | None = None) -> dict:
    if r.get("available"):
        r = {**r, "water_surface": water_surface(r.get("baseline_db"))}
        if lat is not None and lon is not None:
            r["urban"] = urban(lat, lon)
            r["canopy"] = None if r["urban"] else canopy(lat, lon)
            r["cropland"] = cropland(lat, lon) if r.get("n_events") else None
            r.update(seasons(lat, lon, r))
    return r


def seasons(lat: float, lon: float, r: dict) -> dict:
    """LỚP DIỄN GIẢI mùa lũ (services/flood_season.py, cổng đăng ký trước đạt 17/10/2026): gắn nhãn từng đợt trong/ngoài
    mùa lũ của CHÍNH điểm. Bộ phát hiện không đổi — không thêm/bớt đợt. Cổng chưa đạt / không có ERA5 → không gắn gì."""
    from app.services import flood_season as fs
    if not r.get("events") or not fs.gate_passed():
        return {}
    s = fs.season(lat, lon)
    if not s:
        return {}
    ev = [{**e, "season": fs.label(e["start"], s)} for e in r["events"]]
    n_in = sum(1 for e in ev if e["season"] == "in")
    n_out = len(ev) - n_in
    f = _frame_pct(lat, lon) or {}
    small_water = (r.get("water_surface") is not None) or (10.0 <= f.get(80, 0.0) < 50.0)
    use = n_out > 0 and (f.get(40, 0.0) >= CROP_PCT or small_water)
    out = {"events": ev, "n_in": n_in, "n_out": n_out,
           "flood_season": {"months": s["months"], "core": s["core"], "text": fs.months_text(s["months"]),
                            "window": s.get("window"), "source": s.get("source"), "rule_v": s.get("rule_v")},
           "out_note": (fs.seasonal_note() if use else tr("ngoài các tháng mưa lớn nhất của điểm — đối chiếu sự kiện thời tiết",
                                                           "outside the point's wettest months — check against weather events"))
                       if n_out else None}
    if out["flood_season"]:
        out["cropland"] = None              # đã tách trong/ngoài mùa — lời nhắc chung không còn cần
    return out


def history(lat: float, lon: float, radius_m: float = RADIUS_M, today: date | None = None,
            progress=None, use_cache: bool = True) -> dict:
    today = today or date.today()
    key = cache_key(lat, lon, radius_m)
    if use_cache:
        hit = cache_store.get(key)
        if hit is not None:
            return _annotate(hit, lat, lon)
    box = mpc.bbox_around(lat, lon, radius_m)
    orbit, rel, items = pick_track(_items(box, today))
    if not items:
        return {"available": False, "message": tr("Không tìm thấy cảnh Sentinel-1 nào trên thửa này.",
                                                  "No Sentinel-1 scenes found over this plot.")}
    rows, done, failed = [], 0, []

    def one(f):
        return f, _scene_status(f["id"], box)
    with ThreadPoolExecutor(max_workers=S1_WORKERS) as ex:
        for f, (st, s) in ex.map(one, items):
            done += 1
            if st == "ok":
                rows.append({"date": f["properties"]["datetime"][:10], **s})
            elif st == "error":
                failed.append(f)
            if progress and done % 20 == 0:
                progress({"done": done, "total": len(items)})
    # Cảnh lỗi mạng: thử lại chậm hơn (2 luồng, nghỉ giữa các vòng) — một cảnh bị bỏ có thể chính là cảnh chụp lúc ngập.
    for rnd in range(RETRY_ROUNDS):
        if not failed:
            break
        time.sleep(2 + 3 * rnd)
        with ThreadPoolExecutor(max_workers=2) as ex:
            again = list(ex.map(one, failed))
        failed = []
        for f, (st, s) in again:
            if st == "ok":
                rows.append({"date": f["properties"]["datetime"][:10], **s})
            elif st == "error":
                failed.append(f)
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
    if failed:
        out["n_failed"] = len(failed)
        out["failed_dates"] = sorted(f["properties"]["datetime"][:10] for f in failed)
        out["failed_note"] = tr(
            f"{len(failed)} cảnh radar không đọc được (lỗi mạng sau {RETRY_ROUNDS + 1} lần thử) — đợt nước rơi đúng vào các "
            "cảnh đó có thể bị lọt. Mở lại thửa sau vài giờ để đọc lại phần thiếu.",
            f"{len(failed)} radar scene(s) could not be read (network error after {RETRY_ROUNDS + 1} tries) — a water event "
            "falling on those scenes may be missed. Reopen the plot in a few hours to re-read the missing part.")
    cache_store.put(key, out, ttl_seconds=_PARTIAL_TTL if failed else _RESULT_TTL)
    return _annotate(out, lat, lon)


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
    hist = cache_store.get(cache_key(lat, lon))
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
