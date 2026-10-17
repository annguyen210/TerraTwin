"""Kiểm THỰC ĐỊA bộ phát hiện đợt nước radar bằng xác nhận người dùng (17/10/2026).

Cách chấm chốt trước trong data/eval/water_field_protocol.json (đăng ký trước khi đọc câu trả lời nào). Module này chỉ
làm đúng các bước đã ghi: lọc tài khoản, giới hạn mỗi người 20 đợt, nhãn theo đa số, cỡ mẫu tối thiểu, độ chính xác +
khoảng Wilson 95%. Chấm (ghi kết quả) chỉ qua ops/water_field_gate.py — một lần.
"""
from __future__ import annotations

import json
import math
import os
from collections import defaultdict

from sqlalchemy.orm import Session

EVAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "eval")
PROTOCOL = os.path.join(EVAL, "water_field_protocol.json")
RESULT = os.path.join(EVAL, "water_field_result.json")
TEST_DOMAINS = ("vd.vn", "example.com", "example.org", "test", "localhost")
PER_USER_CAP = 20


def protocol() -> dict:
    with open(PROTOCOL, encoding="utf-8") as f:
        return json.load(f)


def result() -> dict | None:
    try:
        with open(RESULT, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _excluded(u) -> bool:
    admins = {e.strip().lower() for e in os.environ.get("TERRATWIN_ADMIN_EMAILS", "").split(",") if e.strip()}
    email = (u.email or "").lower()
    dom = email.rsplit("@", 1)[-1]
    return u.role == "admin" or email in admins or any(dom == d or dom.endswith("." + d) for d in TEST_DOMAINS)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def labelled(db: Session) -> list[dict]:
    """Các đợt có nhãn theo giao thức: [{cell, event_start, v1_label, yes, no, label, users}]."""
    from app.db import User, WaterConfirm
    rows = db.query(WaterConfirm).order_by(WaterConfirm.created_at, WaterConfirm.id).all()
    users = {u.id: u for u in db.query(User).filter(User.id.in_({r.user_id for r in rows})).all()} if rows else {}
    seen: dict[int, int] = defaultdict(int)
    ev: dict[tuple, dict] = {}
    for r in rows:
        u = users.get(r.user_id)
        if u is None or _excluded(u) or r.answer not in ("yes", "no"):
            continue
        if seen[r.user_id] >= PER_USER_CAP:
            continue
        seen[r.user_id] += 1
        e = ev.setdefault((r.cell, r.event_start), {"cell": r.cell, "event_start": r.event_start, "v1_label": r.v1_label,
                                                    "yes": 0, "no": 0, "users": set()})
        e[r.answer] += 1
        e["users"].add(r.user_id)
    out = []
    for e in ev.values():
        if e["yes"] == e["no"]:
            continue
        out.append({**e, "label": "flooded" if e["yes"] > e["no"] else "not_flooded"})
    return out


def _deg_cell(cell: str) -> str:
    la, lo = (float(x) for x in cell.split(","))
    return f"{math.floor(la)},{math.floor(lo)}"


def status(db: Session) -> dict:
    """Tiến độ so với cỡ mẫu tối thiểu — chỉ số đếm, không toạ độ thửa."""
    p = protocol()["minimum_sample"]
    ev = labelled(db)
    n_users = len(set().union(*[e["users"] for e in ev])) if ev else 0
    n_cells = len({_deg_cell(e["cell"]) for e in ev})
    have = {"labelled_events": len(ev), "distinct_users": n_users, "distinct_1deg_cells": n_cells}
    need = {k: p[k] for k in have}
    return {"have": have, "need": need, "ready": all(have[k] >= need[k] for k in have), "result": result()}


def score(db: Session) -> dict:
    """Chấm theo giao thức. Không ghi tệp — ops/water_field_gate.py ghi (một lần)."""
    ev = labelled(db)
    st = status(db)
    k = sum(1 for e in ev if e["label"] == "flooded")
    n = len(ev)
    lo, hi = wilson(k, n)
    p = k / n if n else None
    outcome = ("confirmed" if lo >= 0.60 else "too_many_false" if p is not None and p < 0.50 else "inconclusive")
    by_season = {}
    for s in ("in", "out", None):
        sub = [e for e in ev if e["v1_label"] == s]
        if sub:
            kk = sum(1 for e in sub if e["label"] == "flooded")
            by_season[s or "none"] = {"n": len(sub), "flooded": kk, "p": round(kk / len(sub), 3)}
    per_cell = defaultdict(int)
    for e in ev:
        per_cell[_deg_cell(e["cell"])] += 1
    return {"protocol": "water_field_protocol.json", "sample": st["have"], "minimum": st["need"], "ready": st["ready"],
            "flooded": k, "not_flooded": n - k, "precision": None if p is None else round(p, 3),
            "wilson95": [round(lo, 3), round(hi, 3)], "outcome": outcome if st["ready"] else None,
            "by_v1_season": by_season, "events_per_1deg_cell": dict(per_cell)}
