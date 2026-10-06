"""API GÁN NHÃN kiểm định EUDR v3 — xem services/label_v3.py vì sao cần nhãn người.

Ai được gán: quản trị viên, hoặc email quản trị viên đã cấp (bảng labeler_grants). Gán nhãn
là tạo THƯỚC ĐO cho cả hệ thống, nên không mở cho người lạ.
MÙ: không route nào trả cho người gán tầng lấy mẫu, kết quả máy hay nhãn của người khác.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth
from app.db import LabelerGrant, LabelV3, User, get_session
from app.services import label_v3, reqlang
from app.services.reqlang import tr

router = APIRouter(tags=["label"])


def _can_label(user: User, db: Session) -> bool:
    if getattr(user, "role", "user") == "admin":
        return True
    return db.get(LabelerGrant, (user.email or "").strip().lower()) is not None


def _labeler(user: User = Depends(auth.current_user), db: Session = Depends(get_session)) -> User:
    if not _can_label(user, db):
        raise HTTPException(403, tr("Tài khoản này chưa được cấp quyền gán nhãn — nhờ quản trị viên thêm email ở trang Quản trị.",
                                    "This account may not label yet — ask an administrator to add your email on the Admin page."))
    return user


def _mine(db: Session, user_id: int) -> dict[int, LabelV3]:
    return {r.cell: r for r in db.execute(select(LabelV3).where(LabelV3.user_id == user_id)).scalars()}


def _label_out(r: LabelV3 | None) -> dict | None:
    return None if r is None else {"cover2020": r.cover2020, "loss": r.loss, "confidence": r.confidence, "note": r.note}


@router.get("/api/label/v3/protocol")
def protocol() -> dict:
    """Giao thức đặt trước (công khai) + lớp nhãn song ngữ."""
    return {"protocol": label_v3.PROTOCOL_DOC_V3,
            "cover": {k: {"vi": v[0], "en": v[1]} for k, v in label_v3.COVER.items()},
            "sample_ready": label_v3.load_sample() is not None, "n_cells": len(label_v3.cells())}


@router.get("/api/label/v3/me")
def me(user: User = Depends(auth.current_user), db: Session = Depends(get_session)) -> dict:
    n = len(label_v3.cells())
    can = _can_label(user, db)
    return {"can_label": can, "n_cells": n, "done": len(_mine(db, user.id)) if can else 0,
            "sample_ready": n > 0}


@router.get("/api/label/v3/next")
def next_cell(after: int | None = None, lang: str = "vi", user: User = Depends(_labeler),
              db: Session = Depends(get_session)) -> dict:
    """Ô CHƯA gán tiếp theo theo thứ tự riêng của người này (after = bỏ qua tới sau ô đó)."""
    reqlang.set_lang(lang)
    n = len(label_v3.cells())
    if n == 0:
        raise HTTPException(503, tr("Mẫu v3 chưa được tạo.", "The v3 sample has not been generated yet."))
    mine = _mine(db, user.id)
    order = label_v3.order_for(user.id, n)
    start = order.index(after) + 1 if after is not None and after in order else 0
    rest = [k for k in order[start:] + order[:start] if k not in mine]
    if not rest:
        return {"done": True, "labeled": len(mine), "n_cells": n}
    k = rest[0]
    return {"done": False, "labeled": len(mine), "n_cells": n, "position": order.index(k) + 1,
            "view": label_v3.view(k), "mine": None}


@router.get("/api/label/v3/cell/{k}")
def get_cell(k: int, user: User = Depends(_labeler), db: Session = Depends(get_session)) -> dict:
    v = label_v3.view(k)
    if v is None:
        raise HTTPException(404, tr("Không có ô này.", "No such cell."))
    mine = _mine(db, user.id)
    return {"done": False, "labeled": len(mine), "n_cells": len(label_v3.cells()),
            "position": label_v3.order_for(user.id, len(label_v3.cells())).index(k) + 1,
            "view": v, "mine": _label_out(mine.get(k))}


class LabelIn(BaseModel):
    cover2020: Literal["natural_forest", "planted_forest", "tree_crop", "no_trees", "unclear"]
    loss: Literal["yes", "no", "unclear"]
    confidence: int = Field(default=2, ge=1, le=3)
    seconds: int | None = Field(default=None, ge=0, le=3600)
    note: str = Field(default="", max_length=300)


@router.post("/api/label/v3/cell/{k}")
def put_label(k: int, body: LabelIn, user: User = Depends(_labeler), db: Session = Depends(get_session)) -> dict:
    if label_v3.view(k) is None:
        raise HTTPException(404, tr("Không có ô này.", "No such cell."))
    if (label_v3.load_sample() or {}).get("locked_at"):
        raise HTTPException(409, tr("Nhãn đã khoá để chấm — không sửa được nữa.", "Labels are locked for scoring."))
    row = db.execute(select(LabelV3).where(LabelV3.cell == k, LabelV3.user_id == user.id)).scalar_one_or_none()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if row is None:
        row = LabelV3(cell=k, user_id=user.id, created_at=now)
        db.add(row)
    row.cover2020, row.loss, row.confidence = body.cover2020, body.loss, body.confidence
    row.seconds, row.note, row.updated_at = body.seconds, body.note.strip(), now
    db.commit()
    return {"ok": True, "labeled": len(_mine(db, user.id))}


# ------------------------------------------------------------------ quản trị

class GrantIn(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@router.get("/api/admin/label/v3/labelers")
def list_labelers(_: User = Depends(auth.require_admin), db: Session = Depends(get_session)) -> dict:
    rows = db.execute(select(LabelerGrant).order_by(LabelerGrant.created_at)).scalars().all()
    return {"labelers": [{"email": r.email, "created_at": r.created_at.isoformat() if r.created_at else None}
                         for r in rows]}


@router.post("/api/admin/label/v3/labelers")
def add_labeler(body: GrantIn, admin: User = Depends(auth.require_admin), db: Session = Depends(get_session)) -> dict:
    email = body.email.strip().lower()
    if db.get(LabelerGrant, email) is None:
        db.add(LabelerGrant(email=email, granted_by=admin.id))
        db.commit()
    return {"ok": True, "email": email}


@router.delete("/api/admin/label/v3/labelers/{email}")
def remove_labeler(email: str, _: User = Depends(auth.require_admin), db: Session = Depends(get_session)) -> dict:
    row = db.get(LabelerGrant, email.strip().lower())
    if row is not None:
        db.delete(row)
        db.commit()
    return {"ok": True}


def _all_labels(db: Session) -> list[dict]:
    return [{"cell": r.cell, "user_id": r.user_id, "cover2020": r.cover2020, "loss": r.loss,
             "confidence": r.confidence, "seconds": r.seconds, "note": r.note,
             "updated_at": r.updated_at.isoformat() if r.updated_at else None}
            for r in db.execute(select(LabelV3).order_by(LabelV3.cell, LabelV3.user_id)).scalars()]


@router.get("/api/admin/label/v3/summary")
def summary(_: User = Depends(auth.require_admin), db: Session = Depends(get_session)) -> dict:
    """Tiến độ + độ đồng thuận. KHÔNG có kết quả máy — chỉ chấm một lần sau khi khoá nhãn."""
    labels = _all_labels(db)
    t = label_v3.truth(labels)
    per_user: dict[int, int] = {}
    for r in labels:
        per_user[r["user_id"]] = per_user.get(r["user_id"], 0) + 1
    emails = {u.id: u.email for u in db.execute(select(User).where(User.id.in_(list(per_user) or [-1]))).scalars()}
    return {"n_cells": len(label_v3.cells()), "per_labeler": [{"email": emails.get(u, f"#{u}"), "labeled": n}
                                                                for u, n in sorted(per_user.items())],
            "truth_counts": t["counts"], "cells_2plus": t["cells_2plus"], "excluded": t["excluded"],
            "kappa_forest": t["kappa_forest"], "agree_forest": t["agree_forest"],
            "min_n_per_set": label_v3.PROTOCOL_DOC_V3["min_n_per_set"]}


@router.get("/api/admin/label/v3/export")
def export(_: User = Depends(auth.require_admin), db: Session = Depends(get_session)) -> dict:
    """Toàn bộ nhãn (mã người gán thay cho email) — đầu vào của `python -m app.eudr_validate_v3 run`."""
    labels = _all_labels(db)
    anon = {u: i + 1 for i, u in enumerate(sorted({r["user_id"] for r in labels}))}
    for r in labels:
        r["labeler"] = anon[r.pop("user_id")]
    return {"exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "labels": labels}
