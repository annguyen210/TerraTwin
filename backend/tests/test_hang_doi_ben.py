"""Nâng cấp 25/11/2026 — hàng đợi việc dài BỀN: restart không để việc nào kẹt 'running'.

Trước đây lúc khởi động chỉ lô thẩm định/EUDR được xếp lại; việc radar, lịch sử nước dở dang (Render free ngủ, deploy,
hết RAM) nằm 'running' mãi và trang cứ hỏi tiến độ."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, Job
from app.services import jobs_db


@pytest.fixture
def Session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path/'j.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def test_viec_do_duoc_xep_lai_hoac_bao_loi(Session):
    with Session() as s:
        ids = {k: jobs_db.submit(s, k, {"x": 1}) for k in ("water_history", "radar_sweep_all", "eudr_screen")}
        done = jobs_db.submit(s, "water_history", {})
        for jid in [*ids.values(), done]:
            s.get(Job, jid).state = "running"
        s.get(Job, done).state = "done"                         # việc đã xong không bị đụng
        queued = jobs_db.submit(s, "radar_run", {})             # việc đang chờ không bị đụng
        s.commit()
        n = jobs_db.recover_orphans(s, ("water_history", "eudr_screen", "radar_run"))
        assert n == {"resumed": 2, "failed": 1}
        st = {k: s.get(Job, j).state for k, j in ids.items()}
        assert st == {"water_history": "queued", "radar_sweep_all": "error", "eudr_screen": "queued"}
        assert s.get(Job, ids["radar_sweep_all"]).error == "Restarted"
        assert s.get(Job, ids["water_history"]).started_at is None
        assert s.get(Job, done).state == "done" and s.get(Job, queued).state == "queued"
        assert jobs_db.recover_orphans(s, ("water_history",)) == {"resumed": 0, "failed": 0}   # chạy lại: không đổi gì


def test_viec_xep_lai_duoc_worker_chay_tiep(Session):
    ran = []

    @jobs_db.register("thu_hang_doi_ben")
    def _h(args):
        ran.append(args["n"])
        return {"ok": True}

    with Session() as s:
        jid = jobs_db.submit(s, "thu_hang_doi_ben", {"n": 7})
        s.get(Job, jid).state = "running"                       # tiến trình cũ chết giữa chừng
        s.commit()
        jobs_db.recover_orphans(s, ("thu_hang_doi_ben",))
        assert jobs_db.poll_and_run_one(s) is True
        assert ran == [7] and s.get(Job, jid).state == "done"


def test_bao_loi_restart_bang_loi_thuong(Session):
    from app.services import reqlang
    reqlang.set_lang("vi")
    with Session() as s:
        jid = jobs_db.submit(s, "radar_sweep_all", {})
        s.get(Job, jid).state = "running"
        s.commit()
        jobs_db.recover_orphans(s, ())
        st = jobs_db.status(s, jid)
        assert st["state"] == "error" and "khởi động lại" in st["message"]
