"""Kiểm 18/11/2026 trên production (tài khoản ann953201): /hom-nay hiện HAI dòng "Chấm cảnh báo «Cảnh báo hạn & thiếu nước»
ngày 2026-11-09: BỎ SÓT" — CSDL có hai hàng hồi cứu cho cùng một lần bỏ sót (hai lượt quét chạy cùng lúc). Nhật ký chỉ hiện
một dòng, và sổ điểm chỉ đếm một lần bỏ sót."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import db as dbmod
from app.db import Alert, Plot, User


@pytest.fixture()
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path/'t.db'}", connect_args={"check_same_thread": False})
    dbmod.Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    yield s
    s.close()


def _hai_hang_bo_sot(db):
    u = User(email="a@example.com", password_hash="x")
    db.add(u); db.commit()
    p = Plot(user_id=u.id, name="Ruộng thử", lat=10.0, lon=106.0, created_at=datetime(2026, 10, 1))
    db.add(p); db.commit()
    day = datetime(2026, 11, 9)
    for _ in range(2):                                       # đúng như production: hai hàng giống nhau
        db.add(Alert(user_id=u.id, plot_id=p.id, module_id="drought", risk_level="danger", headline="[HỒI CỨU] x",
                     recommendation="", created_at=day, acknowledged=1, outcome="miss", verified_at=day + timedelta(days=5),
                     verify_source="data", observed_peak=80.0, window_days=1, retro=1))
    db.commit()
    return u, p


def test_nhat_ky_chi_hien_mot_dong(db):
    from app.services import plot_journal, reqlang
    reqlang.set_lang("vi")
    u, p = _hai_hang_bo_sot(db)
    ev = [e for e in plot_journal._db_events(db, u.id, p, datetime(2026, 11, 1)) if e["kind"] == "graded"]
    assert len(ev) == 1 and "BỎ SÓT" in ev[0]["text"] and "drought" not in ev[0]["text"]


def test_so_diem_dem_mot_lan_bo_sot(db):
    from app.services import scorecard
    _hai_hang_bo_sot(db)
    c = scorecard._deduped_counts(db, datetime(2026, 11, 1), env=None)
    assert c["miss"] == 1
