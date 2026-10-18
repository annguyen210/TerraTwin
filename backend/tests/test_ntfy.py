"""Kênh ntfy (18/10/2026): đẩy cảnh báo về điện thoại miễn phí, không tài khoản; chủ đề công khai nên bắt tên khó đoán."""
from __future__ import annotations


def test_ten_chu_de_phai_dai_kho_doan():
    from app.services import notify
    assert notify.ntfy_url("ruongcuatoi")[1]                                  # quá ngắn → lỗi
    url, err = notify.ntfy_url("tt-a8f3c9e1b2d4f6a7")
    assert err is None and url == "https://ntfy.sh/tt-a8f3c9e1b2d4f6a7"
    assert notify.ntfy_url("http://ntfy.sh/tt-a8f3c9e1b2d4f6a7")[1]           # không https
    assert notify.ntfy_url("tt a8f3c9e1b2d4f6a7 x")[1]                         # ký tự lạ


def test_gui_dung_tieu_de_va_noi_dung(monkeypatch):
    from app.services import notify
    seen = {}

    class R:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake(req, timeout=None):
        seen["url"], seen["body"], seen["method"] = req.full_url, req.data.decode("utf-8"), req.get_method()
        return R()
    monkeypatch.setattr(notify.urllib.request, "urlopen", fake)
    assert notify.send_ntfy("tt-a8f3c9e1b2d4f6a7", "Cảnh báo lũ — Huế", "Mưa lớn", click="https://x.vn/so-diem", priority=5) is None
    assert seen["method"] == "POST" and seen["body"] == "Mưa lớn" and "priority=5" in seen["url"]
    assert "title=C%E1%BA%A3nh+b%C3%A1o" in seen["url"] and "click=https" in seen["url"]


def test_tao_kenh_ntfy_qua_api():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        tok = c.post("/api/auth/register", json={"email": "ntfy-1@nong.vn", "password": "MatKhau123", "name": "N"}).json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        assert c.post("/api/channels", json={"kind": "ntfy", "target": "ngan"}, headers=h).status_code == 422
        r = c.post("/api/channels", json={"kind": "ntfy", "target": "tt-a8f3c9e1b2d4f6a7"}, headers=h)
        assert r.status_code == 201 and r.json()["kind"] == "ntfy"
        assert c.get("/api/channels/status").json()["ready"]["ntfy"] is True
