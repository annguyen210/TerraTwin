"""Chạy CỔNG của lớp diễn giải mùa lũ ĐÚNG như giao thức đã đăng ký (backend/data/eval/flood_season_protocol.json).

    cd backend && python ../ops/flood_season_gate.py          # ghi data/eval/flood_season_result.json

Đọc lịch sử nước radar (bộ phát hiện GĐ2, không đổi) + mùa lũ ERA5 (services/flood_season.py) cho từng ca, gắn nhãn
các đợt được chọn, so với nhãn bắt buộc. Trượt thì vẫn ghi kết quả (passed: false) — lớp diễn giải tự tắt.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))

from app.db import init_db  # noqa: E402

init_db()
from app.services import flood_season as fs, water_history as wh  # noqa: E402

PROTO = os.path.join(HERE, "..", "backend", "data", "eval", "flood_season_protocol.json")
OUT = os.path.join(HERE, "..", "backend", "data", "eval", "flood_season_result.json")


def main() -> int:
    proto = json.load(open(PROTO, encoding="utf-8"))
    cases, ok_all = [], True
    for c in proto["gate"]:
        h = wh.history(c["lat"], c["lon"])
        s = fs.season(c["lat"], c["lon"])
        if not h.get("available") or s is None:
            cases.append({"case": c["case"], "pass": False, "why": "thiếu lịch sử nước hoặc khí hậu ERA5"})
            ok_all = False
            continue
        sel = c["select"]
        picked = [e for e in h["events"] if (e["start"] in sel.get("starts", [])) or
                  (int(e["start"][5:7]) in sel.get("start_months", []))]
        got = [{"start": e["start"], "label": fs.label(e["start"], s)} for e in picked]
        passed = bool(picked) and all(g["label"] == c["must"] for g in got)
        if "starts" in sel:
            passed = passed and len(picked) == len(sel["starts"])
        ok_all = ok_all and passed
        cases.append({"case": c["case"], "lat": c["lat"], "lon": c["lon"], "must": c["must"], "pass": passed,
                      "season_months": s["months"], "core": s["core"], "monthly_mm": s["monthly_mm"],
                      "events": got, "all_events": [{"start": e["start"], "label": fs.label(e["start"], s)} for e in h["events"]]})
        print(f"{'ĐẠT ' if passed else 'TRƯỢT'} {c['case']}: mùa lũ tháng {fs.months_text(s['months'])} "
              f"(lõi {s['core']}) · đợt chọn: {', '.join(g['start'] + '=' + g['label'] for g in got) or '—'}")
    res = {"run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "protocol": "flood_season_protocol.json",
           "rule_version": fs.RULE_V, "passed": ok_all, "cases": cases}
    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("CỔNG LỚP MÙA LŨ:", "ĐẠT" if ok_all else "TRƯỢT")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
