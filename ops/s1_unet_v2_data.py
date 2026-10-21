"""Bộ dữ liệu U-Net radar bản 2 (backend/data/ml/s1_unet_vn_protocol.json) — cặp Sentinel-1 RTC + nhãn TỰ ĐỘNG từ
Sentinel-2 (MNDWI > 0) cách nhau ≤ 48 giờ, trên ruộng lúa 33 tỉnh. Ghi ra D:/tt-scratch/unet_v2 (KHÔNG vào repo).

    python ops/s1_unet_v2_data.py
"""
from __future__ import annotations

import json
import os
import random
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import numpy as np  # noqa: E402

from app.services import mpc  # noqa: E402
from app.services import s1_unet as U  # noqa: E402

PROTO = json.load(open(os.path.join(ROOT, "backend", "data", "ml", "s1_unet_vn_protocol.json"), encoding="utf-8"))
OUT = os.environ.get("TT_UNET_V2", "D:/tt-scratch/unet_v2")
GROUP = {"train": 0, "val": 1, "test": 2}
MAX_PAIRS, MAX_DT_H, CLEAR_MIN = 6, 48.0, 0.90
YEARS = [("2023-10-01", "2024-09-30"), ("2024-10-01", "2025-09-30"), ("2025-10-01", "2026-09-30")]


def stac(coll: str, box: list[float], query: dict | None = None) -> list[dict]:
    out = []
    for a, b in YEARS:
        body = {"collections": [coll], "bbox": box, "datetime": f"{a}T00:00:00Z/{b}T23:59:59Z", "limit": 250}
        if query:
            body["query"] = query
        out += (mpc._call(mpc.STAC, body) or {}).get("features") or []
    return out


def t(it: dict) -> datetime:
    return datetime.fromisoformat(it["properties"]["datetime"][:19])


def location(la: float, lo: float, split: str, i: int, k: int) -> list[dict]:
    box = mpc.bbox_around(la, lo, 700.0)
    s2 = sorted(stac("sentinel-2-l2a", box, {"eo:cloud_cover": {"lt": 20}}), key=t)
    s1 = stac("sentinel-1-rtc", box)
    got, slopes = [], {}
    for x in s2:
        if not s1:
            break
        y = min(s1, key=lambda z: abs((t(z) - t(x)).total_seconds()))
        dt = abs((t(y) - t(x)).total_seconds()) / 3600.0
        if dt > MAX_DT_H:
            continue
        epsg, fb = U.s1_grid_box(y, la, lo)
        lab = U.s2_label(x, epsg, fb)
        if lab is None or (lab != 255).mean() < CLEAR_MIN:
            continue
        arr = U.fetch_grid(y, epsg, fb)
        if arr is None or (arr[0] > 0).mean() < CLEAR_MIN:
            continue
        lab[~(arr[0] > 0)] = 255
        if epsg not in slopes:
            slopes[epsg] = U.slope_deg(epsg, fb, la, lo)
        got.append({"s1": arr, "label": lab, "slope": slopes[epsg], "meta": {
            "split": split, "s2": x["id"], "s1": y["id"], "dt_h": round(dt, 1), "epsg": epsg, "box": fb,
            "lat": round(la, 5), "lon": round(lo, 5), "date": x["properties"]["datetime"][:10],
            "water_frac": round(float((lab == 1).sum() / max(1, (lab != 255).sum())), 4)}})
    return mpc._spread(got, MAX_PAIRS)


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    for split, rows in PROTO["data"]["split"].items():
        for i, p in enumerate(rows):
            for k in range(3):
                path = os.path.join(OUT, f"{split}_{i:02d}_{k}.json")
                if os.path.exists(path):
                    continue
                rng = random.Random(20261021 + 1000 * GROUP[split] + 10 * i + k)
                la, lo = (p["lat"], p["lon"]) if k == 0 else (p["lat"] + rng.uniform(-0.06, 0.06), p["lon"] + rng.uniform(-0.06, 0.06))
                pairs = location(la, lo, split, i, k)
                for j, g in enumerate(pairs):
                    np.savez_compressed(os.path.join(OUT, f"{split}_{i:02d}_{k}_{j}.npz"), s1=g["s1"], label=g["label"],
                                        slope=(g["slope"] if g["slope"] is not None else np.zeros_like(g["s1"][0])).astype(np.float16))
                json.dump({"province": p["province"], "lat": round(la, 5), "lon": round(lo, 5), "n": len(pairs),
                           "slope_missing": any(g["slope"] is None for g in pairs),
                           "pairs": [g["meta"] for g in pairs]}, open(path, "w", encoding="utf-8"), ensure_ascii=False)
                print(split, p["province"], k, "cặp:", len(pairs), flush=True)


if __name__ == "__main__":
    main()
