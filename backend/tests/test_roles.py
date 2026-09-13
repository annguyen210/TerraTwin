"""Đ11 — phân quyền: MỌI route /api/admin/* chặn người không phải admin (403)."""
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
