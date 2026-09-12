"""A6 — sổ đăng ký mô hình + quay lui.

Mỗi lần huấn luyện (A1 U-Net, A11 TCN…) ghi một hàng kèm mã băm bộ dữ liệu. Đổi
mô hình đang hoạt động bằng một lời gọi API, không deploy lại; quay lui cũng vậy.
Chỉ một phiên bản 'active' cho mỗi 'kind' tại một thời điểm.
"""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import ModelVersion


def _set_active(db: Session, kind: str, mv_id: int) -> None:
    for m in db.execute(select(ModelVersion).where(ModelVersion.kind == kind)).scalars():
        m.active = 1 if m.id == mv_id else 0


def register(db: Session, kind: str, version: str, *, data_hash: str = "",
             metrics: dict | None = None, artifact_path: str = "",
             notes: str = "", activate: bool = False) -> ModelVersion:
    mv = ModelVersion(
        kind=kind, version=version, data_hash=data_hash,
        metrics_json=json.dumps(metrics or {}, ensure_ascii=False),
        artifact_path=artifact_path, notes=notes, active=0)
    db.add(mv)
    db.flush()
    if activate:
        _set_active(db, kind, mv.id)
    db.commit()
    db.refresh(mv)
    return mv


def activate(db: Session, mv_id: int) -> ModelVersion | None:
    mv = db.get(ModelVersion, mv_id)
    if mv is None:
        return None
    _set_active(db, mv.kind, mv.id)          # tắt các bản khác cùng kind
    db.commit()
    db.refresh(mv)
    return mv


def list_versions(db: Session, kind: str | None = None) -> list[ModelVersion]:
    q = select(ModelVersion).order_by(
        ModelVersion.kind, ModelVersion.trained_at.desc())
    if kind:
        q = q.where(ModelVersion.kind == kind)
    return list(db.execute(q).scalars().all())


def active_for(db: Session, kind: str) -> ModelVersion | None:
    """Phiên bản đang hoạt động của một loại mô hình — pipeline huấn luyện/suy
    luận gọi hàm này để biết dùng bản nào (và stamp vào cảnh báo về sau)."""
    return db.execute(
        select(ModelVersion).where(
            ModelVersion.kind == kind, ModelVersion.active == 1)
    ).scalar_one_or_none()


def to_dict(mv: ModelVersion) -> dict:
    return {
        "id": mv.id, "kind": mv.kind, "version": mv.version,
        "trained_at": mv.trained_at.isoformat(timespec="seconds"),
        "data_hash": mv.data_hash,
        "metrics": json.loads(mv.metrics_json or "{}"),
        "artifact_path": mv.artifact_path,
        "active": bool(mv.active), "notes": mv.notes,
    }
