"""Tập vàng cổng GĐ3 (18/10/2026): ẩn danh trước khi lưu, chỉ quản trị, chấm đúng như ops/listing_gate.py."""
from __future__ import annotations


def test_an_danh_so_dien_thoai_email_duong_dan():
    from app.services import listing_gold
    t = listing_gold.anonymize("Bán đất cao ráo LH 0905 123 456 hoặc +84912345678, a.b@gmail.com, xem https://batdongsan.com.vn/x")
    assert "0905" not in t and "0912" not in t and "gmail" not in t and "batdongsan" not in t
    assert t.count("[số điện thoại]") == 2 and "[email]" in t and "[đường dẫn]" in t and "cao ráo" in t


def test_cham_giong_listing_gate():
    from app.services import listing_gold
    gold = [{"text": "Bán đất thổ cư, cao ráo, không bao giờ ngập, gần sông Hương", "claims": ["residential", "high_ground", "no_flood", "near_river"]},
            {"text": "Lô góc mặt tiền đường nhựa, giá thương lượng", "claims": []}]
    s = listing_gold.score(gold)
    assert s["n"] == 2 and s["enough"] is False and s["macro_f1"] is not None
    assert {r["type"] for r in s["per_type"]} >= {"no_flood", "high_ground", "near_river"}


def test_chi_quan_tri_va_luu_da_an_danh():
    from fastapi.testclient import TestClient
    from app import auth
    from app.main import app
    with TestClient(app) as c:
        tok = c.post("/api/auth/register", json={"email": "lg-1@nong.vn", "password": "MatKhau123", "name": "N"}).json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        assert c.get("/api/admin/listing-gold", headers=h).status_code == 403
        app.dependency_overrides[auth.require_admin] = lambda: None
        try:
            assert c.post("/api/admin/listing-gold", json={"text": "Đất cao ráo, LH 0905123456", "claims": ["bay_lung_tung"]}).status_code == 422
            r = c.post("/api/admin/listing-gold", json={"text": "Đất cao ráo không ngập, LH 0905123456", "claims": ["high_ground", "no_flood"]})
            assert r.status_code == 201 and "0905" not in r.json()["text"]
            j = c.get("/api/admin/listing-gold").json()
            assert any(i["id"] == r.json()["id"] for i in j["items"]) and j["claim_types"]
            assert c.delete(f"/api/admin/listing-gold/{r.json()['id']}").status_code == 204
        finally:
            app.dependency_overrides.pop(auth.require_admin, None)
