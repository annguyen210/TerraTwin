"""A9/G1 — ký báo cáo bằng mã băm: bản in bị sửa phải bị phát hiện."""
from fastapi.testclient import TestClient

from app.main import app
from app.services import report


def test_sign_then_verify_valid():
    facts = {"location": {"lat": 16.46, "lon": 107.59},
             "terrascore": {"score": 72, "grade": "B"}}
    signed = report.sign(facts)
    assert len(signed["hash"]) == 64 and len(signed["short"]) == 16
    assert "signed_at" in signed
    assert report.verify(signed)["valid"] is True


def test_tampered_report_is_caught():
    signed = report.sign({"terrascore": {"score": 72, "grade": "B"}})
    signed["terrascore"]["score"] = 95        # sửa điểm sau khi ký
    v = report.verify(signed)
    assert v["valid"] is False
    assert "KHÔNG khớp" in v["message"]


def test_missing_hash_is_invalid():
    assert report.verify({"terrascore": {"score": 1}})["valid"] is False


def test_endpoints_round_trip():
    with TestClient(app) as c:
        facts = {"location": {"lat": 10.24, "lon": 106.38},
                 "modules": [{"id": "salinity", "risk": "warning", "real": True}]}
        signed = c.post("/api/report/sign", json=facts).json()
        assert signed["hash"] and c.post("/api/report/verify", json=signed).json()["valid"] is True
        signed["modules"][0]["risk"] = "safe"     # giả mạo
        assert c.post("/api/report/verify", json=signed).json()["valid"] is False
