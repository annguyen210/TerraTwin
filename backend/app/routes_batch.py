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
from app.db import BatchRun, Job, User, get_session
from app.services import batch, jobs_db, reqlang

router = APIRouter(tags=["batch"])


class BatchIn(BaseModel):
    csv: str = Field(min_length=1, max_length=400_000)
    title: str = Field(default="", max_length=200)


def _active_job(db: Session, user_id: int) -> Job | None:
    for j in db.execute(select(Job).where(Job.kind == batch.JOB_KIND,
                                          Job.state.in_(("queued", "running")))).scalars():
        try:
            if json.loads(j.args_json or "{}").get("user_id") == user_id:
                return j
        except ValueError:
            continue
    return None


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
    active = _active_job(db, user.id)
    if active is not None:
        # Một lô một lúc cho mỗi tài khoản: mỗi thửa đã gọi nguồn dữ liệu miễn phí.
        raise HTTPException(409, {"message": reqlang.tr(
            "Bạn đang có một lô chưa chạy xong — đợi xong rồi gửi lô mới.",
            "You already have a batch running — wait for it to finish."), "job_id": active.id})
    job_id = jobs_db.submit(db, batch.JOB_KIND,
                            {"user_id": user.id, "rows": rows, "lang": reqlang.cur_lang(),
                             "title": body.title},
                            label=f"Thẩm định {len(rows)} thửa")
    return {"job_id": job_id, "rows": len(rows), "errors": errors,
            "poll": f"/api/batch/{job_id}"}


@router.get("/api/batch")
def list_batches(user: User = Depends(auth.current_user),
                 db: Session = Depends(get_session)) -> dict:
    runs = db.execute(select(BatchRun).where(BatchRun.user_id == user.id)
                      .order_by(BatchRun.created_at.desc()).limit(50)).scalars().all()
    active = _active_job(db, user.id)
    return {
        "active": jobs_db.status(db, active.id) if active else None,
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
    if r is not None:
        return {"id": r.id, "state": "done", "title": r.title,
                "created_at": r.created_at.isoformat(timespec="seconds") + "Z",
                "summary": json.loads(r.summary_json), "rows": json.loads(r.rows_json)}
    args = jobs_db.args_of(db, run_id)
    if args is None or args.get("user_id") != user.id:
        raise HTTPException(404, reqlang.tr("Không có lần thẩm định này.", "No such batch."))
    st = jobs_db.status(db, run_id) or {}
    return {"id": run_id, "state": st.get("state"), "progress": st.get("progress"),
            "error": st.get("error"), "message": st.get("message")}


@router.get("/api/batch/{run_id}/csv")
def batch_csv(run_id: str, user: User = Depends(auth.current_user),
              db: Session = Depends(get_session)) -> Response:
    r = _own_run(db, run_id, user)
    if r is None:
        raise HTTPException(404, reqlang.tr("Không có lần thẩm định này.", "No such batch."))
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
