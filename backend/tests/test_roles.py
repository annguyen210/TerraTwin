"""Đ11 — phân quyền: MỌI route /api/admin/* chặn người không phải admin (403)."""
import os

from fastapi.testclient import TestClient

from app.main import app
from app.db import SessionLocal, User
from sqlalchemy import select

# Mọi route quản trị phải được gác. Giữ danh sách ở đây để thêm route admin mới
# mà quên gác thì test này đỏ.
ADMIN_GET = ["/api/admin/funnel", "/api/admin/drift", "/api/admin/backup-status"]


def _login(c, email, role="user"):
    c.post("/api/auth/register", json={"email": email, "password": "Passw0rd1", "name": "X"})
    if role != "user":
        db = SessionLocal()
        try:
            u = db.execute(select(User).where(User.email == email)).scalar_one()
            u.role = role; db.commit()
        finally:
            db.close()
    return c.post("/api/auth/login", json={"email": email, "password": "Passw0rd1"}).json()["access_token"]


def test_admin_routes_401_without_login():
    with TestClient(app) as c:
        for path in ADMIN_GET:
            assert c.get(path).status_code == 401, path


def test_admin_routes_403_for_normal_user():
    with TestClient(app) as c:
        tok = _login(c, "role_user@x.com", "user")
        for path in ADMIN_GET:
            assert c.get(path, headers={"Authorization": f"Bearer {tok}"}).status_code == 403, path


def test_admin_routes_ok_for_admin():
    with TestClient(app) as c:
        tok = _login(c, "role_admin@x.com", "admin")
        for path in ADMIN_GET:
            # backup-status có thể 200 dù chưa cấu hình sao lưu; điều cần là KHÔNG 403.
            assert c.get(path, headers={"Authorization": f"Bearer {tok}"}).status_code == 200, path


def test_coop_is_not_admin():
    with TestClient(app) as c:
        tok = _login(c, "role_coop@x.com", "coop")
        assert c.get("/api/admin/drift", headers={"Authorization": f"Bearer {tok}"}).status_code == 403


# ---------- Đ11 — /api/coop/plots ----------

def test_coop_plots_401_khong_dang_nhap():
    with TestClient(app) as c:
        assert c.get("/api/coop/plots").status_code == 401


def test_coop_plots_403_cho_user_thuong():
    with TestClient(app) as c:
        tok = _login(c, "coop_user1@x.com", "user")
        assert c.get("/api/coop/plots", headers={"Authorization": f"Bearer {tok}"}).status_code == 403


def test_coop_plots_ok_cho_admin_va_coop():
    with TestClient(app) as c:
        for email, role in [("coop_admin1@x.com", "admin"), ("coop_role1@x.com", "coop")]:
            tok = _login(c, email, role)
            assert c.get("/api/coop/plots", headers={"Authorization": f"Bearer {tok}"}).status_code == 200


