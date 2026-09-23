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


# ---------- N1 — Xác thực email ----------

def test_dang_ky_moi_chua_xac_thuc(client):
    """Tài khoản MỚI phải bắt đầu email_verified=False — SMTP chưa cấu hình
    trong môi trường test nên _send_verification_email() tự bỏ qua êm, đăng ký
    vẫn phải thành công (201)."""
    tok = _register(client)
    me = client.get("/api/auth/me", headers=_hdr(tok)).json()
    assert me["email_verified"] is False


def test_xac_thuc_email_dung_token(client):
    from app.routes_account import _make_verify_token
    from app import db as dbmod

    tok = _register(client)
    with dbmod.SessionLocal() as s:
        uid = s.query(dbmod.User).filter_by(email="a@x.com").first().id
    verify_token = _make_verify_token(uid)

    r = client.post("/api/auth/verify-email", json={"token": verify_token})
    assert r.status_code == 200, r.text
    assert r.json()["already_verified"] is False

    me = client.get("/api/auth/me", headers=_hdr(tok)).json()
    assert me["email_verified"] is True

    # Xác thực lần hai — no-op vô hại, KHÔNG lỗi (khác hẳn token reset mật
    # khẩu, cố ý không cần cơ chế dùng-một-lần vì xác thực lại không nguy hiểm).
    r2 = client.post("/api/auth/verify-email", json={"token": verify_token})
    assert r2.status_code == 200
    assert r2.json()["already_verified"] is True


def test_token_xac_thuc_sai_bi_tu_choi(client):
    r = client.post("/api/auth/verify-email", json={"token": "rac-khong-hop-le"})
    assert r.status_code == 400


def test_token_dang_nhap_khong_xac_thuc_duoc_email(client):
    """Token đăng nhập thường (kind khác 'verify') không được lọt qua đây —
    cùng lớp lỗi đã bắt ở token một chạm (xem test_trust_loop.py)."""
    tok = _register(client)
    r = client.post("/api/auth/verify-email", json={"token": tok})
    assert r.status_code == 400


def test_resend_khi_chua_cau_hinh_smtp_bao_ro_khong_gui(client):
    tok = _register(client)
    r = client.post("/api/auth/resend-verification", headers=_hdr(tok))
    assert r.status_code == 200
    assert r.json()["sent"] is False


def test_resend_khi_da_xac_thuc_thi_khong_gui_lai(client):
    from app.routes_account import _make_verify_token
    from app import db as dbmod

    tok = _register(client)
    with dbmod.SessionLocal() as s:
        uid = s.query(dbmod.User).filter_by(email="a@x.com").first().id
    client.post("/api/auth/verify-email", json={"token": _make_verify_token(uid)})

    r = client.post("/api/auth/resend-verification", headers=_hdr(tok))
    assert r.json()["sent"] is False
    assert "đã được xác thực" in r.json()["message"]


