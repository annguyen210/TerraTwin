"""Kiểm chứng tin đăng: tách câu khẳng định (có dấu/không dấu), đối chiếu số đo, lời văn trung lập, không lưu."""
from __future__ import annotations

import pytest

TIN = """Bán gấp lô đất 500m2 thổ cư 100%, sổ hồng riêng.
Đất cao ráo, không bao giờ ngập nước, view sông thoáng mát.
Mặt bằng vuông vức, bằng phẳng; nuoc ngot quanh nam."""


def test_tach_dung_cac_cau_khang_dinh_ca_khong_dau():
    from app.services import listing_check as lc
    types = sorted({c["type"] for c in lc.extract(TIN)})
    assert types == ["flat", "fresh_water", "high_ground", "near_river", "no_flood", "residential"]


@pytest.mark.parametrize("text,typ", [
    ("Đất chưa từng bị ngập", "no_flood"), ("khong lo ngap", "no_flood"), ("nền cao hơn mặt đường", "high_ground"),
    ("cách biển 2km", "near_sea"), ("không sạt lở", "no_landslide"), ("giáp kênh thủy lợi", "near_river"),
])
def test_nhan_dien_tung_loai(text, typ):
    from app.services import listing_check as lc
    assert typ in {c["type"] for c in lc.extract(text)}


def test_cau_khong_khang_dinh_gi_thi_khong_bat_bua():
    from app.services import listing_check as lc
    assert lc.extract("Liên hệ chính chủ, giá thương lượng, xem đất thứ Bảy.") == []


def test_doi_chieu_khong_ngap_voi_lich_su_nuoc_radar():
    from app.services import listing_check as lc
    wet = {"water": {"n_events": 3, "first": "2017-01-11", "n_scenes": 300,
                     "events": [{"start": "2019-11-02"}, {"start": "2020-10-10"}, {"start": "2025-11-01"}]}}
    v, msg, src = lc.judge("no_flood", wet)
    assert v == "contradicted" and "3 đợt" in msg and "2025-11-01" in msg and "Sentinel-1" in src
    dry = {"water": {"n_events": 0, "first": "2017-01-11", "n_scenes": 300, "events": []}}
    assert lc.judge("no_flood", dry)[0] == "consistent"
    assert lc.judge("no_flood", {"water": None})[0] == "insufficient"       # chưa đọc radar → không đoán


def test_cao_rao_dua_tren_dia_hinh_va_nuoc():
    from app.services import listing_check as lc
    low = {"terrain": {"lower_than_pct": 80, "elevation_m": 3, "slope_deg": 0.5}, "water": None}
    assert lc.judge("high_ground", low)[0] == "contradicted"
    high = {"terrain": {"lower_than_pct": 10, "elevation_m": 40, "slope_deg": 2}, "water": {"n_events": 0}}
    assert lc.judge("high_ground", high)[0] == "consistent"
    mid = {"terrain": {"lower_than_pct": 50, "elevation_m": 10, "slope_deg": 1}, "water": None}
    assert lc.judge("high_ground", mid)[0] == "insufficient"


def test_loai_dat_phap_ly_va_nuoc_ngot_luon_noi_thang_la_khong_kiem_duoc():
    from app.services import listing_check as lc
    assert lc.judge("residential", {})[0] == "insufficient"
    assert lc.judge("fresh_water", {})[0] == "insufficient"


def test_api_kiem_tin_dang_khong_luu_noi_dung(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services import listing_check as lc, quota
    quota.reset()
    monkeypatch.setattr(lc, "evidence", lambda lat, lon, types: {"water": None, "terrain": {"lower_than_pct": 85,
                                                                  "elevation_m": 2, "slope_deg": 0.3}})
    with TestClient(app) as c:
        r = c.post("/api/listing/check", json={"text": TIN, "lat": 16.575, "lon": 107.495}).json()
        assert c.post("/api/listing/check", json={"text": "x" * 5001, "lat": 16.5, "lon": 107.5}).status_code == 422
    v = {x["type"]: x["verdict"] for x in r["claims"]}
    assert v["high_ground"] == "contradicted" and v["flat"] == "consistent" and v["residential"] == "insufficient"
    assert "không được lưu" in r["note"]
