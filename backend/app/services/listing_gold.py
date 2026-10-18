"""Tập vàng cổng GĐ3 (18/10/2026): ẩn danh tin đăng + chấm bộ tách câu khẳng định đúng như ops/listing_gate.py.

Nhãn PHẢI do người gán (chủ dự án) — bộ tách câu là luật do TerraTwin viết, để máy tự gán là tự chấm bài mình.
"""
from __future__ import annotations

import re

_PHONE = re.compile(r"(?:\+?84|0)(?:[\s.\-]?\d){8,10}")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL = re.compile(r"(?:https?://|www\.)\S+", re.I)


def anonymize(text: str) -> str:
    t = _URL.sub("[đường dẫn]", text)
    t = _EMAIL.sub("[email]", t)
    t = _PHONE.sub("[số điện thoại]", t)
    return re.sub(r"[ \t]+", " ", t).strip()


def score(gold: list[dict]) -> dict:
    """Chính xác / độ phủ / F1 từng loại câu + F1 trung bình — CÙNG cách tính với ops/listing_gate.py."""
    from app.services import listing_check as lc
    types = [t for t, *_ in lc.CLAIMS]
    tp = {t: 0 for t in types}; fp = dict(tp); fn = dict(tp)
    for g in gold:
        pred = {c["type"] for c in lc.extract(g["text"])}
        want = set(g["claims"])
        for t in types:
            tp[t] += t in pred and t in want
            fp[t] += t in pred and t not in want
            fn[t] += t not in pred and t in want
    rows, f1s = [], []
    for t in types:
        if tp[t] + fn[t] == 0 and fp[t] == 0:
            continue
        p = tp[t] / max(1, tp[t] + fp[t]); r = tp[t] / max(1, tp[t] + fn[t]); f1 = 2 * p * r / max(1e-9, p + r)
        f1s.append(f1)
        rows.append({"type": t, "precision": round(p, 2), "recall": round(r, 2), "f1": round(f1, 2),
                     "tp": tp[t], "fp": fp[t], "fn": fn[t]})
    return {"n": len(gold), "enough": len(gold) >= 20, "per_type": rows,
            "macro_f1": round(sum(f1s) / len(f1s), 2) if f1s else None}