def test_radar_khong_gui_canh_bao_ra_ngoai_khi_chua_xac_thuc(client, monkeypatch):
    """Cốt lõi của N1: cảnh báo vẫn được TẠO (user thấy trong app) nhưng
    KHÔNG được DISPATCH ra kênh ngoài khi email chưa xác thực — một tài khoản
    gõ sai email hoặc tạo hàng loạt không được phép spam hộ TerraTwin."""
    from app import db as dbmod
    from app.db import NotifyChannel, Plot
    from app.schemas import Location, ScanModule, ScanResult, TerraScoreResult
    from app.services import radar, scan as scan_svc

    # Mô phỏng một lượt quét LUÔN có đúng 1 cảnh báo thật — không chạm mạng,
    # và giữ đúng cốt lõi đang kiểm: dispatch có bị chặn hay không.
    fake_alert = ScanModule(
        id="flood", name="Lũ", icon="🌊", group="B", risk_level="danger",
        headline="Test", recommendation="Test", is_real=True)

    def fake_scan(loc, include_heavy=False):
        ts = TerraScoreResult(location=loc, score=50, grade="C", summary="test")
        return ScanResult(location=loc, terrascore=ts, modules=[fake_alert],
                          alerts=[fake_alert], real_data_ratio=1.0,
                          generated_at="2026-01-01T00:00:00")

    monkeypatch.setattr(scan_svc, "scan", fake_scan)
    from app.services import notify
    monkeypatch.setattr(notify, "send_webhook", lambda url, payload: None)  # None = gửi thành công, không chạm mạng

    tok = _register(client)
    with dbmod.SessionLocal() as s:
        u = s.query(dbmod.User).filter_by(email="a@x.com").first()
        assert bool(u.email_verified) is False
        s.add(Plot(user_id=u.id, name="Ruong", lat=BEN_TRE["lat"], lon=BEN_TRE["lon"]))
        s.add(NotifyChannel(user_id=u.id, kind="webhook",
                            target="https://example.com/hook", enabled=1))
        s.commit()
        uid = u.id

    with dbmod.SessionLocal() as s:
        r = radar.sweep_user(uid, s)
    assert r["new_alerts"] == 1, "cảnh báo vẫn phải được tạo và lưu"
    # Không xác thực → channels rỗng → dispatch không gửi/thử tới đâu cả.
    assert r["delivery"]["sent"] == 0 and r["delivery"]["failed"] == 0

    with dbmod.SessionLocal() as s:
        u = s.query(dbmod.User).filter_by(email="a@x.com").first()
        u.email_verified = 1
        s.commit()
        s.execute(dbmod.Alert.__table__.delete())   # xoá bản ghi cũ để dedup 12h không nuốt lượt sau
        s.commit()

    with dbmod.SessionLocal() as s:
        r2 = radar.sweep_user(uid, s)
    # Đã xác thực → channel webhook được THỬ (và ở đây giả lập thành công).
    assert r2["delivery"]["sent"] == 1


