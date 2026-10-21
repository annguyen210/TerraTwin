"""Phép kiểm đăng ký trước U-Net radar bản 2 — backend/data/ml/s1_unet_vn_protocol.json. Chấm MỘT lần.

    python ops/s1_unet_v2_gate.py      # cần <dữ liệu>/s1_water_unet_vn.onnx (ml/s1_unet_v2_train.py) + bản 1 .onnx

G1 (độc lập): IoU gộp trên cặp TEST so với nhãn tự động S2 — bản 2 / bản 1 / ngưỡng VV < −18 dB, cùng mặt nạ địa hình.
G2 (đã biết trước, không độc lập): đúng các ca của bản 1 (Quảng Điền dương tính; Đà Lạt + Thiên An âm tính).
G3 (độc lập): 3 điểm đồi mới × 24 cảnh — xác nhận nhầm ≤ 1/72.
Ghi backend/data/ml/s1_unet_vn_result.json; từ chối chạy khi đã có (trừ --force, phải ghi run_log).
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import random
import sys
import time
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.join(ROOT, "ops"))

import numpy as np  # noqa: E402
import onnxruntime as ort  # noqa: E402

from app.services import mpc, s1_unet as U, water_history as wh  # noqa: E402
from s1_unet_gate import NEG as OLD_NEG, POS as OLD_POS, SEED as OLD_SEED, N_NEG, overlaps  # noqa: E402

DATA = os.environ.get("TT_UNET_V2", "D:/tt-scratch/unet_v2")
V2 = os.path.join(DATA, "s1_water_unet_vn.onnx")
V1 = os.environ.get("TT_UNET_V1_ONNX", "D:/tt-scratch/model_files/s1_water_unet.onnx")
NEW_NEG = [("Đồi chè Bảo Lộc", 11.555, 107.795), ("Đồi cà phê Đắk Mil", 12.450, 107.620), ("Rừng thông Măng Đen", 14.605, 108.285)]
SEED = 20261021


def sha(p: str) -> str:
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def sess(path: str):
    return ort.InferenceSession(path, providers=["CPUExecutionProvider"])


def g1(s2, s1) -> dict:
    tot = {k: [0, 0] for k in ("v2", "v1", "thr")}
    per = []
    files = sorted(glob.glob(os.path.join(DATA, "test_*_*_*.npz")))
    for f in files:
        z = np.load(f)
        x, lab, slope = U.prepare(z["s1"]), z["label"], z["slope"].astype(np.float32)
        ok, wat = lab != 255, lab == 1
        preds = {"v2": U.predict_mask(s2.run(None, {"s1": x})[0][0, 0], slope),
                 "v1": U.predict_mask(s1.run(None, {"s1": x})[0][0, 0], slope),
                 "thr": U.predict_mask(np.where(10 * np.log10(np.maximum(z["s1"][0], 1e-6)) < -18.0, 1.0, -1.0), slope)}
        row = {"file": os.path.basename(f), "water_frac": round(float(wat[ok].mean()), 4) if ok.any() else None}
        for k, m in preds.items():
            i, u = int((m & wat & ok).sum()), int(((m | wat) & ok).sum())
            tot[k][0] += i
            tot[k][1] += u
            row[k] = round(i / u, 4) if u else None
        per.append(row)
    iou = {k: round(a / b, 4) if b else 0.0 for k, (a, b) in tot.items()}
    checks = {"v2_ge_0_45": [iou["v2"], iou["v2"] >= 0.45], "v2_minus_v1_ge_0_10": [round(iou["v2"] - iou["v1"], 4), iou["v2"] - iou["v1"] >= 0.10],
              "v2_minus_thr_ge_0_10": [round(iou["v2"] - iou["thr"], 4), iou["v2"] - iou["thr"] >= 0.10],
              "n_test_pairs_ge_40": [len(files), len(files) >= 40]}
    return {"pooled_iou": iou, "checks": checks, "pass": all(c[1] for c in checks.values()), "pairs": per}


def item_json(item_id: str) -> dict | None:
    return mpc._call(U.STAC_ITEM.format(c="sentinel-1-rtc", i=item_id))


def share_item(s2, item: dict, lat: float, lon: float):
    for k in range(3):                                         # lỗi mạng: thử lại, không đổi phép chấm
        epsg, box = U.s1_grid_box(item, lat, lon)
        arr = U.fetch_grid(item, epsg, box)
        slope = U.slope_deg(epsg, box, lat, lon)
        if arr is not None and slope is not None:
            return U.plot_share(U.predict_mask(s2.run(None, {"s1": U.prepare(arr)})[0][0, 0], slope))
        time.sleep(3 * (k + 1))
    return None


def share_day(s2, lat, lon, day):
    sc = wh.scene(lat, lon, day)
    it = item_json(sc["item"]) if sc else None
    return (None, None) if not it else (share_item(s2, it, lat, lon), it["id"])


def g2(s2) -> dict:
    name, lat, lon, floods = OLD_POS
    h = wh.history(lat, lon)
    assert h.get("available"), h
    evs = []
    for e in h["events"]:
        s, it = share_day(s2, lat, lon, e["flag_date"])
        evs.append({"start": e["start"], "end": e["end"], "flag_date": e["flag_date"], "share": s, "item": it})
        print("  đợt", evs[-1], flush=True)
    pos = []
    for label, a, b in floods:
        hit = [x for x in evs if overlaps(x, a, b)]
        pos.append({"label": label, "events": hit, "pass": bool(hit) and all(x["share"] is not None and x["share"] >= U.CONFIRM_SHARE for x in hit)})
    neg = []
    for nm, la, lo in OLD_NEG:
        hh = wh.history(la, lo)
        days = sorted(d for d, *_ in hh["series"])
        rows = [{"date": d, "share": share_day(s2, la, lo, d)[0]} for d in sorted(random.Random(OLD_SEED).sample(days, N_NEG))]
        bad = [r for r in rows if r["share"] is None or r["share"] >= U.CONFIRM_SHARE]
        neg.append({"case": nm, "n": len(rows), "bad": len(bad), "scenes": rows, "pass": not bad})
        print(nm, "nhầm/không đọc:", len(bad), flush=True)
    return {"not_independent": True, "positive": pos, "negative": neg, "all_events_quang_dien": evs,
            "pass": all(p["pass"] for p in pos) and all(n["pass"] for n in neg)}


def g3(s2) -> dict:
    out, bad_total = [], 0
    for nm, la, lo in NEW_NEG:
        feats = []
        for a, b in [("2017-01-01", "2019-12-31"), ("2020-01-01", "2022-12-31"), ("2023-01-01", "2026-09-30")]:
            r = mpc._call(mpc.STAC, {"collections": ["sentinel-1-rtc"], "bbox": mpc.bbox_around(la, lo, 100.0),
                                     "datetime": f"{a}T00:00:00Z/{b}T23:59:59Z", "limit": 1000})
            feats += (r or {}).get("features") or []
        by_day = {}
        for f in sorted(feats, key=lambda f: f["properties"]["datetime"]):
            by_day.setdefault(f["properties"]["datetime"][:10], f)
        days = sorted(by_day)
        rows = []
        for d in sorted(random.Random(SEED).sample(days, 24)):
            rows.append({"date": d, "item": by_day[d]["id"], "share": share_item(s2, by_day[d], la, lo)})
        bad = [r for r in rows if r["share"] is None or r["share"] >= U.CONFIRM_SHARE]
        bad_total += len(bad)
        out.append({"case": nm, "lat": la, "lon": lo, "n_days_available": len(days), "n": len(rows), "bad": len(bad), "scenes": rows})
        print(nm, "nhầm/không đọc:", len(bad), "trên", len(rows), flush=True)
    return {"sites": out, "bad_total": bad_total, "n_total": sum(o["n"] for o in out), "pass": bad_total <= 1}


def main() -> None:
    if os.path.exists(U.V2_RESULT_PATH) and "--force" not in sys.argv:
        sys.exit("Đã có kết quả — chấm một lần. Chạy lại phải có --force và ghi lý do vào run_log.")
    t0 = time.time()
    s2, s1 = sess(V2), sess(V1)
    r1 = g1(s2, s1)
    print("G1", r1["pooled_iou"], r1["checks"], flush=True)
    r2 = g2(s2)
    print("G2", r2["pass"], flush=True)
    r3 = g3(s2)
    print("G3", r3["bad_total"], "/", r3["n_total"], flush=True)
    res = {"protocol": "terratwin.s1_unet_vn/2", "scored_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "v2_onnx_sha256": sha(V2), "v1_onnx_sha256": sha(V1), "slope_max_deg": U.SLOPE_MAX_DEG,
           "G1": r1, "G2": r2, "G3": r3, "passed": r1["pass"] and r2["pass"] and r3["pass"], "seconds": round(time.time() - t0, 1)}
    json.dump(res, open(U.V2_RESULT_PATH, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
    print(json.dumps({"passed": res["passed"], "G1": r1["pass"], "G2": r2["pass"], "G3": r3["pass"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
