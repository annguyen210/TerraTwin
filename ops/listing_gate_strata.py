"""F1 riêng từng TẦNG chọn mẫu của một lần chấm cổng GĐ3 — số PHỤ giao thức đã đăng ký (listing_gate_v10_protocol.json
"metric": "F1 riêng tầng A và tầng B").

    python ops/listing_gate_strata.py --run 10      # ghi backend/data/eval/listing_gate_v10_strata.json

KHÔNG chạy lại bộ tách câu: chỉ ghép "per_listing" (gold/pred đã ghi trong tệp kết quả một lần) với tầng của từng tin trong
nhật ký chọn mẫu (listing_gate_v10_selection.json — phải khớp SHA-256 đã khoá trong listing_gate_v10_hashes.json). Ai cũng
tính lại được bằng tay từ hai tệp đó. Thêm 9/11/2026 theo review Qodo PR #8.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
EVAL = os.path.join(ROOT, "backend", "data", "eval")
TYPES = ("no_flood", "high_ground", "near_river", "near_sea", "flat", "no_landslide", "residential", "fresh_water")


def _rows(per: list[dict]) -> tuple[list[dict], float | None]:
    """Cùng cách tính với app.services.listing_gold.score: bỏ loại không có tin đúng/thừa/sót nào."""
    rows, f1s = [], []
    for t in TYPES:
        tp = sum(t in p["pred"] and t in p["gold"] for p in per)
        fp = sum(t in p["pred"] and t not in p["gold"] for p in per)
        fn = sum(t not in p["pred"] and t in p["gold"] for p in per)
        if tp + fn == 0 and fp == 0:
            continue
        pr, rc = tp / max(1, tp + fp), tp / max(1, tp + fn)
        f1 = 2 * pr * rc / max(1e-9, pr + rc)
        f1s.append(f1)
        rows.append({"type": t, "precision": round(pr, 2), "recall": round(rc, 2), "f1": round(f1, 2), "tp": tp, "fp": fp, "fn": fn})
    return rows, (round(sum(f1s) / len(f1s), 2) if f1s else None)


def strata(run: str, eval_dir: str = EVAL) -> dict:
    res = json.load(open(os.path.join(eval_dir, f"listing_gate_v{run}_result.json"), encoding="utf-8"))
    sel_path = os.path.join(eval_dir, f"listing_gate_v{run}_selection.json")
    raw = open(sel_path, "rb").read()
    want = json.load(open(os.path.join(eval_dir, f"listing_gate_v{run}_hashes.json"), encoding="utf-8"))["selection_sha256"]
    got = hashlib.sha256(raw).hexdigest()
    if got != want:
        sys.exit(f"nhật ký chọn mẫu lần {run} không khớp SHA-256 đã khoá ({got[:12]} ≠ {want[:12]}) — dừng")
    stratum = {t["id"]: t["stratum"] for t in json.loads(raw.decode("utf-8"))["taken"]}
    targets = res.get("target_types") or []
    out = {"protocol": res["protocol"], "source_result": f"listing_gate_v{run}_result.json",
           "source_selection": f"listing_gate_v{run}_selection.json", "selection_sha256": got,
           "method": "ghép per_listing (gold/pred) của tệp kết quả với tầng trong nhật ký chọn mẫu — không chạy lại bộ tách câu",
           "labeler_kind": res.get("labeler_kind"), "labeler_independent": res.get("labeler_independent"), "strata": {}}
    for s in sorted(set(stratum.values())):
        per = [p for p in res["per_listing"] if stratum.get(p["id"]) == s]
        rows, macro_all = _rows(per)
        tgt = [r for r in rows if r["type"] in targets]
        out["strata"][s] = {"n": len(per), "ids": [p["id"] for p in per],
                            "target_listings": sum(any(t in p["gold"] for t in targets) for p in per),
                            "macro_f1_targets": round(sum(r["f1"] for r in tgt) / len(tgt), 2) if tgt else None,
                            "macro_f1_all_types": macro_all, "per_type": rows,
                            "no_claim_listings": sum(1 for p in per if not p["gold"]),
                            "no_claim_but_extracted": [p["id"] for p in per if not p["gold"] and p["pred"]]}
    return out


def main() -> None:
    run = sys.argv[sys.argv.index("--run") + 1] if "--run" in sys.argv else "10"
    out = strata(run)
    json.dump(out, open(os.path.join(EVAL, f"listing_gate_v{run}_strata.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({s: {k: v[k] for k in ("n", "target_listings", "macro_f1_targets", "macro_f1_all_types")}
                      for s, v in out["strata"].items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
