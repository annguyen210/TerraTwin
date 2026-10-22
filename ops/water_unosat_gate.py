"""Kiểm ĐỘC LẬP lịch sử nước bằng bản đồ vùng ngập UNOSAT — backend/data/eval/water_unosat_protocol.json. Chấm MỘT lần.

    pip install pyshp
    python ops/water_unosat_gate.py          # đa giác UNOSAT ở D:/tt-scratch/unosat (KHÔNG vào repo)

Ghi backend/data/eval/water_unosat_result.json (toạ độ điểm lấy mẫu + kết quả — dữ liệu dẫn xuất, ghi nguồn UNOSAT CC BY-SA).
"""
from __future__ import annotations

import json
import math
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import shapefile  # noqa: E402  (pyshp)
from shapely import make_valid  # noqa: E402
from shapely.affinity import scale  # noqa: E402
from shapely.geometry import Point, shape  # noqa: E402
from shapely.prepared import prep  # noqa: E402
from shapely.strtree import STRtree  # noqa: E402

from app.services import water_history as wh  # noqa: E402

SRC = os.environ.get("TT_UNOSAT", "D:/tt-scratch/unosat")
PROTO_PATH = os.path.join(ROOT, "backend", "data", "eval", "water_unosat_protocol.json")
RESULT_PATH = os.path.join(ROOT, "backend", "data", "eval", "water_unosat_result.json")
PROTO = json.load(open(PROTO_PATH, encoding="utf-8"))
N_POS = N_NEG = 8
WINDOW = 6


def load(dirname: str, layer: str | None):
    if not layer:
        return None, None
    r = shapefile.Reader(os.path.join(SRC, dirname, layer + ".shp"))
    g = make_valid(shape(r.shape(0).__geo_interface__))
    rec = r.record(0).as_dict()
    return g, rec


def circle(lat: float, lon: float, radius_m: float = 100.0):
    dlat = radius_m / 111_320.0
    dlon = radius_m / (111_320.0 * math.cos(math.radians(lat)))
    return scale(Point(lon, lat).buffer(1.0, 32), dlon, dlat)


def sensor_date(rec: dict, name: str) -> date:
    v = rec.get("Sensor_Dat")
    if isinstance(v, date):
        return v
    if v:
        return date.fromisoformat(str(v)[:10])
    return date.fromisoformat(f"{name.split('_')[1][:4]}-{name.split('_')[1][4:6]}-{name.split('_')[1][6:8]}")


def sample(i: int, ev: dict) -> dict:
    flood, frec = load(ev["dir"], ev["flood"])
    analysis, _ = load(ev["dir"], ev["analysis"])
    water, _ = load(ev["dir"], ev["water"])
    wet = flood if water is None else flood.union(water)
    pf, pa, pw = prep(flood), prep(analysis), prep(wet)
    # Diện tích giao bằng chỉ mục không gian trên từng mảnh đa giác — CÙNG kết quả với flood.intersection(c).area
    # (các mảnh của một vùng hợp lệ không chồng nhau) nhưng không cắt cả vùng ngập khổng lồ cho mỗi lần thử.
    def flat(g):
        if g.geom_type == "Polygon":
            return [g]
        return [p for h in getattr(g, "geoms", []) for p in flat(h)]
    parts = flat(flood)
    tree = STRtree(parts)

    def area_in(c):
        return sum(parts[k].intersection(c).area for k in tree.query(c))
    rng = random.Random(20261022 + i)
    pos, neg = [], []
    x0, y0, x1, y1 = flood.bounds
    for _ in range(200_000):
        if len(pos) >= N_POS:
            break
        lon, lat = rng.uniform(x0, x1), rng.uniform(y0, y1)
        if not pf.contains(Point(lon, lat)):
            continue
        c = circle(lat, lon)
        if area_in(c) / c.area >= 0.5:
            pos.append((round(lat, 6), round(lon, 6)))
    x0, y0, x1, y1 = analysis.bounds
    for _ in range(200_000):
        if len(neg) >= N_NEG:
            break
        lon, lat = rng.uniform(x0, x1), rng.uniform(y0, y1)
        p = Point(lon, lat)
        if pa.contains(p) and not pw.intersects(circle(lat, lon, 500.0)):     # cách mọi vùng có nước ≥ 500 m
            neg.append((round(lat, 6), round(lon, 6)))
    return {"id": ev["id"], "label": ev["label"], "sensor": ev["sensor"], "date": sensor_date(frec, ev["flood"]).isoformat(),
            "pos": pos, "neg": neg}


