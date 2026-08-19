"""C01 Twin Builder · U01 Action & Automation · trạng thái 26 luồng.

Phần đáng chú ý nhất: webhook phải CHẶN địa chỉ nội bộ. Không có nó, người dùng
biến máy chủ TerraTwin thành công cụ quét mạng riêng (SSRF).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BEN_TRE = {"lat": 10.19, "lon": 106.70}
GOOD_PW = "MatKhau123"


def _rows(precip=25.0):
    return [{"day": i, "date": f"2026-08-{17+i:02d}",
             "precip": precip, "et0": 4.0, "tmax": 33.0} for i in range(7)]


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app import db as dbmod
    from app.services import calibration as cal
    from app.services import genome, realdata

    engine = create_engine(f"sqlite:///{tmp_path/'t.db'}",
                           connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    dbmod.Base.metadata.create_all(engine)
    monkeypatch.setattr(dbmod, "engine", engine)
    monkeypatch.setattr(dbmod, "SessionLocal", Session)

    monkeypatch.setattr(realdata, "elevation_m", lambda la, lo: 4.0)
    monkeypatch.setattr(realdata, "slope_deg", lambda la, lo, step_m=500.0: 1.0)
    monkeypatch.setattr(realdata, "weather_7d", lambda la, lo: _rows())
    monkeypatch.setattr(realdata, "river_discharge_7d", lambda la, lo: None)
    monkeypatch.setattr(realdata, "marine_7d", lambda la, lo: None)
    monkeypatch.setattr(realdata, "solar_annual", lambda la, lo: 4.9)
    monkeypatch.setattr(realdata, "historical_weather", lambda *a: None)
    monkeypatch.setattr(cal, "climatology", lambda *a, **k:
                        sorted((i / 400) ** 2 * 200.0 for i in range(400)))
    monkeypatch.setattr(genome, "genome_of", lambda la, lo: None)

    from app.main import app

    def _session():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[dbmod.get_session] = _session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _tok(c, email="a@x.com"):
    r = c.post("/api/auth/register",
               json={"email": email, "password": GOOD_PW, "name": "A"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ---------- C01 Twin Builder ----------

def test_build_twin_without_login(client):
    d = client.post("/api/twin", json=BEN_TRE).json()
    assert d["persisted"] is False
    layers = d["layers"]
    assert layers["terrain"]["elevation_m"] == 4.0
    assert len(layers["modules"]) >= 14
    assert "terrascore" in layers and "data_quality" in layers


def test_twin_records_data_quality_honestly(client):
    q = client.post("/api/twin", json=BEN_TRE).json()["layers"]["data_quality"]
    assert q["modules_total"] >= 14
    # Không phải mọi mô-đun đều dùng dữ liệu thật (5 cái chờ khoá vệ tinh).
    assert 0 < q["modules_real_data"] < q["modules_total"]
    assert q["climate_genome_available"] is False


def test_save_and_reload_twin(client):
    h = _tok(client)
    created = client.post("/api/twins", headers=h,
                          json={"name": "Ruộng nhà", "location": BEN_TRE})
    assert created.status_code == 201
    tid = created.json()["id"]

    assert len(client.get("/api/twins", headers=h).json()) == 1
    got = client.get(f"/api/twins/{tid}", headers=h).json()
    assert got["name"] == "Ruộng nhà"
    assert len(got["layers"]["modules"]) >= 14


def test_twin_is_a_snapshot_not_a_live_query(client, monkeypatch):
    """Twin đã lưu phải giữ NGUYÊN số cũ dù thời tiết đổi — đó là lý do lưu nó."""
    from app.services import realdata
    h = _tok(client)
    tid = client.post("/api/twins", headers=h,
                      json={"name": "T", "location": BEN_TRE}).json()["id"]
    before = client.get(f"/api/twins/{tid}", headers=h).json()["layers"]

    monkeypatch.setattr(realdata, "weather_7d", lambda la, lo: _rows(precip=300.0))
    after = client.get(f"/api/twins/{tid}", headers=h).json()["layers"]
    assert after == before


def test_twins_isolated_between_users(client):
    a = _tok(client, "a@x.com")
    b = _tok(client, "b@x.com")
    tid = client.post("/api/twins", headers=a,
                      json={"name": "A", "location": BEN_TRE}).json()["id"]
    assert client.get("/api/twins", headers=b).json() == []
    assert client.get(f"/api/twins/{tid}", headers=b).status_code == 404
    assert client.delete(f"/api/twins/{tid}", headers=b).status_code == 404


def test_twins_require_auth(client):
    assert client.get("/api/twins").status_code == 401


# ---------- U01: bảo mật webhook (SSRF) ----------

@pytest.mark.parametrize("url", [
    "http://localhost:8000/hook",
    "http://127.0.0.1/hook",
    "http://169.254.169.254/latest/meta-data/",     # metadata cloud
    "http://[::1]/hook",
])
def test_webhook_blocks_internal_addresses(client, url):
    """Không chặn thì máy chủ thành công cụ quét mạng nội bộ."""
    h = _tok(client)
    r = client.post("/api/channels", headers=h,
                    json={"kind": "webhook", "target": url})
    assert r.status_code == 422, f"{url} đáng lẽ phải bị chặn"


@pytest.mark.parametrize("url", ["ftp://example.com/x", "file:///etc/passwd",
                                 "gopher://example.com"])
def test_webhook_rejects_non_http_schemes(client, url):
    h = _tok(client)
    assert client.post("/api/channels", headers=h,
                       json={"kind": "webhook", "target": url}).status_code == 422


def test_webhook_rejects_unresolvable_host(client):
    h = _tok(client)
    r = client.post("/api/channels", headers=h, json={
        "kind": "webhook",
        "target": "https://khong-ton-tai-that-day-12345.invalid/hook"})
    assert r.status_code == 422


# ---------- U01: kênh cảnh báo ----------

def test_email_channel_validates_address(client):
    h = _tok(client)
    assert client.post("/api/channels", headers=h,
                       json={"kind": "email", "target": "khong-phai-email"}
                       ).status_code == 422
    assert client.post("/api/channels", headers=h,
                       json={"kind": "email", "target": "nong.dan@vd.vn"}
                       ).status_code == 201


def test_channel_crud_and_isolation(client):
    a = _tok(client, "a@x.com")
    b = _tok(client, "b@x.com")
    cid = client.post("/api/channels", headers=a,
                      json={"kind": "email", "target": "a@vd.vn"}).json()["id"]
    assert len(client.get("/api/channels", headers=a).json()) == 1
    assert client.get("/api/channels", headers=b).json() == []
    assert client.delete(f"/api/channels/{cid}", headers=b).status_code == 404
    assert client.delete(f"/api/channels/{cid}", headers=a).status_code == 204


def test_min_level_filters_alerts():
    from app.services import notify
    assert notify.level_at_least("danger", "warning") is True
    assert notify.level_at_least("warning", "warning") is True
    assert notify.level_at_least("warning", "danger") is False
    assert notify.level_at_least("safe", "warning") is False


def test_dispatch_skips_channel_below_min_level(monkeypatch):
    from app.services import notify

    class Ch:
        id, kind, target, min_level, enabled = 1, "webhook", "https://x/y", "danger", 1
        last_sent_at = last_error = None

    sent = []
    monkeypatch.setattr(notify, "send_webhook",
                        lambda u, p: sent.append(p) or None)
    res = notify.dispatch([Ch()], [{"risk_level": "warning", "headline": "h",
                                    "recommendation": "r", "module_id": "flood",
                                    "plot_id": None}])
    assert res["sent"] == 0 and sent == []
    assert res["results"][0]["skipped"] is True


def test_dispatch_records_error_without_raising(monkeypatch):
    """Gửi hỏng KHÔNG được làm hỏng lượt quét."""
    from app.services import notify

    class Ch:
        id, kind, target, min_level, enabled = 1, "webhook", "https://x/y", "warning", 1
        last_sent_at = last_error = None

    monkeypatch.setattr(notify, "send_webhook", lambda u, p: "Máy chủ trả mã 500.")
    ch = Ch()
    res = notify.dispatch([ch], [{"risk_level": "danger", "headline": "h",
                                  "recommendation": "r", "module_id": "flood",
                                  "plot_id": None}])
    assert res["failed"] == 1 and ch.last_error == "Máy chủ trả mã 500."


def test_radar_reports_delivery(client, monkeypatch):
    from app.services import notify
    h = _tok(client)
    client.post("/api/plots", headers=h, json={"name": "R", "location": BEN_TRE})
    monkeypatch.setattr(notify, "send_webhook", lambda u, p: None)
    d = client.post("/api/radar/run", headers=h).json()
    assert "delivery" in d


# ---------- Trạng thái 26 luồng ----------

def test_roadmap_covers_all_26_flows(client):
    d = client.get("/api/roadmap").json()
    assert d["total"] == 26
    assert d["done"] + d["partial"] + d["blocked"] == 26


def test_every_blocked_flow_says_what_blocks_it(client):
    """Không luồng nào được ghi mơ hồ kiểu 'đang phát triển'."""
    for f in client.get("/api/roadmap").json()["flows"]:
        if f["status"] == "blocked":
            assert len(f["note"]) > 30, f["id"]
            assert "đang phát triển" not in f["note"].lower()


# ---------- Rate limit sau reverse proxy ----------

def test_rate_limit_uses_forwarded_ip_when_proxy_trusted(monkeypatch):
    """HỒI QUY: đếm theo request.client.host thì sau proxy MỌI người dùng chung
    một hạn mức — deploy lên Render/nginx là sập ngay khi có vài người vào."""
    from app import main

    class Req:
        def __init__(self, headers, host):
            self.headers = headers
            self.client = type("C", (), {"host": host})()

    monkeypatch.setattr(main, "_TRUST_PROXY", True)
    r = Req({"x-forwarded-for": "203.0.113.9, 10.0.0.1"}, "10.0.0.1")
    assert main._client_ip(r) == "203.0.113.9"      # IP thật, không phải proxy
    assert main._client_ip(Req({"x-real-ip": "203.0.113.7"}, "10.0.0.1")) == "203.0.113.7"


def test_forwarded_header_ignored_when_proxy_not_trusted(monkeypatch):
    """Không đứng sau proxy mà tin X-Forwarded-For thì client tự bịa IP để né."""
    from app import main

    class Req:
        headers = {"x-forwarded-for": "1.2.3.4"}
        client = type("C", (), {"host": "198.51.100.5"})()

    monkeypatch.setattr(main, "_TRUST_PROXY", False)
    assert main._client_ip(Req()) == "198.51.100.5"


def test_roadmap_ids_unique_and_complete(client):
    ids = [f["id"] for f in client.get("/api/roadmap").json()["flows"]]
    assert len(ids) == len(set(ids))
    assert sum(1 for i in ids if i.startswith("S")) == 10
    assert sum(1 for i in ids if i.startswith("C")) == 12
    assert sum(1 for i in ids if i.startswith("U")) == 4
