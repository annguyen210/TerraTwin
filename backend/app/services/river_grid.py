"""LƯỚI SÔNG/KÊNH TĨNH của Việt Nam (OpenStreetMap, đóng gói cùng backend) — khoảng cách tới sông/kênh gần nhất
không cần gọi Overpass.

Vì sao: trên Render, Overpass công cộng trả 429/504 cho IP dùng chung → "khoảng cách tới sông" luôn "—" (báo cáo
kiểm toàn bộ 12/10/2026, mục 8). Lưới dựng một lần bằng ops/build_river_grid.py: ô 0,001° (~110 m) được đánh dấu
khi một đường waterway=river|canal của OSM đi qua. Tra = tìm ô có nước gần nhất trong bán kính → sai số ±~0,1 km.

Dữ liệu © những người đóng góp OpenStreetMap (ODbL).
"""
from __future__ import annotations

import json
import math
import os
import threading

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "vn_waterways_grid.npz")
_lock = threading.Lock()
_g: dict | None = None
_missing = False


def _load() -> dict | None:
    global _g, _missing
    if _g is not None or _missing:
        return _g
    with _lock:
        if _g is None and not _missing:
            try:
                import numpy as np
                z = np.load(_PATH)
                _g = {"bits": z["bits"], "meta": json.loads(str(z["meta"]))}
            except (OSError, KeyError, ValueError, ImportError):
                _missing = True
    return _g


def meta() -> dict | None:
    g = _load()
    return g["meta"] if g else None


def nearest_km(lat: float, lon: float, radius_m: float = 3000.0) -> float | None:
    """Km tới ô sông/kênh gần nhất; float('inf') nếu không có trong bán kính; None nếu không có lưới / ngoài vùng."""
    import numpy as np
    g = _load()
    if g is None:
        return None
    m, bits = g["meta"], g["bits"]
    cell, rows, cols = m["cell_deg"], m["rows"], m["cols"]
    i0 = math.floor((lat - m["lat0"]) / cell)
    j0 = math.floor((lon - m["lon0"]) / cell)
    if not (0 <= i0 < rows and 0 <= j0 < cols):
        return None
    ri = math.ceil(radius_m / 111_000 / cell) + 1
    rj = math.ceil(ri / max(0.2, math.cos(math.radians(lat))))
    ia, ib = max(0, i0 - ri), min(rows, i0 + ri + 1)
    ja, jb = max(0, j0 - rj), min(cols, j0 + rj + 1)
    ba, bb = ja // 8, (jb + 7) // 8                    # cột → byte (mỗi hàng bắt đầu đúng biên byte khi cols % 8 == 0)
    stride = cols // 8
    win = np.stack([np.unpackbits(bits[i * stride + ba: i * stride + bb]) for i in range(ia, ib)])
    win = win[:, ja - ba * 8: jb - ba * 8]
    ii, jj = np.nonzero(win)
    if ii.size == 0:
        return float("inf")
    clat = m["lat0"] + (ia + ii + 0.5) * cell
    clon = m["lon0"] + (ja + jj + 0.5) * cell
    p1, p2 = math.radians(lat), np.radians(clat)
    a = np.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * np.cos(p2) * np.sin(np.radians(clon - lon) / 2) ** 2
    km = float((2 * 6371.0 * np.arcsin(np.sqrt(a))).min())
    return round(km, 2) if km <= radius_m / 1000 else float("inf")
