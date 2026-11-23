"""Mỏ / bãi khai thác tra TẠI CHỖ từ danh sách OSM tải sẵn (backend/data/osm_quarries_vn.json) — 23/11/2026.

Mô-đun "An toàn mỏ & công trường" từng gọi Overpass mỗi lần đánh giá: Huế 49 giây, ngày 22/11 Overpass 502 → "chưa đủ
dữ liệu nguồn". Danh sách tải bằng ops/osm_quarries_fetch.py (cùng bộ thẻ với mô-đun: landuse|industrial = quarry|mine).
Trả cùng định dạng osm.nearest() để mô-đun dùng thay thế được. Dữ liệu © OpenStreetMap contributors, ODbL 1.0.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.services.reqlang import tr

DATA = Path(__file__).resolve().parents[2] / "data" / "osm_quarries_vn.json"


@lru_cache(maxsize=1)
def _load() -> dict | None:
    try:
        d = json.loads(DATA.read_text(encoding="utf-8"))
        return d if isinstance(d.get("points"), list) and d["points"] else None
    except (OSError, ValueError):
        return None


def downloaded() -> str | None:
    """Ngày tải danh sách (YYYY-MM-DD) — None nếu không có danh sách dùng được."""
    d = _load()
    return d.get("downloaded") if d else None


def nearest(lat: float, lon: float, radius_m: float = 15_000.0, limit: int = 5) -> list[dict] | None:
    """Các mỏ / bãi khai thác trong bán kính, gần nhất trước — None nếu danh sách thiếu/hỏng (để dùng Overpass dự phòng)."""
    from app.services import datasources as ds
    d = _load()
    if d is None:
        return None
    out = []
    for la, lo, name, osm_id, kind in d["points"]:
        km = ds._haversine_km(lat, lon, la, lo)
        if km * 1000.0 <= radius_m:
            out.append({"lat": la, "lon": lo, "km": round(km, 2), "name": name or tr("chưa có tên", "unnamed"),
                        "tags": {"osm_id": osm_id, "kind": kind}})
    out.sort(key=lambda r: r["km"])
    return out[:limit]
