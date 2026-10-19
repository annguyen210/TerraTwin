"""Đối chứng ÂM bổ sung 1b — 8 lớp đồng ruộng khô còn lại của SUN397 (giao thức field_water_negctrl_protocol.json,
mục supplement_1b). Không tải nguyên 18 tệp (~7 GB): dựng tệp THƯA cùng kích thước, chỉ tải bằng HTTP Range phần chân
tệp (metadata), cột nhãn, và các cột ảnh của đúng nhóm hàng có lớp cần.

    python ml/field_water_negctrl_1b.py <thư_mục_tạm>
"""
from __future__ import annotations

import io
import json
import os
import statistics
import struct
import sys
import urllib.request

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "backend"))
REV = "9c4afd6174afa3974f209a0ef099dbbe244dfd27"
URL = "https://huggingface.co/datasets/tanganke/sun397/resolve/" + REV + "/data/test-{:05d}-of-00018.parquet"
CLASSES = {151: "field cultivated", 181: "hayfield", 260: "orchard", 270: "pasture",
           363: "tree farm", 370: "vegetable garden", 376: "vineyard", 389: "wheat field"}
OUT = os.path.join(ROOT, "backend", "data", "ml", "field_water_negctrl_1b_result.json")


def _get(url: str, start: int | None = None, end: int | None = None) -> tuple[bytes, int]:
    h = {"User-Agent": "terratwin-negctrl"}
    if start is not None:
        h["Range"] = f"bytes={start}-{end}" if end is not None else f"bytes={start}-"
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=300) as r:
        total = int((r.headers.get("Content-Range") or "/0").split("/")[-1] or 0)
        return r.read(), total


def _fill(path: str, url: str, start: int, length: int) -> None:
    data, _ = _get(url, start, start + length - 1)
    with open(path, "r+b") as f:
        f.seek(start)
        f.write(data)


def _sparse(path: str, url: str) -> None:
    _, size = _get(url, 0, 0)                     # kích thước tệp đọc từ Content-Range
    tail8, _ = _get(url, size - 8, size - 1)
    meta_len = struct.unpack("<I", tail8[:4])[0]
    with open(path, "wb") as f:
        f.truncate(size)
    _fill(path, url, size - 8 - meta_len, meta_len + 8)


def _chunks(rg, prefix: str) -> list[tuple[int, int]]:
    out = []
    for i in range(rg.num_columns):
        c = rg.column(i)
        if c.path_in_schema.split(".")[0] == prefix:
            start = c.dictionary_page_offset if c.has_dictionary_page and c.dictionary_page_offset else c.data_page_offset
            out.append((start, c.total_compressed_size))
    return out


def main() -> None:
    import pyarrow.parquet as pq
    from PIL import Image
    from app.services import field_water
    assert field_water.available(), "thiếu tệp mô hình .onnx/.onnx.data hoặc onnxruntime"
    tmp = sys.argv[1]
    os.makedirs(tmp, exist_ok=True)
    rows = []
    for k in range(18):
        url, path = URL.format(k), os.path.join(tmp, f"sun397_test{k:02d}.sparse.parquet")
        _sparse(path, url)
        md = pq.ParquetFile(path).metadata
        base = 0
        for g in range(md.num_row_groups):
            rg = md.row_group(g)
            for s, n in _chunks(rg, "label"):
                _fill(path, url, s, n)
            labels = pq.ParquetFile(path).read_row_group(g, columns=["label"]).column("label").to_pylist()
            want = [i for i, lab in enumerate(labels) if lab in CLASSES]
            if want:
                for s, n in _chunks(rg, "image"):
                    _fill(path, url, s, n)
                col = pq.ParquetFile(path).read_row_group(g, columns=["image"]).column("image")
                for i in want:
                    r = field_water.water_ratio(Image.open(io.BytesIO(col[i].as_py()["bytes"])))
                    rows.append({"file": f"test-{k:05d}", "row": base + i, "class": CLASSES[labels[i]], "water_ratio": r})
                    print(rows[-1], flush=True)
                del col
            base += rg.num_rows
        os.remove(path)
    vals = [r["water_ratio"] for r in rows if r["water_ratio"] is not None]
    per = {}
    for c in sorted(set(r["class"] for r in rows)):
        v = [r["water_ratio"] for r in rows if r["class"] == c and r["water_ratio"] is not None]
        per[c] = {"n": len(v), "median": round(statistics.median(v), 3), "share_over_0_5": round(sum(x > 0.5 for x in v) / len(v), 3)}
    med = statistics.median(vals) if vals else None
    over = sum(v > 0.5 for v in vals) / len(vals) if vals else None
    res = {"protocol": "terratwin.field_water_negctrl/1b", "n": len(vals), "median": None if med is None else round(med, 3),
           "share_over_0_5": None if over is None else round(over, 3), "per_class": per,
           "passed": bool(len(vals) >= 20 and med <= 0.10 and over <= 0.10), "images": rows}
    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: res[k] for k in ("n", "median", "share_over_0_5", "passed", "per_class")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
