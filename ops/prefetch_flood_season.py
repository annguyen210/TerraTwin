"""Tải TRƯỚC mùa lũ (ERA5 qua Open-Meteo, cache 1 năm) cho mọi điểm của phép kiểm U-Net bản 3 — theo nhịp chậm.

Lượt 1 của phép kiểm bị Open-Meteo chặn (429) giữa chừng → thiếu mùa lũ. Script này chỉ LẤY DỮ LIỆU, không chấm gì:
mỗi điểm một lượt, nghỉ giữa các lượt; bị chặn thì chờ rồi thử lại. Xong thì bộ chấm đọc từ cache, không còn phụ thuộc
hạn mức giữa chừng.

    python ops/prefetch_flood_season.py
"""
from __future__ import annotations

import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.join(ROOT, "ops"))

from app.services import flood_season as fs  # noqa: E402
from s1_unet_gate import NEG as OLD_NEG, POS as OLD_POS  # noqa: E402
from s1_unet_v2_gate import NEW_NEG  # noqa: E402

PACE_S, WAIT_S, TRIES = 8, 300, 30


def main() -> None:
    un = json.load(open(os.path.join(ROOT, "backend", "data", "eval", "water_unosat_result.json"), encoding="utf-8"))
    pts = [(p["lat"], p["lon"]) for p in un["points"]] + [(OLD_POS[1], OLD_POS[2])] + [(a, b) for _, a, b in OLD_NEG + NEW_NEG]
    seen, ok, missing = set(), 0, []
    for lat, lon in pts:
        key = (round(lat, 2), round(lon, 2))
        if key in seen:
            continue
        seen.add(key)
        for k in range(TRIES):
            s = fs.season(lat, lon)
            if s:
                ok += 1
                break
            print(f"chờ Open-Meteo ({lat}, {lon}) lần {k + 1}", flush=True)
            time.sleep(WAIT_S)
        else:
            missing.append(key)
        time.sleep(PACE_S)
    print(json.dumps({"points": len(seen), "ok": ok, "missing": missing}), flush=True)


if __name__ == "__main__":
    main()
