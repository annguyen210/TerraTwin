"""CỔNG GĐ2 — lịch sử nước radar phải thấy đúng các trận lũ đã biết và ra 0 đợt ở đất cao.

    python ops/water_gate.py          # chạy thật trên Planetary Computer, in kết quả để ghi REPRODUCE.md

Tiêu chí (kế hoạch tổng, viết TRƯỚC khi chạy):
  · Đồng lúa Quảng Điền (Huế): có đợt nước phủ trong tuần lũ 06–20/10/2020 VÀ trong 25/10–10/11/2025.
  · Đất cao Đà Lạt (≈1.500 m) và đồi thông Huế: 0 đợt.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.services import water_history as wh  # noqa: E402

CASES = [
    ("Đồng lúa Quảng Điền, Huế", 16.575, 107.495,
     [("lũ Huế 10/2020", date(2020, 10, 6), date(2020, 10, 20)),
      ("lũ miền Trung 10/2025", date(2025, 10, 25), date(2025, 11, 10))], None),
    ("Đất cao Đà Lạt", 11.9404, 108.4583, [], 0),
    ("Đồi thông Thiên An, Huế", 16.4283, 107.5628, [], 0),
]


def overlaps(ev: dict, a: date, b: date) -> bool:
    return date.fromisoformat(ev["start"]) <= b and date.fromisoformat(ev["end"]) >= a


ok_all = True
report = []
for name, lat, lon, floods, want_n in CASES:
    t = time.time()
    h = wh.history(lat, lon, use_cache=False)
    if not h.get("available"):
        print(f"KHÔNG ĐỌC ĐƯỢC {name}: {h.get('message')}")
        ok_all = False
        continue
    line = (f"{name}: {h['n_scenes']} cảnh ({h['first']} → {h['last']}, quỹ đạo {h['track']['orbit']} "
            f"#{h['track']['relative_orbit']}), {h['n_events']} đợt · {time.time() - t:.0f}s")
    print(line)
    checks = []
    for label, a, b in floods:
        hit = [e for e in h["events"] if overlaps(e, a, b)]
        checks.append((label, bool(hit), hit[:1]))
        print(f"   {'ĐẠT ' if hit else 'TRƯỢT'} {label}: " + (json.dumps(hit[0], ensure_ascii=False) if hit else "không thấy đợt nào"))
    if want_n is not None:
        good = h["n_events"] == want_n
        checks.append((f"{want_n} đợt", good, h["events"][:3]))
        print(f"   {'ĐẠT ' if good else 'TRƯỢT'} kỳ vọng {want_n} đợt — thấy {h['n_events']}" +
              (f": {json.dumps(h['events'][:3], ensure_ascii=False)}" if h["events"] else ""))
    ok_all &= all(c[1] for c in checks)
    report.append({"case": name, "lat": lat, "lon": lon, "n_scenes": h["n_scenes"], "first": h["first"],
                   "last": h["last"], "track": h["track"], "n_events": h["n_events"],
                   "events": h["events"], "baseline_db": h["baseline_db"],
                   "checks": [{"label": c[0], "pass": c[1]} for c in checks]})
out = os.path.join(os.path.dirname(__file__), "..", "backend", "data", "water_gate.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump({"run_at": date.today().isoformat(), "passed": ok_all, "rule": {"water_db": wh.WATER_DB, "drop_db": wh.DROP_DB,
               "merge_gap_days": wh.MERGE_GAP_DAYS, "radius_m": wh.RADIUS_M}, "cases": report}, f, ensure_ascii=False, indent=1)
print("CỔNG GĐ2:", "ĐẠT" if ok_all else "TRƯỢT")
sys.exit(0 if ok_all else 1)
