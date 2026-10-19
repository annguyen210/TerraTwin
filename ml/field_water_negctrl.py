"""Đối chứng ÂM cho SegFormer nhận nước ảnh thực địa — giao thức backend/data/ml/field_water_negctrl_protocol.json.

    pip install pyarrow onnxruntime pillow numpy
    python ml/field_water_negctrl.py <test-00000-of-00018.parquet> [test-00001-of-00018.parquet]

Chạy ĐÚNG hàm production (backend/app/services/field_water.water_ratio) trên mọi ảnh đồng ruộng khô của SUN397 trong
tệp; ghi backend/data/ml/field_water_negctrl_result.json (không chép ảnh, chỉ chỉ số hàng + lớp + tỉ lệ).
"""
from __future__ import annotations

import io
import json
import os
import statistics
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "backend"))
CLASSES = {111: "corn field", 151: "field cultivated", 181: "hayfield", 260: "orchard", 270: "pasture",
           363: "tree farm", 370: "vegetable garden", 376: "vineyard", 389: "wheat field"}
OUT = os.path.join(ROOT, "backend", "data", "ml", "field_water_negctrl_result.json")


def main() -> None:
    import pyarrow.parquet as pq
    from PIL import Image
    from app.services import field_water
    assert field_water.available(), "thiếu tệp mô hình .onnx/.onnx.data hoặc onnxruntime"
    rows = []
    for path in sys.argv[1:]:
        f = pq.ParquetFile(path)
        labels = f.read(columns=["label"]).column("label").to_pylist()
        want = [i for i, lab in enumerate(labels) if lab in CLASSES]
        if not want:
            continue
        tab = f.read(columns=["image"])
        col = tab.column("image")
        for i in want:
            img = Image.open(io.BytesIO(col[i].as_py()["bytes"]))
            r = field_water.water_ratio(img)
            rows.append({"file": os.path.basename(path), "row": i, "class": CLASSES[labels[i]], "water_ratio": r})
            print(rows[-1], flush=True)
        if len(rows) >= 20:
            break
    vals = [r["water_ratio"] for r in rows if r["water_ratio"] is not None]
    med = statistics.median(vals) if vals else None
    over = sum(v > 0.5 for v in vals) / len(vals) if vals else None
    res = {"protocol": "terratwin.field_water_negctrl/1", "n": len(vals), "median": None if med is None else round(med, 3),
           "share_over_0_5": None if over is None else round(over, 3),
           "passed": bool(len(vals) >= 20 and med <= 0.10 and over <= 0.10), "images": rows}
    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: res[k] for k in ("n", "median", "share_over_0_5", "passed")}))


if __name__ == "__main__":
    main()
