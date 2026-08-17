"""Các hàm chỉ số THUẦN — dùng chung cho forecast/what-if/backtest.

Kiểm tra hành vi vật lý (không cần mạng): mưa nhiều → ngập/sạt lở cao hơn;
khô → hạn/cháy cao hơn; đồng bằng phẳng → sạt lở ~0.
"""
from app.services import datasources as ds


def _rows(precips, et0=3.0, tmax=32.0):
    return [{"day": i, "date": f"2020-10-{i+1:02d}", "precip": p, "et0": et0, "tmax": tmax}
            for i, p in enumerate(precips)]


def _peak(series):
    return max(v for _, _, v in series)


def test_flood_increases_with_rain():
    dry = _rows([0, 0, 0, 0, 0, 0, 0])
    wet = _rows([20, 40, 60, 80, 60, 40, 20])
    assert _peak(ds.flood_index(wet, elev=5.0)) > _peak(ds.flood_index(dry, elev=5.0))


def test_flood_lower_on_high_ground():
    # mưa vừa để đỉnh không chạm trần 100 → khác biệt cao độ mới nhìn thấy được
    moderate = _rows([10, 10, 10, 10, 10, 10, 10])
    assert _peak(ds.flood_index(moderate, elev=30.0)) < _peak(ds.flood_index(moderate, elev=2.0))


def test_drought_rises_when_dry_and_hot():
    dry = _rows([0, 0, 0, 0, 0, 0, 0], et0=6.0)
    wet = _rows([15, 15, 15, 15, 15, 15, 15], et0=3.0)
    assert _peak(ds.drought_index(dry)) > _peak(ds.drought_index(wet))


def test_landslide_flat_delta_near_zero():
    heavy = _rows([100, 100, 100, 100, 100, 100, 100])
    assert _peak(ds.landslide_index(heavy, slope=0.2)) < 5.0     # đồng bằng: an toàn
    assert _peak(ds.landslide_index(heavy, slope=25.0)) > 50.0   # núi dốc + mưa: nguy hiểm


def test_wildfire_high_when_hot_dry():
    hot_dry = _rows([0, 0, 0, 0, 0, 0, 0], tmax=40.0)
    cool_wet = _rows([20, 20, 20, 20, 20, 20, 20], tmax=28.0)
    assert _peak(ds.wildfire_index(hot_dry)) > _peak(ds.wildfire_index(cool_wet))
