"""Mô hình học máy khả năng ngập theo địa hình — giao thức backend/data/eval/flood_susceptibility_protocol.json (đăng ký trước).

    python ops/flood_susceptibility.py points    # sinh 200 điểm (hạt giống cố định) → D:/tt-scratch/fsus/points.json
    python ops/flood_susceptibility.py harvest   # nhãn radar + đặc trưng từng điểm → rows.jsonl (chạy tiếp được)
    python ops/flood_susceptibility.py run       # huấn luyện + chấm cổng MỘT lần → data/eval/flood_susceptibility_result.json
"""
from __future__ import annotations

import json
import math
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "ops"))
PROTO = ROOT / "backend" / "data" / "eval" / "flood_susceptibility_protocol.json"
OUT = ROOT / "backend" / "data" / "eval" / "flood_susceptibility_result.json"
MODEL = ROOT / "backend" / "data" / "ml" / "flood_susceptibility.json"
WORK = Path("D:/tt-scratch/fsus")
SEED, N = 20261125, 200
# v2 (giao thức flood_susceptibility_v2_protocol.json): mẫu MỚI 300 huyện không trùng v1, mô hình chỉ độ cao.
V2 = len(sys.argv) > 2 and sys.argv[2] == "v2"
V3 = len(sys.argv) > 2 and sys.argv[2] == "v3"
if V3:
    PROTO = PROTO.with_name("flood_susceptibility_v3_protocol.json")
    OUT = OUT.with_name("flood_susceptibility_v3_result.json")
    WORK = Path("D:/tt-scratch/fsus_v3")
    SEED, N = 20261127, 600
if V2:
    PROTO = PROTO.with_name("flood_susceptibility_v2_protocol.json")
    OUT = OUT.with_name("flood_susceptibility_v2_result.json")
    WORK = Path("D:/tt-scratch/fsus_v2")
    SEED, N = 20261126, 300


def _km(a, b, c, d) -> float:
    r = math.radians
    x = math.sin(r(c - a) / 2) ** 2 + math.cos(r(a)) * math.cos(r(c)) * math.sin(r(d - b) / 2) ** 2
    return 12742.0 * math.asin(math.sqrt(x))


def points_v3() -> None:
    """v3: chọn huyện ngẫu nhiên (có thể lặp) rồi điểm ngẫu nhiên; mỗi điểm cách mọi điểm v1, v2, v3 khác ≥ 5 km."""
    from shapely.geometry import Point, shape
    WORK.mkdir(parents=True, exist_ok=True)
    units = json.loads((ROOT / "backend" / "data" / "admin" / "vnm_adm2_2020.json").read_text(encoding="utf-8"))["units"]
    ev = ROOT / "backend" / "data" / "eval"
    prior = [(p["lat"], p["lon"]) for f in ("flood_susceptibility_points.json", "flood_susceptibility_v2_points.json")
             for p in json.loads((ev / f).read_text(encoding="utf-8"))]
    rnd = random.Random(SEED)
    geoms: dict[int, object] = {}
    out: list[dict] = []
    tries = 0
    while len(out) < N and tries < 200_000:
        tries += 1
        i = rnd.randrange(len(units))
        if i not in geoms:
            u = units[i]
            geoms[i] = shape({"type": u["type"], "coordinates": json.loads(u["coordinates"]) if isinstance(u["coordinates"], str)
                              else u["coordinates"]})
        g = geoms[i]
        x0, y0, x1, y1 = g.bounds
        p = Point(rnd.uniform(x0, x1), rnd.uniform(y0, y1))
        if not g.contains(p):
            continue
        lat, lon = round(p.y, 5), round(p.x, 5)
        if any(_km(lat, lon, a, b) < 5.0 for a, b in prior):
            continue
        prior.append((lat, lon))
        out.append({"id": f"q{len(out):03d}", "district": units[i]["name"], "province": units[i]["province"], "lat": lat, "lon": lon})
    (WORK / "points.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    (ev / "flood_susceptibility_v3_points.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(out)} điểm, {len({p['province'] for p in out})} tỉnh → {WORK / 'points.json'}")


