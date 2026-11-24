"""Khu bảo tồn / vườn quốc gia tra TẠI CHỖ từ ranh OSM tải sẵn (backend/data/osm_protected_vn.json) — kiểm A–Z 24/11/2026.

Sàng lọc EUDR hỏi Overpass mỗi lần "tâm thửa có nằm trong khu bảo tồn không"; Overpass công cộng hay 502/timeout từ máy
chủ đám mây nên thường ra "Chưa kiểm được khu bảo tồn" — kể cả điểm trong VQG Yok Đôn. Ranh tải bằng
ops/osm_protected_fetch.py (cùng bộ thẻ với truy vấn cũ), làm gọn ~50 m. OSM không phải bản đồ pháp lý: "không thấy"
KHÁC "chắc chắn ngoài". Dữ liệu © OpenStreetMap contributors, ODbL 1.0.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data" / "osm_protected_vn.json"
# Tệp ít hơn ngưỡng này coi như KHÔNG CÓ (quay về Overpass): 24/11/2026 một gương Overpass trả về dở dang chỉ 13 khu —
# dùng tệp thiếu thì điểm trong một VQG không có trong tệp bị báo "không nằm trong khu bảo tồn", tệ hơn "chưa kiểm được".
MIN_AREAS = 60


@lru_cache(maxsize=1)
def _load() -> tuple[str, list] | None:
    """(ngày tải, [(bbox, hình đã chuẩn bị, tên)]) — None nếu tệp thiếu/hỏng (để dùng Overpass dự phòng)."""
    try:
        d = json.loads(DATA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    areas = d.get("areas")
    if not isinstance(areas, list) or len(areas) < MIN_AREAS:
        return None
    from shapely.geometry import shape
    from shapely.prepared import prep
    rows = []
    for a in areas:
        try:
            rows.append((tuple(a["bbox"]), prep(shape(a["geometry"])), a["name"]))
        except Exception:  # noqa: BLE001 — một ranh hỏng không làm hỏng cả danh sách
            continue
    return (d.get("fetched") or "", rows) if rows else None


def fetched() -> str | None:
    d = _load()
    return d[0] if d else None


def inside(lat: float, lon: float) -> list[str] | None:
    """Tên các khu chứa điểm (lat, lon) — [] nếu không thấy, None nếu không có danh sách dùng được."""
    d = _load()
    if d is None:
        return None
    from shapely.geometry import Point
    p = Point(lon, lat)
    names: list[str] = []
    for (x0, y0, x1, y1), geom, name in d[1]:
        if x0 <= lon <= x1 and y0 <= lat <= y1 and geom.contains(p) and name not in names:
            names.append(name)
    return names
