"""4 luồng nâng cao (S07 Explain · S03 Goal-Seek · S02 Time Machine · C10 Anomaly).

Tất cả chạy OFFLINE: giả lập nguồn dữ liệu để test tất định, không gọi mạng.
"""
from datetime import date, timedelta

import pytest

from app.services import anomaly, explain, goalseek, hazard, realdata, timemachine

LAT, LON = 15.87, 108.33      # Quảng Nam — có cả dốc lẫn mưa lớn


def _rows(precips, et0=4.0, tmax=33.0, start="2026-08-17"):
    d0 = date.fromisoformat(start)
    return [{"day": i, "date": (d0 + timedelta(days=i)).isoformat(),
             "precip": p, "et0": et0, "tmax": tmax}
            for i, p in enumerate(precips)]


WET = [10.0, 45.0, 120.0, 90.0, 30.0, 5.0, 0.0]
DRY = [0.0] * 7


@pytest.fixture
def offline(monkeypatch):
    """Cố định địa hình để không phụ thuộc mạng."""
    monkeypatch.setattr(realdata, "elevation_m", lambda la, lo: 3.0)
    monkeypatch.setattr(realdata, "slope_deg", lambda la, lo, step_m=500.0: 22.0)


@pytest.fixture
def wet_forecast(offline, monkeypatch):
    monkeypatch.setattr(realdata, "weather_7d", lambda la, lo: _rows(WET))


# ---------- lõi hazard dùng chung ----------

def test_hazard_core_covers_four_modules():
    assert set(hazard.IDS) == {"drought", "flood", "wildfire", "landslide"}
    for mid in hazard.IDS:
        assert hazard.supports(mid)
    assert not hazard.supports("salinity")


def test_transform_scales_rain_only():
    out = hazard.transform(_rows([10.0, 20.0]), rain_mult=2.0, temp_delta=1.0)
    assert [r["precip"] for r in out] == [20.0, 40.0]
    assert out[0]["tmax"] == 34.0
    assert out[0]["et0"] == 4.0        # ET₀ không bị đụng


# ---------- S07 Causal Explain ----------

def test_explain_rain_dominates_flood(wet_forecast):
    r = explain.explain("flood", LAT, LON)
    assert r["available"] is True
    rain = next(f for f in r["factors"] if "mưa" in f["factor"].lower())
    assert rain["contribution"] > 0
    assert sum(f["share_pct"] for f in r["factors"]) == pytest.approx(100.0, abs=0.5)


def test_explain_leave_one_out_is_exact(wet_forecast):
    """Bỏ mưa đi thì đỉnh phải đúng bằng peak_without mà explain báo."""
    r = explain.explain("flood", LAT, LON)
    rain = next(f for f in r["factors"] if "mưa" in f["factor"].lower())
    no_rain = hazard.peak_of(hazard.index_series("flood", LAT, LON, _rows(DRY)))
    assert rain["peak_without"] == pytest.approx(no_rain, abs=0.1)


def test_explain_slope_matters_for_landslide(wet_forecast):
    r = explain.explain("landslide", LAT, LON)
    assert any("dốc" in f["factor"].lower() for f in r["factors"])


def test_explain_rejects_non_hazard_module():
    assert explain.explain("salinity", LAT, LON) is None


def test_explain_refuses_without_real_data(offline, monkeypatch):
    monkeypatch.setattr(realdata, "weather_7d", lambda la, lo: None)
    r = explain.explain("flood", LAT, LON)
    assert r["available"] is False and r["factors"] == []


# ---------- S03 Goal-Seek ----------

def test_goalseek_finds_required_rain_cut(wet_forecast):
    r = goalseek.run("flood", LAT, LON)
    assert r["available"] is True
    rain = next(l for l in r["levers"] if l["lever"] == "Lượng mưa")
    if not r["safe_now"]:
        assert rain["kind"] == "required" and 0.0 <= rain["value"] <= 1.0
    else:
        assert rain["kind"] == "headroom"


def test_goalseek_solution_actually_reaches_target(wet_forecast):
    """Đáp án phải kiểm chứng được: chạy lại mô hình với hệ số đó."""
    r = goalseek.run("flood", LAT, LON)
    rain = next(l for l in r["levers"] if l["lever"] == "Lượng mưa")
    if rain["value"] is None:
        pytest.skip("không có nghiệm trong khoảng")
    rows = _rows(WET)
    peak = hazard.peak_of(hazard.index_series(
        "flood", LAT, LON, hazard.transform(rows, rain_mult=rain["value"])))
    assert peak == pytest.approx(r["target"], abs=1.0)


