"""CỔNG GĐ3 — đo bộ tách câu khẳng định trên TIN ĐĂNG THẬT do chủ dự án gán nhãn tay.

    python ops/listing_gate.py [backend/data/listings_gold.json]

Tệp vàng (định dạng như backend/data/listings_gold.example.json): danh sách
  {"text": "<nguyên văn tin đăng>", "claims": ["no_flood", "high_ground", ...]}   # loại câu có trong tin
Báo độ chính xác / độ phủ / F1 từng loại câu. Cổng kế hoạch: ≥ 20 tin thật; PhoBERT chỉ thay luật từ khoá
khi F1 ≥ 0,8 trên tập giữ lại. KHÔNG cào tin từ trang bất động sản — chỉ dùng tin tự thu thập.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.services import listing_check as lc  # noqa: E402

path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "backend", "data", "listings_gold.json")
if not os.path.exists(path):
    sys.exit(f"Chưa có tệp vàng {path} — chép listings_gold.example.json, điền ≥20 tin thật đã tự gán nhãn.")
gold = json.load(open(path, encoding="utf-8"))
types = [t for t, *_ in lc.CLAIMS]
tp = {t: 0 for t in types}; fp = dict(tp); fn = dict(tp)
for g in gold:
    pred = {c["type"] for c in lc.extract(g["text"])}
    want = set(g["claims"])
    for t in types:
        tp[t] += t in pred and t in want
        fp[t] += t in pred and t not in want
        fn[t] += t not in pred and t in want
print(f"{len(gold)} tin đăng")
f1s = []
for t in types:
    if tp[t] + fn[t] == 0 and fp[t] == 0:
        continue
    p = tp[t] / max(1, tp[t] + fp[t]); r = tp[t] / max(1, tp[t] + fn[t]); f1 = 2 * p * r / max(1e-9, p + r)
    f1s.append(f1)
    print(f"  {t:13} chính xác {p:.2f} · độ phủ {r:.2f} · F1 {f1:.2f}  (đúng {tp[t]}, thừa {fp[t]}, sót {fn[t]})")
macro = sum(f1s) / len(f1s) if f1s else 0.0
print(f"F1 trung bình: {macro:.2f} · đủ 20 tin: {'có' if len(gold) >= 20 else 'CHƯA'}")
sys.exit(0 if len(gold) >= 20 else 2)
