"""Tải MỘT LẦN danh sách mỏ / bãi khai thác trong lãnh thổ Việt Nam từ OpenStreetMap (Overpass) → backend/data/osm_quarries_vn.json.

Vì sao (23/11/2026): mô-đun "An toàn mỏ & công trường" gọi Overpass mỗi lần đánh giá — Huế mất 49 giây, ngày 22/11
Overpass trả 502 → "chưa đủ dữ liệu nguồn". Mỏ không mọc lên hằng ngày; tải sẵn một lần, mô-đun tra tại chỗ (< 1 giây),
Overpass chỉ là dự phòng khi tệp hỏng/thiếu.

Thẻ khớp đúng bộ lọc của mô-đun: landuse=quarry|mine, industrial=quarry|mine (KHÔNG landuse=industrial — nhà máy không
phải nơi đất bị đào bới). Lấy node + way + relation, toạ độ = tâm (`out center`), giống osm.nearest().

Giới hạn: chỉ trong ranh giới VN của OSM (area ISO3166-1=VN) — mỏ bên kia biên giới cách thửa < 15 km không có trong danh
sách. Dữ liệu © OpenStreetMap contributors, giấy phép ODbL 1.0 (https://www.openstreetmap.org/copyright).

Chạy lại: backend/.venv/Scripts/python.exe ops/osm_quarries_fetch.py
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ENDPOINTS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
             "https://maps.mail.ru/osm/tools/overpass/api/interpreter", "https://overpass.private.coffee/api/interpreter"]
OUT = Path(__file__).resolve().parents[1] / "backend" / "data" / "osm_quarries_vn.json"
SEL = '[~"^(landuse|industrial)$"~"^(quarry|mine)$"]'
QUERY = f"""[out:json][timeout:300];
area["ISO3166-1"="VN"]["admin_level"="2"]->.vn;
(
  node{SEL}(area.vn);
  way{SEL}(area.vn);
  relation{SEL}(area.vn);
);
out center tags;"""


def fetch() -> dict:
    last = None
    for url in ENDPOINTS:
        try:
            req = urllib.request.Request(url, data=urllib.parse.urlencode({"data": QUERY}).encode(),
                                         headers={"User-Agent": "TerraTwin/1.0 (osm_quarries_fetch; one-off)"})
            with urllib.request.urlopen(req, timeout=360) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001 — thử gương kế tiếp
            last = e
            print(f"{url}: {e}", file=sys.stderr)
    raise SystemExit(f"Không tải được từ Overpass: {last}")


def main() -> None:
    d = fetch()
    pts = []
    for el in d.get("elements", []):
        c = el.get("center") or {"lat": el.get("lat"), "lon": el.get("lon")}
        if c.get("lat") is None or c.get("lon") is None:
            continue
        tags = el.get("tags") or {}
        kind = tags.get("landuse") if tags.get("landuse") in ("quarry", "mine") else tags.get("industrial")
        pts.append([round(c["lat"], 6), round(c["lon"], 6), tags.get("name", ""), f"{el['type'][0]}{el['id']}", kind or ""])
    pts.sort(key=lambda p: (p[0], p[1]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "source": "OpenStreetMap qua Overpass API (bản tải một lần)",
        "attribution": "© OpenStreetMap contributors",
        "license": "ODbL-1.0 — https://www.openstreetmap.org/copyright",
        "downloaded": date.today().isoformat(),
        "osm_timestamp": (d.get("osm3s") or {}).get("timestamp_osm_base", ""),
        "scope": "Lãnh thổ Việt Nam theo ranh giới OSM (area ISO3166-1=VN); mỏ bên kia biên giới không có trong danh sách.",
        "tags": "landuse=quarry|mine, industrial=quarry|mine (node + way + relation, toạ độ tâm)",
        "fields": ["lat", "lon", "name", "osm_id", "kind"],
        "count": len(pts),
        "points": pts,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(pts)} điểm → {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
