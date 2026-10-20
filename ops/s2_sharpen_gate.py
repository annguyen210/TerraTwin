"""Phép kiểm đăng ký trước S10 ① / ② — làm sắc B11 20 m → 10 m (backend/data/ml/s2_sharpen_protocol.json).

    python ops/s2_sharpen_gate.py fetch     # đọc cảnh thật cho 49 tỉnh → D:/tt-scratch/sharpen/scenes (không vào repo)
    python ops/s2_sharpen_gate.py run       # học ml trên TRAIN → chọn trên VAL → chấm TEST MỘT lần → kết quả JSON

`run` từ chối chạy khi đã có tệp kết quả (chấm một lần); chạy lại phải ghi lý do vào run_log của giao thức.
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import numpy as np  # noqa: E402

from app.services import mpc  # noqa: E402
from app.services import s2_sharpen as S  # noqa: E402

PROTO = json.load(open(S.PROTOCOL_PATH, encoding="utf-8"))
CACHE = os.environ.get("TT_SHARPEN_CACHE", "D:/tt-scratch/sharpen/scenes")
N20 = 64
BORDER = 2


def stac(box: list[float]) -> list[dict]:
    r = mpc._call(mpc.STAC, {"collections": [mpc.COLLECTION], "bbox": box,
                             "datetime": "2024-01-01T00:00:00Z/2026-09-30T23:59:59Z",
                             "query": {"eo:cloud_cover": {"lt": 20}}, "limit": 8,
                             "sortby": [{"field": "eo:cloud_cover", "direction": "asc"}]})
    return (r or {}).get("features") or []


def pick(lat: float, lon: float) -> dict | None:
    box = mpc.bbox_around(lat, lon, N20 * 10.0 + 40.0)
    for it in stac(box)[:8]:
        d = S.fetch(it, lat, lon, N20)
        if d is None:
            continue
        ok = S.clear_mask(d["scl"], d["valid"])
        if ok.mean() >= 0.95 and (d["scl"] == 6).mean() <= 0.40:
            d["cloud_scene_pct"] = float(it["properties"].get("eo:cloud_cover") or 0.0)
            d["baseline"] = it["properties"].get("s2:processing_baseline")
            return d
    return None


def do_fetch() -> None:
    os.makedirs(CACHE, exist_ok=True)
    for split, rows in PROTO["data"]["split"].items():
        for i, p in enumerate(rows):
            out = os.path.join(CACHE, f"{split}_{i:02d}.npz")
            if os.path.exists(out):
                continue
            rng = random.Random(20261020 + i + {"train": 0, "val": 100, "test": 200}[split])
            got, tries = None, []
            for t in range(4):
                la, lo = p["lat"] + rng.uniform(-0.05, 0.05), p["lon"] + rng.uniform(-0.05, 0.05)
                tries.append([round(la, 5), round(lo, 5)])
                got = pick(la, lo)
                if got:
                    break
            meta = {"split": split, "province": p["province"], "tries": tries, "ok": bool(got)}
            if got:
                meta.update({k: got[k] for k in ("item", "date", "epsg", "box", "offset", "cloud_scene_pct", "baseline")})
                np.savez_compressed(out, fine=got["fine"], b11=got["b11"], scl=got["scl"], valid=got["valid"],
                                    meta=json.dumps(meta, ensure_ascii=False))
            else:
                np.savez_compressed(out, meta=json.dumps(meta, ensure_ascii=False))
            print(split, i, p["province"], "OK " + got["item"] if got else "BỎ (không có cảnh đạt)", flush=True)


def load(split: str) -> list[dict]:
    out = []
    for i in range(len(PROTO["data"]["split"][split])):
        z = np.load(os.path.join(CACHE, f"{split}_{i:02d}.npz"), allow_pickle=False)
        meta = json.loads(str(z["meta"]))
        if not meta["ok"]:
            out.append({"meta": meta})
            continue
        fine20, c40, t20 = S.down(z["fine"]), S.down(z["b11"]), z["b11"]
        m = S.clear_mask(z["scl"], z["valid"])
        m[:BORDER], m[-BORDER:], m[:, :BORDER], m[:, -BORDER:] = False, False, False, False
        out.append({"meta": meta, "fine": fine20, "c": c40, "t": t20, "mask": m})
    return out


def rmse(a, b, m) -> float:
    return float(np.sqrt(np.mean((a[m] - b[m]) ** 2)))


def score(sc: dict, pred) -> dict:
    p = pred(sc["fine"], sc["c"])
    b08 = sc["fine"][3]
    return {"rmse_b11": rmse(p, sc["t"], sc["mask"]),
            "ndmi_rmse": rmse(S.ndmi(b08, p), S.ndmi(b08, sc["t"]), sc["mask"]),
            "consistency": float(np.abs(S.down(p) - sc["c"]).max())}


def do_run() -> None:
    if os.path.exists(S.RESULT_PATH) and "--force" not in sys.argv:
        sys.exit("Đã có kết quả — chấm một lần. Chạy lại phải có --force và ghi lý do vào run_log.")
    t0 = time.time()
    train = [s for s in load("train") if "fine" in s]
    X = np.concatenate([S.ml_features(s["fine"], s["c"])[:, s["mask"]].T for s in train])
    y = np.concatenate([(s["t"] - S.up(s["c"]))[s["mask"]] for s in train])
    G = X.T @ X
    lam = 1e-6 * np.trace(G) / G.shape[0]
    w = np.linalg.solve(G + lam * np.eye(G.shape[0]), X.T @ y)

    methods = {"bicubic": S.bicubic, "rg": S.sharpen_rg, "ml": lambda f, c: S.sharpen_ml(f, c, w)}
    val = [s for s in load("val") if "fine" in s]
    vmed = {k: float(np.median([score(s, methods[k])["rmse_b11"] for s in val])) for k in ("rg", "ml")}
    selected = "ml" if vmed["ml"] < vmed["rg"] - 1e-6 else "rg"

    test_all = load("test")
    rows = []
    for s in test_all:
        if "fine" not in s:
            rows.append({"province": s["meta"]["province"], "skipped": True, "tries": s["meta"]["tries"]})
            continue
        r = {k: score(s, methods[k]) for k in methods}
        rows.append({"province": s["meta"]["province"], "item": s["meta"]["item"], "date": s["meta"]["date"],
                     "pixels": int(s["mask"].sum()),
                     **{f"{k}_{m}": round(v[m], 6) for k, v in r.items() for m in v},
                     "rel_gain": round(1 - r[selected]["rmse_b11"] / r["bicubic"]["rmse_b11"], 4),
                     "ndmi_rel_gain": round(1 - r[selected]["ndmi_rmse"] / r["bicubic"]["ndmi_rmse"], 4),
                     "beats_bicubic": r[selected]["rmse_b11"] < r["bicubic"]["rmse_b11"]})
    sc = [r for r in rows if not r.get("skipped")]
    g1 = float(np.median([r["rel_gain"] for r in sc])) if sc else 0.0
    g2 = float(np.mean([r["beats_bicubic"] for r in sc])) if sc else 0.0
    g3 = float(np.median([r["ndmi_rel_gain"] for r in sc])) if sc else 0.0
    g4 = max((r[f"{selected}_consistency"] for r in sc), default=1.0)
    gate = PROTO["gate"]
    checks = {"g1_median_rel_gain": [round(g1, 4), g1 >= 0.15], "g2_share_beats_bicubic": [round(g2, 4), g2 >= 0.80],
              "g3_median_ndmi_rel_gain": [round(g3, 4), g3 >= 0.15], "g4_max_consistency": [g4, g4 <= 0.002],
              "n_test_scenes": [len(sc), len(sc) >= gate["min_test_scenes"]]}
    other = "ml" if selected == "rg" else "rg"
    res = {
        "protocol": PROTO["id"], "scored_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "passed": all(v[1] for v in checks.values()), "selected": selected, "checks": checks,
        "val_median_rmse_b11": {k: round(v, 6) for k, v in vmed.items()},
        "test_median": {k: {"rmse_b11": round(float(np.median([r[f"{k}_rmse_b11"] for r in sc])), 6),
                            "ndmi_rmse": round(float(np.median([r[f"{k}_ndmi_rmse"] for r in sc])), 6)}
                        for k in methods} if sc else {},
        "other_method_median_rel_gain": round(float(np.median([1 - r[f"{other}_rmse_b11"] / r["bicubic_rmse_b11"]
                                                               for r in sc])), 4) if sc else None,
        "ml_weights": [float(v) for v in w], "ml_lambda": float(lam), "ml_train_pixels": int(len(y)),
        "n": {"train": len(train), "val": len(val), "test": len(sc)},
        "skipped": [r["province"] for r in rows if r.get("skipped")],
        "scenes": {sp: [s["meta"] for s in load(sp)] for sp in ("train", "val")},
        "test": rows,
        "seconds": round(time.time() - t0, 1),
    }
    json.dump(res, open(S.RESULT_PATH, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
    print(json.dumps({k: res[k] for k in ("passed", "selected", "checks", "val_median_rmse_b11", "test_median", "n")},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    {"fetch": do_fetch, "run": do_run}[sys.argv[1]]()
