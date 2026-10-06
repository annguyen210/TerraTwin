"""Phiếu góp ý thí điểm: gửi không cần đăng nhập, ít dữ liệu cá nhân, chỉ admin xem tổng hợp."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

PW = "MatKhau123"
OK = {"role": "farmer", "ease": 4, "trust": 5, "would_use": "yes", "hardest": "boundary",
      "minutes": 12, "region": "Krông Năng, Đắk Lắk", "comment": "Đi bộ quanh vườn dễ"}


@pytest.fixture
def c(tmp_path, monkeypatch):
    from app import db as dbmod
    from app.services import quota
    engine = create_engine(f"sqlite:///{tmp_path/'pilot.db'}", connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    dbmod.Base.metadata.create_all(engine)
    monkeypatch.setattr(dbmod, "engine", engine)
    monkeypatch.setattr(dbmod, "SessionLocal", Session)
    quota.reset()
    from app.main import app

    def _session():
        s = Session()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[dbmod.get_session] = _session
    with TestClient(app) as cl:
        cl.Session = Session
        yield cl
    app.dependency_overrides.clear()


def _login(c, email, admin=False):
    c.post("/api/auth/register", json={"email": email, "password": PW, "name": "N"})
    if admin:
        from app.db import User
        s = c.Session()
        u = s.execute(select(User).where(User.email == email)).scalar_one()
        u.role = "admin"
        s.commit()
        s.close()
    tok = c.post("/api/auth/login", json={"email": email, "password": PW}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def test_gui_phieu_khong_can_dang_nhap_va_khong_luu_ip(c):
    r = c.post("/api/pilot/feedback", json=OK)
    assert r.status_code == 200, r.text
    from app.db import PilotFeedback
    s = c.Session()
    row = s.execute(select(PilotFeedback)).scalar_one()
    s.close()
    assert row.role == "farmer" and row.ease == 4 and row.minutes == 12 and row.user_id is None
    assert row.contact == ""
    cols = {col.name for col in PilotFeedback.__table__.columns}
    assert not cols & {"ip", "client_ip", "user_agent"}


@pytest.mark.parametrize("bad", [
    {"ease": 0}, {"ease": 6}, {"trust": 9}, {"role": "hacker"}, {"would_use": "chac"},
    {"minutes": -1}, {"minutes": 601}, {"comment": "x" * 2001}, {"hardest": "tat-ca"},
])
def test_gia_tri_ngoai_khoang_bi_tu_choi(c, bad):
    assert c.post("/api/pilot/feedback", json={**OK, **bad}).status_code == 422


def test_co_lien_he_ma_khong_dong_y_thi_tu_choi_ca_phieu(c):
    r = c.post("/api/pilot/feedback", json={**OK, "contact": "0912 345 678"})
    assert r.status_code == 422 and "đồng ý" in r.json()["detail"]
    r = c.post("/api/pilot/feedback", json={**OK, "contact": "0912 345 678", "consent_contact": True})
    assert r.status_code == 200


def test_nhap_phieu_giay_can_dang_nhap(c):
    assert c.post("/api/pilot/feedback", json={**OK, "source": "paper"}).status_code == 401
    h = _login(c, "canbo@htx.vn")
    assert c.post("/api/pilot/feedback", json={**OK, "source": "paper"}, headers=h).status_code == 200


def test_an_danh_bi_gioi_han_so_phieu_moi_ngay(c):
    codes = [c.post("/api/pilot/feedback", json=OK).status_code for _ in range(11)]
    assert codes[:10] == [200] * 10 and codes[10] == 429


def test_tong_hop_chi_admin_xem_va_so_lieu_dung(c):
    c.post("/api/pilot/feedback", json=OK)
    c.post("/api/pilot/feedback", json={**OK, "role": "exporter", "ease": 2, "trust": 3,
                                         "would_use": "maybe", "minutes": None, "hardest": "lot"})
    assert c.get("/api/admin/pilot/feedback").status_code == 401
    assert c.get("/api/admin/pilot/feedback", headers=_login(c, "thuong@vd.vn")).status_code == 403
    r = c.get("/api/admin/pilot/feedback", headers=_login(c, "admin@vd.vn", admin=True)).json()
    assert r["all"]["n"] == 2 and r["all"]["ease_mean"] == 3.0
    assert r["all"]["minutes_median"] == 12          # phiếu không ghi phút không bị tính là 0
    assert r["by_role"]["exporter"]["would_use"] == {"yes": 0, "maybe": 1, "no": 0}
    assert r["all"]["hardest"]["lot"] == 1 and r["note"]   # n < 30 → có cảnh báo


def test_csv_chan_chen_cong_thuc_excel(c):
    c.post("/api/pilot/feedback", json={**OK, "comment": "=HYPERLINK(\"http://x\")"})
    h = _login(c, "admin2@vd.vn", admin=True)
    r = c.get("/api/admin/pilot/feedback.csv", headers=h)
    assert r.status_code == 200 and "text/csv" in r.headers["content-type"]
    assert "'=HYPERLINK" in r.text and ",=HYPERLINK" not in r.text


def test_xoa_tai_khoan_xoa_gop_y_cua_minh_giu_phieu_giay_nhap_ho(c):
    from app.db import PilotFeedback
    h = _login(c, "canbo2@htx.vn")
    c.post("/api/pilot/feedback", json=OK, headers=h)
    c.post("/api/pilot/feedback", json={**OK, "source": "paper"}, headers=h)
    exp = c.get("/api/account/export", headers=h).json()
    assert len(exp["pilot_feedback"]) == 2
    assert c.delete("/api/account", headers=h).status_code == 204
    s = c.Session()
    rows = s.execute(select(PilotFeedback)).scalars().all()
    s.close()
    assert [(r.source, r.user_id) for r in rows] == [("paper", None)]
