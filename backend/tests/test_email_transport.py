"""27/10/2026 — Render gói miễn phí chặn cổng SMTP, nên email đi qua API HTTPS (Brevo/Resend) khi có khoá.

Và /api/health không được báo "✅" chỉ vì đã đặt biến: lần gửi gần nhất hỏng thì phải báo hỏng.
"""
from __future__ import annotations

import io
import json
import urllib.error

import pytest
from fastapi.testclient import TestClient

from app.services import notify

_KEYS = ("TERRATWIN_BREVO_API_KEY", "TERRATWIN_RESEND_API_KEY", "TERRATWIN_SMTP_HOST",
         "TERRATWIN_SMTP_USER", "TERRATWIN_SMTP_FROM", "TERRATWIN_EMAIL_FROM")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in _KEYS:
        monkeypatch.delenv(k, raising=False)
    notify._LAST_SEND.clear()
    notify._SMTP_PROBE.clear()
    yield
    notify._LAST_SEND.clear()
    notify._SMTP_PROBE.clear()


class _Resp:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _capture(monkeypatch):
    sent = []

    def fake(req, timeout=None):
        sent.append({"url": req.full_url, "headers": {k.lower(): v for k, v in req.header_items()},
                     "body": json.loads(req.data.decode("utf-8"))})
        return _Resp()
    monkeypatch.setattr(notify.urllib.request, "urlopen", fake)
    return sent


def test_brevo_duoc_uu_tien_hon_smtp(monkeypatch):
    monkeypatch.setenv("TERRATWIN_SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("TERRATWIN_BREVO_API_KEY", "k-brevo")
    monkeypatch.setenv("TERRATWIN_EMAIL_FROM", "TerraTwin <a@b.vn>")
    monkeypatch.setattr(notify.smtplib, "SMTP", lambda *a, **k: pytest.fail("không được đi SMTP"))
    sent = _capture(monkeypatch)
    assert notify.email_transport() == "brevo"
    assert notify.send_email("u@x.vn", "Tiêu đề", "Nội dung có dấu") is None
    (s,) = sent
    assert s["url"] == notify.BREVO_API and s["headers"]["api-key"] == "k-brevo"
    assert s["body"]["sender"] == {"email": "a@b.vn", "name": "TerraTwin"}
    assert s["body"]["to"] == [{"email": "u@x.vn"}] and s["body"]["textContent"] == "Nội dung có dấu"
    assert notify.email_last_send()["error"] is None


def test_resend_mac_dinh_gui_tu_onboarding(monkeypatch):
    monkeypatch.setenv("TERRATWIN_RESEND_API_KEY", "k-resend")
    monkeypatch.setenv("TERRATWIN_SMTP_USER", "x@gmail.com")   # gmail không gửi được qua Resend — không được lấy làm From
    sent = _capture(monkeypatch)
    assert notify.send_email("u@x.vn", "s", "b") is None
    assert sent[0]["headers"]["authorization"] == "Bearer k-resend"
    assert sent[0]["body"]["from"] == "TerraTwin <onboarding@resend.dev>"


def test_api_tu_choi_thi_bao_ma_va_ly_do(monkeypatch):
    monkeypatch.setenv("TERRATWIN_BREVO_API_KEY", "sai")

    def fake(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {},
                                     io.BytesIO(b'{"message":"Key not found"}'))
    monkeypatch.setattr(notify.urllib.request, "urlopen", fake)
    err = notify.send_email("u@x.vn", "s", "b")
    assert err == "Brevo trả mã 401: Key not found"
    assert notify.email_last_send()["error"] == err


def test_smtp_bi_chan_cong_thi_goi_y_api(monkeypatch):
    monkeypatch.setenv("TERRATWIN_SMTP_HOST", "smtp.gmail.com")

    def blocked(*a, **k):
        raise OSError(101, "Network is unreachable")
    monkeypatch.setattr(notify.smtplib, "SMTP", blocked)
    err = notify.send_email("u@x.vn", "s", "b")
    assert err.startswith("SMTP lỗi: OSError") and "TERRATWIN_BREVO_API_KEY" in err


def test_chua_cau_hinh_thi_bao_ro():
    assert notify.email_transport() is None and notify.smtp_configured() is False
    assert "Chưa cấu hình gửi email" in notify.send_email("u@x.vn", "s", "b")


def test_health_bao_hong_khi_lan_gui_gan_nhat_loi(monkeypatch):
    from app.main import app
    monkeypatch.setenv("TERRATWIN_SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setattr(notify.smtplib, "SMTP", lambda *a, **k: (_ for _ in ()).throw(OSError("blocked")))
    monkeypatch.setattr(notify, "smtp_probe", lambda: None)      # cổng mở được — chỉ kiểm phần "lần gửi gần nhất"
    c = TestClient(app)
    e = c.get("/api/health").json()["email"]
    assert e["smtp_configured"] and e["email_verification_works"] and e["transport"] == "smtp"
    notify.send_email("u@x.vn", "s", "b")
    e = c.get("/api/health").json()["email"]
    assert e["smtp_configured"] is True and e["email_verification_works"] is False
    assert e["forgot_password_works"] is False and "HỎNG" in e["message"]
    # Đổi sang Brevo: lỗi cũ thuộc đường SMTP, không được làm đường mới bị báo hỏng.
    monkeypatch.setenv("TERRATWIN_BREVO_API_KEY", "k")
    e = c.get("/api/health").json()["email"]
    assert e["transport"] == "brevo" and e["email_verification_works"] is True


def test_health_thu_cong_smtp_ngay_ca_khi_chua_gui_lan_nao(monkeypatch):
    """Render khởi động lại là mất lần gửi gần nhất — không thử cổng thì health báo ✅ tới tận lần gửi hỏng đầu tiên."""
    from app.main import app
    monkeypatch.setenv("TERRATWIN_SMTP_HOST", "smtp.gmail.com")
    calls = []

    def blocked(addr, timeout=None):
        calls.append(addr)
        raise TimeoutError("timed out")
    monkeypatch.setattr(notify.socket, "create_connection", blocked)
    c = TestClient(app)
    e = c.get("/api/health").json()["email"]
    assert e["email_verification_works"] is False and e["last_send"] is None
    assert "TERRATWIN_BREVO_API_KEY" in e["message"] and calls == [("smtp.gmail.com", 587)]
    c.get("/api/health")
    assert len(calls) == 1          # có hạn dùng lại — health không mở cổng mỗi lần bị gọi
    monkeypatch.setenv("TERRATWIN_BREVO_API_KEY", "k")   # đi HTTPS thì không thử cổng SMTP
    assert c.get("/api/health").json()["email"]["email_verification_works"] is True and len(calls) == 1
