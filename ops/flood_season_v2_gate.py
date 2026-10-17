"""Chạy CỔNG lớp diễn giải mùa lũ v2 ĐÚNG như giao thức (backend/data/eval/flood_season_v2_protocol.json).

    cd backend && python ../ops/flood_season_v2_gate.py      # ghi data/eval/flood_season_v2_result.json

Hai chiều: dương tính (bão Soulik 19/9/2024, bão Noru 28/9/2022 phải là 'extreme'), âm tính (Cà Mau tháng 3–5, Hà Nội
tháng 2–3 vẫn 'out'), và giữ v1 (Huế 10–11/2020, 11/2025 vẫn 'in'). Trượt vẫn ghi kết quả (passed: false).
"""
from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))

from app.db import init_db  # noqa: E402

init_db()
from app.services import flood_season as fs, landuse, water_history as wh  # noqa: E402

PROTO = os.path.join(HERE, "..", "backend", "data", "eval", "flood_season_v2_protocol.json")
OUT = os.path.join(HERE, "..", "backend", "data", "eval", "flood_season_v2_result.json")


def labelled(lat: float, lon: float):
    h = wh.history(lat, lon)
    s = fs.season(lat, lon)
    if not h.get("available") or s is None:
        return None, None, None
    ev = fs.label_v2(h["events"], [x[0] for x in h["series"]], s, lat, lon)
    return h, s, ev


def pick(ev: list[dict], sel: dict) -> list[dict]:
    out = []
    for e in ev:
        if e["start"] in sel.get("starts", []):
            out.append(e)
        elif int(e["start"][5:7]) in sel.get("start_months", []):
            out.append(e)
        elif sel.get("start_from") and sel["start_from"] <= e["start"] <= sel["start_to"]:
            out.append(e)
    return out


def ev_view(e: dict) -> dict:
    return {k: e[k] for k in ("start", "end", "season", "rain3d_mm", "rain3d_end", "p97_mm", "rain_window") if k in e}


def keep_cropland(lat: float, lon: float) -> tuple[bool, dict | None]:
    raw = landuse.fetch_raw(lat, lon, 100.0)
    if not raw:
        return False, None
    g = landuse.describe(raw)["group_pct"]
    hist = {int(k): float(v) for k, v in raw["hist"].items()}
    tot = sum(hist.values()) or 1.0
    crop, built, water = 100 * hist.get(40, 0) / tot, 100 * hist.get(50, 0) / tot, 100 * hist.get(80, 0) / tot
    return (crop >= 50 and built < 10 and water < 50), g


def main() -> int:
    proto = json.load(open(PROTO, encoding="utf-8"))
    cases, ok_all = [], True
    for c in proto["gate"]:
        if "candidates" in c:
            pts = [(la, lo) for la in c["candidates"]["lat"] for lo in c["candidates"]["lon"]]
            with ThreadPoolExecutor(max_workers=4) as ex:
                keeps = list(ex.map(lambda p: keep_cropland(*p), pts))
            kept = [p for p, (k, _) in zip(pts, keeps) if k]
            with ThreadPoolExecutor(max_workers=4) as ex:
                labs = list(ex.map(lambda p: labelled(*p), kept))
            got = []
            for (la, lo), (h, s, ev) in zip(kept, labs):
                for e in pick(ev or [], c["select"]):
                    got.append({"lat": la, "lon": lo, **ev_view(e)})
            passed = len(got) >= c.get("min_events", 1) and all(g["season"] == c["must"] for g in got)
            cases.append({"id": c["id"], "direction": c["direction"], "case": c["case"], "must": c["must"], "pass": passed,
                          "candidates": len(pts), "kept_cropland": [list(p) for p in kept], "events": got})
        else:
            h, s, ev = labelled(c["lat"], c["lon"])
            if ev is None:
                cases.append({"id": c["id"], "case": c["case"], "pass": False, "why": "thiếu lịch sử nước hoặc ERA5"})
                ok_all = False
                continue
            sel = pick(ev, c["select"])
            passed = bool(sel) and all(e["season"] == c["must"] for e in sel)
            if "starts" in c["select"]:
                passed = passed and len(sel) == len(c["select"]["starts"])
            cases.append({"id": c["id"], "direction": c["direction"], "case": c["case"], "lat": c["lat"], "lon": c["lon"],
                          "must": c["must"], "pass": passed, "season_months": s["months"], "p97_mm": fs.threshold_p97(c["lat"], c["lon"]),
                          "events": [ev_view(e) for e in sel], "all_events": [ev_view(e) for e in ev]})
        r = cases[-1]
        ok_all = ok_all and r["pass"]
        print(f"{'ĐẠT ' if r['pass'] else 'TRƯỢT'} [{r['direction']}] {r['case']}: " +
              "; ".join(f"{e['start']}={e['season']}" + (f" (mưa 3 ngày {e['rain3d_mm']} mm / P97 {e['p97_mm']} mm)" if "rain3d_mm" in e else "")
                        for e in r.get("events", [])) or "—", flush=True)
    res = {"run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "protocol": "flood_season_v2_protocol.json",
           "rule_version": fs.RULE_V2, "passed": ok_all, "cases": cases}
    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("CỔNG LỚP MÙA LŨ v2:", "ĐẠT" if ok_all else "TRƯỢT")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
