"""Hai nguồn dữ liệu thật mới, miễn phí, không cần key:
  - GloFAS lưu lượng sông (Open-Meteo Flood API)  → đối chứng cho module Lũ
  - Open-Meteo Marine (nhiệt mặt nước, sóng)      → module Ao nuôi thành THẬT

Test chạy offline: giả lập tầng realdata.
"""
import pytest

from app.modules.registry import get_module
from app.schemas import Location
from app.services import datasources as ds
from app.services import realdata

COASTAL = Location(lat=9.85, lon=106.65)     # Bến Tre ven biển
INLAND = Location(lat=11.94, lon=108.44)     # Đà Lạt


def _river(discharge, mean):
    return [{"day": i, "date": f"2026-08-{17+i:02d}", "discharge": d, "mean": m}
            for i, (d, m) in enumerate(zip(discharge, mean))]


def _marine(ssts, waves=None):
    waves = waves or [0.5] * len(ssts)
    return [{"day": i, "date": f"2026-08-{17+i:02d}", "sst": s, "wave": w}
            for i, (s, w) in enumerate(zip(ssts, waves))]


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(realdata, "elevation_m", lambda la, lo: 3.0)
    monkeypatch.setattr(realdata, "slope_deg", lambda la, lo, step_m=500.0: 2.0)
    monkeypatch.setattr(realdata, "weather_7d", lambda la, lo: [
        {"day": i, "date": f"2026-08-{17+i:02d}", "precip": 20.0, "et0": 4.0, "tmax": 32.0}
        for i in range(7)])
    monkeypatch.setattr(realdata, "river_discharge_7d", lambda la, lo: None)
    monkeypatch.setattr(realdata, "marine_7d", lambda la, lo: None)


# ---------- GloFAS lưu lượng sông ----------

def test_river_context_flags_high_discharge(offline, monkeypatch):
    monkeypatch.setattr(realdata, "river_discharge_7d",
                        lambda la, lo: _river([100, 200, 400, 900, 600, 300, 150],
                                              [150] * 7))
    c = ds.river_discharge_context(9.85, 106.65)
    assert c["ratio"] == pytest.approx(6.0, abs=0.01)   # 900/150
    assert c["level"] == "danger"
    assert c["peak_m3s"] == 900.0


def test_river_context_quiet_when_normal(offline, monkeypatch):
    monkeypatch.setattr(realdata, "river_discharge_7d",
                        lambda la, lo: _river([140, 150, 160, 155, 145, 150, 148],
                                              [150] * 7))
    c = ds.river_discharge_context(9.85, 106.65)
    assert c["level"] == "safe" and c["ratio"] < 1.2


def test_river_context_none_without_data(offline):
    assert ds.river_discharge_context(9.85, 106.65) is None


def test_flood_module_reports_river_metrics(offline, monkeypatch):
    monkeypatch.setattr(realdata, "river_discharge_7d",
                        lambda la, lo: _river([100, 300, 800, 500, 200, 150, 120],
                                              [150] * 7))
    a = get_module("flood").assess(COASTAL)
    assert "ty_so_so_binh_thuong" in a.metrics
    assert "GloFAS" in " ".join(a.data_sources)
    assert "lưu lượng sông" in a.headline.lower() or "GloFAS" in a.detail


def test_flood_confidence_rises_when_two_sources_agree(offline, monkeypatch):
    without = get_module("flood").assess(COASTAL).confidence
    monkeypatch.setattr(realdata, "river_discharge_7d",
                        lambda la, lo: _river([100] * 7, [150] * 7))
    with_river = get_module("flood").assess(COASTAL).confidence
    assert with_river > without


# ---------- Marine: ao nuôi ----------

def test_aquaculture_safe_in_optimal_water(offline, monkeypatch):
    monkeypatch.setattr(realdata, "marine_7d", lambda la, lo: _marine([29.5] * 7))
    a = get_module("aquaculture").assess(COASTAL)
    assert a.is_real is True and a.risk_level == "safe"
    assert len(a.forecast) == 7


def test_aquaculture_danger_when_water_too_hot(offline, monkeypatch):
    monkeypatch.setattr(realdata, "marine_7d", lambda la, lo: _marine([31, 33, 34.2, 34, 32, 31, 30]))
    a = get_module("aquaculture").assess(COASTAL)
    assert a.risk_level == "danger"
    assert "sục khí" in a.recommendation or "giảm cho ăn" in a.recommendation.lower()


def test_aquaculture_warns_when_water_cold(offline, monkeypatch):
    monkeypatch.setattr(realdata, "marine_7d", lambda la, lo: _marine([24.5] * 7))
    assert get_module("aquaculture").assess(COASTAL).risk_level == "warning"


def test_aquaculture_flags_big_waves(offline, monkeypatch):
    monkeypatch.setattr(realdata, "marine_7d",
                        lambda la, lo: _marine([29.0] * 7, [0.5, 0.8, 2.6, 2.2, 1.0, 0.6, 0.5]))
    a = get_module("aquaculture").assess(COASTAL)
    assert a.risk_level == "warning"          # nước tốt nhưng sóng lớn
    assert "sóng" in a.headline.lower()


def test_aquaculture_honest_when_inland(offline):
    """Đà Lạt không có dữ liệu biển → phải nói thật, KHÔNG bịa số."""
    a = get_module("aquaculture").assess(INLAND)
    # "Ở đây không nuôi biển được" là một CÂU TRẢ LỜI dứt khoát, không phải một
    # lỗ hổng dữ liệu. Trước đây trả need_data nên một thửa lúa giữa đồng bằng
    # bị đếm là "thiếu dữ liệu ao nuôi", làm màn hình đầu báo thiếu nhiều hơn
    # thực tế.
    assert a.status == "out_of_scope"
    assert a.risk_level == "unknown"
    assert a.metrics == {}
