"""Tài khoản, thửa đất, khóa API — gồm các ca BẢO MẬT.

Dùng database SQLite tạm trong thư mục test, không đụng dữ liệu thật.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BEN_TRE = {"lat": 10.19, "lon": 106.70}
GOOD_PW = "MatKhau123"


@pytest.fixture
def client(tmp_path, monkeypatch):
    """App với database riêng cho mỗi test."""
    from app import db as dbmod

    engine = create_engine(f"sqlite:///{tmp_path/'t.db'}",
                           connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    dbmod.Base.metadata.create_all(engine)
    monkeypatch.setattr(dbmod, "engine", engine)
    monkeypatch.setattr(dbmod, "SessionLocal", Session)

    from app.main import app

    def _session():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[dbmod.get_session] = _session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _register(c, email="a@x.com", pw=GOOD_PW):
    r = c.post("/api/auth/register", json={"email": email, "password": pw, "name": "A"})
    assert r.status_code == 201, r.text
    return r.json()["access_token"]


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


# ---------- Đăng ký / đăng nhập ----------

def test_register_then_login(client):
    tok = _register(client)
    assert tok
    r = client.post("/api/auth/login", json={"email": "a@x.com", "password": GOOD_PW})
    assert r.status_code == 200
    assert r.json()["user"]["email"] == "a@x.com"


def test_password_never_returned_or_stored_plaintext(client, tmp_path):
    from app import db as dbmod
    _register(client)
    with dbmod.SessionLocal() as s:
        u = s.query(dbmod.User).first()
    assert GOOD_PW not in u.password_hash
    assert u.password_hash.startswith("$2")          # bcrypt


def test_duplicate_email_rejected(client):
    _register(client)
    r = client.post("/api/auth/register",
                    json={"email": "a@x.com", "password": GOOD_PW, "name": "B"})
    assert r.status_code == 409


def test_weak_password_rejected(client):
    for pw in ("short1", "khongcoso", "12345678"):
        r = client.post("/api/auth/register",
                        json={"email": f"{pw}@x.com", "password": pw, "name": ""})
        assert r.status_code == 422, pw


def test_login_does_not_leak_which_email_exists(client):
    _register(client)
    wrong_pw = client.post("/api/auth/login",
                           json={"email": "a@x.com", "password": "SaiRoi123"})
    no_user = client.post("/api/auth/login",
                          json={"email": "khong@x.com", "password": "SaiRoi123"})
    assert wrong_pw.status_code == no_user.status_code == 401
    assert wrong_pw.json()["detail"] == no_user.json()["detail"]


def test_me_requires_auth(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer rac"}).status_code == 401


# ---------- Thửa đất ----------

def test_plot_crud(client):
    tok = _register(client)
    r = client.post("/api/plots", headers=_hdr(tok), json={
        "name": "Ruộng nhà", "location": {**BEN_TRE, "area_ha": 5},
        "score": 88, "grade": "A"})
    assert r.status_code == 201
    pid = r.json()["id"]

    rows = client.get("/api/plots", headers=_hdr(tok)).json()
    assert len(rows) == 1 and rows[0]["name"] == "Ruộng nhà"

    assert client.delete(f"/api/plots/{pid}", headers=_hdr(tok)).status_code == 204
    assert client.get("/api/plots", headers=_hdr(tok)).json() == []


def test_saving_same_coord_updates_instead_of_duplicating(client):
    tok = _register(client)
    body = {"name": "Lần 1", "location": BEN_TRE, "score": 70, "grade": "B"}
    client.post("/api/plots", headers=_hdr(tok), json=body)
    client.post("/api/plots", headers=_hdr(tok),
                json={**body, "name": "Lần 2", "score": 90, "grade": "A"})
    rows = client.get("/api/plots", headers=_hdr(tok)).json()
    assert len(rows) == 1 and rows[0]["name"] == "Lần 2" and rows[0]["score"] == 90


def test_plots_are_isolated_between_users(client):
    a = _register(client, "a@x.com")
    b = _register(client, "b@x.com")
    client.post("/api/plots", headers=_hdr(a),
                json={"name": "Của A", "location": BEN_TRE})
    assert client.get("/api/plots", headers=_hdr(b)).json() == []


def test_cannot_delete_other_users_plot(client):
    a = _register(client, "a@x.com")
    b = _register(client, "b@x.com")
    pid = client.post("/api/plots", headers=_hdr(a),
                      json={"name": "Của A", "location": BEN_TRE}).json()["id"]
    # 404 chứ không phải 403 — không xác nhận ID này có tồn tại.
    assert client.delete(f"/api/plots/{pid}", headers=_hdr(b)).status_code == 404
    assert len(client.get("/api/plots", headers=_hdr(a)).json()) == 1


def test_plot_rejects_coord_outside_vietnam(client):
    tok = _register(client)
    r = client.post("/api/plots", headers=_hdr(tok),
                    json={"name": "Ngoài VN", "location": {"lat": 48.85, "lon": 2.35}})
    assert r.status_code == 422


def test_plots_require_auth(client):
    assert client.get("/api/plots").status_code == 401
    assert client.post("/api/plots", json={"name": "x", "location": BEN_TRE}).status_code == 401


# ---------- Khóa Twin API (C12) ----------

def test_api_key_works_as_credential(client):
    tok = _register(client)
    created = client.post("/api/keys?label=tich-hop", headers=_hdr(tok)).json()
    raw = created["key"]
    assert raw.startswith("tt_")

    r = client.get("/api/auth/me", headers={"X-API-Key": raw})
    assert r.status_code == 200 and r.json()["email"] == "a@x.com"


def test_api_key_plaintext_only_shown_once(client):
    tok = _register(client)
    client.post("/api/keys", headers=_hdr(tok))
    listed = client.get("/api/keys", headers=_hdr(tok)).json()
    assert "key" not in listed[0]              # danh sách chỉ có prefix
    assert listed[0]["prefix"].startswith("tt_")


def test_api_key_stored_hashed_not_plaintext(client):
    from app import db as dbmod
    tok = _register(client)
    raw = client.post("/api/keys", headers=_hdr(tok)).json()["key"]
    with dbmod.SessionLocal() as s:
        row = s.query(dbmod.ApiKey).first()
    assert row.key_hash != raw and raw not in row.key_hash


def test_revoked_key_stops_working(client):
    tok = _register(client)
    created = client.post("/api/keys", headers=_hdr(tok)).json()
    raw, kid = created["key"], created["id"]
    assert client.get("/api/auth/me", headers={"X-API-Key": raw}).status_code == 200
    assert client.delete(f"/api/keys/{kid}", headers=_hdr(tok)).status_code == 204
    assert client.get("/api/auth/me", headers={"X-API-Key": raw}).status_code == 401


def test_bogus_api_key_rejected(client):
    assert client.get("/api/auth/me", headers={"X-API-Key": "tt_khonghople"}).status_code == 401


def test_cannot_revoke_other_users_key(client):
    a = _register(client, "a@x.com")
    b = _register(client, "b@x.com")
    kid = client.post("/api/keys", headers=_hdr(a)).json()["id"]
    assert client.delete(f"/api/keys/{kid}", headers=_hdr(b)).status_code == 404


# ---------- Băm mật khẩu ----------

def test_long_password_not_silently_truncated():
    """bcrypt bỏ byte thứ 73 trở đi — nếu không băm trước thì hai mật khẩu dài
    khác nhau sẽ đăng nhập lẫn được cho nhau."""
    from app import auth
    a = "x" * 100 + "AAA1"
    b = "x" * 100 + "BBB2"
    h = auth.hash_password(a)
    assert auth.verify_password(a, h)
    assert not auth.verify_password(b, h)


def test_same_password_different_hash():
    from app import auth
    assert auth.hash_password(GOOD_PW) != auth.hash_password(GOOD_PW)   # có salt
