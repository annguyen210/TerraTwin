"""Xác nhận TỪNG đợt nước (17/10/2026): "Ruộng tôi có ngập đợt này không?" — bảng riêng water_confirms, không lẫn vào
bảng quan sát (hiệu chuẩn cảnh báo); "Có" ở đợt v1 "ngoài mùa" → ca kiểm thật cho lớp mùa lũ v4."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.mua_lu_that
LAT, LON = 16.5201, 107.5902
PW = "MatKhau123"


@pytest.fixture
def c(monkeypatch):
    from app.main import app
    from app.services import cache_store, flood_season as fs, water_history as wh
    hist = {"available": True, "events": [{"start": "2024-09-19", "end": "2024-09-19"},
                                          {"start": "2023-10-19", "end": "2023-10-25"}]}
    key = wh.cache_key(LAT, LON)
    real = cache_store.get
    monkeypatch.setattr(cache_store, "get", lambda k: hist if k == key else real(k))
    monkeypatch.setattr(fs, "season", lambda la, lo: {"months": [1, 10, 11, 12]})
    with TestClient(app) as cl:
        yield cl


def _login(c, email):
    tok = c.post("/api/auth/register", json={"email": email, "password": PW, "name": "N"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _cases(start):
    from app.db import SeasonCase, SessionLocal
    with SessionLocal() as s:
        return s.query(SeasonCase).filter(SeasonCase.event_start == start, SeasonCase.source == "event").count()


def test_can_dang_nhap_va_dot_phai_co_that(c):
    body = {"lat": LAT, "lon": LON, "event_start": "2024-09-19", "answer": "yes"}
    assert c.post("/api/water/confirm", json=body).status_code == 401
    h = _login(c, "xn-1@vd.vn")
    assert c.post("/api/water/confirm", json={**body, "event_start": "2022-01-01"}, headers=h).status_code == 404
    assert c.post("/api/water/confirm", json={**body, "answer": "maybe"}, headers=h).status_code == 422


def test_co_ngap_dot_ngoai_mua_thanh_mot_ca_v4_bam_lai_khong_nhan_doi(c):
    h = _login(c, "xn-2@vd.vn")
    body = {"lat": LAT, "lon": LON, "event_start": "2024-09-19", "answer": "yes"}
    r = c.post("/api/water/confirm", json=body, headers=h).json()
    assert r["ok"] and r["v1_label"] == "out" and r["season_case"] is True
    n = _cases("2024-09-19")
    r2 = c.post("/api/water/confirm", json=body, headers=h).json()          # bấm lại
    assert r2["season_case"] is False and _cases("2024-09-19") == n
    # Đợt TRONG mùa: ghi xác nhận nhưng không phải ca v4
    r3 = c.post("/api/water/confirm", json={**body, "event_start": "2023-10-19"}, headers=h).json()
    assert r3["v1_label"] == "in" and r3["season_case"] is False


def test_dem_theo_dot_chi_tra_so_dem_va_cau_cua_minh(c):
    a, b = _login(c, "xn-3@vd.vn"), _login(c, "xn-4@vd.vn")
    c.post("/api/water/confirm", json={"lat": LAT, "lon": LON, "event_start": "2023-10-19", "answer": "yes"}, headers=a)
    c.post("/api/water/confirm", json={"lat": LAT, "lon": LON, "event_start": "2023-10-19", "answer": "no"}, headers=b)
    c.post("/api/water/confirm", json={"lat": LAT, "lon": LON, "event_start": "2023-10-19", "answer": "unsure"}, headers=b)  # đổi ý
    anon = c.get("/api/water/confirmations", params={"lat": LAT, "lon": LON}).json()["events"]["2023-10-19"]
    assert anon["yes"] >= 1 and anon["mine"] is None and "user_id" not in str(anon)
    mine = c.get("/api/water/confirmations", params={"lat": LAT, "lon": LON}, headers=b).json()["events"]["2023-10-19"]
    assert mine["mine"] == "unsure"
    assert mine["yes"] + mine["no"] + mine["unsure"] == anon["yes"] + anon["no"] + anon["unsure"]


def test_khong_ghi_vao_bang_quan_sat(c):
    from app.db import Observation, SessionLocal
    with SessionLocal() as s:
        before = s.query(Observation).count()
    h = _login(c, "xn-5@vd.vn")
    c.post("/api/water/confirm", json={"lat": LAT, "lon": LON, "event_start": "2024-09-19", "answer": "no"}, headers=h)
    with SessionLocal() as s:
        assert s.query(Observation).count() == before


def test_admin_xem_gom_theo_dot_khong_lo_nguoi_tra_loi(c, monkeypatch):
    from app import auth
    from app.main import app
    h = _login(c, "xn-6@vd.vn")
    c.post("/api/water/confirm", json={"lat": LAT, "lon": LON, "event_start": "2024-09-19", "answer": "no"}, headers=h)
    assert c.get("/api/admin/water-confirms", headers=h).status_code == 403
    app.dependency_overrides[auth.require_admin] = lambda: None
    try:
        j = c.get("/api/admin/water-confirms").json()
    finally:
        app.dependency_overrides.pop(auth.require_admin, None)
    ev = [e for e in j["events"] if e["event_start"] == "2024-09-19"]
    assert ev and ev[0]["no"] >= 1 and ev[0]["lat"] == round(LAT, 2) and "user_id" not in str(j)
