"""Dựng LƯỚI SÔNG/KÊNH TĨNH cho Việt Nam từ OpenStreetMap — dự phòng khi Overpass không gọi được.

Vì sao (báo cáo kiểm toàn bộ 12/10/2026, mục 8): trên Render, Overpass công cộng trả 429/504 cho IP dùng chung
→ "khoảng cách tới sông" luôn "—" ở Kiểm tin đăng và So sánh thửa. Tệp này chạy MỘT LẦN ở máy có mạng tốt,
tải đường sông + kênh (waterway=river|canal) theo ô 1°, đánh dấu ô lưới 0,001° (~110 m) có nước chảy qua,
rồi nén thành backend/data/vn_waterways_grid.npz (đóng gói cùng backend).

    python ops/build_river_grid.py            # tải (cache ở backend/data/dl_rivers/) + dựng
    python ops/build_river_grid.py --offline  # chỉ dựng lại từ cache

Dữ liệu © những người đóng góp OpenStreetMap, giấy phép ODbL — bản lưới là cơ sở dữ liệu phái sinh, công khai
cùng kho mã theo đúng ODbL. Độ chính xác: ±1 ô (~0,1 km) — đủ cho "gần sông" / "cách sông bao xa".
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "backend", "data", "dl_rivers")
OUT = os.path.join(ROOT, "backend", "data", "vn_waterways_grid.npz")
LAT0, LAT1, LON0, LON1 = 8.0, 24.0, 102.0, 110.0
CELL = 0.001
UA = "TerraTwin/0.6 (Vietnam land digital twin; contact via repo)"
EPS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
       "https://maps.mail.ru/osm/tools/overpass/api/interpreter"]


def fetch(lat: int, lon: int) -> dict:
    p = os.path.join(CACHE, f"{lat}_{lon}.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    if "--offline" in sys.argv:
        return {"elements": []}
    q = (f'[out:json][timeout:170];way["waterway"~"^(river|canal)$"]({lat},{lon},{lat + 1},{lon + 1});'
         "out skel geom qt;")
    last = None
    for attempt in range(8):
        # máy chính trước (nhanh nhất, 4 suất); gương chỉ khi máy chính lỗi liên tiếp
        url = EPS[0] if attempt < 5 else EPS[1 + attempt % 2]
        try:
            req = urllib.request.Request(url, data=urllib.parse.urlencode({"data": q}).encode(),
                                         headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=190) as r:
                d = json.loads(r.read().decode("utf-8"))
            if "elements" not in d:
                raise ValueError("no elements")
            os.makedirs(CACHE, exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(d, f)
            return d
        except Exception as e:                       # 429/504: nghỉ rồi thử lại
            last = e
            time.sleep(5 + 5 * attempt)
    raise RuntimeError(f"ô {lat},{lon}: {last}")


# Các ô 1° có đất liền Việt Nam (vĩ độ: các kinh độ) — bỏ ô toàn biển / toàn nước ngoài cho đỡ gọi.
TILES = {8: range(104, 107), 9: range(104, 107), 10: range(103, 108), 11: range(105, 110), 12: range(107, 110),
         13: range(107, 110), 14: range(107, 110), 15: range(107, 109), 16: range(106, 108), 17: range(105, 108),
         18: range(103, 107), 19: range(103, 107), 20: range(102, 108), 21: range(102, 109), 22: range(102, 108),
         23: range(104, 107)}


def main() -> None:
    nr, nc = round((LAT1 - LAT0) / CELL), round((LON1 - LON0) / CELL)
    grid = np.zeros((nr, nc), dtype=bool)
    n_ways = n_pts = 0
    for lat, lons in TILES.items():
        for lon in lons:
            t0 = time.time()
            d = fetch(lat, lon)
            for el in d.get("elements", []):
                g = el.get("geometry") or []
                n_ways += 1
                for a, b in zip(g, g[1:] or g):
                    # rải điểm ≤ nửa ô dọc mỗi đoạn để đoạn dài không nhảy cóc qua ô
                    steps = max(1, int(max(abs(b["lat"] - a["lat"]), abs(b["lon"] - a["lon"])) / (CELL / 2)) + 1)
                    t = np.linspace(0, 1, steps + 1)
                    la = a["lat"] + (b["lat"] - a["lat"]) * t
                    lo = a["lon"] + (b["lon"] - a["lon"]) * t
                    i = np.floor((la - LAT0) / CELL).astype(int)
                    j = np.floor((lo - LON0) / CELL).astype(int)
                    ok = (i >= 0) & (i < nr) & (j >= 0) & (j < nc)
                    grid[i[ok], j[ok]] = True
                    n_pts += int(ok.sum())
            print(f"{lat},{lon}: {len(d.get('elements', []))} đường ({time.time() - t0:.0f}s)", flush=True)
    meta = {"lat0": LAT0, "lon0": LON0, "cell_deg": CELL, "rows": nr, "cols": nc,
            "source": "OpenStreetMap waterway=river|canal (Overpass)", "license": "ODbL — © OpenStreetMap contributors",
            "built": time.strftime("%Y-%m-%d"), "n_ways": n_ways, "n_cells": int(grid.sum())}
    np.savez_compressed(OUT, bits=np.packbits(grid, axis=None), meta=np.array(json.dumps(meta)))
    print(json.dumps(meta, ensure_ascii=False), os.path.getsize(OUT) // 1024, "KB")


if __name__ == "__main__":
    main()
