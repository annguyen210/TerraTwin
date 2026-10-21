"""Ảnh nền thật dưới thửa phải nói rõ ngày chụp, độ phân giải, nguồn — không gọi mạng thật trong test."""
from __future__ import annotations


def test_doc_sieu_du_lieu_esri():
    from app.services import basemap
    p = basemap._parse({"DATE (YYYYMMDD)": "20260221", "RESOLUTION (M)": "0.34", "SOURCE": "Vantor", "SOURCE_INFO": "Vivid"})
    assert p == {"date": "2026-02-21", "resolution_m": 0.34, "source": "Vantor", "product": "Vivid"}
    q = basemap._parse({"DATE (YYYYMMDD)": "99999999", "RESOLUTION (M)": "99999", "SOURCE": "Null"})
    assert q["date"] is None and q["resolution_m"] is None and q["source"] is None      # không bịa ngày khi dịch vụ không biết


def test_meta_tinh_tuoi_anh_va_cache(monkeypatch):
    import io
    import json
    from app.services import basemap, cache_store
    store = {}
    monkeypatch.setattr(cache_store, "get", lambda k: store.get(k))
    monkeypatch.setattr(cache_store, "put", lambda k, v, ttl_seconds=0: store.__setitem__(k, v))
    calls = []

    class R(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake(req, timeout=0):
        calls.append(req.full_url)
        return R(json.dumps({"results": [{"attributes": {"DATE (YYYYMMDD)": "20230131", "RESOLUTION (M)": "0.31", "SOURCE": "Vantor"}}]}).encode())
    monkeypatch.setattr(basemap.urllib.request, "urlopen", fake)
    a = basemap.meta(9.18, 105.15)
    assert a["available"] and a["date"] == "2023-01-31" and a["age_years"] > 3
    basemap.meta(9.18, 105.15)
    assert len(calls) == 1                                             # lần hai lấy từ cache


def test_diem_cuoi(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services import basemap
    with TestClient(app) as c:
        monkeypatch.setattr(basemap, "meta", lambda la, lo: {"available": True, "date": "2026-02-21", "resolution_m": 0.34})
        assert c.get("/api/basemap/meta", params={"lat": 16.57, "lon": 107.49}).json()["date"] == "2026-02-21"
        assert c.get("/api/basemap/meta", params={"lat": 1, "lon": 2}).status_code == 422
        monkeypatch.setattr(basemap, "meta", lambda la, lo: None)
        assert c.get("/api/basemap/meta", params={"lat": 16.57, "lon": 107.49}).status_code == 503
