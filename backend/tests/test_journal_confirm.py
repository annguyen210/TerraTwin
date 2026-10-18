"""Nhật ký thửa ghi câu xác nhận từng đợt nước của chính chủ thửa (18/10/2026)."""
from __future__ import annotations

from datetime import datetime, timedelta


def test_xac_nhan_dot_nuoc_vao_nhat_ky_dung_thua():
    from app.db import Plot, SessionLocal, User, WaterConfirm
    from app.services import plot_journal
    with SessionLocal() as db:
        u = User(email="nk-xn@nong.vn", password_hash="x", name="N")
        db.add(u)
        db.commit()
        p = Plot(user_id=u.id, name="Ruộng", lat=16.5751, lon=107.4952)
        db.add(p)
        db.commit()
        db.add(WaterConfirm(user_id=u.id, lat=16.5751, lon=107.4952, cell="16.575,107.495", event_start="2020-10-10", answer="yes"))
        db.add(WaterConfirm(user_id=u.id, lat=16.5751, lon=107.4952, cell="16.575,107.495", event_start="2021-10-17", answer="unsure"))
        db.add(WaterConfirm(user_id=u.id, lat=10.0, lon=106.0, cell="10.000,106.000", event_start="2022-01-01", answer="no"))  # thửa khác
        db.commit()
        ev = [e for e in plot_journal._db_events(db, u.id, p, datetime.utcnow() - timedelta(days=1)) if e["kind"] == "water_confirm"]
    assert {e["event_start"] for e in ev} == {"2020-10-10", "2021-10-17"}
    yes = next(e for e in ev if e["event_start"] == "2020-10-10")
    assert yes["significant"] is True and "có ngập" in yes["text"]
    assert next(e for e in ev if e["event_start"] == "2021-10-17")["significant"] is False      # "không rõ" chỉ là bối cảnh