def test_goalseek_reports_headroom_when_safe(offline, monkeypatch):
    monkeypatch.setattr(realdata, "weather_7d", lambda la, lo: _rows(DRY))
    r = goalseek.run("flood", LAT, LON)
    assert r["safe_now"] is True
    assert next(l for l in r["levers"] if l["lever"] == "Lượng mưa")["kind"] == "headroom"


def test_goalseek_offers_elevation_lever_for_flood(wet_forecast):
    assert any(l["lever"] == "Cao độ nền" for l in goalseek.run("flood", LAT, LON)["levers"])


def test_goalseek_rejects_non_hazard_module():
    assert goalseek.run("carbon", LAT, LON) is None


# ---------- S02 Time Machine (analog ensemble) ----------

def _fake_archive(lat, lon, start, end):
    """10 năm dữ liệu giả: 3 năm mưa lớn, còn lại khô → xác suất ~30%."""
    y0, y1 = int(start[:4]), int(end[:4])
    out = []
    for y in range(y0, y1 + 1):
        wet_year = y % 3 == 0
        d = date(y, 1, 1)
        while d.year == y:
            out.append({"day": 0, "date": d.isoformat(),
                        "precip": 110.0 if wet_year else 1.0,
                        "et0": 4.0, "tmax": 33.0})
            d += timedelta(days=1)
    return out


def test_timemachine_probability_from_real_years(offline, monkeypatch):
    monkeypatch.setattr(realdata, "historical_weather", _fake_archive)
    monkeypatch.setattr(realdata, "weather_7d", lambda la, lo: _rows(WET))
    r = timemachine.run("flood", LAT, LON, years=9, today=date(2026, 8, 17))
    assert r["available"] is True
    assert r["years"] == 9
    assert 20 <= r["prob_danger_pct"] <= 45          # ~1/3 số năm là năm mưa
    assert r["p10"] <= r["p50"] <= r["p90"]
    assert r["worst_year"]["peak"] >= r["best_year"]["peak"]
    assert len(r["members"]) == 9


def test_timemachine_ranks_current_forecast(offline, monkeypatch):
    monkeypatch.setattr(realdata, "historical_weather", _fake_archive)
    monkeypatch.setattr(realdata, "weather_7d", lambda la, lo: _rows(WET))
    r = timemachine.run("flood", LAT, LON, years=9, today=date(2026, 8, 17))
    assert r["current_peak"] is not None
    assert 0 <= r["current_rank_pct"] <= 100


def test_timemachine_handles_missing_archive(offline, monkeypatch):
    monkeypatch.setattr(realdata, "historical_weather", lambda *a: None)
    r = timemachine.run("flood", LAT, LON)
    assert r["available"] is False


# ---------- C10 Anomaly ----------

def test_anomaly_flags_extreme_rain(offline, monkeypatch):
    def calm_archive(lat, lon, start, end):
        rows = _fake_archive(lat, lon, start, end)
        for r in rows:              # mọi năm đều khô → tuần mưa lớn là bất thường
            r["precip"] = 2.0
        return rows
    monkeypatch.setattr(realdata, "historical_weather", calm_archive)
    monkeypatch.setattr(realdata, "weather_7d", lambda la, lo: _rows(WET))
    r = anomaly.run(LAT, LON, years=9, today=date(2026, 8, 17))
    assert r["available"] is True
    rain = next(m for m in r["metrics"] if m["key"] == "precip")
    assert rain["current"] > rain["normal_mean"]
    assert rain["percentile"] == 100
    assert "bất thường" in r["headline"].lower() or rain["alert"]


def test_anomaly_quiet_when_normal(offline, monkeypatch):
    def archive(lat, lon, start, end):
        rows = _fake_archive(lat, lon, start, end)
        for i, r in enumerate(rows):
            r["precip"] = 10.0 + (i % 5)      # dao động nhẹ quanh 12
        return rows
    monkeypatch.setattr(realdata, "historical_weather", archive)
    monkeypatch.setattr(realdata, "weather_7d",
                        lambda la, lo: _rows([12.0] * 7))
    r = anomaly.run(LAT, LON, years=9, today=date(2026, 8, 17))
    rain = next(m for m in r["metrics"] if m["key"] == "precip")
    assert rain["level"] in ("normal", "notable")


def test_anomaly_needs_both_sources(offline, monkeypatch):
    monkeypatch.setattr(realdata, "historical_weather", lambda *a: None)
    monkeypatch.setattr(realdata, "weather_7d", lambda la, lo: _rows(WET))
    assert anomaly.run(LAT, LON)["available"] is False
