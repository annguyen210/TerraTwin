"""Phép kiểm đăng ký trước U-Net radar BẢN 3 — backend/data/ml/s1_unet_v3_protocol.json. Chấm MỘT lần.

Trọng số bản 2, quy tắc mức THỬA mới: xác nhận khi tỉ lệ nước cảnh ngày D VƯỢT nền mùa khô của chính thửa ≥ 0,10.
U1 (độc lập với U-Net): 160 điểm UNOSAT; U2 (đã biết): ca GĐ2; U3: 3 điểm đồi.

    python ops/s1_unet_v3_gate.py
"""
from __future__ import annotations

import json
import os
import random
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.join(ROOT, "ops"))

from app.services import flood_season as fs, s1_unet as U, water_history as wh  # noqa: E402
from s1_unet_gate import NEG as OLD_NEG, POS as OLD_POS, SEED as OLD_SEED, N_NEG, overlaps  # noqa: E402
from s1_unet_v2_gate import NEW_NEG, V2, item_json, sess  # noqa: E402

RESULT = os.path.join(ROOT, "backend", "data", "ml", "s1_unet_v3_result.json")
RUN1 = os.path.join(ROOT, "backend", "data", "ml", "s1_unet_v3_result_run1.json")
UNOSAT = os.path.join(ROOT, "backend", "data", "eval", "water_unosat_result.json")
K_BASE, EXCESS, WIN = 6, 0.10, 6
_slope: dict = {}
S2 = None


def share_day(lat: float, lon: float, day: str):
    """Tỉ lệ nước khung tâm (bản 2 + mặt nạ dốc) trên cảnh ngày `day` của chuỗi thửa; None nếu không đọc được."""
    for k in range(3):
        sc = wh.scene(lat, lon, day)
        it = item_json(sc["item"]) if sc else None
        if it:
            epsg, box = U.s1_grid_box(it, lat, lon)
            arr = U.fetch_grid(it, epsg, box)
            key = (epsg, tuple(round(v) for v in box))
            if key not in _slope:
                _slope[key] = U.slope_deg(epsg, box, lat, lon)
            if arr is not None and _slope[key] is not None:
                return U.plot_share(U.predict_mask(S2.run(None, {"s1": U.prepare(arr)})[0][0, 0], _slope[key]))
        time.sleep(3 * (k + 1))
    return None


def flood_months(lat, lon, h) -> set | None:
    """Tháng mùa lũ của thửa; KHÔNG đoán khi thiếu (lượt 1 bị Open-Meteo chặn → nền lấy cả mùa lũ — lệch giao thức)."""
    m = (h.get("flood_season") or {}).get("months") or (fs.season(lat, lon) or {}).get("months")
    return set(m) if m else None


def baseline(lat, lon, h, avoid: list[date], seed: int):
    months = flood_months(lat, lon, h)
    if months is None:
        return None, "no flood season"
    days = [d for d, *_ in h["series"] if int(d[5:7]) not in months
            and all(abs((date.fromisoformat(d) - a).days) > 30 for a in avoid)]
    if len(days) < K_BASE:
        return None, "too few dry scenes"
    pick = sorted(random.Random(seed).sample(sorted(days), K_BASE))
    vals = [share_day(lat, lon, d) for d in pick]
    vals = [v for v in vals if v is not None]
    return (statistics.median(vals) if len(vals) >= 4 else None), list(zip(pick, vals))


def nearest(h, d: date):
    best = None
    for s, *_ in h["series"]:
        dd = abs((date.fromisoformat(s) - d).days)
        if dd <= WIN and (best is None or dd < best[0]):
            best = (dd, s)
    return best[1] if best else None


def judge(lat, lon, d: date, seed: int) -> dict:
    h = wh.history(lat, lon)
    if not h.get("available"):
        return {"read": False, "reason": "no water history"}
    day = nearest(h, d)
    if not day:
        return {"read": False, "reason": f"không có cảnh trong ±{WIN} ngày"}
    s = share_day(lat, lon, day)
    base, bl = baseline(lat, lon, h, [d], seed)
    if s is None or base is None:
        return {"read": False, "reason": bl if isinstance(bl, str) else "không đọc được cảnh hoặc nền"}
    return {"read": True, "scene": day, "share": s, "baseline": base, "excess": round(s - base, 4),
            "confirmed": s - base >= EXCESS, "baseline_scenes": bl}


def rate(rows):
    rd = [r for r in rows if r["read"]]
    k = sum(r["confirmed"] for r in rd)
    return {"n": len(rows), "read": len(rd), "confirmed": k, "rate": round(k / len(rd), 3) if rd else None}


