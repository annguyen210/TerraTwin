"""Module mặn — kiểm chứng 4 tính chất vật lý, tất định (không cần mạng).

1. Đo khoảng cách bờ biển đúng trên toàn quốc (đường bờ đa điểm).
2. KHÔNG báo động giả nội địa/miền núi.
3. MÙA VỤ: mặn là hiện tượng mùa khô — tháng 3 cao, tháng 9 thấp.
4. PHẠM VI: chỉ áp ngưỡng lúa trong vùng đồng bằng nhiễm mặn.
"""
from datetime import date

import pytest

from app.modules.registry import get_module
from app.schemas import Location
from app.services import datasources as ds
from app.services import realdata

DRY_PEAK = date(2026, 3, 15)    # đỉnh mùa khô
WET_PEAK = date(2026, 9, 15)    # đỉnh mùa lũ

BEN_TRE = (9.95, 106.60)        # cửa sông ĐBSCL, sát biển
HA_NOI = (21.03, 105.85)
DA_LAT = (11.94, 108.44)
DA_NANG = (16.05, 108.22)
HA_LONG = (20.95, 107.08)


@pytest.fixture
def low_land(monkeypatch):
    """Cao độ cửa sông thấp — bỏ phụ thuộc mạng."""
    monkeypatch.setattr(realdata, "elevation_m", lambda la, lo: 2.0)


# ---------- 1. Khoảng cách bờ biển ----------

def test_distance_to_coast_nationwide():
    assert ds.distance_to_coast_km(*HA_LONG) < 20      # Hạ Long sát biển
    assert ds.distance_to_coast_km(*HA_NOI) > 50       # Hà Nội sâu trong đất liền
    assert ds.distance_to_coast_km(*DA_LAT) > 40       # Đà Lạt cao nguyên


# ---------- 2. Không báo động giả nội địa ----------

def test_no_false_alarm_inland(monkeypatch):
    monkeypatch.setattr(realdata, "elevation_m", lambda la, lo: 22.0)
    assert ds.salinity_peak(*HA_NOI, today=DRY_PEAK) < 1.0     # kể cả đỉnh mùa khô
    monkeypatch.setattr(realdata, "elevation_m", lambda la, lo: 1480.0)
    assert ds.salinity_peak(*DA_LAT, today=DRY_PEAK) < 0.5


# ---------- 3. Mùa vụ ----------

def test_season_factor_peaks_in_dry_season():
    assert ds.salinity_season_factor(DRY_PEAK) > 0.95      # tháng 3: đỉnh
    assert ds.salinity_season_factor(WET_PEAK) < 0.20      # tháng 9: đáy
    assert ds.salinity_season_factor(date(2026, 8, 17)) < 0.30   # giữa mùa mưa


def test_season_factor_bounded_all_year():
    for m in range(1, 13):
        f = ds.salinity_season_factor(date(2026, m, 15))
        assert 0.10 <= f <= 1.0


def test_salinity_higher_in_dry_than_wet_season(low_land):
    dry = ds.salinity_peak(*BEN_TRE, today=DRY_PEAK)
    wet = ds.salinity_peak(*BEN_TRE, today=WET_PEAK)
    assert dry > wet * 3          # mùa khô cao hơn hẳn mùa lũ
    assert dry >= 4.0             # đỉnh mùa khô: chạm ngưỡng nguy hiểm
    assert wet < 1.0              # đỉnh mùa lũ: an toàn


def test_no_close_sluice_advice_in_flood_season(low_land, monkeypatch):
    """Hồi quy: bản cũ báo 4.87 g/L và khuyên 'ĐÓNG CỐNG' giữa tháng 8 —
    đúng đỉnh mùa mưa, khi sông Mekong đang xả lũ đẩy mặn ra biển."""
    import app.modules.salinity as salmod
    monkeypatch.setattr(
        salmod, "get_salinity_context",
        lambda la, lo: ds.get_salinity_context(la, lo, today=date(2026, 8, 17)))
    a = get_module("salinity").assess(Location(lat=BEN_TRE[0], lon=BEN_TRE[1]))
    assert a.risk_level != "danger"
    assert "ĐÓNG CỐNG" not in a.recommendation
    assert max(f.value for f in a.forecast) < 2.0   # cũ: 4.87


# ---------- 4. Phạm vi vùng ----------

def test_zone_detection():
    assert ds.salinity_zone(*BEN_TRE) == "Đồng bằng sông Cửu Long"
    assert ds.salinity_zone(20.86, 106.68) == "Đồng bằng sông Hồng"   # Hải Phòng
    assert ds.salinity_zone(*DA_NANG) is None
    assert ds.salinity_zone(*HA_LONG) is None
    assert ds.salinity_zone(12.24, 109.19) is None                    # Nha Trang


def test_coastal_city_outside_delta_is_out_of_scope(low_land):
    """Trung tâm Đà Nẵng KHÔNG được nhận ngưỡng lúa & lời khuyên đóng cống."""
    a = get_module("salinity").assess(Location(lat=DA_NANG[0], lon=DA_NANG[1]))
    assert a.status == "out_of_scope"
    assert a.risk_level == "unknown"
    assert a.forecast == []
    assert "cống" not in a.recommendation.lower()


def test_delta_location_gets_full_assessment(low_land):
    a = get_module("salinity").assess(Location(lat=BEN_TRE[0], lon=BEN_TRE[1]))
    assert a.status == "ok"
    assert len(a.forecast) == 7
    assert "Cửu Long" in a.detail
