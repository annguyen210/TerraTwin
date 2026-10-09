#!/usr/bin/env python3
"""GĐ5 · MÔ HÌNH NƯỚC TRÊN RADAR — U-Net trên Sen1Floods11 (nhãn tay), chạy trên GPU Kaggle.

Giao thức ĐĂNG KÝ TRƯỚC: backend/data/ml/gd5_protocol.json (mục "s1_water"). Tóm tắt:
  · Dữ liệu: Sen1Floods11 v1.1, phần nhãn tay (446 ô 512×512, Sentinel-1 VV/VH dB). Chia tập CHÍNH THỨC của
    bộ dữ liệu: train 252 · valid 89 · test 90 · Bolivia 15 (sự kiện giữ lại hoàn toàn).
  · Chọn mô hình CHỈ bằng tập valid. Test, Bolivia, Mekong (6 ô test của sự kiện Mekong — gần Việt Nam nhất)
    chấm ĐÚNG MỘT LẦN ở cuối.
  · So với phương pháp ngưỡng đang chạy: điểm ảnh VV < −18 dB (cùng ngưỡng tuyệt đối của GĐ2), và Otsu theo ô.
  · ĐẠT khi IoU lớp nước của mô hình > IoU của ngưỡng −18 dB trên CẢ BA: test, Bolivia, Mekong. Không đạt thì
    ghi kết quả trượt, công khai, GĐ2 giữ phương pháp ngưỡng.
  · Đạt mới chỉ là bước 1: muốn thay hàm flag() của GĐ2 còn phải qua lại cổng GĐ2 (lũ Huế 10/2020, miền Trung
    10/2025, đất cao 0 đợt) — ops/water_gate.py.

Chạy trên Kaggle (Notebook → Accelerator: GPU T4 → Internet: On):
    !pip -q install rasterio
    !python s1_water_seg.py --out /kaggle/working/s1_water_result.json
Thử nhanh trên CPU (không cần torch, chỉ chấm phương pháp ngưỡng trên vài ô):
    python s1_water_seg.py --baseline-only --limit 3
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import time
import urllib.request

import numpy as np

BASE = "https://storage.googleapis.com/sen1floods11/v1.1"
SPLITS = {"train": "flood_train_data", "valid": "flood_valid_data", "test": "flood_test_data", "bolivia": "flood_bolivia_data"}
WATER_DB = -18.0
SEED = 20261009
PROTOCOL_ID = "terratwin.gd5.s1_water/1"


# ------------------------------------------------------------------ dữ liệu

def _get(url: str, path: str) -> str:
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        for k in range(5):
            try:
                with urllib.request.urlopen(url, timeout=120) as r:
                    data = r.read()
                with open(path + ".part", "wb") as f:
                    f.write(data)
                os.replace(path + ".part", path)
                break
            except Exception:  # noqa: BLE001 — thử lại, mạng Kaggle đôi khi chập chờn
                time.sleep(2 * (k + 1))
        else:
            raise RuntimeError(f"không tải được {url}")
    return path


def split_list(name: str, root: str) -> list[str]:
    p = _get(f"{BASE}/splits/flood_handlabeled/{SPLITS[name]}.csv", os.path.join(root, "splits", f"{name}.csv"))
    return [ln.split(",")[0].replace("_S1Hand.tif", "") for ln in open(p).read().splitlines() if ln.strip()]


def load_chip(chip: str, root: str) -> tuple[np.ndarray, np.ndarray]:
    """(x: 2×H×W float32 dB VV/VH, NaN = không có dữ liệu; y: H×W int8 — 1 nước, 0 không, −1 bỏ qua)."""
    import rasterio
    s1 = _get(f"{BASE}/data/flood_events/HandLabeled/S1Hand/{chip}_S1Hand.tif", os.path.join(root, "S1Hand", f"{chip}.tif"))
    lb = _get(f"{BASE}/data/flood_events/HandLabeled/LabelHand/{chip}_LabelHand.tif", os.path.join(root, "LabelHand", f"{chip}.tif"))
    with rasterio.open(s1) as r:
        x = r.read().astype(np.float32)
    with rasterio.open(lb) as r:
        y = r.read(1).astype(np.int8)
    bad = ~np.isfinite(x).all(axis=0)
    y = np.where(bad, -1, y).astype(np.int8)
    return x, y


# ------------------------------------------------------------------ chấm điểm

class IoU:
    """IoU lớp nước gộp theo điểm ảnh trên cả tập (không trung bình theo ô — ô ít nước không bị phóng đại)."""

    def __init__(self) -> None:
        self.tp = self.fp = self.fn = 0

    def add(self, pred: np.ndarray, y: np.ndarray) -> None:
        m = y >= 0
        p, t = pred[m].astype(bool), (y[m] == 1)
        self.tp += int((p & t).sum())
        self.fp += int((p & ~t).sum())
        self.fn += int((~p & t).sum())

    @property
    def value(self) -> float | None:
        d = self.tp + self.fp + self.fn
        return self.tp / d if d else None


def thresh_pred(x: np.ndarray) -> np.ndarray:
    vv = np.nan_to_num(x[0], nan=0.0)
    return vv < WATER_DB


def otsu_pred(x: np.ndarray) -> np.ndarray:
    vv = x[0][np.isfinite(x[0])]
    if vv.size < 100:
        return np.zeros(x.shape[1:], bool)
    hist, edges = np.histogram(np.clip(vv, -40, 5), bins=256)
    w = hist.cumsum()
    mu = (hist * (edges[:-1] + edges[1:]) / 2).cumsum()
    tot_w, tot_mu = w[-1], mu[-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        between = (tot_mu * w / tot_w - mu) ** 2 / (w * (tot_w - w))
    t = edges[int(np.nanargmax(between)) + 1]
    return np.nan_to_num(x[0], nan=0.0) < t


def baselines(chips: list[str], root: str) -> dict:
    a, b = IoU(), IoU()
    for c in chips:
        x, y = load_chip(c, root)
        a.add(thresh_pred(x), y)
        b.add(otsu_pred(x), y)
    r4 = lambda v: None if v is None else round(v, 4)  # noqa: E731
    return {"threshold_-18dB": r4(a.value), "otsu_per_chip": r4(b.value), "n_chips": len(chips)}


# ------------------------------------------------------------------ mô hình (PyTorch, chỉ trên GPU Kaggle)

def build_unet(base: int = 32):
    import torch
    import torch.nn as nn

    def block(i, o):
        return nn.Sequential(nn.Conv2d(i, o, 3, padding=1), nn.BatchNorm2d(o), nn.ReLU(inplace=True),
                             nn.Conv2d(o, o, 3, padding=1), nn.BatchNorm2d(o), nn.ReLU(inplace=True))

    class UNet(nn.Module):
        def __init__(self):
            super().__init__()
            c = [base, base * 2, base * 4, base * 8, base * 16]
            self.d = nn.ModuleList([block(2, c[0]), block(c[0], c[1]), block(c[1], c[2]), block(c[2], c[3])])
            self.mid = block(c[3], c[4])
            self.up = nn.ModuleList([nn.ConvTranspose2d(c[i + 1], c[i], 2, stride=2) for i in reversed(range(4))])
            self.u = nn.ModuleList([block(c[i] * 2, c[i]) for i in reversed(range(4))])
            self.head = nn.Conv2d(c[0], 1, 1)
            self.pool = nn.MaxPool2d(2)

        def forward(self, x):
            skips = []
            for d in self.d:
                x = d(x)
                skips.append(x)
                x = self.pool(x)
            x = self.mid(x)
            for up, u, s in zip(self.up, self.u, reversed(skips)):
                x = u(torch.cat([up(x), s], 1))
            return self.head(x)

    return UNet()


def norm_stats(chips: list[str], root: str) -> tuple[list[float], list[float]]:
    vals = [[], []]
    for c in chips:
        x, _ = load_chip(c, root)
        for b in range(2):
            v = x[b][np.isfinite(x[b])]
            vals[b].append(np.clip(v, -50, 5)[:: 37])
    m = [float(np.concatenate(v).mean()) for v in vals]
    s = [float(np.concatenate(v).std()) for v in vals]
    return m, s


def to_tensor(x: np.ndarray, m, s) -> np.ndarray:
    out = np.empty_like(x)
    for b in range(2):
        out[b] = (np.clip(np.nan_to_num(x[b], nan=m[b]), -50, 5) - m[b]) / s[b]
    return out


def train_and_eval(root: str, epochs: int, out: str, limit: int | None, width: int = 32) -> dict:
    import torch
    import torch.nn.functional as F
    random.seed(SEED); np.random.seed(SEED); torch.manual_seed(SEED)
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    sp = {k: split_list(k, root)[:limit] if limit else split_list(k, root) for k in SPLITS}
    m, s = norm_stats(sp["train"], root)
    cache = {}

    def get(c):
        if c not in cache:
            x, y = load_chip(c, root)
            cache[c] = (to_tensor(x, m, s), y)
        return cache[c]

    net = build_unet(width).to(dev)
    opt = torch.optim.AdamW(net.parameters(), lr=1e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
    pos_w = torch.tensor([2.0], device=dev)

    def predict(chips):
        net.eval()
        iou = IoU()
        with torch.no_grad():
            for c in chips:
                x, y = get(c)
                p = net(torch.from_numpy(x)[None].to(dev))[0, 0].sigmoid().cpu().numpy() > 0.5
                iou.add(p, y)
        return iou.value or 0.0

    best, best_state, log = -1.0, None, []
    for ep in range(epochs):
        net.train()
        order = sp["train"][:]
        random.shuffle(order)
        tot = 0.0
        for i in range(0, len(order), 8):
            xs, ys = [], []
            for c in order[i:i + 8]:
                x, y = get(c)
                k = random.randint(0, 3)
                x, y = np.rot90(x, k, (1, 2)), np.rot90(y, k)
                if random.random() < 0.5:
                    x, y = x[:, :, ::-1], y[:, ::-1]
                xs.append(np.ascontiguousarray(x)); ys.append(np.ascontiguousarray(y))
            xb = torch.from_numpy(np.stack(xs)).to(dev)
            yb = torch.from_numpy(np.stack(ys)).to(dev)[:, None].float()
            valid = (yb >= 0).float()
            logit = net(xb)
            bce = (F.binary_cross_entropy_with_logits(logit, yb.clamp(min=0), pos_weight=pos_w, reduction="none") * valid).sum() / valid.sum()
            p = logit.sigmoid() * valid
            dice = 1 - (2 * (p * yb.clamp(min=0)).sum() + 1) / (p.sum() + (yb.clamp(min=0) * valid).sum() + 1)
            loss = bce + dice
            opt.zero_grad(); loss.backward(); opt.step()
            tot += float(loss)
        sched.step()
        v = predict(sp["valid"])                       # CHỈ tập valid được dùng để chọn
        log.append({"epoch": ep + 1, "loss": round(tot, 4), "valid_iou": round(v, 4)})
        print(log[-1], flush=True)
        if v > best:
            best = v
            best_state = {k: t.detach().cpu().clone() for k, t in net.state_dict().items()}

    net.load_state_dict(best_state)
    mekong = [c for c in sp["test"] if c.startswith("Mekong")]
    res = {}
    for name, chips in (("test", sp["test"]), ("bolivia", sp["bolivia"]), ("mekong", mekong)):
        res[name] = {"model": round(predict(chips), 4) if chips else None, **baselines(chips, root)}
    passed = all(res[k]["model"] is not None and res[k]["threshold_-18dB"] is not None
                 and res[k]["model"] > res[k]["threshold_-18dB"] for k in res) and not limit
    torch.save(best_state, os.path.join(os.path.dirname(out) or ".", "s1_water_unet.pt"))
    try:
        dummy = torch.zeros(1, 2, 512, 512, device=dev)
        torch.onnx.export(net, dummy, os.path.join(os.path.dirname(out) or ".", "s1_water_unet.onnx"),
                          input_names=["s1"], output_names=["logit"], opset_version=17,
                          dynamic_axes={"s1": {2: "h", 3: "w"}, "logit": {2: "h", 3: "w"}})
    except Exception as e:  # noqa: BLE001 — ONNX là tiện ích cho bước cắm vào máy chủ, không ảnh hưởng kết quả
        print("ONNX lỗi:", e)
    return {"best_valid_iou": round(best, 4), "epochs": epochs, "log": log, "norm": {"mean": m, "std": s},
            "results": res, "passed": passed, "device": dev}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.environ.get("S1F_DIR", "./sen1floods11"))
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--out", default="s1_water_result.json")
    ap.add_argument("--baseline-only", action="store_true", help="chỉ chấm phương pháp ngưỡng (không cần torch)")
    ap.add_argument("--limit", type=int, help="thử nhanh: chỉ lấy N ô mỗi tập")
    ap.add_argument("--width", type=int, default=32, help="số kênh tầng đầu U-Net (giao thức: 32)")
    a = ap.parse_args()
    t0 = time.time()
    proto = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "backend", "data", "ml", "gd5_protocol.json"),
                 "rb").read() if os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "backend", "data", "ml", "gd5_protocol.json")) else b""
    head = {"protocol": PROTOCOL_ID, "protocol_sha256": hashlib.sha256(proto).hexdigest() if proto else None,
            # Gắn kết quả với ĐÚNG phiên bản script đã commit (trên Kaggle chỉ có tệp này, không có giao thức).
            "script_sha256": hashlib.sha256(open(os.path.abspath(__file__), "rb").read()).hexdigest(),
            "seed": SEED, "limit": a.limit, "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    if a.baseline_only:
        out = {**head, "baselines": {k: baselines(split_list(k, a.data)[:a.limit] if a.limit else split_list(k, a.data), a.data)
                                     for k in ("test", "bolivia")}}
    else:
        out = {**head, "width": a.width, **train_and_eval(a.data, a.epochs, a.out, a.limit, a.width)}
    out["seconds"] = round(time.time() - t0, 1)
    json.dump(out, open(a.out, "w"), indent=1)
    print(json.dumps(out, indent=1)[:2000])
    if a.limit:
        print("CHÚ Ý: --limit chỉ để thử máy — KHÔNG phải kết quả kiểm định.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
