"""Đ10 — hàng đợi việc dài BỀN (bảng jobs), thay hàng đợi trong bộ nhớ.

Test trên SQLite (nhánh không-SKIP-LOCKED của claim_next()) — xem docstring
jobs_db.py cho lý do SQLite không cần SKIP LOCKED để đúng ở quy mô một tiến
trình. Không test được thật sự "hai worker Postgres giành nhau" trong bộ test
offline này; test tập trung vào HỢP ĐỒNG: submit→claim→run→status đúng vòng
đời, registry đúng, và một job đã 'running' không bị claim lại.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import db as dbmod
from app.services import jobs_db


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path/'jobs.db'}",
                           connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    dbmod.Base.metadata.create_all(engine)
    s = Session()
    yield s
    s.close()


@pytest.fixture
def clean_registry():
    """_HANDLERS là biến MODULE-LEVEL, dùng chung cho cả tiến trình (kể cả
    genome_warm đăng ký thật trong main.py) — snapshot/khôi phục để test
    không rò rỉ handler giả sang test khác chạy sau."""
    saved = dict(jobs_db._HANDLERS)
    yield
    jobs_db._HANDLERS.clear()
    jobs_db._HANDLERS.update(saved)


def test_submit_tao_job_trang_thai_queued(session):
    job_id = jobs_db.submit(session, "echo", {"msg": "xin chao"}, "test job")
    job = session.get(dbmod.Job, job_id)
    assert job is not None
    assert job.state == "queued"
    assert job.label == "test job"


def test_claim_next_lay_dung_job_cu_nhat_truoc(session):
    id1 = jobs_db.submit(session, "echo", {"n": 1})
    id2 = jobs_db.submit(session, "echo", {"n": 2})
    claimed = jobs_db.claim_next(session)
    assert claimed.id == id1          # cũ nhất (created_at nhỏ nhất) trước
    assert claimed.state == "running"

    # Job thứ hai vẫn 'queued' — chưa bị giành.
    job2 = session.get(dbmod.Job, id2)
    assert job2.state == "queued"


def test_claim_next_bo_qua_job_dang_running(session):
    """Cốt lõi của Đ10: một job đã 'running' (một worker khác đã giành) thì
    claim_next() KHÔNG được trả lại nó lần nữa."""
    job_id = jobs_db.submit(session, "echo", {})
    first = jobs_db.claim_next(session)
    assert first.id == job_id

    second = jobs_db.claim_next(session)
    assert second is None, "job đã 'running' không được giành lại lần hai"


def test_claim_next_tra_none_khi_hang_doi_rong(session):
    assert jobs_db.claim_next(session) is None


def test_run_claimed_ghi_ket_qua_khi_thanh_cong(session, clean_registry):
    @jobs_db.register("double")
    def _double(args: dict) -> dict:
        return {"result": args["n"] * 2}

    job_id = jobs_db.submit(session, "double", {"n": 21})
    job = jobs_db.claim_next(session)
    jobs_db.run_claimed(session, job)

    st = jobs_db.status(session, job_id)
    assert st["state"] == "done"
    assert st["result"] == {"result": 42}


def test_run_claimed_ghi_loi_khi_handler_nem_ngoai_le(session, clean_registry):
    @jobs_db.register("boom")
    def _boom(args: dict):
        raise ValueError("co y hong de test")

    job_id = jobs_db.submit(session, "boom", {})
    job = jobs_db.claim_next(session)
    jobs_db.run_claimed(session, job)

    st = jobs_db.status(session, job_id)
    assert st["state"] == "error"
    assert st["error"] == "ValueError"
    assert "message" in st


def test_run_claimed_kind_chua_dang_ky_bao_loi_ro_rang(session):
    job_id = jobs_db.submit(session, "khong_ton_tai", {})
    job = jobs_db.claim_next(session)
    jobs_db.run_claimed(session, job)

    st = jobs_db.status(session, job_id)
    assert st["state"] == "error"
    assert st["error"] == "UnknownJobKind"


def test_poll_and_run_one_chay_het_mot_luot(session, clean_registry):
    calls = []

    @jobs_db.register("track")
    def _track(args: dict) -> dict:
        calls.append(args["i"])
        return {"ok": True}

    for i in range(3):
        jobs_db.submit(session, "track", {"i": i})

    ran = 0
    while jobs_db.poll_and_run_one(session):
        ran += 1
    assert ran == 3
    assert calls == [0, 1, 2]   # đúng thứ tự nộp (created_at tăng dần)


def test_status_tra_none_khi_khong_ton_tai(session):
    assert jobs_db.status(session, "khong-co-that") is None


def test_status_bao_dung_hinh_dang_cho_tung_trang_thai(session, clean_registry):
    @jobs_db.register("noop")
    def _noop(args: dict) -> dict:
        return {}

    qid = jobs_db.submit(session, "noop", {})
    st_queued = jobs_db.status(session, qid)
    assert st_queued["state"] == "queued"
    assert "result" not in st_queued
    assert "error" not in st_queued

    job = jobs_db.claim_next(session)
    jobs_db.run_claimed(session, job)
    st_done = jobs_db.status(session, qid)
    assert st_done["state"] == "done"
    assert st_done["result"] == {}


def test_prune_xoa_job_xong_qua_han_ttl(session, clean_registry, monkeypatch):
    @jobs_db.register("noop")
    def _noop(args: dict) -> dict:
        return {}

    job_id = jobs_db.submit(session, "noop", {})
    job = jobs_db.claim_next(session)
    jobs_db.run_claimed(session, job)

    # Giả lập job đã xong từ RẤT LÂU — quá TTL.
    j = session.get(dbmod.Job, job_id)
    j.finished_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=2)
    session.commit()

    monkeypatch.setattr(jobs_db, "JOB_TTL", 1800.0)   # 30 phút, job trên đã 2 giờ
    deleted = jobs_db.prune(session)
    assert deleted == 1
    assert session.get(dbmod.Job, job_id) is None


def test_prune_khong_dung_job_moi_xong(session, clean_registry):
    @jobs_db.register("noop")
    def _noop(args: dict) -> dict:
        return {}

    job_id = jobs_db.submit(session, "noop", {})
    job = jobs_db.claim_next(session)
    jobs_db.run_claimed(session, job)   # vừa xong — trong TTL

    deleted = jobs_db.prune(session)
    assert deleted == 0
    assert session.get(dbmod.Job, job_id) is not None


def test_prune_khong_dung_job_dang_cho_hoac_dang_chay(session):
    """queued/running không bao giờ bị prune() dọn — kể cả nếu tạo rất lâu
    trước đó (không có nghĩa là 'kẹt', có thể worker đang thật sự bận)."""
    job_id = jobs_db.submit(session, "echo", {})
    j = session.get(dbmod.Job, job_id)
    j.created_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)
    session.commit()

    deleted = jobs_db.prune(session)
    assert deleted == 0
    assert session.get(dbmod.Job, job_id) is not None
