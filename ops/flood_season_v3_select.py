"""Bước CHỌN CA của cổng v3 — đúng quy trình đã đăng ký (backend/data/eval/flood_season_v3_protocol.json).

    cd backend && python ../ops/flood_season_v3_select.py     # ghi data/eval/flood_season_v3_cases.json

CHỈ dùng các phép kiểm được phép: WorldCover, mùa lũ v1 (khí hậu ERA5), lưu lượng TRUNG BÌNH 10 năm của ô sông, và danh
sách NGÀY cảnh Sentinel-1 của quỹ đạo cố định. KHÔNG đọc giá trị radar (ướt/khô), KHÔNG đọc lưu lượng hay mưa quanh ngày
lũ. Danh sách ca ghi ra được commit TRƯỚC khi chạy cổng (ops/flood_season_v3_gate.py).
"""
from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))

from app.db import init_db  # noqa: E402

init_db()
from app.services import flood_season as fs, landuse, mpc, water_history as wh  # noqa: E402

PROTO = os.path.join(HERE, "..", "backend", "data", "eval", "flood_season_v3_protocol.json")
OUT = os.path.join(HERE, "..", "backend", "data", "eval", "flood_season_v3_cases.json")
STEP = 0.04


def grid(box):
    la0, la1, lo0, lo1 = box
    pts, la = [], la0
    while la <= la1 + 1e-9:
        lo = lo0
        while lo <= lo1 + 1e-9:
            pts.append((round(la, 4), round(lo, 4)))
            lo += STEP
        la += STEP
    return pts


def wc(lat, lon):
    raw = landuse.fetch_raw(lat, lon, 100.0)
    if not raw:
        return None
    h = {int(k): float(v) for k, v in raw["hist"].items()}
    t = sum(h.values()) or 1.0
    return {"crop": round(100 * h.get(40, 0) / t, 1), "built": round(100 * h.get(50, 0) / t, 1), "water": round(100 * h.get(80, 0) / t, 1)}


def scene_dates(lat, lon) -> list[str]:
    """NGÀY các cảnh của quỹ đạo cố định mà bộ phát hiện dùng ở điểm này — chỉ siêu dữ liệu STAC, không đọc điểm ảnh."""
    box = mpc.bbox_around(lat, lon, wh.RADIUS_M)
    _orbit, _rel, items = wh.pick_track(wh._items(box, date.today()))
    return [f["properties"]["datetime"][:10] for f in items]


def check(pt, d: str):
    """(1)–(3) cho một điểm; trả lý do loại hoặc thông tin giữ."""
    w = wc(*pt)
    if not w:
        return {"pt": pt, "keep": False, "why": "không đọc được WorldCover"}
    if not (w["crop"] >= 50 and w["built"] < 10 and w["water"] < 50):
        return {"pt": pt, "keep": False, "why": f"không phải đất nông nghiệp ({w})", "wc": w}
    s = fs.season(*pt)
    if not s:
        return {"pt": pt, "keep": False, "why": "không có khí hậu ERA5", "wc": w}
    if int(d[5:7]) in s["months"]:
        return {"pt": pt, "keep": False, "why": f"tháng {int(d[5:7])} TRONG mùa lũ v1 ({s['months']})", "wc": w}
    cell = fs.river_cell(*pt)
    if not cell:
        return {"pt": pt, "keep": False, "why": "không đọc được GloFAS", "wc": w}
    cinfo = {k: cell[k] for k in ("lat", "lon", "km", "mean_m3s")}
    if not cell["in_scope"]:
        return {"pt": pt, "keep": False, "why": f"ngoài phạm vi v3 (ô sông TB {cell['mean_m3s']} m³/s < 10)", "wc": w, "river": cinfo}
    return {"pt": pt, "keep": True, "wc": w, "season_months": s["months"], "river": cinfo}


def main() -> int:
    proto = json.load(open(PROTO, encoding="utf-8"))
    events_out = []
    for ev in proto["positive_candidates"]["events"]:
        d = ev["date"]
        pts = [tuple(ev["point"])] if "point" in ev else grid(ev["box"])
        with ThreadPoolExecutor(max_workers=4) as ex:
            checks = list(ex.map(lambda p: check(p, d), pts))
        kept = sorted([c for c in checks if c["keep"]], key=lambda c: (-c["wc"]["crop"], pts.index(c["pt"])))
        chosen, tried = None, []
        lo, hi = d, (date.fromisoformat(d) + timedelta(days=6)).isoformat()
        for c in kept:
            sd = [x for x in scene_dates(*c["pt"]) if lo <= x <= hi]
            tried.append({"pt": list(c["pt"]), "scenes_in_window": sd})
            if sd:
                chosen = {**c, "pt": list(c["pt"]), "scenes_in_window": sd}
                break
        events_out.append({"id": ev["id"], "name": ev["name"], "date": d, "region": ev["region"], "eligible": chosen is not None,
                           "case_point": chosen, "n_points": len(pts), "n_kept_1_3": len(kept), "scene_checks": tried,
                           "rejected": [{"pt": list(c["pt"]), "why": c["why"]} for c in checks if not c["keep"]][:40]})
        print(f"{ev['id']} {ev['name']} {d}: {len(pts)} điểm, đạt (1)–(3): {len(kept)} → "
              + (f"CA tại {chosen['pt']} (ruộng {chosen['wc']['crop']}%, ô sông {chosen['river']['mean_m3s']} m³/s cách {chosen['river']['km']} km, cảnh {chosen['scenes_in_window']})"
                 if chosen else "KHÔNG đủ điều kiện"), flush=True)

    # Âm tính N3: 8 điểm chọn nhanh — chỉ kiểm phạm vi (không đọc gì trong cửa sổ)
    src = open(os.path.join(HERE, "..", "frontend", "components", "Start.tsx"), encoding="utf-8").read()
    import re
    quick = [(float(a), float(b)) for a, b in re.findall(r"lat: ([\d.]+), lon: ([\d.]+), note:", src)]
    qs = []
    for pt in quick:
        cell = fs.river_cell(*pt)
        qs.append({"pt": list(pt), "in_scope": bool(cell and cell["in_scope"]),
                   "river": {k: cell[k] for k in ("lat", "lon", "km", "mean_m3s")} if cell else None})
    scope_neg = {}
    for key, pt in (("N1", (9.18, 105.09)), ("N2", (21.12, 105.89))):
        cell = fs.river_cell(*pt)
        scope_neg[key] = {"pt": list(pt), "in_scope": bool(cell and cell["in_scope"]),
                          "river": {k: cell[k] for k in ("lat", "lon", "km", "mean_m3s")} if cell else None}
    elig = [e for e in events_out if e["eligible"]]
    res = {"selected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "protocol": "flood_season_v3_protocol.json",
           "positives": events_out, "n_eligible": len(elig), "regions": sorted({e["region"] for e in elig}),
           "enough": len(elig) >= 4 and len({e["region"] for e in elig}) >= 2,
           "negatives_scope": scope_neg, "quick_picks_scope": qs}
    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"ĐỦ ĐIỀU KIỆN: {len(elig)} trận ở vùng {res['regions']} → {'ĐỦ' if res['enough'] else 'THIẾU'} ca dương tính")
    print("Phạm vi âm tính:", {k: v["in_scope"] for k, v in scope_neg.items()}, "· chọn nhanh trong phạm vi:",
          [q["pt"] for q in qs if q["in_scope"]])
    return 0


if __name__ == "__main__":
    sys.exit(main())
