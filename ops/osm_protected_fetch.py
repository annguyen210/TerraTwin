"""Tải MỘT LẦN ranh khu bảo tồn / vườn quốc gia / khu dự trữ thiên nhiên trong lãnh thổ Việt Nam từ OpenStreetMap
(Overpass) → backend/data/osm_protected_vn.json.

Vì sao (kiểm A–Z 24/11/2026): sàng lọc EUDR hỏi Overpass "tâm thửa có nằm trong khu bảo tồn không" mỗi lần — Overpass
công cộng hay 502/timeout từ máy chủ đám mây nên kết quả thường là "Chưa kiểm được khu bảo tồn", kể cả một điểm trong
VQG Yok Đôn. Ranh khu bảo tồn gần như không đổi; tải sẵn một lần (cùng cách osm_quarries_fetch.py), tra tại chỗ.

Thẻ khớp đúng truy vấn cũ của eudr_forest.protected_areas: boundary=protected_area | boundary=national_park |
leisure=nature_reserve. Ranh được làm gọn (simplify ~50 m) — đủ cho câu hỏi "tâm thửa có nằm trong không", KHÔNG phải
ranh pháp lý. OSM không phải bản đồ pháp lý: "không thấy" KHÁC "chắc chắn ngoài".

Dữ liệu © OpenStreetMap contributors, giấy phép ODbL 1.0 (https://www.openstreetmap.org/copyright).

Chạy lại: backend/.venv/Scripts/python.exe ops/osm_protected_fetch.py
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

from shapely.geometry import LineString, Polygon, mapping
from shapely.ops import polygonize, unary_union

ENDPOINTS = ["https://overpass-api.de/api/interpreter", "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
             "https://overpass.kumi.systems/api/interpreter", "https://overpass.private.coffee/api/interpreter"]
OUT = Path(__file__).resolve().parents[1] / "backend" / "data" / "osm_protected_vn.json"
QUERY = """[out:json][timeout:600];
area["ISO3166-1"="VN"]["admin_level"="2"]->.vn;
(
  way["boundary"~"^(protected_area|national_park)$"](area.vn);
  relation["boundary"~"^(protected_area|national_park)$"](area.vn);
  way["leisure"="nature_reserve"](area.vn);
  relation["leisure"="nature_reserve"](area.vn);
);
out geom;"""
SIMPLIFY_DEG = 0.0005        # ~50 m


def fetch() -> dict:
    last = None
    for url in ENDPOINTS:
        try:
            req = urllib.request.Request(url, data=urllib.parse.urlencode({"data": QUERY}).encode(),
                                         headers={"User-Agent": "TerraTwin/1.0 (osm_protected_fetch; one-off)"})
            with urllib.request.urlopen(req, timeout=900) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001 — thử gương kế tiếp
            last = e
            print(f"{url}: {e}", file=sys.stderr)
    raise SystemExit(f"Không tải được từ Overpass: {last}")


def _line(geom: list[dict]) -> LineString | None:
    pts = [(g["lon"], g["lat"]) for g in geom or [] if g]
    return LineString(pts) if len(pts) >= 2 else None


def _shape(el: dict):
    if el["type"] == "way":
        pts = [(g["lon"], g["lat"]) for g in el.get("geometry") or []]
        return Polygon(pts) if len(pts) >= 4 and pts[0] == pts[-1] else None
    outer = [ln for m in el.get("members") or [] if m.get("type") == "way" and m.get("role") in ("outer", "")
             for ln in [_line(m.get("geometry"))] if ln is not None]
    inner = [ln for m in el.get("members") or [] if m.get("type") == "way" and m.get("role") == "inner"
             for ln in [_line(m.get("geometry"))] if ln is not None]
    polys = list(polygonize(unary_union(outer))) if outer else []
    if not polys:
        return None
    shp = unary_union(polys)
    holes = list(polygonize(unary_union(inner))) if inner else []
    return shp.difference(unary_union(holes)) if holes else shp


def main() -> None:
    d = fetch()
    out = []
    for el in d.get("elements", []):
        tags = el.get("tags") or {}
        try:
            shp = _shape(el)
        except Exception as e:  # noqa: BLE001 — ranh vẽ hỏng ở OSM: bỏ, ghi lại
            print(f"bỏ {el['type']}/{el['id']}: {e}", file=sys.stderr)
            continue
        if shp is None or shp.is_empty:
            continue
        shp = shp.buffer(0).simplify(SIMPLIFY_DEG, preserve_topology=True)
        if shp.is_empty or shp.area <= 0:
            continue
        name = tags.get("name:vi") or tags.get("name") or tags.get("name:en")
        if not name:
            continue
        out.append({"osm": f"{el['type']}/{el['id']}", "name": name,
                    "kind": tags.get("boundary") or tags.get("leisure"),
                    "protect_class": tags.get("protect_class"),
                    "bbox": [round(v, 5) for v in shp.bounds],
                    "geometry": json.loads(json.dumps(mapping(shp), default=float),
                                           parse_float=lambda s: round(float(s), 5))})
    out.sort(key=lambda r: r["name"])
    doc = {"source": "OpenStreetMap contributors (ODbL 1.0) qua Overpass API", "fetched": date.today().isoformat(),
           "query": "boundary=protected_area|national_park, leisure=nature_reserve trong ranh VN",
           "simplify_deg": SIMPLIFY_DEG, "count": len(out), "areas": out}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(out)} khu → {OUT} ({OUT.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