def test_tai_khoan_cu_duoc_grandfather_khi_them_cot(tmp_path):
    """Tài khoản đã tồn tại TRƯỚC khi cột email_verified ra đời không được
    đột ngột mất quyền nhận cảnh báo vì một yêu cầu MỚI thêm — _ensure_columns()
    phải tự backfill email_verified=1 cho họ, ĐÚNG MỘT LẦN lúc thêm cột."""
    from sqlalchemy import create_engine, text

    from app import db as dbmod

    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    # Bảng users kiểu CŨ — dựng tay, KHÔNG có cột email_verified (mô phỏng
    # database đã chạy production trước khi tính năng này ra đời).
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY, email VARCHAR(255) UNIQUE,
                password_hash VARCHAR(255), name VARCHAR(120) DEFAULT '',
                role VARCHAR(16) DEFAULT 'user', morning_brief INTEGER DEFAULT 0,
                brief_last VARCHAR(10) DEFAULT '', created_at TIMESTAMP
            )
        """))
        conn.execute(text(
            "INSERT INTO users (email, password_hash, name, created_at) "
            "VALUES ('cu@x.com', 'x', 'Cu', '2020-01-01')"))

    original_engine = dbmod.engine
    dbmod.engine = engine
    try:
        dbmod._ensure_columns()
        with engine.begin() as conn:
            row = conn.execute(text(
                "SELECT email_verified FROM users WHERE email='cu@x.com'")).fetchone()
        assert row[0] == 1, "tài khoản cũ phải được grandfather thành đã xác thực"
    finally:
        dbmod.engine = original_engine


# ---------- N8 — đồng ý tách mục đích ----------

def test_mac_dinh_dong_y_canh_bao_va_quan_sat_tat_nghien_cuu(client):
    """Mặc định: nhận cảnh báo BẬT, góp quan sát BẬT (đây là hành vi vốn có,
    không được đổi hành vi người dùng cũ khi thêm tính năng), nghiên cứu TẮT
    (đây là mục đích MỚI, không nghiễm nhiên đồng ý cho ai)."""
    tok = _register(client)
    me = client.get("/api/auth/me", headers=_hdr(tok)).json()
    assert me["consent_alerts"] is True
    assert me["consent_observations"] is True
    assert me["consent_research"] is False


def test_doi_dong_y_tung_muc_rieng(client):
    tok = _register(client)
    r = client.put("/api/account/consent", json={"consent_research": True}, headers=_hdr(tok))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["consent_research"] is True
    # Không gửi consent_alerts/consent_observations → không đổi giá trị đang có.
    assert body["consent_alerts"] is True
    assert body["consent_observations"] is True

    r2 = client.put("/api/account/consent", json={"consent_alerts": False}, headers=_hdr(tok))
    assert r2.json()["consent_alerts"] is False
    assert r2.json()["consent_research"] is True, "đổi mục này không được xoá mục đã đổi trước đó"


def test_can_dang_nhap_moi_doi_duoc_dong_y(client):
    r = client.put("/api/account/consent", json={"consent_alerts": False})
    assert r.status_code == 401


def test_radar_khong_gui_canh_bao_khi_tat_consent_alerts(client, monkeypatch):
    """Cốt lõi N8: đã xác thực email NHƯNG tắt 'nhận cảnh báo' → vẫn không
    dispatch ra kênh ngoài, dù channels đã cấu hình sẵn."""
    from app import db as dbmod
    from app.db import NotifyChannel, Plot
    from app.schemas import Location, ScanModule, ScanResult, TerraScoreResult
    from app.services import notify, radar
    from app.services import scan as scan_svc

    fake_alert = ScanModule(
        id="flood", name="Lũ", icon="🌊", group="B", risk_level="danger",
        headline="Test", recommendation="Test", is_real=True)

    def fake_scan(loc, include_heavy=False):
        ts = TerraScoreResult(location=loc, score=50, grade="C", summary="test")
        return ScanResult(location=loc, terrascore=ts, modules=[fake_alert],
                          alerts=[fake_alert], real_data_ratio=1.0,
                          generated_at="2026-01-01T00:00:00")

    monkeypatch.setattr(scan_svc, "scan", fake_scan)
    monkeypatch.setattr(notify, "send_webhook", lambda url, payload: None)

    tok = _register(client)
    with dbmod.SessionLocal() as s:
        u = s.query(dbmod.User).filter_by(email="a@x.com").first()
        u.email_verified = 1
        u.consent_alerts = 0
        s.add(Plot(user_id=u.id, name="Ruong", lat=BEN_TRE["lat"], lon=BEN_TRE["lon"]))
        s.add(NotifyChannel(user_id=u.id, kind="webhook",
                            target="https://example.com/hook", enabled=1))
        s.commit()
        uid = u.id

    with dbmod.SessionLocal() as s:
        r = radar.sweep_user(uid, s)
    assert r["new_alerts"] == 1, "cảnh báo vẫn phải được tạo và lưu dù tắt gửi ra ngoài"
    assert r["delivery"]["sent"] == 0 and r["delivery"]["failed"] == 0


def test_radar_khong_hoi_gop_quan_sat_khi_tat_consent_observations(client, monkeypatch):
    """Tắt riêng 'góp quan sát' không được ảnh hưởng việc gửi cảnh báo — hai
    mục đích độc lập với nhau."""
    from app import db as dbmod
    from app.db import NotifyChannel, Plot
    from app.schemas import Location, ScanModule, ScanResult, TerraScoreResult
    from app.services import notify, radar
    from app.services import scan as scan_svc

    fake_alert = ScanModule(
        id="flood", name="Lũ", icon="🌊", group="B", risk_level="danger",
        headline="Test", recommendation="Test", is_real=True)

    def fake_scan(loc, include_heavy=False):
        ts = TerraScoreResult(location=loc, score=50, grade="C", summary="test")
        return ScanResult(location=loc, terrascore=ts, modules=[fake_alert],
                          alerts=[fake_alert], real_data_ratio=1.0,
                          generated_at="2026-01-01T00:00:00")

    monkeypatch.setattr(scan_svc, "scan", fake_scan)
    monkeypatch.setattr(notify, "send_webhook", lambda url, payload: None)

    tok = _register(client)
    with dbmod.SessionLocal() as s:
        u = s.query(dbmod.User).filter_by(email="a@x.com").first()
        u.email_verified = 1
        u.consent_observations = 0
        s.add(Plot(user_id=u.id, name="Ruong", lat=BEN_TRE["lat"], lon=BEN_TRE["lon"]))
        s.add(NotifyChannel(user_id=u.id, kind="webhook",
                            target="https://example.com/hook", enabled=1))
        s.commit()
        uid = u.id

    with dbmod.SessionLocal() as s:
        r = radar.sweep_user(uid, s)
    assert r["delivery"]["sent"] == 1, "cảnh báo vẫn gửi bình thường"
    assert r["asked"]["asked"] == 0
    assert r["asked"].get("reason") == "người dùng đã tắt góp quan sát"


# ---------- M5 — đóng góp trên trang cá nhân ----------

def test_contribution_bat_dau_bang_khong(client):
    tok = _register(client)
    r = client.get("/api/account/contribution", headers=_hdr(tok))
    assert r.status_code == 200
    body = r.json()
    assert body == {"observations_contributed": 0, "alerts_verified": 0, "alerts_hit": 0}


def test_contribution_dem_dung_quan_sat_va_canh_bao_da_xac_minh(client):
    from app import db as dbmod
    from app.db import Alert, Observation, Plot

    tok = _register(client)
    # Quan sát của NGƯỜI KHÁC không được tính vào của mình — tạo và commit TRƯỚC,
    # đóng session lại hẳn rồi mới mở session thứ hai (SQLite chỉ cho MỘT giao
    # dịch ghi mở cùng lúc trên cùng file — hai session ghi chồng lên nhau sẽ
    # "database is locked").
    _register(client, email="b@x.com")
    with dbmod.SessionLocal() as s2:
        ob = s2.query(dbmod.User).filter_by(email="b@x.com").first()
        s2.add(Observation(user_id=ob.id, plot_id=None, lat=1.0, lon=1.0,
                           module_id="flood", observed_on="2026-01-01", outcome="occurred"))
        s2.commit()

    with dbmod.SessionLocal() as s:
        u = s.query(dbmod.User).filter_by(email="a@x.com").first()
        p = Plot(user_id=u.id, name="Ruong", lat=BEN_TRE["lat"], lon=BEN_TRE["lon"])
        s.add(p)
        s.flush()
        # Hai quan sát của CHÍNH người này.
        s.add(Observation(user_id=u.id, plot_id=p.id, lat=p.lat, lon=p.lon,
                          module_id="flood", observed_on="2026-01-01", outcome="occurred"))
        s.add(Observation(user_id=u.id, plot_id=p.id, lat=p.lat, lon=p.lon,
                          module_id="flood", observed_on="2026-01-05", outcome="none"))
        # Ba cảnh báo: hai đã chấm (một hit, một miss), một CHƯA tới hạn chấm.
        s.add(Alert(user_id=u.id, plot_id=p.id, module_id="flood", risk_level="danger",
                    headline="x", outcome="hit"))
        s.add(Alert(user_id=u.id, plot_id=p.id, module_id="flood", risk_level="warning",
                    headline="x", outcome="miss"))
        s.add(Alert(user_id=u.id, plot_id=p.id, module_id="flood", risk_level="warning",
                    headline="x", outcome=None))
        s.commit()

    r = client.get("/api/account/contribution", headers=_hdr(tok))
    body = r.json()
    assert body["observations_contributed"] == 2
    assert body["alerts_verified"] == 2
    assert body["alerts_hit"] == 1


def test_contribution_can_dang_nhap(client):
    assert client.get("/api/account/contribution").status_code == 401
