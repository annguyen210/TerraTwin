"""Tinh chỉnh U-Net radar trên ruộng Việt Nam — đúng công thức trong backend/data/ml/s1_unet_vn_protocol.json.

    python ml/s1_unet_v2_train.py            # CPU; dữ liệu từ ops/s1_unet_v2_data.py (D:/tt-scratch/unet_v2)

Khởi tạo từ s1_water_unet.pt (bản 1, Sen1Floods11). Chọn vòng theo IoU gộp trên VAL (có mặt nạ địa hình) — TEST không
được đọc ở đây. Ghi: <dữ liệu>/model_v2.pt, <dữ liệu>/s1_water_unet_vn.onnx (kiểm khớp PyTorch) và nhật ký học
backend/data/ml/s1_unet_vn_train.json.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import random
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.environ.get("TT_TORCHLIB", "D:/tt-scratch/torchlib"))
sys.path.insert(0, os.path.join(ROOT, "ml", "kaggle"))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import numpy as np  # noqa: E402
import torch  # noqa: E402

from app.services import s1_unet as U  # noqa: E402
from s1_water_seg import build_unet  # noqa: E402

DATA = os.environ.get("TT_UNET_V2", "D:/tt-scratch/unet_v2")
INIT = os.environ.get("TT_UNET_V1_PT", "D:/tt-scratch/s1_water_unet.pt")
LOG = os.path.join(ROOT, "backend", "data", "ml", "s1_unet_vn_train.json")
SEED, EPOCHS, BATCH, CROP, LR = 20261021, 10, 16, 64, 1e-4


def sha(path: str) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def load(split: str) -> list[dict]:
    out = []
    for f in sorted(glob.glob(os.path.join(DATA, f"{split}_*_*_*.npz"))):
        z = np.load(f)
        out.append({"x": U.prepare(z["s1"])[0], "y": z["label"], "slope": z["slope"].astype(np.float32)})
    return out


def pooled_iou(net, rows) -> float:
    inter = union = 0
    net.eval()
    with torch.no_grad():
        for r in rows:
            logit = net(torch.from_numpy(r["x"][None]))[0, 0].numpy()
            pred, ok = U.predict_mask(logit, r["slope"]), r["y"] != 255
            lab = r["y"] == 1
            inter += int((pred & lab & ok).sum())
            union += int(((pred | lab) & ok).sum())
    return inter / union if union else 0.0


def batches(rows, rng):
    items = []
    for r in rows:
        for _ in range(2):
            i, j = rng.randrange(0, 128 - CROP + 1), rng.randrange(0, 128 - CROP + 1)
            x, y = r["x"][:, i:i + CROP, j:j + CROP], r["y"][i:i + CROP, j:j + CROP]
            k = rng.randrange(4)
            x, y = np.rot90(x, k, axes=(1, 2)), np.rot90(y, k)
            if rng.random() < 0.5:
                x, y = x[:, :, ::-1], y[:, ::-1]
            items.append((np.ascontiguousarray(x), np.ascontiguousarray(y)))
    rng.shuffle(items)
    for b in range(0, len(items), BATCH):
        chunk = items[b:b + BATCH]
        yield (torch.from_numpy(np.stack([c[0] for c in chunk])), torch.from_numpy(np.stack([c[1] for c in chunk])))


def main() -> None:
    torch.manual_seed(SEED)
    rng = random.Random(SEED)
    train, val = load("train"), load("val")
    lab = np.concatenate([r["y"].ravel() for r in train])
    p = float((lab == 1).sum() / max(1, (lab != 255).sum()))
    pos_weight = float(min(5.0, (1 - p) / p)) if p > 0 else 5.0
    net = build_unet(32)
    net.load_state_dict(torch.load(INIT, map_location="cpu", weights_only=True))
    opt = torch.optim.AdamW(net.parameters(), lr=LR, weight_decay=1e-4)
    pw = torch.tensor(pos_weight)
    log = {"protocol": "terratwin.s1_unet_vn/2", "init_sha256": sha(INIT), "script_sha256": sha(os.path.abspath(__file__)),
           "n": {"train": len(train), "val": len(val)}, "train_water_frac": round(p, 4), "pos_weight": round(pos_weight, 3),
           "val_iou_init": round(pooled_iou(net, val), 4), "epochs": []}
    print("bắt đầu", log["n"], "IoU VAL ban đầu", log["val_iou_init"], flush=True)
    best, best_state = -1.0, None
    for ep in range(1, EPOCHS + 1):
        net.train()
        t0, tot, nb = time.time(), 0.0, 0
        for x, y in batches(train, rng):
            logit = net(x)[:, 0]
            valid = (y != 255).float()
            loss = torch.nn.functional.binary_cross_entropy_with_logits(logit, (y == 1).float(), pos_weight=pw, reduction="none")
            loss = (loss * valid).sum() / valid.sum().clamp(min=1)
            opt.zero_grad()
            loss.backward()
            opt.step()
            tot, nb = tot + float(loss), nb + 1
        v = pooled_iou(net, val)
        log["epochs"].append({"epoch": ep, "train_loss": round(tot / max(1, nb), 4), "val_iou": round(v, 4),
                              "seconds": round(time.time() - t0, 1)})
        print(log["epochs"][-1], flush=True)
        if v > best:
            best, best_state = v, {k: t.clone() for k, t in net.state_dict().items()}
    net.load_state_dict(best_state)
    log["selected_epoch"] = max(log["epochs"], key=lambda e: e["val_iou"])["epoch"]
    log["val_iou_selected"] = round(best, 4)
    pt = os.path.join(DATA, "model_v2.pt")
    torch.save(best_state, pt)
    onnx = os.path.join(DATA, "s1_water_unet_vn.onnx")
    net.eval()
    torch.onnx.export(net, torch.zeros(1, 2, 128, 128), onnx, input_names=["s1"], output_names=["logit"], opset_version=17,
                      dynamo=False, dynamic_axes={"s1": {2: "h", 3: "w"}, "logit": {2: "h", 3: "w"}})
    import onnxruntime as ort
    s = ort.InferenceSession(onnx, providers=["CPUExecutionProvider"])
    x = np.random.default_rng(0).normal(0, 1, (1, 2, 128, 128)).astype(np.float32)
    with torch.no_grad():
        diff = float(np.abs(net(torch.from_numpy(x)).numpy() - s.run(None, {"s1": x})[0]).max())
    log.update({"pt_sha256": sha(pt), "onnx_sha256": sha(onnx), "onnx_parity_max_abs": diff})
    json.dump(log, open(LOG, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
    print("xong — vòng", log["selected_epoch"], "IoU VAL", log["val_iou_selected"], "ONNX lệch", diff, flush=True)


if __name__ == "__main__":
    main()
