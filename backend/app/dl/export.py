"""Xuất mô hình đã huấn luyện sang ONNX để máy chủ dùng mà không cần torch.

    python -m app.dl.export

VÌ SAO ONNX CHỨ KHÔNG PHẢI .pt: máy chủ sản phẩm chạy trên gói free, và cài
PyTorch vào đó tốn ~2 GB cho một việc suy luận. onnxruntime nhẹ hơn hàng chục
lần và không cần CUDA. Huấn luyện cần torch; chạy thì không.
"""
from __future__ import annotations

import argparse
import json
import os
import sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", default="data/dl/unet_landcover.pt")
    ap.add_argument("--out", default="data/landcover.onnx")
    ap.add_argument("--size", type=int, default=256)
    a = ap.parse_args()

    try:
        import torch
    except ImportError:
        print("Cần torch để xuất. pip install torch")
        return 1
    if not os.path.exists(a.ckpt):
        print(f"Chưa có {a.ckpt}. Chạy: python -m app.dl.train")
        return 1

    from app.dl.fetch import WC_CODES, WC_NAMES
    from app.dl.train import build_unet

    ck = torch.load(a.ckpt, map_location="cpu")
    net = build_unet(ck["in_ch"], ck["n_classes"], ck["base"])
    net.load_state_dict(ck["state"])
    net.eval()

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    dummy = torch.zeros(1, ck["in_ch"], a.size, a.size)
    torch.onnx.export(
        net, dummy, a.out, input_names=["image"], output_names=["logits"],
        dynamic_axes={"image": {0: "n"}, "logits": {0: "n"}}, opset_version=17)

    # Thẻ mô hình đi KÈM tệp .onnx. Một mô hình không có điểm số đi cùng thì
    # không ai kiểm được nó tốt tới đâu — và đó là lúc người ta bắt đầu tin bừa.
    card = {
        "task": "Phân đoạn lớp phủ từ Sentinel-2",
        "classes": WC_NAMES, "codes": WC_CODES,
        "in_channels": ck["in_ch"], "patch": a.size,
        "bands": ["B02", "B03", "B04", "B08"],
        "scale": "phản xạ chia 10000, cắt trần 1.0",
        "miou_holdout": ck["miou"], "iou_per_class": ck["iou"],
        "holdout_provinces": ck.get("holdout"),
        "epoch": ck["epoch"],
        "labels": "ESA WorldCover 10 m (2021)",
        "note": ("Điểm số đo trên các tỉnh GIỮ LẠI HOÀN TOÀN khỏi tập huấn "
                 "luyện, không phải trên ô ngẫu nhiên — hai ô cách nhau 2 km "
                 "gần như giống hệt nhau nên chia ngẫu nhiên cho điểm giả tạo."),
    }
    with open(a.out.replace(".onnx", ".json"), "w", encoding="utf-8") as f:
        json.dump(card, f, ensure_ascii=False, indent=1)

    mb = os.path.getsize(a.out) / 1e6
    print(f"Đã xuất {a.out}  ({mb:.1f} MB)")
    print(f"Thẻ mô hình: {a.out.replace('.onnx', '.json')}")
    print(f"mIoU trên tỉnh chưa từng thấy: {ck['miou']:.3f}")
    print("\nChép hai tệp đó vào backend/data/ trên máy chủ, rồi:")
    print("    pip install onnxruntime")
    return 0


if __name__ == "__main__":
    sys.exit(main())
