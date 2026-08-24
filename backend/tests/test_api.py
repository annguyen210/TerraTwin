"""Smoke test API qua TestClient. Ép offline (patch nguồn mạng) để nhanh & ổn định."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import realdata


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    # Ép mọi nguồn mạng trả None → chạy nhánh fallback, không phụ thuộc Internet.
    monkeypatch.setattr(realdata, "weather_7d", lambda la, lo: None)
    monkeypatch.setattr(realdata, "elevation_m", lambda la, lo: None)
    monkeypatch.setattr(realdata, "solar_annual", lambda la, lo: None)
    monkeypatch.setattr(realdata, "slope_deg", lambda la, lo, **k: None)
    monkeypatch.setattr(realdata, "historical_weather", lambda la, lo, s, e: None)


client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    # KHÔNG ghim con số: thêm ngành là phải sửa test, và người sửa dễ chỉnh
    # con số cho xanh lại mà không kiểm gì. Ghim bất biến thay vì con số.
    assert r.status_code == 200 and r.json()["modules"] >= 14


def test_modules_list():
    r = client.get("/api/modules")
    assert r.status_code == 200 and len(r.json()) >= 14


@pytest.mark.parametrize("body", [
    {"lat": 999, "lon": 9999},
    {"lat": 0, "lon": -160},
    {"lat": 10, "lon": 106, "area_ha": -5},
])
def test_validation_422(body):
    assert client.post("/api/terrascore", json=body).status_code == 422


def test_assess_valid_vn():
    r = client.post("/api/assess/flood", json={"lat": 10.03, "lon": 105.78})
    assert r.status_code == 200
    assert r.json()["module_id"] == "flood"


def test_scan_structure():
    r = client.post("/api/scan", json={"lat": 10.03, "lon": 105.78})
    assert r.status_code == 200
    d = r.json()
    # Quét toàn cảnh bỏ qua mô-đun NẶNG (quét cả vùng, ~10 giây). Số mô-đun
    # trong kết quả = tổng trừ đi số đã bỏ qua, và phần bỏ qua phải khai báo.
    total = len(client.get("/api/modules").json())
    # Lượt quét nhanh trả về ĐỦ mọi mục. Mục nặng (cần ảnh vệ tinh) có mặt với
    # trạng thái "pending" thay vì biến mất — bỏ hẳn chúng làm màn hình từ 18
    # mục còn 11, trông trống hơn hẳn, trong khi sự thật là chúng đang chạy chứ
    # không phải không có. "Chưa xong" và "không có" là hai chuyện khác nhau.
    assert len(d["modules"]) == total
    cho = [m for m in d["modules"] if m["status"] == "pending"]
    assert {m["id"] for m in cho} == set(d["skipped_heavy"])
    assert len(d["modules"]) >= 14
    # cảnh báo chỉ gồm module dữ liệu thật
    assert all(m["is_real"] for m in d["alerts"])


def test_unknown_module_404():
    assert client.post("/api/assess/khong_ton_tai", json={"lat": 10, "lon": 106}).status_code == 404


def test_whatif_rejects_non_hazard():
    assert client.post("/api/whatif/carbon", json={"lat": 10, "lon": 106}).status_code == 404
