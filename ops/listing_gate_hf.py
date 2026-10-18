"""CỔNG GĐ3 trên tin đăng đất THẬT từ bộ công khai tinixai/vietnam-real-estates — giao thức backend/data/eval/listing_gate_protocol.json.

    python ops/listing_gate_hf.py sample <shard_0000.parquet> <thư_mục_ra>    # in mẫu 40 tin ra thư mục NGOÀI repo để gán nhãn
    python ops/listing_gate_hf.py score  <shard_0000.parquet>                 # chấm MỘT lần, ghi backend/data/eval/listing_gate_result.json

Không chép nguyên văn tin vào repo (giấy phép CC BY-NC 4.0): tệp nhãn chỉ có chỉ số hàng + SHA-256 mô tả + loại câu.
Cần pyarrow (pip install pyarrow). Tải shard: https://huggingface.co/datasets/tinixai/vietnam-real-estates/resolve/
ca3fedcbb089bf65f7e4cfb03316cce4bd0d779f/shard_0000.parquet
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "backend"))
SHARD_SHA256 = "e3fe7e7af9b4b4d01f6a93a3d9ba9dde49f7fc828eaa785a653d35d9d6a42e13"
LABELS = os.path.join(ROOT, "backend", "data", "eval", "listing_gate_labels.json")
RESULT = os.path.join(ROOT, "backend", "data", "eval", "listing_gate_result.json")
SEED, N = 20261019, 40


def _sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def sample(shard: str) -> tuple[list[dict], int]:
    import pyarrow.parquet as pq
    if _sha(shard) != SHARD_SHA256:
        sys.exit("shard không đúng tệp đã đăng ký (SHA-256 khác)")
    t = pq.read_table(shard, columns=["property_type_name", "description"])
    kinds, descs = t.column("property_type_name").to_pylist(), t.column("description").to_pylist()
    pop = [i for i, (k, d) in enumerate(zip(kinds, descs)) if k == "Đất" and d and len(d.strip()) >= 50]
    idx = sorted(random.Random(SEED).sample(pop, N))
    return [{"row": i, "sha256": hashlib.sha256(descs[i].strip().encode("utf-8")).hexdigest(), "text": descs[i].strip()} for i in idx], len(pop)


def main() -> None:
    mode, shard = sys.argv[1], sys.argv[2]
    rows, n_pop = sample(shard)
    if mode == "sample":
        out = sys.argv[3]
        os.makedirs(out, exist_ok=True)
        json.dump({"population": n_pop, "rows": rows}, open(os.path.join(out, "listing_sample.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(f"tổng thể {n_pop} tin đất · mẫu {len(rows)} → {out}")
        return
    from app.services import listing_check as lc, listing_gold
    lab = json.load(open(LABELS, encoding="utf-8"))
    by_row = {r["row"]: r for r in lab["labels"]}
    gold, per = [], []
    for r in rows:
        g = by_row[r["row"]]
        if g["sha256"] != r["sha256"]:
            sys.exit(f"hàng {r['row']}: SHA-256 mô tả khác tệp nhãn")
        gold.append({"text": r["text"], "claims": g["claims"]})
        pred = sorted({c["type"] for c in lc.extract(r["text"])})
        per.append({"row": r["row"], "gold": sorted(g["claims"]), "pred": pred})
    s = listing_gold.score(gold)
    res = {"protocol": "terratwin.listing_gate/1", "population": n_pop, **s, "threshold_macro_f1": 0.80,
           "passed": bool(s["enough"] and s["macro_f1"] is not None and s["macro_f1"] >= 0.80),
           "labeler": lab.get("labeler"), "per_listing": per}
    json.dump(res, open(RESULT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: res[k] for k in ("n", "macro_f1", "passed")}, ensure_ascii=False))
    for r in s["per_type"]:
        print(" ", r)


if __name__ == "__main__":
    main()
