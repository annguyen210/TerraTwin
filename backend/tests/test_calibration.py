"""Tầng hiệu chuẩn theo khí hậu từng điểm — sửa gốc bệnh báo động giả.

Bối cảnh đo được trước khi sửa (2026-08-17): thang tuyệt đối bão hòa, mức
"nguy hiểm" nổ 45.8% số ngày ở Huế và 60.6% ở Quảng Nam trong năm 2022.

Test chạy OFFLINE: tự dựng phân bố khí hậu, không gọi mạng.
"""
from datetime import date, timedelta

import pytest

from app.services import calibration as cal
from app.services import hazard, realdata

LAT, LON = 15.87, 108.33


def _rows(precips, et0=4.0, tmax=33.0, start="2026-08-17"):
    d0 = date.fromisoformat(start)
    return [{"day": i, "date": (d0 + timedelta(days=i)).isoformat(),
             "precip": p, "et0": et0, "tmax": tmax}
            for i, p in enumerate(precips)]


@pytest.fixture
def terrain(monkeypatch):
    monkeypatch.setattr(realdata, "elevation_m", lambda la, lo: 3.0)
    monkeypatch.setattr(realdata, "slope_deg", lambda la, lo, step_m=500.0: 22.0)


# ---------- Ánh xạ phân vi ----------

def test_percentile_mapping_hits_design_points():
    assert cal.map_percentile(0) == pytest.approx(0.0)
    assert cal.map_percentile(90) == pytest.approx(40.0)   # ngưỡng cảnh báo
    assert cal.map_percentile(97) == pytest.approx(70.0)   # ngưỡng nguy hiểm
    assert cal.map_percentile(100) == pytest.approx(100.0)


def test_percentile_mapping_is_monotonic():
    vals = [cal.map_percentile(p) for p in range(0, 101)]
    assert vals == sorted(vals)


def test_percentile_of_positions_correctly():
    dist = list(range(100))          # 0..99
    assert cal.percentile_of(-5, dist) == 0.0
    assert cal.percentile_of(50, dist) == pytest.approx(50.0)
    assert cal.percentile_of(999, dist) == pytest.approx(100.0)


# ---------- Động lực thô KHÔNG bị chặn trần (gốc bệnh cũ) ----------

def test_raw_flood_does_not_saturate(terrain):
    """Thang cũ chạm trần 100; thang thô phải còn phân biệt được mưa to/rất to."""
    from app.services import datasources as ds
    big = _rows([50.0] * 7)
    huge = _rows([200.0] * 7)
    old_big = max(v for _, _, v in ds.flood_index(big, 3.0))
    old_huge = max(v for _, _, v in ds.flood_index(huge, 3.0))
    assert old_big == old_huge == 100.0          # bằng chứng bão hòa của bản cũ

    new_big = max(v for _, _, v in cal.raw_flood(big, 3.0))
    new_huge = max(v for _, _, v in cal.raw_flood(huge, 3.0))
    assert new_huge > new_big * 2                # thang thô vẫn phân biệt được


def test_raw_landslide_zero_on_flat_ground():
    heavy = _rows([120.0] * 7)
    assert max(v for _, _, v in cal.raw_landslide(heavy, slope=0.0)) == 0.0
    assert max(v for _, _, v in cal.raw_landslide(heavy, slope=25.0)) > 50.0


# ---------- Tỉ lệ báo động theo THIẾT KẾ ----------

def _synthetic_dist(n=2000, top=200.0):
    """Phân bố khí hậu giả lập, lệch phải như mưa thật.

    `top` là đỉnh mưa tích lũy 7 ngày của vùng — đặt quá cao thì ngay cả mưa
    cực đoan cũng chỉ là phân vi tầm thường (chính bẫy đã làm test đầu sai).
    """
    return sorted((i / n) ** 2 * top for i in range(n))


