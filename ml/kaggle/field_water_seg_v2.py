#!/usr/bin/env python3
"""NƯỚC TRONG ẢNH THỰC ĐỊA — bản 2: SegFormer-b0 học thêm ẢNH ĐỒNG RUỘNG KHÔ (mặt nạ rỗng) để không gọi lúa mì vàng,
cỏ khô là nước (bản 1 trượt đối chứng âm 19/10/2026). Giao thức ĐĂNG KÝ TRƯỚC: backend/data/ml/field_water_v2_protocol.json.

Trên Kaggle (Add Input: dataset faizalkarim/flood-area-segmentation · GPU T4 · Internet On):
    !pip -q install onnx onnxscript pyarrow
    !python field_water_seg_v2.py --out /kaggle/working/field_water_v2_result.json
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import io
import json
import os
import random
import statistics
import struct
import time
import urllib.request

import numpy as np

SEED = 20261018
SIZE = 512
PROTOCOL_ID = "terratwin.field_water/2"
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
REV = "9c4afd6174afa3974f209a0ef099dbbe244dfd27"
SUN = "https://huggingface.co/datasets/tanganke/sun397/resolve/" + REV + "/data/{split}-{k:05d}-of-00018.parquet"
DRY = {111: "corn field", 151: "field cultivated", 181: "hayfield", 260: "orchard", 270: "pasture",
       363: "tree farm", 370: "vegetable garden", 376: "vineyard", 389: "wheat field"}
NEG_TRAIN, NEG_VALID = 25, 5            # mỗi lớp, lấy theo thứ tự trong phần TRAIN của SUN397


# ------------------------------------------------------------------ ảnh lũ (giữ NGUYÊN phép chia của bản 1)

def find_root(base: str = "/kaggle/input") -> str:
    for h in glob.glob(os.path.join(base, "**", "Image"), recursive=True):
        if os.path.isdir(os.path.join(os.path.dirname(h), "Mask")):
            return os.path.dirname(h)
    raise SystemExit("không thấy Image/ + Mask/ — chưa gắn dataset flood-area-segmentation?")


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


def rgb512(im) -> np.ndarray:
    from PIL import Image
    return np.asarray(im.convert("RGB").resize((SIZE, SIZE), Image.BILINEAR), dtype=np.float32) / 255.0


def load(img_path: str, mask_path: str):
    from PIL import Image
    mk = Image.open(mask_path).convert("L").resize((SIZE, SIZE), Image.NEAREST)
    return rgb512(Image.open(img_path)), (np.asarray(mk) > 127).astype(np.int64)


def color_baseline(rgb: np.ndarray) -> np.ndarray:
    mx, mn = rgb.max(axis=2), rgb.min(axis=2)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
    return ((sat < 0.35) & (mx >= 0.25) & (mx <= 0.85)).astype(np.int64)


# ------------------------------------------------------------------ ảnh đồng ruộng khô SUN397 (đọc HTTP Range)

def _get(url, start, end):
    req = urllib.request.Request(url, headers={"User-Agent": "terratwin", "Range": f"bytes={start}-{end}"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read(), int((r.headers.get("Content-Range") or "/0").split("/")[-1] or 0)


def _fill(path, url, start, length):
    data, _ = _get(url, start, start + length - 1)
    with open(path, "r+b") as f:
        f.seek(start)
        f.write(data)


def _chunks(rg, prefix):
    out = []
    for i in range(rg.num_columns):
        c = rg.column(i)
        if c.path_in_schema.split(".")[0] == prefix:
            s = c.dictionary_page_offset if c.has_dictionary_page and c.dictionary_page_offset else c.data_page_offset
            out.append((s, c.total_compressed_size))
    return out


def sun_images(split_name: str, per_class: int | None, tmp: str):
    """(lớp, chỉ số, ảnh PIL) của 9 lớp đồng ruộng khô, theo thứ tự trong các tệp; per_class=None → lấy hết."""
    import pyarrow.parquet as pq
    from PIL import Image
    got = {c: 0 for c in DRY}
    for k in range(18):
        url, path = SUN.format(split=split_name, k=k), os.path.join(tmp, f"{split_name}{k}.parquet")
        _, size = _get(url, 0, 0)
        tail, _ = _get(url, size - 8, size - 1)
        meta = struct.unpack("<I", tail[:4])[0]
        with open(path, "wb") as f:
            f.truncate(size)
        _fill(path, url, size - 8 - meta, meta + 8)
        md = pq.ParquetFile(path).metadata
        base = 0
        for g in range(md.num_row_groups):
            rg = md.row_group(g)
            for s, n in _chunks(rg, "label"):
                _fill(path, url, s, n)
            labels = pq.ParquetFile(path).read_row_group(g, columns=["label"]).column("label").to_pylist()
            want = [i for i, lab in enumerate(labels) if lab in DRY and (per_class is None or got[lab] < per_class)]
            if want:
                for s, n in _chunks(rg, "image"):
                    _fill(path, url, s, n)
                col = pq.ParquetFile(path).read_row_group(g, columns=["image"]).column("image")
                for i in want:
                    if per_class is not None and got[labels[i]] >= per_class:
                        continue
                    got[labels[i]] += 1
                    yield DRY[labels[i]], base + i, Image.open(io.BytesIO(col[i].as_py()["bytes"]))
            base += rg.num_rows
        os.remove(path)
        if per_class is not None and all(v >= per_class for v in got.values()):
            return


def main() -> None:
    import torch
    import torch.nn.functional as F
    from transformers import SegformerForSemanticSegmentation

    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="field_water_v2_result.json")
    ap.add_argument("--epochs", type=int, default=40)
    a = ap.parse_args()
    t0 = time.time()
    random.seed(SEED); np.random.seed(SEED); torch.manual_seed(SEED)
    tmp = "/kaggle/temp" if os.path.isdir("/kaggle") else "sun_tmp"
    os.makedirs(tmp, exist_ok=True)

    sp = split(pairs(find_root()))
    data = {k: [load(i, m) for i, m in v] for k, v in sp.items()}
    neg_tr, neg_va, neg_ids = [], [], []
    per_cls: dict = {}
    for cls, idx, im in sun_images("train", NEG_TRAIN + NEG_VALID, tmp):
        per_cls[cls] = per_cls.get(cls, 0) + 1
        (neg_tr if per_cls[cls] <= NEG_TRAIN else neg_va).append(rgb512(im))
        neg_ids.append({"class": cls, "row": idx, "use": "train" if per_cls[cls] <= NEG_TRAIN else "valid"})
    zero = np.zeros((SIZE, SIZE), dtype=np.int64)
    train = data["train"] + [(x, zero) for x in neg_tr]
    print(f"lũ train {len(data['train'])} · khô train {len(neg_tr)} · khô valid {len(neg_va)}", flush=True)

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    net = SegformerForSemanticSegmentation.from_pretrained("nvidia/mit-b0", num_labels=2).to(dev)
    opt = torch.optim.AdamW(net.parameters(), lr=6e-5, weight_decay=0.01)

    def to_x(rgbs):
        x = (np.stack(rgbs) - MEAN) / STD
        return torch.from_numpy(x.transpose(0, 3, 1, 2).copy()).float().to(dev)

    def logits(rgbs):
        return net(pixel_values=to_x(rgbs)).logits                      # (b, 2, 128, 128) — đúng như ONNX production

    def flood_iou(samples):
        net.eval(); i = u = 0
        with torch.no_grad():
            for k in range(0, len(samples), 8):
                lg = F.interpolate(logits([s[0] for s in samples[k:k + 8]]), size=(SIZE, SIZE), mode="bilinear", align_corners=False)
                for p, s in zip(lg.argmax(1).cpu().numpy(), samples[k:k + 8]):
                    i += int(np.logical_and(p == 1, s[1] == 1).sum()); u += int(np.logical_or(p == 1, s[1] == 1).sum())
        net.train()
        return i / u if u else None

    def ratios(rgbs):
        net.eval(); out = []
        with torch.no_grad():
            for k in range(0, len(rgbs), 8):
                out += [float((p == 1).mean()) for p in logits(rgbs[k:k + 8]).argmax(1).cpu().numpy()]
        net.train()
        return out

    best, best_state, log = None, None, []
    for ep in range(a.epochs):
        order = list(range(len(train))); random.shuffle(order); tot = 0.0
        for k in range(0, len(order), 8):
            xs, ys = [], []
            for rgb, y in (train[i] for i in order[k:k + 8]):
                if random.random() < 0.5:
                    rgb, y = rgb[:, ::-1], y[:, ::-1]
                xs.append(np.ascontiguousarray(rgb)); ys.append(np.ascontiguousarray(y))
            lg = F.interpolate(logits(xs), size=(SIZE, SIZE), mode="bilinear", align_corners=False)
            loss = F.cross_entropy(lg, torch.from_numpy(np.stack(ys)).to(dev))
            opt.zero_grad(); loss.backward(); opt.step(); tot += float(loss.detach())
        v_iou, v_dry = flood_iou(data["valid"]), statistics.median(ratios(neg_va))
        log.append({"epoch": ep + 1, "loss": round(tot, 4), "valid_iou": round(v_iou, 4), "valid_dry_median": round(v_dry, 4)})
        print(log[-1], flush=True)
        # CHỌN (đăng ký trước): trong các vòng có trung vị khô (valid) ≤ 0,10, lấy IoU lũ (valid) cao nhất; không vòng nào thì lấy IoU cao nhất
        key = (v_dry <= 0.10, v_iou)
        if best is None or key > best:
            best = key
            best_state = {k: t.detach().cpu().clone() for k, t in net.state_dict().items()}

    net.load_state_dict(best_state)
    test_iou = flood_iou(data["test"])
    bi = bu = 0
    for rgb, y in data["test"]:
        p = color_baseline(rgb); bi += int(np.logical_and(p == 1, y == 1).sum()); bu += int(np.logical_or(p == 1, y == 1).sum())
    base_iou = bi / bu if bu else None
    neg_test, neg_test_ids = [], []
    for cls, idx, im in sun_images("test", None, tmp):                     # ĐỐI CHỨNG ÂM — phần TEST, chấm MỘT lần
        neg_test.append(ratios([rgb512(im)])[0]); neg_test_ids.append({"class": cls, "row": idx})
    per_class = {}
    for c in sorted(set(d["class"] for d in neg_test_ids)):
        v = [r for r, d in zip(neg_test, neg_test_ids) if d["class"] == c]
        per_class[c] = {"n": len(v), "median": round(statistics.median(v), 3), "share_over_0_5": round(sum(x > 0.5 for x in v) / len(v), 3)}
    med = statistics.median(neg_test); over = sum(x > 0.5 for x in neg_test) / len(neg_test)
    flood_ok = test_iou is not None and test_iou >= 0.70 and base_iou is not None and test_iou > base_iou
    dry_ok = len(neg_test) >= 400 and med <= 0.10 and over <= 0.10
    out_dir = os.path.dirname(a.out) or "."
    torch.save(best_state, os.path.join(out_dir, "field_water_v2_segformer.pt"))
    onnx_ok = False
    try:
        class Wrap(torch.nn.Module):
            def __init__(self, m):
                super().__init__(); self.m = m

            def forward(self, x):
                return self.m(pixel_values=x).logits
        torch.onnx.export(Wrap(net).eval(), torch.zeros(1, 3, SIZE, SIZE, device=dev),
                          os.path.join(out_dir, "field_water_segformer.onnx"), input_names=["image"], output_names=["logits"],
                          opset_version=17)
        onnx_ok = True
    except Exception as e:  # noqa: BLE001
        print("ONNX lỗi:", e)
    r4 = lambda v: None if v is None else round(v, 4)  # noqa: E731
    res = {"protocol": PROTOCOL_ID, "script_sha256": hashlib.sha256(open(os.path.abspath(__file__), "rb").read()).hexdigest(),
           "seed": SEED, "size": SIZE, "epochs": a.epochs, "device": dev,
           "n": {"flood_train": len(data["train"]), "dry_train": len(neg_tr), "flood_valid": len(data["valid"]),
                 "dry_valid": len(neg_va), "flood_test": len(data["test"]), "dry_test": len(neg_test)},
           "selected": {"dry_ok_on_valid": bool(best[0]), "valid_iou": r4(best[1])}, "log": log,
           "test": {"model_iou": r4(test_iou), "color_baseline_iou": r4(base_iou)},
           "dry_test": {"median": round(med, 3), "share_over_0_5": round(over, 3), "per_class": per_class},
           "neg_train_valid_ids": neg_ids, "neg_test_ids": neg_test_ids,
           "passed_flood": flood_ok, "passed_dry": dry_ok, "passed": bool(flood_ok and dry_ok),
           "onnx_exported": onnx_ok, "seconds": round(time.time() - t0, 1)}
    json.dump(res, open(a.out, "w"), indent=1)
    print(json.dumps({k: res[k] for k in ("n", "selected", "test", "dry_test", "passed_flood", "passed_dry", "passed", "seconds")}, indent=1))


if __name__ == "__main__":
    main()
