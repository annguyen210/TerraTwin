"""CỔNG GĐ3 lần 4–8 — 20 tin bán đất thật từ trang Facebook công khai của môi giới (listing_gate_v4/v5_protocol.json).

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
    "6": ("listing_gate_v6_labels.json", "listing_gate_v6_result.json",
          "20 bài bán đất trên trang Facebook công khai của môi giới (Bến Tre 15, Nghệ An 4, Khánh Hòa 1 — 3/4 trang chính không xem được, "
          "lấy từ trang dự phòng theo thứ tự đăng ký); NHÃN NGƯỜI do chủ dự án tự gán, không thấy nhãn máy",
          "20 land-sale posts from public Facebook broker pages (Bến Tre 15, Nghệ An 4, Khánh Hòa 1 — 3 of 4 main pages were unavailable, "
          "filled from backup pages in registered order); HUMAN labels by the owner, who did not see any machine labels"),
    "7": ("listing_gate_v7_labels.json", "listing_gate_v7_result.json",
          "20 bài bán đất MỚI trên trang Facebook công khai của môi giới (Vĩnh Long, Thanh Hóa, Long An, Đồng Nai + dự phòng), thu SAU khi khoá "
          "luật sửa lần 7; NHÃN NGƯỜI do chủ dự án tự gán; 20 tin lần 6 là tập phát triển",
          "20 NEW land-sale posts from public Facebook broker pages (Vĩnh Long, Thanh Hóa, Long An, Đồng Nai + backups), collected AFTER the "
          "run-7 rule fix was frozen; HUMAN labels by the owner; the run-6 posts are the development set"),
    "8": ("listing_gate_v8_labels.json", "listing_gate_v8_result.json",
          "30 bài bán đất trên trang Facebook công khai của môi giới, CHỌN THEO TỪ CHỦ ĐỀ (biển, sông, ngập, phẳng/dốc, sạt lở, nước — "
          "5 bài/nhóm) để đo 6 loại câu chưa từng chấm trên nhãn người; luật GIỮ NGUYÊN lần 7; NHÃN NGƯỜI do chủ dự án tự gán",
          "30 land-sale posts from public Facebook broker pages, SELECTED BY TOPIC WORD (sea, river, flood, flat/slope, landslide, water — "
          "5 per group) to measure the 6 claim types never scored on human labels; rules UNCHANGED from run 7; HUMAN labels by the owner"),
}
# Lần 8: F1 CHÍNH chỉ tính 6 loại đích (listing_gate_v8_protocol.json "target_types"); F1 mọi loại vẫn ghi làm số phụ.
TARGETS = {"8": ["no_flood", "near_river", "near_sea", "flat", "no_landslide", "fresh_water"]}
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
    primary = s["macro_f1"]
    if run in TARGETS:
        rows = [r for r in s["per_type"] if r["type"] in TARGETS[run]]
        primary = round(sum(r["f1"] for r in rows) / len(rows), 2) if rows else None
    false_alarm = [p["id"] for p in per if not p["gold"] and p["pred"]]
    res = {"protocol": lab["protocol"], "source": "facebook_public_pages", "n": s["n"], "enough": s["enough"],
           "per_type": s["per_type"], "macro_f1": primary, "threshold_macro_f1": THRESHOLD,
           "passed": primary is not None and primary >= THRESHOLD,
           "no_claim_listings": sum(1 for p in per if not p["gold"]), "no_claim_but_extracted": false_alarm,
           "labeler": lab["labeler"],
           "data_note": note_vi, "data_note_en": note_en,
           "per_listing": per}
    if run in TARGETS:
        res["target_types"] = TARGETS[run]
        res["macro_f1_all_types"] = s["macro_f1"]
        res["target_positives"] = {t: sum(t in g["claims"] for g in gold) for t in TARGETS[run]}
        res["few_samples"] = [t for t, n in res["target_positives"].items() if n < 3]
    # Lần 6: nhãn chấm cổng là nhãn NGƯỜI; nhãn AI (khoá trước) chỉ để đo độ khớp AI–người.
    ai_path = os.path.join(EVAL, LABELS.replace("_labels.json", "_ai_labels.json"))
    if os.path.exists(ai_path):
        ai = {r["id"]: set(r["claims"]) for r in json.load(open(ai_path, encoding="utf-8"))["labels"]}
        hum = {r["id"]: set(r["claims"]) for r in lab["labels"]}
        tp = sum(len(ai[i] & hum[i]) for i in hum); fp = sum(len(ai[i] - hum[i]) for i in hum); fn = sum(len(hum[i] - ai[i]) for i in hum)
        p, r = tp / max(1, tp + fp), tp / max(1, tp + fn)
        res["labeler_kind"] = "human"
        res["ai_vs_human"] = {"listings_exact_match": sum(ai[i] == hum[i] for i in hum), "n": len(hum),
                              "precision": round(p, 2), "recall": round(r, 2), "f1": round(2 * p * r / max(1e-9, p + r), 2),
                              "tp": tp, "fp": fp, "fn": fn,
                              "note": "Nhãn AI (Claude, khoá trước khi người gán) so với nhãn người, gộp mọi loại câu"}
    json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: res[k] for k in ("macro_f1", "passed", "per_type", "no_claim_but_extracted")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
