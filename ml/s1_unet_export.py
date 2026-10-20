"""Chuyển U-Net radar (s1_water_unet.pt từ Kaggle) sang ONNX cho máy chủ — KHÔNG huấn luyện lại.

    pip install torch onnx onnxruntime
    python ml/s1_unet_export.py <s1_water_unet.pt>     # ghi backend/data/ml/s1_water_unet.onnx

Kiến trúc lấy đúng từ ml/kaggle/s1_water_seg.py (build_unet, rộng 32). Kiểm lại: đầu ra ONNX khớp PyTorch (sai số lớn
nhất < 1e-3 trên logit) trên ảnh ngẫu nhiên và trên ảnh 128 × 128 (kích thước máy chủ dùng).
"""
from __future__ import annotations

import hashlib
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "ml", "kaggle"))
OUT = os.path.join(ROOT, "backend", "data", "ml", "s1_water_unet.onnx")


def main() -> None:
    import numpy as np
    import onnxruntime as ort
    import torch
    from s1_water_seg import build_unet

    pt = sys.argv[1]
    net = build_unet(32)
    state = torch.load(pt, map_location="cpu", weights_only=True)
    net.load_state_dict(state)
    net.eval()
    dummy = torch.zeros(1, 2, 128, 128)
    torch.onnx.export(net, dummy, OUT, input_names=["s1"], output_names=["logit"], opset_version=17, dynamo=False,
                      dynamic_axes={"s1": {2: "h", 3: "w"}, "logit": {2: "h", 3: "w"}})
    sess = ort.InferenceSession(OUT, providers=["CPUExecutionProvider"])
    rng = np.random.default_rng(0)
    worst = 0.0
    for hw in (128, 256):
        x = rng.normal(0, 1, (1, 2, hw, hw)).astype(np.float32)
        with torch.no_grad():
            a = net(torch.from_numpy(x)).numpy()
        b = sess.run(None, {"s1": x})[0]
        worst = max(worst, float(np.abs(a - b).max()))
    assert worst < 1e-3, f"ONNX lệch PyTorch: {worst}"
    print("ONNX:", OUT, os.path.getsize(OUT), "byte · lệch lớn nhất", round(worst, 6),
          "· sha256", hashlib.sha256(open(OUT, "rb").read()).hexdigest(),
          "· .pt sha256", hashlib.sha256(open(pt, "rb").read()).hexdigest())


if __name__ == "__main__":
    main()