def test_coop_thay_ma_khong_tu_dong_lo_thua():
    """Cốt lõi Đ11: đặt coop_code không tự động chia sẻ — phải bật riêng
    share_with_coop. Thửa của thành viên CHƯA bật share_with_coop không được
    lọt vào danh sách, dù cùng mã nhóm."""
    from app.db import Plot, SessionLocal, User
    from sqlalchemy import select

    with TestClient(app) as c:
        # Thành viên A: cùng mã nhóm, CHƯA bật chia sẻ.
        c.post("/api/auth/register", json={"email": "coop_a@x.com", "password": "Passw0rd1", "name": "A"})
        tok_a = c.post("/api/auth/login", json={"email": "coop_a@x.com", "password": "Passw0rd1"}).json()["access_token"]
        c.put("/api/account/coop", json={"coop_code": "HTX01", "share_with_coop": False},
              headers={"Authorization": f"Bearer {tok_a}"})

        with SessionLocal() as db:
            ua = db.execute(select(User).where(User.email == "coop_a@x.com")).scalar_one()
            db.add(Plot(user_id=ua.id, name="Ruong A", lat=10.0, lon=106.0))
            db.commit()

        # Người xem vai trò coop, CÙNG mã nhóm.
        tok_viewer = _login(c, "coop_viewer@x.com", "coop")
        with SessionLocal() as db:
            uv = db.execute(select(User).where(User.email == "coop_viewer@x.com")).scalar_one()
            uv.coop_code = "HTX01"
            db.commit()

        r = c.get("/api/coop/plots", headers={"Authorization": f"Bearer {tok_viewer}"})
        assert r.status_code == 200
        body = r.json()
        assert body["members"] == 0, "A chưa bật share_with_coop — không được tính là thành viên lộ thửa"
        assert body["plots"] == []

        # A bật chia sẻ → giờ mới thấy.
        c.put("/api/account/coop", json={"share_with_coop": True},
              headers={"Authorization": f"Bearer {tok_a}"})
        r2 = c.get("/api/coop/plots", headers={"Authorization": f"Bearer {tok_viewer}"})
        body2 = r2.json()
        assert body2["members"] == 1
        assert len(body2["plots"]) == 1
        assert body2["plots"][0]["name"] == "Ruong A"


def test_coop_khac_ma_khong_thay_nhau():
    from app.db import Plot, SessionLocal, User
    from sqlalchemy import select

    with TestClient(app) as c:
        c.post("/api/auth/register", json={"email": "coop_b@x.com", "password": "Passw0rd1", "name": "B"})
        tok_b = c.post("/api/auth/login", json={"email": "coop_b@x.com", "password": "Passw0rd1"}).json()["access_token"]
        c.put("/api/account/coop", json={"coop_code": "HTX-KHAC", "share_with_coop": True},
              headers={"Authorization": f"Bearer {tok_b}"})
        with SessionLocal() as db:
            ub = db.execute(select(User).where(User.email == "coop_b@x.com")).scalar_one()
            db.add(Plot(user_id=ub.id, name="Ruong B", lat=11.0, lon=107.0))
            db.commit()

        tok_viewer = _login(c, "coop_viewer2@x.com", "coop")
        with SessionLocal() as db:
            uv = db.execute(select(User).where(User.email == "coop_viewer2@x.com")).scalar_one()
            uv.coop_code = "HTX-TOI"
            db.commit()

        r = c.get("/api/coop/plots", headers={"Authorization": f"Bearer {tok_viewer}"})
        assert r.json()["members"] == 0, "mã nhóm khác nhau — không được thấy thửa của nhau"