def run_v3() -> None:
    """v3: huấn luyện = v3 + v1 + v2 ngoài tỉnh kiểm tra; kiểm tra CHỈ điểm v3 trong tỉnh i % 5 == 2 (giao thức v3)."""
    g = json.loads(PROTO.read_text(encoding="utf-8"))["gate"]
    rows = [json.loads(l) for l in (WORK / "rows.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    pts = json.loads((WORK / "points.json").read_text(encoding="utf-8"))
    if len({r["id"] for r in rows}) < len(pts):
        sys.exit(f"DỪNG — mới có {len(rows)}/{len(pts)} điểm; chạy harvest trước.")
    ev = ROOT / "backend" / "data" / "eval"
    old = [json.loads(l) for f in ("flood_susceptibility_rows.jsonl", "flood_susceptibility_v2_rows.jsonl")
           for l in (ev / f).read_text(encoding="utf-8").splitlines() if l.strip()]
    ok = [r for r in rows if r.get("radar_ok") and "elev_m" in r]
    ok_old = [r for r in old if r.get("radar_ok") and "elev_m" in r]
    provs = sorted({p["province"] for p in pts})
    test_p = {p for i, p in enumerate(provs) if i % 5 == 2}
    tr_ = [r for r in ok + ok_old if r["province"] not in test_p]
    te = [r for r in ok if r["province"] in test_p]
    ytr, yte = [r["label"] for r in tr_], [r["label"] for r in te]
    m = _fit([_x(r, True) for r in tr_], ytr)
    pte = _pred(m, [_x(r, True) for r in te])
    auc = _auc(yte, pte)
    base = sum(ytr) / max(1, len(ytr))
    brier = sum((p - y) ** 2 for p, y in zip(pte, yte)) / max(1, len(yte))
    brier0 = sum((base - y) ** 2 for y in yte) / max(1, len(yte))
    bss = 1 - brier / brier0 if brier0 else None
    checks = {"min_test_points": len(te) >= g["min_test_points"], "min_test_positives": sum(yte) >= g["min_test_positives"],
              "auc": auc is not None and auc >= g["auc_min"],
              "brier_skill": bss is not None and bss > g["brier_skill_vs_base_rate_min"]}
    passed = all(checks.values())
    res = {"protocol": PROTO.name, "ran_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
           "n_points": len(rows), "n_radar_ok": len(ok), "n_train": len(tr_), "n_train_from_v1_v2": len([r for r in ok_old if r["province"] not in test_p]),
           "n_test": len(te), "pos_rate_train": round(base, 3), "pos_test": sum(yte), "test_provinces": sorted(test_p),
           "auc": None if auc is None else round(auc, 3), "brier": round(brier, 4), "brier_base_rate": round(brier0, 4),
           "brier_skill": None if bss is None else round(bss, 3), "weights": m, "checks": checks, "passed": passed,
           "excluded": [{k: r.get(k) for k in ("id", "province", "why")} for r in rows if not r.get("radar_ok")]}
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    if passed:
        MODEL.parent.mkdir(parents=True, exist_ok=True)
        MODEL.write_text(json.dumps({"features": ["log1p(elev+5)"], **m, "auc_test": round(auc, 3), "brier_skill": round(bss, 3),
                                     "ref_scores": sorted(round(v, 4) for v in _pred(m, [_x(r, True) for r in ok + ok_old])),
                                     "protocol": PROTO.name}, indent=1), encoding="utf-8")
    print(f"v3 AUC {auc} · BSS {bss} · test {len(te)} điểm ({sum(yte)} dương) → {'ĐẠT' if passed else 'TRƯỢT'} {checks}")


def points() -> None:
    from shapely.geometry import Point, shape
    WORK.mkdir(parents=True, exist_ok=True)
    units = json.loads((ROOT / "backend" / "data" / "admin" / "vnm_adm2_2020.json").read_text(encoding="utf-8"))["units"]
    rnd = random.Random(SEED)
    pool = range(len(units))
    if V2:                                    # loại huyện đã có trong mẫu v1
        v1 = json.loads((ROOT / "backend" / "data" / "eval" / "flood_susceptibility_points.json").read_text(encoding="utf-8"))
        used = {(p["district"], p["province"]) for p in v1}
        pool = [i for i in range(len(units)) if (units[i]["name"], units[i]["province"]) not in used]
    pick = rnd.sample(list(pool), N)
    out = []
    for i in pick:
        u = units[i]
        g = shape({"type": u["type"], "coordinates": json.loads(u["coordinates"]) if isinstance(u["coordinates"], str)
                   else u["coordinates"]})
        x0, y0, x1, y1 = g.bounds
        for _ in range(500):
            p = Point(rnd.uniform(x0, x1), rnd.uniform(y0, y1))
            if g.contains(p):
                out.append({"id": f"p{len(out):03d}", "district": u["name"], "province": u["province"],
                            "lat": round(p.y, 5), "lon": round(p.x, 5)})
                break
    (WORK / "points.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    if V2:
        (ROOT / "backend" / "data" / "eval" / "flood_susceptibility_v2_points.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(out)} điểm, {len({p['province'] for p in out})} tỉnh → {WORK / 'points.json'}")


def _features(lat: float, lon: float) -> dict:
    from alert_calibration import _get
    from app.services import datasources as ds, river_grid
    step = 500.0
    dlat = step / 111_320.0
    dlon = step / (111_320.0 * max(0.1, math.cos(math.radians(lat))))
    lats = [lat, lat + dlat, lat - dlat, lat, lat]
    lons = [lon, lon, lon, lon + dlon, lon - dlon]
    d = _get("https://api.open-meteo.com/v1/elevation?latitude=" + ",".join(f"{v:.5f}" for v in lats)
             + "&longitude=" + ",".join(f"{v:.5f}" for v in lons))
    e = [float(x) for x in d["elevation"]]
    grad = math.hypot((e[1] - e[2]) / (2 * step), (e[3] - e[4]) / (2 * step))
    river = river_grid.nearest_km(lat, lon)
    return {"elev_m": round(e[0], 1), "slope_deg": round(math.degrees(math.atan(grad)), 2), "relief_m": round(max(e) - min(e), 1),
            "dist_coast_km": round(ds.distance_to_coast_km(lat, lon), 2),
            "dist_river_km": round(min(3.0, river) if river is not None and math.isfinite(river) else 3.0, 3)}


def harvest() -> None:
    from app.db import init_db
    from app.services import water_history
    init_db()
    pts = json.loads((WORK / "points.json").read_text(encoding="utf-8"))
    f = WORK / "rows.jsonl"
    done = {json.loads(l)["id"] for l in f.read_text(encoding="utf-8").splitlines() if l.strip()} if f.exists() else set()
    for k, p in enumerate(pts):
        if p["id"] in done:
            continue
        t0 = time.time()
        row = {**p}
        try:
            row.update(_features(p["lat"], p["lon"]))
            h = water_history.history(p["lat"], p["lon"])
            if h.get("available"):
                evs = h.get("events") or []
                row.update(radar_ok=True, n_events=len(evs), label=1 if evs else 0,
                           n_scenes=h.get("n_scenes"), first=(h.get("first") or "")[:10])
            else:
                row.update(radar_ok=False, why=(h.get("message") or "")[:120])
        except Exception as e:  # noqa: BLE001 — ghi lỗi, chạy lại sẽ bỏ qua điểm đã có dòng
            row.update(radar_ok=False, why=f"{type(e).__name__}: {str(e)[:100]}")
        with f.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"[{k + 1}/{len(pts)}] {p['id']} {p['province']:<14} label={row.get('label')} "
              f"{round(time.time() - t0)}s", flush=True)


def _x(r: dict, base: bool = False) -> list[float]:
    if base:
        return [math.log1p(max(0.0, r["elev_m"] + 5))]
    return [math.log1p(max(0.0, r["elev_m"] + 5)), r["slope_deg"], math.log1p(r["relief_m"]),
            math.log1p(r["dist_coast_km"]), math.log1p(r["dist_river_km"])]


def _fit(X, y, lam=1.0, steps=2000, lr=0.1):
    import numpy as np
    X, y = np.asarray(X, float), np.asarray(y, float)
    mu, sd = X.mean(0), X.std(0) + 1e-9
    Z = np.hstack([np.ones((len(X), 1)), (X - mu) / sd])
    w = np.zeros(Z.shape[1])
    for _ in range(steps):
        p = 1 / (1 + np.exp(-Z @ w))
        g = Z.T @ (p - y) / len(y) + lam * np.r_[0, w[1:]] / len(y)
        w -= lr * g
    return {"mu": mu.tolist(), "sd": sd.tolist(), "w": w.tolist()}


def _pred(m, X):
    import numpy as np
    X = np.asarray(X, float)
    Z = np.hstack([np.ones((len(X), 1)), (X - np.asarray(m["mu"])) / np.asarray(m["sd"])])
    return (1 / (1 + np.exp(-Z @ np.asarray(m["w"])))).tolist()


def _auc(y, s) -> float | None:
    pos = [b for a, b in zip(y, s) if a == 1]
    neg = [b for a, b in zip(y, s) if a == 0]
    if not pos or not neg:
        return None
    win = sum((1.0 if p > n else 0.5 if p == n else 0.0) for p in pos for n in neg)
    return win / (len(pos) * len(neg))


def run_v2() -> None:
    """v2: logistic CHỈ độ cao, cổng AUC + Brier skill so với tỉ lệ nền (giao thức v2)."""
    g = json.loads(PROTO.read_text(encoding="utf-8"))["gate"]
    rows = [json.loads(l) for l in (WORK / "rows.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    pts = json.loads((WORK / "points.json").read_text(encoding="utf-8"))
    if len({r["id"] for r in rows}) < len(pts):
        sys.exit(f"DỪNG — mới có {len(rows)}/{len(pts)} điểm; chạy harvest trước.")
    ok = [r for r in rows if r.get("radar_ok") and "elev_m" in r]
    provs = sorted({p["province"] for p in pts})
    test_p = {p for i, p in enumerate(provs) if i % 5 == 4}
    tr_, te = [r for r in ok if r["province"] not in test_p], [r for r in ok if r["province"] in test_p]
    ytr, yte = [r["label"] for r in tr_], [r["label"] for r in te]
    m = _fit([_x(r, True) for r in tr_], ytr)
    pte = _pred(m, [_x(r, True) for r in te])
    auc = _auc(yte, pte)
    base = sum(ytr) / max(1, len(ytr))
    brier = sum((p - y) ** 2 for p, y in zip(pte, yte)) / max(1, len(yte))
    brier0 = sum((base - y) ** 2 for y in yte) / max(1, len(yte))
    bss = 1 - brier / brier0 if brier0 else None
    checks = {"min_test_points": len(te) >= g["min_test_points"], "min_test_positives": sum(yte) >= g["min_test_positives"],
              "auc": auc is not None and auc >= g["auc_min"],
              "brier_skill": bss is not None and bss > g["brier_skill_vs_base_rate_min"]}
    passed = all(checks.values())
    res = {"protocol": PROTO.name, "ran_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
           "n_points": len(rows), "n_radar_ok": len(ok), "n_train": len(tr_), "n_test": len(te),
           "pos_rate_train": round(base, 3), "pos_test": sum(yte), "test_provinces": sorted(test_p),
           "auc": None if auc is None else round(auc, 3), "brier": round(brier, 4), "brier_base_rate": round(brier0, 4),
           "brier_skill": None if bss is None else round(bss, 3), "weights": m, "checks": checks, "passed": passed,
           "excluded": [{k: r.get(k) for k in ("id", "province", "why")} for r in rows if not r.get("radar_ok")]}
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    if passed:
        MODEL.parent.mkdir(parents=True, exist_ok=True)
        MODEL.write_text(json.dumps({"features": ["log1p(elev+5)"], **m, "auc_test": round(auc, 3), "brier_skill": round(bss, 3),
                                     "ref_scores": sorted(round(v, 4) for v in _pred(m, [_x(r, True) for r in ok])),
                                     "protocol": PROTO.name}, indent=1), encoding="utf-8")
    print(f"v2 AUC {auc} · BSS {bss} · test {len(te)} điểm ({sum(yte)} dương) → {'ĐẠT' if passed else 'TRƯỢT'} {checks}")


def run() -> None:
    proto = json.loads(PROTO.read_text(encoding="utf-8"))
    g = proto["gate"]
    rows = [json.loads(l) for l in (WORK / "rows.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    pts = json.loads((WORK / "points.json").read_text(encoding="utf-8"))
    if len({r["id"] for r in rows}) < len(pts):
        sys.exit(f"DỪNG — mới có {len(rows)}/{len(pts)} điểm; chạy harvest trước.")
    ok = [r for r in rows if r.get("radar_ok") and "elev_m" in r]
    provs = sorted({p["province"] for p in pts})
    test_p = {p for i, p in enumerate(provs) if i % 5 == 4}
    tr_, te = [r for r in ok if r["province"] not in test_p], [r for r in ok if r["province"] in test_p]
    ytr, yte = [r["label"] for r in tr_], [r["label"] for r in te]
    m = _fit([_x(r) for r in tr_], ytr)
    mb = _fit([_x(r, True) for r in tr_], ytr)
    auc = _auc(yte, _pred(m, [_x(r) for r in te]))
    auc_b = _auc(yte, _pred(mb, [_x(r, True) for r in te]))
    checks = {"min_test_points": len(te) >= g["min_test_points"], "min_test_positives": sum(yte) >= g["min_test_positives"],
              "auc": auc is not None and auc >= g["auc_min"],
              "gain_over_baseline": auc is not None and auc_b is not None and auc - auc_b >= g["auc_gain_over_baseline_min"]}
    passed = all(checks.values())
    res = {"protocol": PROTO.name, "ran_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
           "n_points": len(rows), "n_radar_ok": len(ok), "n_train": len(tr_), "n_test": len(te),
           "pos_rate_train": round(sum(ytr) / max(1, len(ytr)), 3), "pos_test": sum(yte), "test_provinces": sorted(test_p),
           "auc": None if auc is None else round(auc, 3), "auc_baseline_elev": None if auc_b is None else round(auc_b, 3),
           "weights": m, "checks": checks, "passed": passed,
           "excluded": [{k: r.get(k) for k in ("id", "province", "why")} for r in rows if not r.get("radar_ok")]}
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    if passed:
        MODEL.parent.mkdir(parents=True, exist_ok=True)
        MODEL.write_text(json.dumps({"features": ["log1p(elev+5)", "slope_deg", "log1p(relief)", "log1p(coast_km)",
                                                  "log1p(river_km)"], **m, "auc_test": round(auc, 3),
                                     # điểm số của mọi điểm mẫu đọc được radar — để nói "thuộc nhóm X% dễ ngập nhất"
                                     "ref_scores": sorted(round(v, 4) for v in _pred(m, [_x(r) for r in ok])),
                                     "auc_baseline": round(auc_b, 3), "protocol": PROTO.name}, indent=1), encoding="utf-8")
    print(f"AUC {auc} vs chỉ độ cao {auc_b} · test {len(te)} điểm ({sum(yte)} dương) → {'ĐẠT' if passed else 'TRƯỢT'} {checks}")


if __name__ == "__main__":
    {"points": points_v3 if V3 else points, "harvest": harvest,
     "run": run_v3 if V3 else run_v2 if V2 else run}[sys.argv[1]]()