def test_alarm_rate_is_about_3pct_by_design(terrain, monkeypatch):
    dist = _synthetic_dist()
    monkeypatch.setattr(cal, "climatology", lambda *a, **k: dist)
    ar = cal.alarm_rate("flood", LAT, LON, threshold=70.0)
    assert 0.0 <= ar["alarm_rate_pct"] <= 4.0     # thiết kế ~3%


def test_warning_rate_is_about_10pct_by_design(terrain, monkeypatch):
    dist = _synthetic_dist()
    monkeypatch.setattr(cal, "climatology", lambda *a, **k: dist)
    ar = cal.alarm_rate("flood", LAT, LON, threshold=40.0)
    assert 5.0 <= ar["alarm_rate_pct"] <= 12.0    # thiết kế ~10%


def test_calibrated_series_stays_in_range(terrain, monkeypatch):
    dist = _synthetic_dist()
    monkeypatch.setattr(cal, "climatology", lambda *a, **k: dist)
    s, ok = cal.calibrated_series("flood", LAT, LON, _rows([80.0] * 7))
    assert ok
    assert all(0.0 <= v <= 100.0 for _, _, v in s)


# ---------- Chốt tuyệt đối: cực đoan so với hư không ----------

def test_absolute_floor_blocks_alarm_in_dry_climate(terrain, monkeypatch):
    """Vùng gần như không mưa: 3 mm là P100 nhưng KHÔNG được báo nguy hiểm."""
    bone_dry = sorted([0.0] * 1900 + [0.1 * i for i in range(100)])
    monkeypatch.setattr(cal, "climatology", lambda *a, **k: bone_dry)
    s, ok = cal.calibrated_series("flood", LAT, LON, _rows([3.0] * 7))
    assert ok
    assert max(v for _, _, v in s) < 40.0        # bị chốt về an toàn


def test_floor_does_not_block_genuinely_heavy_rain(terrain, monkeypatch):
    """Mưa vượt hẳn đỉnh lịch sử của vùng thì PHẢI nổ mức nguy hiểm."""
    dist = _synthetic_dist()
    monkeypatch.setattr(cal, "climatology", lambda *a, **k: dist)
    s, ok = cal.calibrated_series("flood", LAT, LON, _rows([150.0] * 7))
    assert max(v for _, _, v in s) >= 70.0


def test_index_rises_with_rain(terrain, monkeypatch):
    """Tính đơn điệu — điều kiện cần để Goal-Seek tìm kiếm nhị phân đúng."""
    dist = _synthetic_dist()
    monkeypatch.setattr(cal, "climatology", lambda *a, **k: dist)
    peaks = []
    for mm in (5.0, 20.0, 50.0, 100.0):
        s, _ = cal.calibrated_series("flood", LAT, LON, _rows([mm] * 7))
        peaks.append(max(v for _, _, v in s))
    assert peaks == sorted(peaks)


# ---------- Lùi an toàn khi offline ----------

def test_falls_back_to_absolute_when_no_climatology(terrain, monkeypatch):
    monkeypatch.setattr(cal, "climatology", lambda *a, **k: None)
    s, ok = hazard.index_series_calibrated("flood", LAT, LON, _rows([40.0] * 7))
    assert ok is False                            # phải báo rõ là CHƯA hiệu chuẩn
    assert s                                      # nhưng vẫn có kết quả để app chạy


def test_terrain_override_uses_same_calibration(terrain, monkeypatch):
    """Explain/Goal-Seek ép địa hình phải đi qua cùng thang, nếu không phần
    chênh lệch là chênh giữa hai thang đo chứ không phải đóng góp thật."""
    dist = _synthetic_dist()
    monkeypatch.setattr(cal, "climatology", lambda *a, **k: dist)
    rows = _rows([60.0] * 7)
    low, ok1 = cal.calibrated_with_terrain("flood", LAT, LON, rows, terrain=2.0)
    high, ok2 = cal.calibrated_with_terrain("flood", LAT, LON, rows, terrain=60.0)
    assert ok1 and ok2
    assert max(v for _, _, v in high) <= max(v for _, _, v in low)
