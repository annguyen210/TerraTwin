"""GĐ5 · LOẠI ĐẤT BẰNG MÔ HÌNH NỀN ĐỊA KHÔNG GIAN (AlphaEarth Foundations) — thay U-Net đã trượt hai lần.

Kế hoạch tổng ghi "tinh chỉnh Prithvi-EO-2.0 (hoặc Clay)". AlphaEarth Foundations (Google DeepMind) cùng
loại: mô hình nền học từ chuỗi đa cảm biến (Sentinel-1/2, Landsat, …) cả năm, xuất một vectơ 64 chiều cho
mỗi điểm ảnh ~10 m. Lợi thế với dự án này: CHẠY ĐƯỢC TRÊN CPU (chỉ cần một bộ phân loại tuyến tính trên vectơ
đã tính sẵn), không cần GPU Kaggle; và đã tích hợp trong máy chủ (services/aef.py).

CÙNG ĐỀ BÀI VỚI U-NET để so công bằng (backend/data/landcover_runs.json):
  · Nhãn: ESA WorldCover 2021, đúng 213 ô 2,56 km của bộ dữ liệu U-Net lần 2 (backend/data/dl2).
  · Chia theo tỉnh, y hệt: KIỂM TRA (giữ lại hoàn toàn) Cần Giờ, Cần Thơ, Hà Giang, Đà Nẵng · KIỂM ĐỊNH Buôn Ma
    Thuột, Huế · còn lại huấn luyện.
  · Ngưỡng: mIoU ≥ 0,35 trên tỉnh giữ lại (cùng cách tính: trung bình IoU các lớp có mặt); báo riêng lớp Đất
    trồng trọt. Chấm tập kiểm tra ĐÚNG MỘT LẦN; hệ số L2 chọn trên tập kiểm định.
  · Khác biệt nói rõ: vectơ AlphaEarth năm 2021 thay ảnh Sentinel-2; chấm trên 1.024 điểm ảnh ngẫu nhiên mỗi ô
    (ước lượng không chệch của ma trận nhầm lẫn theo điểm ảnh) thay vì cả ô.
  · Lưu ý trung thực: 4 tỉnh kiểm tra đã được hai lần chạy U-Net dùng để chấm. Đây là lần chấm thứ ba, cuối cùng
    trên bộ tỉnh này; lần sau phải đổi tỉnh giữ lại.

    cd backend && python -m app.ml.aef_landcover protocol   # ghi giao thức (commit TRƯỚC khi chạy)
    python -m app.ml.aef_landcover extract                  # lấy vectơ (tiếp tục được nếu đứt)
    python -m app.ml.aef_landcover train                    # chọn L2 trên kiểm định, chấm kiểm tra một lần
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from collections import defaultdict
from datetime import date

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "..", "data")
DL2 = os.path.join(DATA, "dl2")
OUT = os.path.join(DATA, "ml")
PROTO = os.path.join(OUT, "aef_landcover_protocol.json")
FEAT = os.path.join(OUT, "aef_lc_features.npz")
MODEL = os.path.join(OUT, "aef_landcover_model.json")
RUNS = os.path.join(DATA, "landcover_runs.json")

YEAR = 2021
PER_PATCH = 1024
SEED = 20261009
TEST = ["Cần Giờ", "Cần Thơ", "Hà Giang", "Đà Nẵng"]
VAL = ["Buôn Ma Thuột", "Huế"]
L2_GRID = [1e-4, 1e-3, 1e-2]
THRESHOLD = 0.35
PATCH, PX_M = 256, 10.0

PROTOCOL = {
    "id": "terratwin.gd5.aef_landcover/1",
    "question": "Vectơ AlphaEarth 2021 + bộ phân loại tuyến tính có đạt mIoU ≥ 0,35 trên 4 tỉnh giữ lại "
                "(cùng nhãn, cùng chia tập với U-Net đã trượt 0,232 và 0,314) không?",
    "data": {"labels": "ESA WorldCover 2021 — backend/data/dl2/patches.npz (213 ô 256×256, 10 m)",
             "features": f"AlphaEarth Foundations annual embedding {YEAR}, 64 chiều (source.coop/tge-labs/aef-mosaic)",
             "sampling": f"{PER_PATCH} điểm ảnh ngẫu nhiên có nhãn mỗi ô, hạt giống {SEED}"},
    "split": {"test_provinces": TEST, "val_provinces": VAL, "train": "các ô còn lại"},
    "model": "hồi quy softmax 11 lớp trên vectơ 64 chiều, trọng số lớp căn bậc hai nghịch tần suất (trần 10), "
             f"L2 chọn trong {L2_GRID} theo mIoU kiểm định",
    "metric": "mIoU = trung bình IoU các lớp có mặt (tp+fp+fn > 0), như backend/app/dl/train.py; báo riêng Đất trồng trọt",
    "threshold": {"miou_test_min": THRESHOLD},
    "rules": ["Chấm tập kiểm tra đúng một lần.", "Không đạt thì ghi rejected vào landcover_runs.json và không bật.",
              "Tập kiểm tra này đã dùng cho U-Net lần 1–2; đây là lần chấm cuối trên bộ tỉnh này."],
    "registered": "2026-10-09",
}


# ------------------------------------------------------------------ dữ liệu

def _box(lat: float, lon: float) -> list[float]:
    """Y hệt app.dl.fetch._box: khung ô 256 điểm ảnh 10 m quanh tâm."""
    import math
    half = PATCH * PX_M / 2.0
    dlat = half / 111_320.0
    dlon = half / (111_320.0 * max(0.2, abs(math.cos(math.radians(lat)))))
    return [lon - dlon, lat - dlat, lon + dlon, lat + dlat]


def vectors(coords: np.ndarray, year: int) -> np.ndarray:
    """Vectơ AlphaEarth tại từng (lat, lon) — gom theo khối con để mỗi khối chỉ tải một lần. NaN nếu trống."""
    from app.services import aef
    t = aef.YEARS.index(year)
    rc = [aef.pixel(float(la), float(lo)) for la, lo in coords]
    groups: dict[tuple, list[int]] = defaultdict(list)
    for k, (r, c) in enumerate(rc):
        groups[(r // aef.SHARD, c // aef.SHARD, (r % aef.SHARD) // aef.INNER, (c % aef.SHARD) // aef.INNER)].append(k)
    out = np.full((len(rc), 64), np.nan, dtype="float32")
    for (sy, sx, iy, ix), ks in groups.items():
        ch = aef._chunk(t, sy, sx, iy, ix)
        if ch is None:
            continue
        for k in ks:
            r, c = rc[k]
            v = ch[:, r % aef.INNER, c % aef.INNER]
            if (v == aef.NODATA).any():
                continue
            out[k] = aef.dequantize(v)
    return out


def _split(site: str) -> str:
    if any(p in site for p in TEST):
        return "test"
    if any(p in site for p in VAL):
        return "val"
    return "train"


def extract(verbose: bool = True) -> dict:
    meta = json.load(open(os.path.join(DL2, "meta.json"), encoding="utf-8"))["meta"]
    Y = np.load(os.path.join(DL2, "patches.npz"))["Y"]
    have = dict(np.load(FEAT)) if os.path.exists(FEAT) else {}
    done = set(int(i) for i in have.get("done", []))
    Xs = [have["X"]] if "X" in have else []
    ys = [have["y"]] if "y" in have else []
    ps = [have["patch"]] if "patch" in have else []
    rng = np.random.default_rng(SEED)
    picks = []
    for i in range(len(meta)):                     # rút mẫu TRƯỚC, tất định, không phụ thuộc thứ tự tải
        ok = np.flatnonzero(Y[i].ravel() != 255)
        picks.append(rng.choice(ok, size=min(PER_PATCH, len(ok)), replace=False) if len(ok) else np.array([], int))
    t0 = time.time()
    for i, m in enumerate(meta):
        if i in done:
            continue
        l, b, r, tp = _box(m["lat"], m["lon"])
        idx = picks[i]
        rows, cols = idx // PATCH, idx % PATCH
        lat = tp - (rows + 0.5) * (tp - b) / PATCH
        lon = l + (cols + 0.5) * (r - l) / PATCH
        v = vectors(np.stack([lat, lon], 1), YEAR)
        keep = np.isfinite(v).all(1)
        Xs.append(v[keep].astype("float16"))
        ys.append(Y[i].ravel()[idx][keep].astype("uint8"))
        ps.append(np.full(int(keep.sum()), i, dtype="int16"))
        done.add(i)
        if verbose:
            print(f"  ô {i + 1}/{len(meta)} {m['site']}: {int(keep.sum())} điểm ảnh · {time.time() - t0:.0f}s", flush=True)
        if len(done) % 10 == 0 or len(done) == len(meta):
            np.savez_compressed(FEAT, X=np.concatenate(Xs), y=np.concatenate(ys), patch=np.concatenate(ps),
                                done=np.array(sorted(done)))
    return {"patches": len(done), "pixels": int(sum(len(y) for y in ys))}


# ------------------------------------------------------------------ mô hình

def _softmax(z):
    z = z - z.max(1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(1, keepdims=True)


def fit(X: np.ndarray, y: np.ndarray, n_cls: int, l2: float, iters: int = 600, lr: float = 0.05) -> tuple[np.ndarray, np.ndarray]:
    """Hồi quy softmax, Adam toàn lô, trọng số lớp căn bậc hai nghịch tần suất (trần 10) — như U-Net lần 2."""
    cnt = np.bincount(y, minlength=n_cls).astype(float)
    w_cls = np.sqrt(cnt.sum() / (n_cls * np.maximum(cnt, 1)))
    w_cls = np.minimum(w_cls, 10.0)
    sw = w_cls[y]
    sw /= sw.sum()
    W = np.zeros((X.shape[1], n_cls)); b = np.zeros(n_cls)
    Y1 = np.eye(n_cls)[y]
    mW = np.zeros_like(W); vW = np.zeros_like(W); mb = np.zeros_like(b); vb = np.zeros_like(b)
    for t in range(1, iters + 1):
        P = _softmax(X @ W + b)
        G = (P - Y1) * sw[:, None]
        gW = X.T @ G + l2 * W
        gb = G.sum(0)
        for g, m_, v_, p in ((gW, mW, vW, W), (gb, mb, vb, b)):
            m_ *= 0.9; m_ += 0.1 * g
            v_ *= 0.999; v_ += 0.001 * g * g
            p -= lr * (m_ / (1 - 0.9 ** t)) / (np.sqrt(v_ / (1 - 0.999 ** t)) + 1e-8)
    return W, b


def miou(y: np.ndarray, pred: np.ndarray, n_cls: int) -> tuple[float, list]:
    conf = np.bincount(y * n_cls + pred, minlength=n_cls * n_cls).reshape(n_cls, n_cls)
    ious = []
    for i in range(n_cls):
        tp = conf[i, i]; fp = conf[:, i].sum() - tp; fn = conf[i, :].sum() - tp
        d = tp + fp + fn
        ious.append(float(tp / d) if d > 0 else None)
    valid = [v for v in ious if v is not None]
    return (sum(valid) / len(valid) if valid else 0.0), ious


def train() -> dict:
    from app.dl.fetch import WC_NAMES
    if not os.path.exists(PROTO):
        raise SystemExit("Chưa ghi giao thức — chạy `protocol` và commit trước.")
    meta = json.load(open(os.path.join(DL2, "meta.json"), encoding="utf-8"))["meta"]
    d = np.load(FEAT)
    if len(d["done"]) < len(meta):
        raise SystemExit(f"Mới lấy {len(d['done'])}/{len(meta)} ô — chạy `extract` cho đủ rồi mới huấn luyện.")
    X, y, patch = d["X"].astype("float64"), d["y"].astype(int), d["patch"].astype(int)
    split = np.array([_split(meta[i]["site"]) for i in patch])
    n = len(WC_NAMES)
    tr, va, te = split == "train", split == "val", split == "test"
    scores = {}
    for l2 in L2_GRID:                                   # chọn trên KIỂM ĐỊNH
        W, b = fit(X[tr], y[tr], n, l2)
        scores[l2] = miou(y[va], (X[va] @ W + b).argmax(1), n)[0]
    best = max(scores, key=scores.get)
    W, b = fit(X[tr], y[tr], n, best)
    m_te, ious = miou(y[te], (X[te] @ W + b).argmax(1), n)   # chấm KIỂM TRA một lần
    acc = float(((X[te] @ W + b).argmax(1) == y[te]).mean())
    status = "accepted" if m_te >= THRESHOLD else "rejected"
    run = {"date": date.today().isoformat(), "status": status, "model": "AlphaEarth 2021 + hồi quy softmax (CPU)",
           "reason": (f"mIoU trên tỉnh giữ lại {m_te:.3f} {'≥' if status == 'accepted' else '<'} ngưỡng 0,35 đặt trước"),
           "miou_test": round(m_te, 3), "miou_val": round(scores[best], 3), "l2": best,
           "val_by_l2": {str(k): round(v, 3) for k, v in scores.items()}, "pixel_acc_test": round(acc, 3),
           "iou_per_class_test": {WC_NAMES[i]: (None if v is None else round(v, 3)) for i, v in enumerate(ious)},
           "test_provinces": TEST, "val_provinces": VAL,
           "n_pixels": {"train": int(tr.sum()), "val": int(va.sum()), "test": int(te.sum())},
           "protocol": PROTOCOL["id"],
           "protocol_sha256": hashlib.sha256(open(PROTO, "rb").read()).hexdigest(),
           "data": PROTOCOL["data"]["features"] + " · nhãn ESA WorldCover 2021 · " + PROTOCOL["data"]["sampling"],
           "attribution": "The AlphaEarth Foundations Satellite Embedding dataset is produced by Google and Google DeepMind."}
    runs = json.load(open(RUNS, encoding="utf-8")) if os.path.exists(RUNS) else []
    runs.append(run)
    json.dump(runs, open(RUNS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if status == "accepted":
        json.dump({"W": W.round(6).tolist(), "b": b.round(6).tolist(), "classes": WC_NAMES, "year_trained": YEAR,
                   "l2": best, "miou_test": round(m_te, 3), "protocol": PROTOCOL["id"]},
                  open(MODEL, "w", encoding="utf-8"), ensure_ascii=False)
    return run


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "protocol":
        os.makedirs(OUT, exist_ok=True)
        json.dump(PROTOCOL, open(PROTO, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("Đã ghi", PROTO)
    elif cmd == "extract":
        print(extract())
    elif cmd == "train":
        print(json.dumps(train(), ensure_ascii=False, indent=1))
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