def check(lat: float, lon: float, d: date) -> dict:
    for k in range(3):                                          # lỗi mạng: thử lại, không đổi phép chấm
        try:
            h = wh.history(lat, lon)
            break
        except Exception as e:  # noqa: BLE001
            h = {"available": False, "reason": repr(e)[:120]}
            time.sleep(5 * (k + 1))
    if not h.get("available"):
        return {"read": False, "reason": h.get("reason") or h.get("message")}
    a, b = d - timedelta(days=WINDOW), d + timedelta(days=WINDOW)
    hit = [e for e in h.get("events", []) if date.fromisoformat(e["start"]) <= b and date.fromisoformat(e["end"]) >= a]
    return {"read": True, "has_event": bool(hit), "events": [{"start": e["start"], "end": e["end"], "cover": e.get("peak_cover")} for e in hit],
            "n_scenes": h.get("n_scenes")}


def wilson(k: int, n: int) -> list:
    if not n:
        return [None, None]
    z, p = 1.96, k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    w = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(c - w, 3), round(c + w, 3)]


def main() -> None:
    if os.path.exists(RESULT_PATH) and "--force" not in sys.argv:
        sys.exit("Đã có kết quả — chấm một lần. Chạy lại phải có --force và ghi lý do vào run_log.")
    t0 = time.time()
    evs = [sample(i, ev) for i, ev in enumerate(PROTO["events"])]
    for e in evs:
        print(e["id"], e["label"], e["date"], "dương", len(e["pos"]), "âm", len(e["neg"]), flush=True)
    jobs = [(e, kind, lat, lon) for e in evs for kind in ("pos", "neg") for lat, lon in e[kind]]
    with ThreadPoolExecutor(4) as ex:
        res = list(ex.map(lambda j: check(j[2], j[3], date.fromisoformat(j[0]["date"])), jobs))
    rows = []
    for (e, kind, lat, lon), r in zip(jobs, res):
        rows.append({"event": e["id"], "kind": kind, "lat": lat, "lon": lon, **r})
    def rate(sel):
        rd = [r for r in sel if r["read"]]
        k = sum(r["has_event"] for r in rd)
        return {"n": len(sel), "read": len(rd), "with_event": k, "rate": round(k / len(rd), 3) if rd else None, "wilson95": wilson(k, len(rd))}
    pos, neg = [r for r in rows if r["kind"] == "pos"], [r for r in rows if r["kind"] == "neg"]
    other = {"E4", "E5"}
    summary = {"sensitivity": rate(pos), "false_alarm": rate(neg),
               "sensitivity_other_sensor": rate([r for r in pos if r["event"] in other]),
               "false_alarm_other_sensor": rate([r for r in neg if r["event"] in other]),
               "per_event": {e["id"]: {"label": e["label"], "sensor": e["sensor"], "date": e["date"],
                                       "sensitivity": rate([r for r in pos if r["event"] == e["id"]]),
                                       "false_alarm": rate([r for r in neg if r["event"] == e["id"]])} for e in evs}}
    read_rate = sum(r["read"] for r in rows) / len(rows)
    s, f = summary["sensitivity"]["rate"] or 0.0, summary["false_alarm"]["rate"]
    checks = {"sensitivity_ge_0_60": [s, s >= 0.60], "false_alarm_le_0_20": [f, f is not None and f <= 0.20],
              "read_rate_ge_0_80": [round(read_rate, 3), read_rate >= 0.80]}
    out = {"protocol": PROTO["id"], "scored_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "attribution": "Vùng ngập tham chiếu: UNOSAT/UNITAR (CC BY-SA), qua HDX", "checks": checks,
           "passed": all(c[1] for c in checks.values()), "summary": summary, "points": rows, "seconds": round(time.time() - t0, 1)}
    json.dump(out, open(RESULT_PATH, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
    print(json.dumps({"passed": out["passed"], "checks": checks}, ensure_ascii=False))


if __name__ == "__main__":
    main()