def test_backup_status_nhan_dien_ban_da_ma_hoa_gpg(tmp_path, monkeypatch):
    """Đ11 — sửa lỗi: ops/backup.sh (N2) ghi *.sql.gz.gpg khi có passphrase, nhưng
    backup_status() trước đây chỉ glob *.sql.gz trần nên luôn báo sai 'chưa có
    bản sao lưu nào' trên prod (nơi LUÔN có passphrase). Test này giữ lỗi khỏi
    tái diễn."""
    daily = tmp_path / "daily"
    daily.mkdir()
    (daily / "terratwin-20260101-000000.sql.gz.gpg").write_bytes(b"gia lap ban ma hoa")
    monkeypatch.setenv("TERRATWIN_BACKUP_DIR", tmp_path.as_posix())

    with TestClient(app) as c:
        tok = _login(c, "backup_admin@x.com", "admin")
        r = c.get("/api/admin/backup-status", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200
        body = r.json()
        assert body["configured"] is True, "bản .sql.gz.gpg phải được nhận diện là đã có sao lưu"
        assert body["count"] == 1


# ---------- Sửa sau kiểm toán #2 — TERRATWIN_ADMIN_EMAILS ----------
#
# Trước đây role="admin" CHỈ gán được bằng cách sửa thẳng database — không có
# đường cấp quyền nào qua phần mềm, nghĩa là /admin vừa dựng không ai vào
# được. Bốn test dưới đây khoá đúng hành vi mới.

def test_dang_ky_bang_email_trong_danh_sach_tu_dong_thanh_admin(monkeypatch):
    monkeypatch.setenv("TERRATWIN_ADMIN_EMAILS", "chu@x.com, khac@x.com")
    with TestClient(app) as c:
        r = c.post("/api/auth/register",
                   json={"email": "Chu@X.com", "password": "Passw0rd1", "name": "Chu"})
        assert r.status_code == 201
        assert r.json()["user"]["role"] == "admin", (
            "email trong TERRATWIN_ADMIN_EMAILS phải tự thành admin lúc đăng ký "
            "(khớp không phân biệt hoa/thường)")


def test_dang_ky_email_ngoai_danh_sach_van_la_user(monkeypatch):
    monkeypatch.setenv("TERRATWIN_ADMIN_EMAILS", "chu@x.com")
    with TestClient(app) as c:
        r = c.post("/api/auth/register",
                   json={"email": "nguoi_thuong@x.com", "password": "Passw0rd1", "name": "X"})
        assert r.status_code == 201
        assert r.json()["user"]["role"] == "user"


def test_dang_ky_khong_dat_bien_moi_truong_van_403(monkeypatch):
    """Không đặt TERRATWIN_ADMIN_EMAILS (trường hợp mặc định) — không ai được
    tự thăng admin, mọi route /api/admin/* vẫn 403 cho user thường."""
    monkeypatch.delenv("TERRATWIN_ADMIN_EMAILS", raising=False)
    with TestClient(app) as c:
        tok = _login(c, "ai_do@x.com", "user")
        for path in ADMIN_GET:
            assert c.get(path, headers={"Authorization": f"Bearer {tok}"}).status_code == 403, path


def test_tai_khoan_cu_duoc_nang_admin_khi_dang_nhap_sau_khi_them_vao_danh_sach(monkeypatch):
    """Tài khoản đã tồn tại TRƯỚC khi email được thêm vào danh sách — vẫn phải
    được nâng lên admin, không chỉ email ĐĂNG KÝ MỚI mới có hiệu lực."""
    monkeypatch.delenv("TERRATWIN_ADMIN_EMAILS", raising=False)
    with TestClient(app) as c:
        r = c.post("/api/auth/register",
                   json={"email": "sau_nay_len_admin@x.com", "password": "Passw0rd1", "name": "X"})
        assert r.json()["user"]["role"] == "user"

        monkeypatch.setenv("TERRATWIN_ADMIN_EMAILS", "sau_nay_len_admin@x.com")
        r2 = c.post("/api/auth/login",
                    json={"email": "sau_nay_len_admin@x.com", "password": "Passw0rd1"})
        assert r2.json()["user"]["role"] == "admin"

        tok = r2.json()["access_token"]
        assert c.get("/api/admin/drift", headers={"Authorization": f"Bearer {tok}"}).status_code == 200


def test_rut_khoi_danh_sach_khong_tu_dong_ha_quyen(monkeypatch):
    """Gỡ email khỏi TERRATWIN_ADMIN_EMAILS KHÔNG được tự động hạ quyền một
    admin đã có — hạ quyền phải là việc chủ động (sửa database), không phải
    tác dụng phụ của một lần gõ nhầm biến môi trường."""
    monkeypatch.setenv("TERRATWIN_ADMIN_EMAILS", "van_con_admin@x.com")
    with TestClient(app) as c:
        c.post("/api/auth/register",
              json={"email": "van_con_admin@x.com", "password": "Passw0rd1", "name": "X"})

        monkeypatch.delenv("TERRATWIN_ADMIN_EMAILS", raising=False)
        r = c.post("/api/auth/login",
                   json={"email": "van_con_admin@x.com", "password": "Passw0rd1"})
        assert r.json()["user"]["role"] == "admin", (
            "rút khỏi danh sách không được tự động hạ quyền admin đã cấp")
