"""GĐ7 — xác thực hai lớp TOTP: đúng RFC 6238, chống dùng lại mã, mã khôi phục một lần, chặn dò mã,
quản trị bắt buộc 2FA khi bật cờ, không lộ bí mật khi xuất dữ liệu."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PW = "MatKhau123"


def test_vector_rfc6238_sha1():
    from app.services import totp
    sec = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"            # "12345678901234567890"
    assert totp.code_at(sec, 59 // 30, digits=8) == "94287082"
    assert totp.code_at(sec, 1111111109 // 30, digits=8) == "07081804"
    assert totp.code_at(sec, 1234567890 // 30, digits=8) == "89005924"
    assert totp.code_at(sec, 2000000000 // 30, digits=8) == "69279037"


def test_chong_dung_lai_va_lech_dong_ho():
    from app.services import totp
    sec = totp.new_secret()
    t = 1_790_000_000
    c = totp.code_at(sec, totp.now_step(t))
    st = totp.verify(sec, c, None, t=t)
    assert st == totp.now_step(t)
    assert totp.verify(sec, c, st, t=t) is None                       # cùng mã lần hai → từ chối
    assert totp.verify(sec, totp.code_at(sec, totp.now_step(t) - 1), None, t=t) is not None   # lệch 30 giây
    assert totp.verify(sec, totp.code_at(sec, totp.now_step(t) - 3), None, t=t) is None       # quá cũ


def test_bi_mat_ma_hoa_khi_luu():
    from app.services import totp
    sec = totp.new_secret()
    blob = totp.seal(sec)
    assert sec not in blob and totp.unseal(blob) == sec


@pytest.fixture
def c(tmp_path, monkeypatch):
    from app import db as dbmod
    from app.services import quota
    engine = create_engine(f"sqlite:///{tmp_path/'a.db'}", connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    dbmod.Base.metadata.create_all(engine)
    monkeypatch.setattr(dbmod, "engine", engine)
    monkeypatch.setattr(dbmod, "SessionLocal", Session)
    monkeypatch.setenv("TERRATWIN_ADMIN_EMAILS", "quantri@vd.vn")
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
        yield cl
    app.dependency_overrides.clear()
    quota.reset()


def _reg(c, email):
    r = c.post("/api/auth/register", json={"email": email, "password": PW, "name": "N"})
    assert r.status_code in (200, 201), r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _enable(c, h):
    from app.services import totp
    s = c.post("/api/auth/2fa/setup", headers=h).json()
    assert s["otpauth_uri"].startswith("otpauth://totp/TerraTwin") and s["qr"].startswith("data:image/svg")
    assert c.post("/api/auth/2fa/enable", headers=h, json={"code": "000000"}).status_code in (200, 422)
    st = totp.now_step()
    r = c.post("/api/auth/2fa/enable", headers=h, json={"code": totp.code_at(s["secret"], st)})
    assert r.status_code == 200, r.text
    return s["secret"], st, r.json()["recovery_codes"]


def test_luong_bat_dang_nhap_khoi_phuc_tat(c):
    from app.services import quota, totp
    h = _reg(c, "a@vd.vn")
    sec, st, rec = _enable(c, h)
    quota.reset()
    assert len(rec) == 8 and c.get("/api/auth/me", headers=h).json()["totp_enabled"] is True

    r = c.post("/api/auth/login", json={"email": "a@vd.vn", "password": PW})
    assert r.status_code == 401 and r.headers.get("x-otp-required") == "1"
    r = c.post("/api/auth/login", json={"email": "a@vd.vn", "password": PW, "otp": totp.code_at(sec, st)})
    assert r.status_code == 401                                       # mã vừa dùng để bật → không dùng lại
    r = c.post("/api/auth/login", json={"email": "a@vd.vn", "password": PW, "otp": totp.code_at(sec, st + 1)})
    assert r.status_code == 200, r.text

    r = c.post("/api/auth/login", json={"email": "a@vd.vn", "password": PW, "otp": rec[0]})
    assert r.status_code == 200                                        # mã khôi phục
    r = c.post("/api/auth/login", json={"email": "a@vd.vn", "password": PW, "otp": rec[0]})
    assert r.status_code == 401                                        # dùng một lần

    exp = c.get("/api/account/export", headers=h).json()
    assert "totp" not in str(exp.get("account")) and sec not in str(exp)

    quota.reset()
    assert c.post("/api/auth/2fa/disable", headers=h, json={"password": "sai-mat-khau", "code": rec[1]}).status_code == 401
    assert c.post("/api/auth/2fa/disable", headers=h, json={"password": PW, "code": rec[1]}).json()["enabled"] is False
    assert c.post("/api/auth/login", json={"email": "a@vd.vn", "password": PW}).status_code == 200


def test_do_ma_bi_chan_sau_5_lan(c):
    from app.services import quota
    h = _reg(c, "b@vd.vn")
    _enable(c, h)
    quota.reset()
    codes = [c.post("/api/auth/login", json={"email": "b@vd.vn", "password": PW, "otp": f"{i:06d}"}).status_code
             for i in range(6)]
    assert codes[:5] == [401] * 5 and codes[5] == 429


def test_quan_tri_bat_buoc_hai_lop_khi_bat_co(c, monkeypatch):
    from app.services import quota
    h = _reg(c, "quantri@vd.vn")
    assert c.get("/api/admin/funnel", headers=h).status_code == 200
    monkeypatch.setenv("TERRATWIN_ADMIN_REQUIRE_2FA", "1")
    r = c.get("/api/admin/funnel", headers=h)
    assert r.status_code == 403 and "hai lớp" in r.json()["detail"]
    _enable(c, h)
    quota.reset()
    assert c.get("/api/admin/funnel", headers=h).status_code == 200


def test_khong_co_khoa_may_chu_co_dinh_thi_tu_choi_bat(c, monkeypatch):
    h = _reg(c, "d@vd.vn")
    monkeypatch.delenv("TERRATWIN_SECRET", raising=False)
    r = c.post("/api/auth/2fa/setup", headers=h)
    assert r.status_code == 503 and "TERRATWIN_SECRET" in r.json()["detail"]
