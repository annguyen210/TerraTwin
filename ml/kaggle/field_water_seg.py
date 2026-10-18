#!/usr/bin/env python3
"""NƯỚC TRONG ẢNH THỰC ĐỊA — SegFormer-b0 trên bộ Flood Area Segmentation (CC0), chạy trên GPU Kaggle.

Giao thức ĐĂNG KÝ TRƯỚC: backend/data/ml/field_water_protocol.json. Tóm tắt: chia 70/15/15 cố định theo hạt giống
20261018; chọn mô hình CHỈ bằng valid; test chấm MỘT lần; đạt khi IoU nước trên test ≥ 0,70 và hơn đường cơ sở màu.

Trên Kaggle (Add Input: dataset faizalkarim/flood-area-segmentation · GPU T4 · Internet On):
    !pip -q install onnx onnxscript
    !python field_water_seg.py --out /kaggle/working/field_water_result.json
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import random
import time

import numpy as np

SEED = 20261018
SIZE = 512
PROTOCOL_ID = "terratwin.field_water/1"
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def find_root(base: str = "/kaggle/input") -> str:
    hits = glob.glob(os.path.join(base, "**", "Image"), recursive=True)
    for h in hits:
        if os.path.isdir(os.path.join(os.path.dirname(h), "Mask")):
            return os.path.dirname(h)
    raise SystemExit("không thấy thư mục Image/ + Mask/ — chưa gắn dataset flood-area-segmentation?")


def pairs(root: str) -> list[tuple[str, str]]:
    out = []
    for img in sorted(glob.glob(os.path.join(root, "Image", "*"))):
        stem = os.path.splitext(os.path.basename(img))[0]
        m = glob.glob(os.path.join(root, "Mask", stem + ".*"))
        if m:
            out.append((img, m[0]))
    return out


def split(items: list) -> dict:
    items = sorted(items)
    random.Random(SEED).shuffle(items)
    n = len(items)
    n_va, n_te = int(n * 0.15), int(n * 0.15)
    return {"train": items[: n - n_va - n_te], "valid": items[n - n_va - n_te: n - n_te], "test": items[n - n_te:]}


def load(img_path: str, mask_path: str) -> tuple[np.ndarray, np.ndarray]:
    from PIL import Image
    im = Image.open(img_path).convert("RGB").resize((SIZE, SIZE), Image.BILINEAR)
    mk = Image.open(mask_path).convert("L").resize((SIZE, SIZE), Image.NEAREST)
    return np.asarray(im, dtype=np.float32) / 255.0, (np.asarray(mk) > 127).astype(np.int64)


class IoU:
    def __init__(self):
        self.i = self.u = 0

    def add(self, pred: np.ndarray, y: np.ndarray):
        self.i += int(np.logical_and(pred == 1, y == 1).sum())
        self.u += int(np.logical_or(pred == 1, y == 1).sum())

    @property
    def value(self):
        return self.i / self.u if self.u else None


def color_baseline(rgb: np.ndarray) -> np.ndarray:
    """Đường cơ sở không học: bão hoà HSV < 0,35 và độ sáng (V) trong [0,25; 0,85] → nước."""
    mx, mn = rgb.max(axis=2), rgb.min(axis=2)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
    return ((sat < 0.35) & (mx >= 0.25) & (mx <= 0.85)).astype(np.int64)


def main() -> None:
    import torch
    import torch.nn.functional as F
    from transformers import SegformerForSemanticSegmentation

    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="field_water_result.json")
    ap.add_argument("--epochs", type=int, default=40)
    a = ap.parse_args()
    t0 = time.time()
    random.seed(SEED); np.random.seed(SEED); torch.manual_seed(SEED)
    root = find_root()
    sp = split(pairs(root))
    data = {k: [load(i, m) for i, m in v] for k, v in sp.items()}
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    net = SegformerForSemanticSegmentation.from_pretrained("nvidia/mit-b0", num_labels=2).to(dev)
    opt = torch.optim.AdamW(net.parameters(), lr=6e-5, weight_decay=0.01)

    def to_x(rgbs):
        x = (np.stack(rgbs) - MEAN) / STD
        return torch.from_numpy(x.transpose(0, 3, 1, 2).copy()).float().to(dev)

    def predict(samples) -> float:
        net.eval()
        iou = IoU()
        with torch.no_grad():
            for k in range(0, len(samples), 8):
                xs = [s[0] for s in samples[k:k + 8]]
                logit = net(pixel_values=to_x(xs)).logits
                logit = F.interpolate(logit, size=(SIZE, SIZE), mode="bilinear", align_corners=False)
                pred = logit.argmax(1).cpu().numpy()
                for p, s in zip(pred, samples[k:k + 8]):
                    iou.add(p, s[1])
        net.train()
        return iou.value

    best, best_state, log = -1.0, None, []
    train = data["train"]
    for ep in range(a.epochs):
        order = list(range(len(train)))
        random.shuffle(order)
        tot = 0.0
        for k in range(0, len(order), 8):
            batch = [train[i] for i in order[k:k + 8]]
            xs, ys = [], []
            for rgb, y in batch:
                if random.random() < 0.5:
                    rgb, y = rgb[:, ::-1], y[:, ::-1]
                xs.append(np.ascontiguousarray(rgb)); ys.append(np.ascontiguousarray(y))
            logit = net(pixel_values=to_x(xs)).logits
            logit = F.interpolate(logit, size=(SIZE, SIZE), mode="bilinear", align_corners=False)
            loss = F.cross_entropy(logit, torch.from_numpy(np.stack(ys)).to(dev))
            opt.zero_grad(); loss.backward(); opt.step()
            tot += float(loss.detach())
        v = predict(data["valid"])                    # CHỈ valid dùng để chọn
        log.append({"epoch": ep + 1, "loss": round(tot, 4), "valid_iou": round(v, 4)})
        print(log[-1], flush=True)
        if v > best:
            best = v
            best_state = {k: t.detach().cpu().clone() for k, t in net.state_dict().items()}

    net.load_state_dict(best_state)
    test_iou = predict(data["test"])                  # chấm MỘT lần
    base = IoU()
    for rgb, y in data["test"]:
        base.add(color_baseline(rgb), y)
    r4 = lambda v: None if v is None else round(v, 4)  # noqa: E731
    passed = test_iou is not None and test_iou >= 0.70 and base.value is not None and test_iou > base.value
    out_dir = os.path.dirname(a.out) or "."
    torch.save(best_state, os.path.join(out_dir, "field_water_segformer.pt"))
    onnx_ok = False
    try:
        class Wrap(torch.nn.Module):
            def __init__(self, m):
                super().__init__()
                self.m = m

            def forward(self, x):
                return self.m(pixel_values=x).logits
        torch.onnx.export(Wrap(net).eval(), torch.zeros(1, 3, SIZE, SIZE, device=dev),
                          os.path.join(out_dir, "field_water_segformer.onnx"), input_names=["image"], output_names=["logits"],
                          opset_version=17)
        onnx_ok = True
    except Exception as e:  # noqa: BLE001 — ONNX chỉ là tiện ích triển khai, không ảnh hưởng kết quả
        print("ONNX lỗi:", e)
    res = {"protocol": PROTOCOL_ID, "script_sha256": hashlib.sha256(open(os.path.abspath(__file__), "rb").read()).hexdigest(),
           "seed": SEED, "size": SIZE, "epochs": a.epochs, "device": dev,
           "n": {k: len(v) for k, v in sp.items()},
           "split_files": {k: [os.path.basename(i) for i, _ in v] for k, v in sp.items()},
           "best_valid_iou": r4(best), "log": log,
           "test": {"model_iou": r4(test_iou), "color_baseline_iou": r4(base.value)},
           "threshold": 0.70, "passed": passed, "onnx_exported": onnx_ok, "seconds": round(time.time() - t0, 1)}
    json.dump(res, open(a.out, "w"), indent=1)
    print(json.dumps({k: res[k] for k in ("n", "best_valid_iou", "test", "passed", "onnx_exported", "seconds")}, indent=1))


if __name__ == "__main__":
    main()
