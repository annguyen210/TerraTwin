"""Giai đoạn thử nghiệm (20/10/2026, theo chủ dự án): CHƯA chia gói — mặc định tắt thu tiền. Mọi tài khoản dùng đủ tính
năng; người dùng không thấy gói / nâng cấp / chuyển khoản; máy chủ không nhận yêu cầu nâng gói."""
from __future__ import annotations


def test_mac_dinh_tat_thu_tien(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services import plans
    monkeypatch.delenv("TERRATWIN_BILLING", raising=False)
    assert plans.billing_on() is False
    with TestClient(app) as c:
        tok = c.post("/api/auth/register", json={"email": "bill-off@nong.vn", "password": "MatKhau123", "name": "N"}).json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        me = c.get("/api/account/plan", headers=h).json()
        assert me["billing"] is False and me["limits"]["dossier_per_day"] > 0
        r = c.post("/api/account/upgrade-request", json={"plan_wanted": "pro"}, headers=h)
        assert r.status_code == 409 and "đủ mọi tính năng" in r.json()["detail"]
        assert c.get("/api/plans").json()["billing"] is False


def test_bat_lai_khi_can(monkeypatch):
    from app.services import plans
    monkeypatch.setenv("TERRATWIN_BILLING", "1")
    assert plans.billing_on() is True
