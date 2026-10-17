"""CỔNG lớp mùa lũ v3 — chấm R-a và R-b trên CÙNG bộ ca đã chốt (backend/data/eval/flood_season_v3_cases.json).

    cd backend && python ../ops/flood_season_v3_gate.py      # ghi data/eval/flood_season_v3_result.json

Một quy tắc chỉ bật khi đạt cả ba: dương tính ≥ 75% (và đủ ≥ 4 trận ở ≥ 2 vùng), âm tính 0 bắt nhầm, v1 không đổi.
Cả hai đạt → chọn quy tắc có biên âm tính lớn hơn. Báo biên tới ngưỡng cho từng ca; |biên| ≤ 5% = "biên mỏng".
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))

from app.db import init_db  # noqa: E402

init_db()
from app.services import flood_season as fs, water_history as wh  # noqa: E402

EVAL = os.path.join(HERE, "..", "backend", "data", "eval")
PROTO = os.path.join(EVAL, "flood_season_v3_protocol.json")
CASES = os.path.join(EVAL, "flood_season_v3_cases.json")
OUT = os.path.join(EVAL, "flood_season_v3_result.json")
THIN = 0.05
_memo: dict = {}


def labelled(lat, lon, rule):
    k = (lat, lon, rule)
    if k not in _memo:
        h = wh.history(lat, lon)
        s = fs.season(lat, lon)
        ev = fs.label_v3(h["events"], [x[0] for x in h["series"]], s, lat, lon, rule) if h.get("available") and s else None
        _memo[k] = ev
    return _memo[k]


def margins(e: dict, rule: str) -> dict:
    """(giá trị − ngưỡng)/ngưỡng: dương = vượt ngưỡng. R-b báo cả hai điều kiện."""
    m = {}
    if "q_max_m3s" in e:
        if rule == "a":
            m["q_vs_p97"] = round((e["q_max_m3s"] - e["p97_m3s"]) / e["p97_m3s"], 3)
        else:
            m["q_vs_p90"] = round((e["q_max_m3s"] - e["p90_m3s"]) / e["p90_m3s"], 3)
            if "rain3d_mm" in e and e.get("p97_mm"):
                m["rain_vs_p97"] = round((e["rain3d_mm"] - e["p97_mm"]) / e["p97_mm"], 3)
    m["thin"] = any(abs(v) <= THIN for v in m.values() if isinstance(v, float))
    return m


def view(e: dict) -> dict:
    keys = ("start", "end", "season", "v3_scope", "q_max_m3s", "q_date", "p97_m3s", "p90_m3s", "rain3d_mm", "p97_mm", "river_km", "rain_window")
    return {k: e[k] for k in keys if k in e}


def neg_safety(e: dict, rule: str) -> float | None:
    """Biên an toàn của MỘT đợt âm tính: (ngưỡng − giá trị)/ngưỡng; R-b lấy điều kiện xa ngưỡng hơn."""
    if "q_max_m3s" not in e:
        return None
    if rule == "a":
        return (e["p97_m3s"] - e["q_max_m3s"]) / e["p97_m3s"]
    a = (e["p90_m3s"] - e["q_max_m3s"]) / e["p90_m3s"]
    b = (e["p97_mm"] - e["rain3d_mm"]) / e["p97_mm"] if e.get("p97_mm") and "rain3d_mm" in e else 1.0
    return max(a, b)


def run_rule(rule: str, proto: dict, cases: dict, quick: list) -> dict:
    pos = []
    for ev in cases["positives"]:
        if not ev["eligible"]:
            continue
        la, lo = ev["case_point"]["pt"]
        d = date.fromisoformat(ev["date"])
        lo_d, hi_d = (d - timedelta(days=3)).isoformat(), (d + timedelta(days=6)).isoformat()
        evs = labelled(la, lo, rule) or []
        hit = sorted([e for e in evs if lo_d <= e["start"] <= hi_d], key=lambda e: e["start"])
        if not hit:
            pos.append({"id": ev["id"], "name": ev["name"], "date": ev["date"], "region": ev["region"], "pt": [la, lo],
                        "caught": False, "why": "radar không thấy nước trong [ngày lũ − 3, + 6]"})
            continue
        e = hit[0]
        pos.append({"id": ev["id"], "name": ev["name"], "date": ev["date"], "region": ev["region"], "pt": [la, lo],
                    "caught": e["season"] in ("in", "river"), "event": view(e), "margins": margins(e, rule)})
    # âm tính
    neg = []
    pos_pts = {(round(p["pt"][0], 3), round(p["pt"][1], 3)): p["date"] for p in pos}
    groups = [("N1", 9.18, 105.09, {"months": [3, 4, 5]}), ("N2", 21.12, 105.89, {"months": [2, 3]})]
    groups += [("N3", q["pt"][0], q["pt"][1], {"all_out": True}) for q in quick if q["in_scope"]]
    for gid, la, lo, sel in groups:
        evs = labelled(la, lo, rule) or []
        for e in evs:
            v1 = fs.label(e["start"], fs.season(la, lo))
            if "months" in sel and (int(e["start"][5:7]) not in sel["months"] or v1 != "out"):
                continue
            if sel.get("all_out"):
                if v1 != "out":
                    continue
                pd = pos_pts.get((round(la, 3), round(lo, 3)))
                if pd and abs((date.fromisoformat(e["start"]) - date.fromisoformat(pd)).days) <= 6:
                    continue                       # đợt trùng trận dương tính (vd Soulik ở ruộng Huế) — không tính âm tính
            sf = neg_safety(e, rule)
            neg.append({"group": gid, "pt": [la, lo], "event": view(e), "false_positive": e["season"] == "river",
                        "safety": None if sf is None else round(sf, 3), "margins": margins(e, rule)})
    # v1 không đổi
    v1 = []
    for c in proto["v1_unchanged"]:
        if "starts" not in c:
            continue
        evs = {e["start"]: e for e in (labelled(c["lat"], c["lon"], rule) or [])}
        v1.append({"case": c["case"], "ok": all(evs.get(s, {}).get("season") == c["must"] for s in c["starts"]),
                   "labels": {s: evs.get(s, {}).get("season") for s in c["starts"]}})
    n_pos = len(pos)
    caught = sum(1 for p in pos if p["caught"])
    regions = sorted({p["region"] for p in pos})
    fps = sum(1 for n in neg if n["false_positive"])
    safeties = [n["safety"] for n in neg if n["safety"] is not None]
    pos_ok = n_pos >= 4 and len(regions) >= 2 and caught / n_pos >= 0.75 if n_pos else False
    return {"rule": rule, "positives": pos, "n_pos": n_pos, "caught": caught, "regions": regions, "pos_pass": pos_ok,
            "negatives": neg, "n_neg": len(neg), "false_positives": fps, "neg_pass": fps == 0,
            "neg_min_safety": min(safeties) if safeties else None,
            "v1": v1, "v1_pass": all(x["ok"] for x in v1), "passed": pos_ok and fps == 0 and all(x["ok"] for x in v1)}


def main() -> int:
    proto = json.load(open(PROTO, encoding="utf-8"))
    cases = json.load(open(CASES, encoding="utf-8"))
    quick = cases["quick_picks_scope"]
    res = {r: run_rule(r, proto, cases, quick) for r in ("a", "b")}
    passing = [r for r in ("a", "b") if res[r]["passed"]]
    if len(passing) == 2:
        enabled = max(passing, key=lambda r: res[r]["neg_min_safety"] if res[r]["neg_min_safety"] is not None else -1)
    else:
        enabled = passing[0] if passing else None
    for r in ("a", "b"):
        x = res[r]
        print(f"R-{r}: dương tính {x['caught']}/{x['n_pos']} (vùng {x['regions']}) {'ĐẠT' if x['pos_pass'] else 'TRƯỢT'} · "
              f"âm tính bắt nhầm {x['false_positives']}/{x['n_neg']} {'ĐẠT' if x['neg_pass'] else 'TRƯỢT'} · "
              f"v1 {'giữ' if x['v1_pass'] else 'ĐỔI'} → {'ĐẠT' if x['passed'] else 'TRƯỢT'}")
        for p in x["positives"]:
            print(f"   + {p['id']} {p['date']} {'BẮT' if p['caught'] else 'trượt'} {p.get('event', {}).get('season', '')} "
                  f"{p.get('margins', '') or p.get('why', '')}")
        for n in x["negatives"]:
            if n["false_positive"] or n["margins"].get("thin"):
                print(f"   − {n['group']} {n['pt']} {n['event']['start']} {'BẮT NHẦM' if n['false_positive'] else 'biên mỏng'} {n['margins']}")
    out = {"run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "protocol": "flood_season_v3_protocol.json",
           "cases": "flood_season_v3_cases.json", "rule_version": fs.RULE_V3, "rules": res,
           "enabled_rule": enabled, "passed": enabled is not None}
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("CỔNG v3:", f"ĐẠT — bật R-{enabled}" if enabled else "TRƯỢT — giữ v1")
    return 0 if enabled else 1


if __name__ == "__main__":
    sys.exit(main())
