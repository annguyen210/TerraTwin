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


def test_the_mo_hinh_doc_lan_cham_moi_nhat(monkeypatch):
    """Cổng GĐ3: thẻ đọc lần chấm MỚI NHẤT, ghi rõ nhãn AI; trượt vẫn hiện độ chính xác từng loại."""
    from app.services import model_cards
    real = model_cards._load
    r1 = {"n": 40, "population": 9, "macro_f1": 0.58, "passed": False, "per_type": []}
    r2 = {"n": 40, "population": 9, "macro_f1": 0.85, "passed": True,
          "per_type": [{"type": "residential", "precision": 1.0, "recall": 1.0, "f1": 1.0, "tp": 8, "fp": 0, "fn": 0}]}
    files = {("eval", "listing_gate_result.json"): r1, ("eval", "listing_gate_v2_result.json"): r2,
             ("eval", "listing_gate_v3_result.json"): None, ("eval", "listing_gate_v4_result.json"): None}
    monkeypatch.setattr(model_cards, "_load", lambda *p: files[p] if p in files else real(*p))
    c = next(x for x in model_cards.cards() if x["id"] == "listing_rules")
    assert c["status"] == "accepted" and "lần 2" in c["status_label"] and "KHÔNG phải nhãn người" in c["split"]
    assert c["metrics"][-1]["value"] == 0.85 and c["metrics"][0]["passed"] is True


def test_the_mo_hinh_lan_4_tin_facebook_truot(monkeypatch):
    """Lần 4 (26/10/2026) đổi nguồn sang trang Facebook công khai: thẻ ghi đúng nguồn của lần đó, trượt thì ghi trượt
    dù lần 3 đạt, và vẫn liệt kê F1 của mọi lần."""
    from app.services import model_cards
    real = model_cards._load
    r3 = {"n": 40, "population": 9, "macro_f1": 0.99, "passed": True, "per_type": []}
    r4 = {"n": 20, "macro_f1": 0.5, "passed": False, "source": "facebook_public_pages", "data_note": "20 bài trên 4 trang Facebook",
          "per_type": [{"type": "near_sea", "precision": 0.0, "recall": 0.0, "f1": 0.0, "tp": 0, "fp": 0, "fn": 1}]}
    files = {("eval", "listing_gate_result.json"): None, ("eval", "listing_gate_v2_result.json"): None,
             ("eval", "listing_gate_v3_result.json"): r3, ("eval", "listing_gate_v4_result.json"): r4}
    monkeypatch.setattr(model_cards, "_load", lambda *p: files[p] if p in files else real(*p))
    c = next(x for x in model_cards.cards() if x["id"] == "listing_rules")
    assert c["status"] == "rejected" and "lần 4 trượt" in c["status_label"]
    assert c["data"] == "20 bài trên 4 trang Facebook" and "lần 3: F1 0.99" in c["split"] and "lần 4: F1 0.5" in c["split"]
    assert "Facebook" in c["limits"] and c["metrics"][0]["passed"] is False
