"""Mô-đun mỏ tra danh sách OSM tải sẵn (backend/data/osm_quarries_vn.json) — 23/11/2026: Huế từng mất 49 giây vì Overpass,
22/11 Overpass 502 → "chưa đủ dữ liệu nguồn". Overpass chỉ còn là dự phòng."""
import json
import time

import pytest

from app.modules.registry import get_module
from app.schemas import Location
from app.services import datasources as ds
from app.services import optical, osm, quarries, reqlang


@pytest.fixture
def khong_overpass(monkeypatch):
    def _cam(*a, **k):
        raise AssertionError("không được gọi Overpass khi đã có danh sách tải sẵn")
    monkeypatch.setattr(osm, "nearest", _cam)
    monkeypatch.setattr(ds, "slope_context", lambda la, lo: (2.0, True))
    monkeypatch.setattr(ds, "forecast_precip_7d_total", lambda la, lo: (40.0, True))
    monkeypatch.setattr(ds, "elevation_proxy", lambda la, lo: 5.0)
    monkeypatch.setattr(optical, "vegetation_loss", lambda *a, **k: None)
    reqlang.set_lang("vi")


def test_danh_sach_co_nguon_giay_phep_ngay_tai():
    d = json.loads(quarries.DATA.read_text(encoding="utf-8"))
    assert d["license"].startswith("ODbL") and "OpenStreetMap contributors" in d["attribution"]
    assert d["downloaded"] and d["count"] == len(d["points"]) > 0
    assert d["fields"] == ["lat", "lon", "name", "osm_id", "kind"]


def test_hue_bai_gan_nhat_9_56_km_duoi_1_giay(khong_overpass):
    t = time.perf_counter()
    sites = quarries.nearest(16.52, 107.59, radius_m=15_000.0)
    a = get_module("mining").assess(Location(lat=16.52, lon=107.59))
    assert time.perf_counter() - t < 1.0
    assert sites and abs(sites[0]["km"] - 9.56) < 0.05
    assert "9,56 km" in a.headline
    assert f"bản tải ngày {quarries.downloaded()}" in a.data_sources[0] and "ODbL" in a.data_sources[0]


def test_tue_tinh_khong_thay_mo_trong_10_km(khong_overpass):
    a = get_module("mining").assess(Location(lat=20.9716, lon=106.2834))
    assert a.status == "out_of_scope" and a.risk_level == "unknown"
    assert a.headline.startswith("Không áp dụng — không thấy mỏ hay bãi khai thác nào trong 10 km (OSM)")
    assert "bản tải ngày" in a.data_sources[0]


def test_danh_sach_hong_thi_dung_overpass_du_phong(monkeypatch, tmp_path):
    monkeypatch.setattr(quarries, "DATA", tmp_path / "khong-co.json")
    quarries._load.cache_clear()
    try:
        goi = []
        monkeypatch.setattr(osm, "nearest", lambda *a, **k: goi.append(1) or [])
        monkeypatch.setattr(ds, "slope_context", lambda la, lo: (2.0, True))
        monkeypatch.setattr(ds, "forecast_precip_7d_total", lambda la, lo: (40.0, True))
        monkeypatch.setattr(ds, "elevation_proxy", lambda la, lo: 5.0)
        monkeypatch.setattr(optical, "vegetation_loss", lambda *a, **k: None)
        assert quarries.nearest(16.52, 107.59) is None
        get_module("mining").assess(Location(lat=16.52, lon=107.59))
        assert goi == [1]
    finally:
        quarries._load.cache_clear()
