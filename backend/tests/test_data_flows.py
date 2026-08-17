"""C06 Heatmap · C11 Bring-Your-Own-Data · C05 Proactive Radar.

Chạy offline: giả lập realdata + khí hậu nền.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BEN_TRE = {"lat": 10.19, "lon": 106.70}
GOOD_PW = "MatKhau123"


def _rows(precip=30.0):
    return [{"day": i, "date": f"2026-08-{17+i:02d}",
             "precip": precip, "et0": 4.0, "tmax": 33.0} for i in range(7)]


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app import db as dbmod
    from app.services import calibration as cal
    from app.services import realdata

    engine = create_engine(f"sqlite:///{tmp_path/'t.db'}",
                           connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    dbmod.Base.metadata.create_all(engine)
    monkeypatch.setattr(dbmod, "engine", engine)
    monkeypatch.setattr(dbmod, "SessionLocal", Session)

    # Nguồn dữ liệu giả lập, tất định
    monkeypatch.setattr(realdata, "elevation_m", lambda la, lo: 3.0)
    monkeypatch.setattr(realdata, "slope_deg", lambda la, lo, step_m=500.0: 2.0)
    monkeypatch.setattr(realdata, "weather_7d", lambda la, lo: _rows())
    monkeypatch.setattr(realdata, "river_discharge_7d", lambda la, lo: None)
    monkeypatch.setattr(realdata, "marine_7d", lambda la, lo: None)
    monkeypatch.setattr(realdata, "solar_annual", lambda la, lo: 4.9)
    monkeypatch.setattr(realdata, "weather_multi",
                        lambda pts: [_rows(10.0 + i) for i in range(len(pts))])
    monkeypatch.setattr(realdata, "elevation_multi",
                        lambda pts: [3.0] * len(pts))
    dist = sorted((i / 500) ** 2 * 200.0 for i in range(500))
    monkeypatch.setattr(cal, "climatology", lambda *a, **k: dist)

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


# ---------- C06 Heatmap ----------

def test_heatmap_returns_full_grid(client):
    r = client.post("/api/heatmap/flood?side=5&radius_km=6", json=BEN_TRE)
    assert r.status_code == 200
    d = r.json()
    assert len(d["cells"]) == 25
    assert d["side"] == 5
    assert all(c["risk"] in ("safe", "warning", "danger", "unknown") for c in d["cells"])


def test_heatmap_clamps_absurd_grid_size(client):
    d = client.post("/api/heatmap/flood?side=999&radius_km=9999", json=BEN_TRE).json()
    assert d["side"] <= 11 and d["radius_km"] <= 40


def test_heatmap_states_its_caveats(client):
    """Bản đồ mượt dễ khiến người ta tin quá mức — phải nói rõ giới hạn."""
    d = client.post("/api/heatmap/flood?side=3", json=BEN_TRE).json()
    assert "TÂM" in d["caveat"] or "tâm" in d["caveat"]
    assert "phân giải" in d["caveat"]


def test_heatmap_second_call_is_cached(client):
    a = client.post("/api/heatmap/flood?side=3", json=BEN_TRE).json()
    b = client.post("/api/heatmap/flood?side=3", json=BEN_TRE).json()
    assert a["cached"] is False and b["cached"] is True
    assert a["cells"] == b["cells"]


def test_heatmap_rejects_non_hazard_module(client):
    assert client.post("/api/heatmap/carbon", json=BEN_TRE).status_code == 404


def test_heatmap_rejects_coord_outside_vn(client):
    assert client.post("/api/heatmap/flood",
                       json={"lat": 48.85, "lon": 2.35}).status_code == 422


def test_module_card_and_heatmap_agree_at_same_point(client):
    """HỒI QUY: các module từng gọi thẳng ds.*_series() (thang TUYỆT ĐỐI) trong
    khi heatmap/explain/backtest đã dùng thang ĐÃ HIỆU CHUẨN. Cùng một toạ độ,
    thẻ module báo 'nguy hiểm 74.5' còn bản đồ nhiệt báo an toàn."""
    card = client.post("/api/assess/flood", json=BEN_TRE).json()
    grid = client.post("/api/heatmap/flood?side=3&radius_km=2", json=BEN_TRE).json()
    center = grid["cells"][len(grid["cells"]) // 2]
    card_peak = max(f["value"] for f in card["forecast"])
    assert center["value"] is not None
    assert abs(card_peak - center["value"]) < 12.0, (
        f"thẻ module {card_peak} vs ô tâm heatmap {center['value']} — hai thang đo lệch")


def test_all_hazard_modules_use_calibrated_scale(client):
    """Mọi module hiểm họa phải nói rõ đang dùng thang nào."""
    for mid in ("drought", "flood", "wildfire", "landslide"):
        d = client.post(f"/api/assess/{mid}", json=BEN_TRE).json()
        assert "HIỆU CHUẨN" in d["detail"] or "hiệu chuẩn" in d["detail"], mid


# ---------- C11 Bring-Your-Own-Data ----------

CSV_OK = "ten,lat,lon\nRuong A,10.19,106.70\nRuong B,9.85,106.65\n"
CSV_EN = "name,latitude,longitude\nPlot A,10.19,106.70\n"


def test_upload_csv_and_list(client):
    h = _tok(client)
    r = client.post("/api/datasets", headers=h,
                    json={"name": "HTX Bến Tre", "kind": "csv", "content": CSV_OK})
    assert r.status_code == 201 and r.json()["row_count"] == 2
    assert len(client.get("/api/datasets", headers=h).json()) == 1


def test_upload_accepts_english_headers(client):
    h = _tok(client)
    r = client.post("/api/datasets", headers=h,
                    json={"name": "EN", "kind": "csv", "content": CSV_EN})
    assert r.status_code == 201 and r.json()["row_count"] == 1


def test_upload_rejects_csv_without_coords(client):
    h = _tok(client)
    r = client.post("/api/datasets", headers=h,
                    json={"name": "x", "kind": "csv", "content": "a,b\n1,2\n"})
    assert r.status_code == 422 and "toạ độ" in r.json()["detail"]


def test_upload_drops_rows_outside_vietnam(client):
    h = _tok(client)
    csv = "ten,lat,lon\nVN,10.19,106.70\nParis,48.85,2.35\n"
    assert client.post("/api/datasets", headers=h,
                       json={"name": "mix", "kind": "csv",
                             "content": csv}).json()["row_count"] == 1


def test_upload_geojson(client):
    h = _tok(client)
    gj = json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": "Thửa 1"},
         "geometry": {"type": "Point", "coordinates": [106.70, 10.19]}}]})
    r = client.post("/api/datasets", headers=h,
                    json={"name": "gj", "kind": "geojson", "content": gj})
    assert r.status_code == 201 and r.json()["row_count"] == 1


def test_score_dataset_ranks_worst_first(client):
    h = _tok(client)
    did = client.post("/api/datasets", headers=h,
                      json={"name": "HTX", "kind": "csv",
                            "content": CSV_OK}).json()["id"]
    d = client.post(f"/api/datasets/{did}/score", headers=h).json()
    assert d["scored"] == 2
    scores = [r["score"] for r in d["results"] if r["score"] is not None]
    assert scores == sorted(scores)              # rủi ro cao (điểm thấp) lên trước


def test_datasets_isolated_between_users(client):
    a = _tok(client, "a@x.com")
    b = _tok(client, "b@x.com")
    did = client.post("/api/datasets", headers=a,
                      json={"name": "A", "kind": "csv", "content": CSV_OK}).json()["id"]
    assert client.get("/api/datasets", headers=b).json() == []
    assert client.post(f"/api/datasets/{did}/score", headers=b).status_code == 404
    assert client.delete(f"/api/datasets/{did}", headers=b).status_code == 404


def test_datasets_require_auth(client):
    assert client.get("/api/datasets").status_code == 401


# ---------- C05 Proactive Radar ----------

def _save_plot(c, h, name="Ruộng"):
    return c.post("/api/plots", headers=h,
                  json={"name": name, "location": BEN_TRE}).json()["id"]


def test_radar_needs_plots_first(client):
    h = _tok(client)
    d = client.post("/api/radar/run", headers=h).json()
    assert d["plots_scanned"] == 0 and d["new_alerts"] == 0


def test_radar_creates_alerts_then_dedupes(client):
    h = _tok(client)
    _save_plot(client, h)
    first = client.post("/api/radar/run", headers=h).json()
    assert first["plots_scanned"] == 1
    second = client.post("/api/radar/run", headers=h).json()
    # Chạy lại ngay không được sinh trùng — nếu không sẽ spam người dùng.
    assert second["new_alerts"] == 0


def test_alerts_listed_and_acknowledged(client):
    h = _tok(client)
    _save_plot(client, h)
    client.post("/api/radar/run", headers=h)
    rows = client.get("/api/alerts", headers=h).json()
    if not rows:
        pytest.skip("dữ liệu giả lập không sinh cảnh báo nào")
    aid = rows[0]["id"]
    assert client.post(f"/api/alerts/{aid}/ack", headers=h).json()["acknowledged"] is True
    assert all(a["id"] != aid for a in
               client.get("/api/alerts?unread_only=true", headers=h).json())


def test_alerts_isolated_between_users(client):
    a = _tok(client, "a@x.com")
    b = _tok(client, "b@x.com")
    _save_plot(client, a)
    client.post("/api/radar/run", headers=a)
    assert client.get("/api/alerts", headers=b).json() == []


# ---------- Cache bền ----------

def test_cache_survives_and_expires(client):
    from app.services import cache_store
    k = cache_store.make_key("test", 1, 2)
    cache_store.put(k, {"x": 1}, ttl_seconds=60)
    assert cache_store.get(k) == {"x": 1}
    cache_store.put(k, {"x": 2}, ttl_seconds=-1)     # đã hết hạn
    assert cache_store.get(k) is None
