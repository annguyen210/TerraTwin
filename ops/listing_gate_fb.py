"""CỔNG GĐ3 lần 4–9 — 20 tin bán đất thật từ trang Facebook công khai của môi giới (listing_gate_v4/v5_protocol.json).

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
          "lấy từ trang dự phòng theo thứ tự đăng ký); NHÃN DO CLAUDE GÁN (phiên chat khác; ghi nhầm là nhãn người tới 8/11/2026)",
          "20 land-sale posts from public Facebook broker pages (Bến Tre 15, Nghệ An 4, Khánh Hòa 1 — 3 of 4 main pages were unavailable, "
          "filled from backup pages in registered order); labels by CLAUDE (a separate chat session; misrecorded as human labels until 8 Nov 2026)"),
    "7": ("listing_gate_v7_labels.json", "listing_gate_v7_result.json",
          "20 bài bán đất MỚI trên trang Facebook công khai của môi giới (Vĩnh Long, Thanh Hóa, Long An, Đồng Nai + dự phòng), thu SAU khi khoá "
          "luật sửa lần 7; NHÃN DO CLAUDE GÁN (phiên chat khác; ghi nhầm là nhãn người tới 8/11/2026); 20 tin lần 6 là tập phát triển",
          "20 NEW land-sale posts from public Facebook broker pages (Vĩnh Long, Thanh Hóa, Long An, Đồng Nai + backups), collected AFTER the "
          "run-7 rule fix was frozen; labels by CLAUDE (a separate chat session; misrecorded as human labels until 8 Nov 2026); the run-6 posts are the development set"),
    "8": ("listing_gate_v8_labels.json", "listing_gate_v8_result.json",
          "30 bài bán đất trên trang Facebook công khai của môi giới, CHỌN THEO TỪ CHỦ ĐỀ (biển, sông, ngập, phẳng/dốc, sạt lở, nước — "
          "5 bài/nhóm) để đo 6 loại câu chưa từng chấm trên nhãn người; luật GIỮ NGUYÊN lần 7; NHÃN DO CLAUDE GÁN (phiên chat khác; ghi nhầm là nhãn người tới 8/11/2026)",
          "30 land-sale posts from public Facebook broker pages, SELECTED BY TOPIC WORD (sea, river, flood, flat/slope, landslide, water — "
          "5 per group) to measure the 6 claim types never scored on human labels; rules UNCHANGED from run 7; labels by CLAUDE (a separate chat session; misrecorded as human labels until 8 Nov 2026)"),
    "9": ("listing_gate_v9_labels.json", "listing_gate_v9_result.json",
          "30 bài bán đất MỚI trên 4 trang Facebook công khai của môi giới (Đắk Lắk, Quảng Nam, Tây Ninh, An Giang + dự phòng): 20 bài đầu theo "
          "thứ tự trên trang + 10 bài có chữ 'quy hoạch'/'QH'/'ONT'/'ODT'; thu SAU khi khoá luật sửa lần 9; NHÃN DO CLAUDE GÁN (phiên chat khác; ghi nhầm là nhãn người tới 8/11/2026); "
          "30 tin lần 8 là tập phát triển",
          "30 NEW land-sale posts from 4 public Facebook broker pages (Đắk Lắk, Quảng Nam, Tây Ninh, An Giang + backups): first 20 in page "
          "order + 10 containing 'quy hoạch'/'QH'/'ONT'/'ODT'; collected AFTER the run-9 rule fix was frozen; labels by CLAUDE (a separate chat session; misrecorded as human labels until 8 Nov 2026); "
          "the run-8 posts are the development set"),
    "10": ("listing_gate_v10_labels.json", "listing_gate_v10_result.json",
           "Bài bán đất MỚI trên 5 trang Facebook công khai của môi giới ở vùng hay ngập chưa dùng (Huế, Quảng Trị – Đông Hà, Hải Phòng – "
           "Hải Dương cũ, Đồng Tháp – Tiền Giang cũ, Cần Thơ – Sóc Trăng cũ + dự phòng): 3 bài đầu mỗi trang theo thứ tự + tối đa 3 bài/trang "
           "có gốc chữ lấy từ HƯỚNG DẪN gán mã A/B ('ngập', 'lụt', 'khô ráo', 'cao', 'trũng') — KHÔNG lọc bằng luật của bộ tách câu; luật "
           "giữ nguyên như lần 9; giao thức đăng ký đo trên nhãn người; lần 1–9 là tập phát triển",
           "NEW land-sale posts from 5 public Facebook broker pages in flood-prone regions not used before (Huế, Quảng Trị – Đông Hà, Hải Phòng "
           "– former Hải Dương, Đồng Tháp – former Tiền Giang, Cần Thơ – former Sóc Trăng + backups): first 3 per page in page order + up to 3 "
           "per page containing word stems taken from the A/B labelling GUIDELINE ('ngập', 'lụt', 'khô ráo', 'cao', 'trũng') — NOT filtered "
           "with the extractor's own rules; rules unchanged since run 9; protocol registered to score on human labels; runs 1–9 are the "
           "development set"),
}
# Lần 9: chỗ sửa nào ĐƯỢC KIỂM — đếm tin mới có đúng kiểu câu đã sửa (trên chữ đã bỏ dấu) và máy đúng/sai ở loại đó.
FIX_FAMILIES = {"9": {
    "quy_hoach_ont": ("residential", r"(quy hoach|\bqh\b)[^.;\n]{0,25}\b(ont|odt)\b"),
    "cao_thoang_mat_bang_cao": ("high_ground", r"\bcao thoang\b|\bmat bang (dat )?cao\b"),
    "ben_do_qua_song": ("near_river", r"\bben (do|pha|ghe)\b|\bqua (dong |con )?song\b"),
    "tho_kem_so": ("residential", r"\btho (\d|het\b)"),
    "ra_bien_km_co_phay": ("near_sea", r"\b(di|ra|xuong|toi|den) (bai )?bien\b[^.;]{0,45}?,[^.;]*?\d+ ?(km|p|phut)\b"),
}}
# Lần 8: F1 CHÍNH chỉ tính 6 loại đích (listing_gate_v8_protocol.json "target_types"); F1 mọi loại vẫn ghi làm số phụ.
TARGETS = {"8": ["no_flood", "near_river", "near_sea", "flat", "no_landslide", "fresh_water"],
           # Lần 10 (đăng ký 7/11/2026): đo "không ngập" và "cao ráo" — lần 9 chỉ đo được gần sông + thổ cư.
           "10": ["no_flood", "high_ground"]}
# Lần 10: cần ≥ 8 tin có câu đích (mã A hoặc B theo nhãn chấm cổng); thiếu thì CHƯA KẾT LUẬN — không tính đạt, không tính trượt.
MIN_TARGET_LISTINGS = {"10": 8}
# Lần 4–5 nhãn do Claude gán (REPRODUCE.md §13) — tệp nhãn cũ không có labeler_kind nên khai thay ở đây.
DEFAULT_KIND = {"4": "claude", "5": "claude"}
# Giao thức đã đăng ký chấm trên NHÃN NGƯỜI (listing_gate_v10_protocol.json "labelers") — nhãn khác thì CHƯA KẾT LUẬN.
HUMAN_REQUIRED = {"10"}
THRESHOLD = 0.80


def labeler_kind(run: str, lab: dict) -> str:
    """Ai gán nhãn chấm cổng — tệp nhãn PHẢI tự khai (đính chính 8/11/2026: nhãn "người" lần 6–9 là của Claude)."""
    kind = lab.get("labeler_kind") or DEFAULT_KIND.get(run)
    if kind not in ("human", "claude"):
        sys.exit(f"lần {run}: tệp nhãn thiếu labeler_kind ('human' hoặc 'claude') — khai rõ ai gán trước khi chấm")
    return kind


def require_human(res: dict, run: str, kind: str) -> None:
    """Giao thức cần nhãn người mà nhãn không phải của người → không tính đạt hay trượt, dù F1 bao nhiêu."""
    if run in HUMAN_REQUIRED and kind != "human":
        res["passed"] = None
        res["verdict"] = (f"CHƯA KẾT LUẬN — giao thức lần {run} đăng ký chấm trên nhãn người, tệp nhãn khai labeler_kind "
                          f"'{kind}'" + (f"; {res['verdict']}" if res.get("verdict") else ""))


def main() -> None:
    from app.services import listing_check as lc, listing_gold

    run = sys.argv[sys.argv.index("--run") + 1] if "--run" in sys.argv else "4"
    LABELS, RESULT, note_vi, note_en = RUNS[run]
    out = os.path.join(EVAL, RESULT)
    if os.path.exists(out):
        sys.exit(f"{RESULT} đã có — giao thức chấm MỘT lần, không chấm lại")
    lab = json.load(open(os.path.join(EVAL, LABELS), encoding="utf-8"))
    kind = labeler_kind(run, lab)
    if kind == "claude":
        note_vi += "; NHÃN DO CLAUDE GÁN — không phải nhãn người"
        note_en += "; labels by CLAUDE — not human labels"
    tin ={t["id"]: t["text"].strip() for t in json.load(open(sys.argv[1], encoding="utf-8"))}
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
           "labeler": lab["labeler"], "labeler_kind": kind,
           "data_note": note_vi, "data_note_en": note_en,
           "per_listing": per}
    if run in TARGETS:
        res["target_types"] = TARGETS[run]
        res["macro_f1_all_types"] = s["macro_f1"]
        res["target_positives"] = {t: sum(t in g["claims"] for g in gold) for t in TARGETS[run]}
        res["few_samples"] = [t for t, n in res["target_positives"].items() if n < 3]
        if run in MIN_TARGET_LISTINGS:
            n_t = sum(any(t in g["claims"] for t in TARGETS[run]) for g in gold)
            res["target_listings"], res["min_target_listings"] = n_t, MIN_TARGET_LISTINGS[run]
            if n_t < MIN_TARGET_LISTINGS[run]:
                res["passed"] = None
                res["verdict"] = (f"CHƯA KẾT LUẬN — chỉ {n_t} tin có câu không ngập / cao ráo theo nhãn chấm cổng "
                                  f"(cần ≥ {MIN_TARGET_LISTINGS[run]})")
    require_human(res, run, kind)
    # Lần 6: nhãn AI phụ (khoá trước) chỉ để đo độ khớp với nhãn chấm cổng — tên khoá ai_vs_human giữ cho tương thích.
    ai_path = os.path.join(EVAL, LABELS.replace("_labels.json", "_ai_labels.json"))
    if os.path.exists(ai_path):
        ai = {r["id"]: set(r["claims"]) for r in json.load(open(ai_path, encoding="utf-8"))["labels"]}
        hum = {r["id"]: set(r["claims"]) for r in lab["labels"]}
        tp = sum(len(ai[i] & hum[i]) for i in hum); fp = sum(len(ai[i] - hum[i]) for i in hum); fn = sum(len(hum[i] - ai[i]) for i in hum)
        p, r = tp / max(1, tp + fp), tp / max(1, tp + fn)
        res["ai_vs_human"] = {"listings_exact_match": sum(ai[i] == hum[i] for i in hum), "n": len(hum),
                              "precision": round(p, 2), "recall": round(r, 2), "f1": round(2 * p * r / max(1e-9, p + r), 2),
                              "tp": tp, "fp": fp, "fn": fn,
                              "note": ("Nhãn AI (Claude, khoá trước khi người gán) so với nhãn người, gộp mọi loại câu" if kind == "human" else
                                       "Nhãn AI phụ (phiên Claude viết luật, khoá trước) so với nhãn chấm cổng (phiên Claude khác) — "
                                       "Claude so với Claude, gộp mọi loại câu")}
    if run in FIX_FAMILIES:
        import re
        fam = {}
        for name, (typ, rx) in FIX_FAMILIES[run].items():
            hit = [p for p, g in zip(per, gold) if re.search(rx, lc.fold(g["text"]))]
            ok = sum((typ in p["gold"]) == (typ in p["pred"]) for p in hit)
            fam[name] = {"type": typ, "listings": len(hit), "machine_correct": ok,
                         "tested": bool(hit), "ids": [p["id"] for p in hit]}
        res["fixes_exercised"] = fam
    json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: res[k] for k in ("macro_f1", "passed", "per_type", "no_claim_but_extracted")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
