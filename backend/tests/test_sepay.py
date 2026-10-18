"""SePay (18/10/2026): đúng khoá + đúng mã TT<số> + đủ tiền → tự cấp gói; gửi lại không cấp hai lần; sai/thiếu → không cấp."""
from __future__ import annotations

KEY = "khoa-thu-sepay-123456"


def test_doc_ma_yeu_cau_trong_noi_dung():
    from app.services import sepay
    assert sepay.request_id("TT12 PRO") == 12
    assert sepay.request_id("MBVCB.3312.TT12PRO.CT tu 0123 toi 456") == 12
    assert sepay.request_id("tt007 pro") == 7
    assert sepay.request_id("chuyen tien an trua") is None


def test_khoa(monkeypatch):
    from app.services import sepay
    monkeypatch.delenv("TERRATWIN_SEPAY_API_KEY", raising=False)
    assert not sepay.authorized(f"Apikey {KEY}")          # chưa đặt khoá → không bao giờ mở cửa
    monkeypatch.setenv("TERRATWIN_SEPAY_API_KEY", KEY)
    assert sepay.authorized(f"Apikey {KEY}") and not sepay.authorized("Apikey sai") and not sepay.authorized(KEY)


def test_webhook_cap_goi_mot_lan(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    monkeypatch.setenv("TERRATWIN_SEPAY_API_KEY", KEY)
    with TestClient(app) as c:
        tok = c.post("/api/auth/register", json={"email": "sepay-1@nong.vn", "password": "MatKhau123", "name": "N"}).json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        req = c.post("/api/account/upgrade-request", json={"plan_wanted": "pro"}, headers=h).json()
        assert req["payment"]["memo"] == f"TT{req['id']} PRO"
        good = {"id": 900001, "transferType": "in", "transferAmount": 299000, "content": f"MBVCB.1.TT{req['id']}PRO.CT", "referenceCode": "FT1"}
        sk = {"Authorization": f"Apikey {KEY}"}

        assert c.post("/api/payments/sepay", json=good).status_code == 401                       # thiếu khoá
        assert c.post("/api/payments/sepay", json=good, headers={"Authorization": "Apikey sai"}).status_code == 401
        short = {**good, "id": 900002, "transferAmount": 100000}
        assert c.post("/api/payments/sepay", json=short, headers=sk).json()["status"] == "underpaid"
        assert c.get("/api/account/plan", headers=h).json()["plan"] == "free"                    # thiếu tiền → chưa cấp

        assert c.post("/api/payments/sepay", json=good, headers=sk).json()["status"] == "matched"
        me = c.get("/api/account/plan", headers=h).json()
        assert me["plan"] == "pro" and me["requests"][0]["status"] == "approved"
        assert c.post("/api/payments/sepay", json=good, headers=sk).json().get("duplicate") is True  # SePay gửi lại

        again = {**good, "id": 900003}                                                           # chuyển lần hai cùng mã
        assert c.post("/api/payments/sepay", json=again, headers=sk).json()["status"] == "unmatched"
        out = {**good, "id": 900004, "transferType": "out"}
        assert c.post("/api/payments/sepay", json=out, headers=sk).json()["status"] == "ignored"


def test_chua_dat_khoa_thi_tat(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    monkeypatch.delenv("TERRATWIN_SEPAY_API_KEY", raising=False)
    with TestClient(app) as c:
        assert c.post("/api/payments/sepay", json={"id": 1}, headers={"Authorization": "Apikey x"}).status_code == 503
