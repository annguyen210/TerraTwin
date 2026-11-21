"""Kiểm A–Z 21/11/2026, P1-4: /api/landcover và /api/landchange trả "chưa có data/landcover.onnx" — đọc như quên chép tệp,
trong khi mô hình U-Net đã huấn luyện và TRƯỢT ngưỡng đặt trước (mIoU 0,314 < 0,35), cố ý không bật. Giao diện không gọi
hai đường này; câu trả lời của API phải nói đúng và chỉ sang loại đất AlphaEarth (đã đạt)."""
from fastapi.testclient import TestClient

from app.main import app


def test_trang_thai_noi_truot_nguong_khong_phai_quen_tep():
    with TestClient(app) as c:
        s = c.get("/api/landcover").json()
    assert s["available"] is False and s["state"] == "trained_below_threshold"
    assert not any("chưa có data/landcover.onnx" in m for m in s["missing"])
    assert any("trượt ngưỡng" in m and "cố ý không đưa" in m for m in s["missing"])
    assert s["alternative"]["endpoint"] == "/api/landcover/change"


def test_landchange_chi_sang_duong_thay_the(monkeypatch):
    with TestClient(app) as c:
        r = c.post("/api/landchange?lang=vi", json={"lat": 20.9716, "lon": 106.2834}).json()
    assert r["available"] is False and r["use_instead"] == "/api/landcover/change"
    assert "AlphaEarth" in r["use_instead_note"] and r["state"] == "trained_below_threshold"
