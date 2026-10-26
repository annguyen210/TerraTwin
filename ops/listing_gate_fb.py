"""CỔNG GĐ3 lần 4 và 5 — 20 tin bán đất thật từ trang Facebook công khai của môi giới (listing_gate_v4/v5_protocol.json).

    python ops/listing_gate_fb.py <tin.json>            # lần 4: chấm MỘT lần, ghi backend/data/eval/listing_gate_v4_result.json
    python ops/listing_gate_fb.py <tin.json> --run 5    # lần 5 (luật sửa, tập kiểm tra mới): listing_gate_v5_result.json

<tin.json> là bản văn bản đã ẩn danh, giữ NGOÀI repo ([{"id", "source", "text"}]). Mỗi tin phải khớp SHA-256 trong
listing_gate_v4_labels.json (nhãn commit trước khi chấm) — lệch một ký tự là dừng. Kết quả không chứa nguyên văn tin.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "backend"))
EVAL = os.path.join(ROOT, "backend", "data", "eval")
RUNS = {   # lần → (tệp nhãn, tệp kết quả, mô tả dữ liệu VI, EN)
    "4": ("listing_gate_v4_labels.json", "listing_gate_v4_result.json",
          "20 bài bán đất trên 4 trang Facebook công khai của môi giới (Huế, Quảng Trị, Hải Phòng, Tiền Giang cũ), 5 bài/trang theo thứ tự trên trang",
          "20 land-sale posts from 4 public Facebook pages of brokers (Huế, Quảng Trị, Hải Phòng, former Tiền Giang), first 5 per page in page order"),
    "5": ("listing_gate_v5_labels.json", "listing_gate_v5_result.json",
          "20 bài bán đất MỚI trên 4 trang Facebook công khai khác (Nam Định, Quảng Bình cũ, Bình Định, Cần Thơ), thu SAU khi khoá luật sửa lần 5; "
          "20 tin lần 4 là tập phát triển",
          "20 NEW land-sale posts from 4 other public Facebook broker pages (Nam Định, former Quảng Bình, Bình Định, Cần Thơ), collected AFTER "
          "the run-5 rule fix was frozen; the run-4 posts are the development set"),
}
THRESHOLD = 0.80


def main() -> None:
    from app.services import listing_check as lc, listing_gold

    run = sys.argv[sys.argv.index("--run") + 1] if "--run" in sys.argv else "4"
    LABELS, RESULT, note_vi, note_en = RUNS[run]
    out = os.path.join(EVAL, RESULT)
    if os.path.exists(out):
        sys.exit(f"{RESULT} đã có — giao thức chấm MỘT lần, không chấm lại")
    lab = json.load(open(os.path.join(EVAL, LABELS), encoding="utf-8"))
    tin = {t["id"]: t["text"].strip() for t in json.load(open(sys.argv[1], encoding="utf-8"))}
    gold, per = [], []
    for row in lab["labels"]:
        text = tin.get(row["id"])
        if text is None or hashlib.sha256(text.encode("utf-8")).hexdigest() != row["sha256"]:
            sys.exit(f"tin {row['id']}: văn bản không khớp SHA-256 đã commit — dừng")
        pred = sorted({c["type"] for c in lc.extract(text)})
        gold.append({"text": text, "claims": row["claims"]})
        per.append({"id": row["id"], "region": row["region"], "gold": sorted(row["claims"]), "pred": pred})
    s = listing_gold.score(gold)
    false_alarm = [p["id"] for p in per if not p["gold"] and p["pred"]]
    res = {"protocol": lab["protocol"], "source": "facebook_public_pages", "n": s["n"], "enough": s["enough"],
           "per_type": s["per_type"], "macro_f1": s["macro_f1"], "threshold_macro_f1": THRESHOLD,
           "passed": s["macro_f1"] is not None and s["macro_f1"] >= THRESHOLD,
           "no_claim_listings": sum(1 for p in per if not p["gold"]), "no_claim_but_extracted": false_alarm,
           "labeler": lab["labeler"],
           "data_note": note_vi, "data_note_en": note_en,
           "per_listing": per}
    json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: res[k] for k in ("macro_f1", "passed", "per_type", "no_claim_but_extracted")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
