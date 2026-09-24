"""Đ10 — hàng đợi việc dài BỀN qua database, thay hàng đợi trong bộ nhớ
(services/jobs.py). ƯU TIÊN THẤP NHẤT trong 18 việc — chỉ cần khi có nhiều
người dùng đồng thời VÀ nhiều tiến trình worker; hiện TerraTwin chạy một
instance, jobs.py trong RAM vẫn đủ dùng. Viết sẵn cho lúc cần.

KHÁC BIỆT GỐC RỄ với jobs.py: jobs.submit(kind, fn, label) nhận thẳng một
CLOSURE Python — không thể lưu xuống database (không tuần tự hoá được một
hàm + biến nó đóng gói). Ở đây bắt buộc phải có REGISTRY: mỗi `kind` đăng ký
TRƯỚC một hàm xử lý nhận `args: dict` (JSON-serializable) và trả về kết quả
cũng JSON-serializable — job lưu (kind, args), NGƯỜI XỬ LÝ tự tra registry ra
hàm bằng kind lúc chạy, không lưu bản thân hàm.

SELECT ... FOR UPDATE SKIP LOCKED (PostgreSQL) — nhiều worker cùng gọi
claim_next() không worker nào giành trúng việc worker khác vừa khoá, mỗi việc
chỉ chạy ĐÚNG MỘT LẦN dù có bao nhiêu worker đang chạy song song. SQLite
(dev/test) không có SKIP LOCKED (khoá ở mức FILE, không phải mức HÀNG) —
nhưng khoá mức file của SQLite lại cho tính đúng tương đương ở quy mô một
tiến trình: chỉ một writer tại một thời điểm nên không cần SKIP LOCKED để
tránh đụng độ, xem nhánh else trong claim_next().
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db import Job

JobHandler = Callable[[dict], object]

_HANDLERS: dict[str, JobHandler] = {}

JOB_TTL = 1800.0   # giữ kết quả 30 phút rồi dọn — cùng giá trị jobs.py cũ
MAX_JOBS = 500


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def register(kind: str):
    """Decorator: đăng ký hàm xử lý cho một loại việc.

    @jobs_db.register("genome_warm")
    def _handle(args: dict) -> dict: ...
    """
    def deco(fn: JobHandler) -> JobHandler:
        _HANDLERS[kind] = fn
        return fn
    return deco


def submit(db: Session, kind: str, args: dict | None = None, label: str = "") -> str:
    """Đẩy một việc mới vào hàng đợi BỀN. Trả mã để hỏi lại kết quả sau."""
    job_id = uuid.uuid4().hex[:16]
    db.add(Job(id=job_id, kind=kind, label=label,
              args_json=json.dumps(args or {}), state="queued"))
    db.commit()
    return job_id


def claim_next(db: Session) -> Job | None:
    """Giành lấy MỘT việc đang 'queued', đánh dấu 'running', trả về nó.

    An toàn khi NHIỀU worker gọi đồng thời — xem docstring module. None nếu
    hàng đợi rỗng."""
    dialect = db.bind.dialect.name if db.bind is not None else ""

    if dialect == "postgresql":
        row = db.execute(text(
            "SELECT id FROM jobs WHERE state = 'queued' "
            "ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED"
        )).first()
        if row is None:
            return None
        job = db.get(Job, row[0])
    else:
        job = db.execute(
            select(Job).where(Job.state == "queued")
            .order_by(Job.created_at).limit(1)
        ).scalar_one_or_none()

    if job is None:
        return None
    job.state = "running"
    job.started_at = _utcnow()
    db.commit()
    db.refresh(job)
    return job


def run_claimed(db: Session, job: Job) -> None:
    """Chạy hàm đã đăng ký cho job.kind, ghi kết quả/lỗi. Job PHẢI đã ở trạng
    thái 'running' (từ claim_next()) — gọi trực tiếp trên một job 'queued' là
    bỏ qua bước khoá, không an toàn khi có nhiều worker."""
    handler = _HANDLERS.get(job.kind)
    if handler is None:
        job.state = "error"
        job.error = "UnknownJobKind"
        job.finished_at = _utcnow()
        db.commit()
        return

    try:
        args = json.loads(job.args_json or "{}")
        result = handler(args)
        job.state = "done"
        job.result_json = json.dumps(result)
        job.finished_at = _utcnow()
    except Exception as e:
        import traceback
        traceback.print_exc()   # chi tiết vào log máy chủ, không lộ ra người dùng
        job.state = "error"
        job.error = type(e).__name__
        job.finished_at = _utcnow()
    db.commit()


def poll_and_run_one(db: Session) -> bool:
    """Giành một việc (nếu có) và chạy nó NGAY trong luồng gọi. Trả True nếu
    có việc để chạy — dùng làm nhịp cho vòng lặp worker nền (xem main.py)."""
    job = claim_next(db)
    if job is None:
        return False
    run_claimed(db, job)
    return True


def status(db: Session, job_id: str) -> dict | None:
    """Trạng thái một việc — cùng hình dạng trả về với jobs.status() cũ để
    /api/jobs/{id} không phải đổi hợp đồng khi chuyển sang bảng bền."""
    job = db.get(Job, job_id)
    if job is None:
        return None
    now = time.time()
    started = job.started_at.replace(tzinfo=timezone.utc).timestamp() if job.started_at else None
    created = job.created_at.replace(tzinfo=timezone.utc).timestamp() if job.created_at else now
    finished = job.finished_at.replace(tzinfo=timezone.utc).timestamp() if job.finished_at else None

    out = {
        "id": job.id, "kind": job.kind, "label": job.label, "state": job.state,
        "queued_s": round((started or now) - created, 1),
        "elapsed_s": round((finished or now) - (started or now), 1),
    }
    if job.state == "done":
        out["result"] = json.loads(job.result_json) if job.result_json else None
    elif job.state == "error":
        out["error"] = job.error
        out["message"] = ("Việc chạy nền gặp lỗi. Thử lại; nếu vẫn hỏng thì "
                          "nhiều khả năng nguồn dữ liệu ngoài đang không phản hồi.")
    return out


def stats(db: Session) -> dict:
    """Số việc theo trạng thái trong hàng đợi BỀN — để /api/jobs báo đúng, vì
    jobs.py (bể việc cũ) giờ luôn báo rỗng cho những kind đã chuyển sang đây."""
    rows = db.execute(select(Job.state)).scalars().all()
    by: dict[str, int] = {}
    for s in rows:
        by[s] = by.get(s, 0) + 1
    return {"jobs_tracked": len(rows), "by_state": by,
           "registered_kinds": sorted(_HANDLERS.keys())}


def prune(db: Session) -> int:
    """Dọn việc đã xong (done/error) quá hạn TTL, hoặc vượt trần MAX_JOBS
    (xoá cũ nhất trước). Trả số hàng đã xoá."""
    # _utcnow() trả naive datetime — .timestamp() trên naive datetime hiểu
    # ngầm là GIỜ ĐỊA PHƯƠNG, không phải UTC (bẫy kinh điển của Python). Phải
    # gắn tzinfo=utc TRƯỚC khi gọi .timestamp(), khớp cách tính finished_ts
    # bên dưới — nếu không, máy ở múi giờ UTC+7 sẽ dọn sai lệch 7 giờ.
    cutoff = _utcnow().replace(tzinfo=timezone.utc).timestamp() - JOB_TTL
    old = db.execute(
        select(Job).where(Job.state.in_(("done", "error")))
    ).scalars().all()
    deleted = 0
    keep = []
    for j in old:
        finished_ts = j.finished_at.replace(tzinfo=timezone.utc).timestamp() if j.finished_at else 0
        if finished_ts < cutoff:
            db.delete(j)
            deleted += 1
        else:
            keep.append(j)

    total = db.execute(select(Job)).scalars().all()
    if len(total) - deleted > MAX_JOBS:
        finished_sorted = sorted(
            (j for j in keep), key=lambda j: j.created_at)
        overflow = (len(total) - deleted) - MAX_JOBS
        for j in finished_sorted[:overflow]:
            db.delete(j)
            deleted += 1

    if deleted:
        db.commit()
    return deleted
