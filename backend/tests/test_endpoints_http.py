"""Gọi endpoint QUA TẦNG HTTP, không gọi thẳng hàm tính toán.

VÌ SAO CẦN RIÊNG NHÓM NÀY. /api/contrast và /api/anomaly-ml từng nổ 500 ngay
lời gọi đầu tiên — chúng gọi _off_site() với sai số lượng tham số. Toàn bộ test
lúc đó vẫn xanh, vì test kiểm tra calibration.contrast() và anomaly_ml.score()
TRỰC TIẾP. Phần bị hỏng nằm ở lớp keo giữa HTTP và hàm tính toán, và không test
nào chạm tới nó.

Bài học chung: hàm đúng KHÔNG có nghĩa là endpoint đúng. Mỗi endpoint cần ít
nhất một lần gọi thật qua HTTP, kể cả khi lõi đã được kiểm kỹ.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

DAT_LIEN = {"lat": 15.33, "lon": 108.05}      # Trà Leng
BIEN = {"lat": 12.0, "lon": 111.0}            # giữa Biển Đông


def test_moi_endpoint_GET_deu_tra_loi_duoc():
    for p in ("/api/health", "/api/modules", "/api/plans", "/api/model",
              "/api/landcover", "/api/satellite", "/api/roadmap",
              "/api/place?q=Ba%20Tri"):
        r = client.get(p)
        assert r.status_code == 200, f"{p} → {r.status_code}"
        assert r.json() is not None


@pytest.mark.parametrize("path", ["/api/contrast", "/api/anomaly-ml"])
def test_endpoint_dat_lien_khong_no_500(path, monkeypatch):
    """Đây là chính xác lỗi đã lọt: sai chữ ký hàm, chỉ lộ khi gọi thật."""
    from app.services import calibration, region
    monkeypatch.setattr(region, "classify",
                        lambda la, lo: {"serviceable": True, "kind": "land"})
    monkeypatch.setattr(calibration, "climatology",
                        lambda *a, **k: sorted([1.0, 50.0, 200.0] * 40))
    r = client.post(path, json={"location": DAT_LIEN})
    assert r.status_code == 200, f"{path} → {r.status_code}: {r.text[:200]}"


@pytest.mark.parametrize("path", ["/api/contrast", "/api/anomaly-ml"])
def test_endpoint_ngoai_vung_tra_loi_lich_su_chu_khong_no(path, monkeypatch):
    from app.services import region
    monkeypatch.setattr(region, "classify", lambda la, lo: {
        "serviceable": False, "kind": "sea",
        "note": "Đây là mặt nước — TerraTwin phục vụ đất liền."})
    r = client.post(path, json={"location": BIEN})
    assert r.status_code == 200, f"{path} → {r.status_code}: {r.text[:200]}"
    d = r.json()
    assert d.get("available") is False
    assert "mặt nước" in (d.get("message") or "")


def test_contrast_tra_du_bon_hiem_hoa(monkeypatch):
    from app.services import calibration, region
    monkeypatch.setattr(region, "classify",
                        lambda la, lo: {"serviceable": True, "kind": "land"})
    monkeypatch.setattr(calibration, "climatology",
                        lambda *a, **k: sorted([1.0, 50.0, 200.0] * 40))
    d = client.post("/api/contrast", json={"location": DAT_LIEN}).json()
    assert d["available"] is True
    assert {m["module_id"] for m in d["modules"]} == {
        "flood", "landslide", "drought", "wildfire"}
    for m in d["modules"]:
        assert "fixed_days_per_year" in m and "calibrated_days_per_year" in m


def test_scan_qua_http_tra_du_moi_muc(monkeypatch):
    from app.services import region
    monkeypatch.setattr(region, "classify",
                        lambda la, lo: {"serviceable": True, "kind": "land"})
    d = client.post("/api/scan", json=DAT_LIEN).json()
    from app.modules.registry import list_modules
    assert len(d["modules"]) == len(list_modules())
    for m in d["modules"]:
        assert m["status"] in ("ok", "need_data", "out_of_scope", "pending")
