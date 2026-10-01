"""Thẩm định hàng loạt — xem services/batch.py.

Cần đăng nhập: kết quả là danh mục khoản vay / hợp đồng của một tổ chức, chỉ
chủ lần chạy xem, tải và xoá được.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth
from app.db import BatchRun, User, get_session
from app.services import batch, jobs_db, reqlang

router = APIRouter(tags=["batch"])


class BatchIn(BaseModel):
    csv: str = Field(min_length=1, max_length=400_000)
    title: str = Field(default="", max_length=200)


def _active_run(db: Session, user_id: int) -> BatchRun | None:
    return db.execute(select(BatchRun).where(BatchRun.user_id == user_id,
                                             BatchRun.state.in_(("queued", "running")))
                      .order_by(BatchRun.created_at.desc())).scalars().first()


def _progress(db: Session, r: BatchRun) -> dict:
    """Tiến độ: ưu tiên bản việc nền đang báo (có pha 'chờ hạn mức'); máy chủ vừa
    thức dậy chưa ai báo thì tự đếm số thửa đã ghi."""
    st = jobs_db.status(db, r.id) or {}
    p = st.get("progress") or {}
    done = len(json.loads(r.rows_json or "[]"))
    return {"done": max(done, int(p.get("done") or 0)), "total": r.n_rows,
            "current": p.get("current") or "", "phase": p.get("phase") or r.state,
            "detail": p.get("detail")}


@router.get("/api/batch/template")
def batch_template() -> Response:
    """Tệp mẫu — cột ma, lat, lon, area_ha (cũng nhận vi_do/kinh_do/dien_tich)."""
    return Response("﻿" + batch.TEMPLATE, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="terratwin-mau.csv"'})


@router.post("/api/batch")
def submit_batch(body: BatchIn, lang: str = "vi",
                 user: User = Depends(auth.current_user),
                 db: Session = Depends(get_session)) -> dict:
    """Đọc CSV, báo lỗi từng dòng, đẩy phần hợp lệ vào hàng đợi bền."""
    reqlang.set_lang(lang)
    rows, errors = batch.parse_csv(body.csv)
    if not rows:
        raise HTTPException(422, {"message": reqlang.tr("Không có dòng hợp lệ nào.",
                                                        "No valid rows."), "errors": errors})
    active = _active_run(db, user.id)
    if active is not None:
        # Một lô một lúc cho mỗi tài khoản: mỗi thửa đã gọi nguồn dữ liệu miễn phí.
        raise HTTPException(409, {"message": reqlang.tr(
            "Bạn đang có một lô chưa chạy xong — đợi xong rồi gửi lô mới.",
            "You already have a batch running — wait for it to finish."), "job_id": active.id})
    job_id = jobs_db.submit(db, batch.JOB_KIND,
                            {"user_id": user.id, "rows": rows, "lang": reqlang.cur_lang(),
                             "title": body.title, "run_created": True},
                            label=f"Thẩm định {len(rows)} thửa")
    # Tạo bản ghi NGAY: kết quả ghi dần vào đây sau mỗi thửa (chạy tiếp được).
    db.add(BatchRun(id=job_id, user_id=user.id, title=body.title[:200], n_rows=len(rows),
                    rows_json="[]", state="queued"))
    db.commit()
    return {"job_id": job_id, "rows": len(rows), "errors": errors,
            "max_rows": batch.max_rows(), "poll": f"/api/batch/{job_id}"}


@router.get("/api/batch")
def list_batches(user: User = Depends(auth.current_user),
                 db: Session = Depends(get_session)) -> dict:
    runs = db.execute(select(BatchRun).where(BatchRun.user_id == user.id,
                                             BatchRun.state == "done")
                      .order_by(BatchRun.created_at.desc()).limit(50)).scalars().all()
    active = _active_run(db, user.id)
    return {
        "max_rows": batch.max_rows(),
        "active": ({"id": active.id, "state": active.state, "progress": _progress(db, active)}
                   if active else None),
        "runs": [{"id": r.id, "title": r.title, "n_rows": r.n_rows,
                  "created_at": r.created_at.isoformat(timespec="seconds") + "Z",
                  "headline": json.loads(r.summary_json or "{}").get("headline")}
                 for r in runs],
    }


def _own_run(db: Session, run_id: str, user: User) -> BatchRun | None:
    r = db.get(BatchRun, run_id)
    return r if r is not None and r.user_id == user.id else None


@router.get("/api/batch/{run_id}")
def get_batch(run_id: str, user: User = Depends(auth.current_user),
              db: Session = Depends(get_session)) -> dict:
    """Xong → kết quả đầy đủ (bền). Đang chạy → tiến độ. Không phải của bạn → 404."""
    r = _own_run(db, run_id, user)
    if r is None:
        raise HTTPException(404, reqlang.tr("Không có lần thẩm định này.", "No such batch."))
    if r.state == "done":
        return {"id": r.id, "state": "done", "title": r.title,
                "created_at": r.created_at.isoformat(timespec="seconds") + "Z",
                "summary": json.loads(r.summary_json), "rows": json.loads(r.rows_json)}
    st = jobs_db.status(db, run_id) or {}
    return {"id": r.id, "state": r.state, "title": r.title, "progress": _progress(db, r),
            "error": st.get("error"), "message": st.get("message")}


@router.get("/api/batch/{run_id}/csv")
def batch_csv(run_id: str, user: User = Depends(auth.current_user),
              db: Session = Depends(get_session)) -> Response:
    r = _own_run(db, run_id, user)
    if r is None or r.state != "done":
        raise HTTPException(404, reqlang.tr("Không có lần thẩm định đã xong này.",
                                            "No finished batch with this ID."))
    return Response(batch.to_csv(json.loads(r.rows_json)), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="terratwin-tham-dinh-{r.id[:8]}.csv"'})


@router.delete("/api/batch/{run_id}", status_code=204)
def delete_batch(run_id: str, user: User = Depends(auth.current_user),
                 db: Session = Depends(get_session)) -> Response:
    r = _own_run(db, run_id, user)
    if r is None:
        raise HTTPException(404, reqlang.tr("Không có lần thẩm định này.", "No such batch."))
    db.delete(r)
    db.commit()
    return Response(status_code=204)