def main() -> None:
    global S2
    if os.path.exists(RESULT) and "--force" not in sys.argv:
        sys.exit("Đã có kết quả — chấm một lần.")
    # Lượt chạy lại (22/10/2026): lượt 1 giữ nguyên ở s1_unet_v3_result_run1.json; lượt này áp ĐÚNG quy tắc nền mùa khô.
    if "--rerun-compliance" in sys.argv and not os.path.exists(RUN1):
        sys.exit("Thiếu lượt 1 để đối chiếu.")
    t0 = time.time()
    S2 = sess(V2)
    un = json.load(open(UNOSAT, encoding="utf-8"))
    evd = {e: v["date"] for e, v in un["summary"]["per_event"].items()}
    pts = un["points"]
    with ThreadPoolExecutor(4) as ex:
        res = list(ex.map(lambda ip: judge(ip[1]["lat"], ip[1]["lon"], date.fromisoformat(evd[ip[1]["event"]]), 20261022 + ip[0]),
                          enumerate(pts)))
    rows = [{"event": p["event"], "kind": p["kind"], "lat": p["lat"], "lon": p["lon"], **r} for p, r in zip(pts, res)]
    pos, neg = [r for r in rows if r["kind"] == "pos"], [r for r in rows if r["kind"] == "neg"]
    other = {"E4", "E5"}
    u1s = {"pos": rate(pos), "neg": rate(neg), "pos_other_sensor": rate([r for r in pos if r["event"] in other]),
           "neg_other_sensor": rate([r for r in neg if r["event"] in other])}
    read_rate = sum(r["read"] for r in rows) / len(rows)
    u1c = {"pos_confirm_ge_0_60": [u1s["pos"]["rate"], (u1s["pos"]["rate"] or 0) >= 0.60],
           "neg_confirm_le_0_10": [u1s["neg"]["rate"], u1s["neg"]["rate"] is not None and u1s["neg"]["rate"] <= 0.10],
           "read_ge_0_80": [round(read_rate, 3), read_rate >= 0.80]}
    print("U1", u1s, u1c, flush=True)

    name, lat, lon, floods = OLD_POS
    h = wh.history(lat, lon)
    u2p = []
    for label, a, b in floods:
        hit = [e for e in h["events"] if overlaps(e, a, b)]
        rr = [judge(lat, lon, date.fromisoformat(e["flag_date"]), 20261022) | {"flag_date": e["flag_date"]} for e in hit]
        u2p.append({"label": label, "events": rr, "pass": bool(rr) and all(x["read"] and x["confirmed"] for x in rr)})
    u2n = []
    for nm, la, lo in OLD_NEG:
        hh = wh.history(la, lo)
        days = sorted(random.Random(OLD_SEED).sample(sorted(d for d, *_ in hh["series"]), N_NEG))
        base, bl = baseline(la, lo, hh, [date.fromisoformat(d) for d in days], 20261022)
        sc = [{"date": d, "share": share_day(la, lo, d)} for d in days]
        bad = [x for x in sc if base is None or x["share"] is None or x["share"] - base >= EXCESS]
        u2n.append({"case": nm, "baseline": base, "baseline_scenes": bl, "scenes": sc, "bad": len(bad), "n": len(sc), "pass": not bad})
        print("U2", nm, "nền", base, "nhầm/không đọc", len(bad), flush=True)
    u3, bad3 = [], 0
    for nm, la, lo in NEW_NEG:
        hh = wh.history(la, lo)
        if not hh.get("available"):
            u3.append({"case": nm, "available": False})
            bad3 += 24
            continue
        days = sorted(random.Random(20261022).sample(sorted(d for d, *_ in hh["series"]), 24))
        base, bl = baseline(la, lo, hh, [date.fromisoformat(d) for d in days], 20261022)
        sc = [{"date": d, "share": share_day(la, lo, d)} for d in days]
        bad = [x for x in sc if base is None or x["share"] is None or x["share"] - base >= EXCESS]
        bad3 += len(bad)
        u3.append({"case": nm, "baseline": base, "scenes": sc, "bad": len(bad), "n": len(sc)})
        print("U3", nm, "nhầm/không đọc", len(bad), flush=True)
    out = {"protocol": "terratwin.s1_unet_vn/3", "scored_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "U1": {"summary": u1s, "checks": u1c, "pass": all(c[1] for c in u1c.values()), "points": rows},
           "U2": {"not_independent": True, "positive": u2p, "negative": u2n,
                  "pass": all(p["pass"] for p in u2p) and all(n["pass"] for n in u2n)},
           "U3": {"sites": u3, "bad_total": bad3, "pass": bad3 <= 1}}
    out["passed"] = out["U1"]["pass"] and out["U2"]["pass"] and out["U3"]["pass"]
    out["seconds"] = round(time.time() - t0, 1)
    json.dump(out, open(RESULT, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
    print(json.dumps({"passed": out["passed"], "U1": out["U1"]["pass"], "U2": out["U2"]["pass"], "U3": out["U3"]["pass"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
