"""Thang CHƯA hiệu chuẩn không được phát cảnh báo (8/11/2026).

Ruộng Tân Trụ (Long An), mưa dự báo ~10 mm/ngày: thang tuyệt đối 75,4 ngày 12/11 → "NGUY CƠ NGẬP CAO, sẵn sàng sơ tán"
trong Kế hoạch thửa (lượt quét riêng, khí hậu nền 10 năm chưa về), trong khi thang hiệu chuẩn cùng ngày 21,7 và thẻ
cùng trang báo "7 ngày tới: yên". Điểm chưa hiệu chuẩn = chưa biết, như rủi ro vùng nguyên liệu (group_d).

Chạy OFFLINE: giả lập dự báo, địa hình và khí hậu nền.
"""
from datetime import date, timedelta

import pytest

from app.modules.registry import get_module
from app.schemas import Location
from app.services import calibration as cal
from app.services import datasources as ds
from app.services import hazard, realdata, terrascore

LAT, LON = 10.6512, 106.3478
TAN_TRU = [5.15, 2.05, 3.1, 9.9, 9.8, 10.35, 8.05]      # mưa dự báo thật 8–14/11/2026 (mm)


def _rows(precips, start="2026-11-08"):
    d0 = date.fromisoformat(start)
    return [{"day": i, "date": (d0 + timedelta(days=i)).isoformat(), "precip": p, "et0": 3.5, "tmax": 31.0}
            for i, p in enumerate(precips)]


@pytest.fixture
def tan_tru(monkeypatch):
    cal._CACHE.clear()
    monkeypatch.setattr(realdata, "weather_7d", lambda la, lo: _rows(TAN_TRU))
    monkeypatch.setattr(realdata, "elevation_m", lambda la, lo: 2.0)
    monkeypatch.setattr(realdata, "slope_deg", lambda la, lo, step_m=500.0: 0.1)
    monkeypatch.setattr(ds, "elevation_context", lambda la, lo: (2.0, True))
    monkeypatch.setattr(ds, "slope_context", lambda la, lo: (0.1, True))
    monkeypatch.setattr(ds, "river_discharge_context", lambda la, lo: None)
    yield
    cal._CACHE.clear()


def test_thang_tuyet_doi_bao_dong_oan_o_tan_tru(tan_tru, monkeypatch):
    """Tiền đề: cùng dự báo, thang tuyệt đối vượt ngưỡng nguy hiểm (≥ 70) dù mưa chỉ ~10 mm/ngày."""
    monkeypatch.setattr(cal, "climatology", lambda *a, **k: None)
    assert hazard.peak_of(hazard.index_series_absolute("flood", LAT, LON, _rows(TAN_TRU))) >= 70.0


@pytest.mark.parametrize("mid", sorted(hazard.IDS))
def test_chua_hieu_chuan_thi_chua_biet_khong_canh_bao(tan_tru, monkeypatch, mid):
    monkeypatch.setattr(cal, "climatology", lambda *a, **k: None)
    a = get_module(mid).assess(Location(lat=LAT, lon=LON))
    assert a.status == "need_data" and a.risk_level == "unknown" and a.is_real is False
    assert "khí hậu nền" in a.headline


def test_terrascore_khong_tru_diem_vi_thang_chua_hieu_chuan(tan_tru, monkeypatch):
    monkeypatch.setattr(cal, "climatology", lambda *a, **k: None)
    loc = Location(lat=LAT, lon=LON)
    got = {mid: get_module(mid).assess(loc) for mid in hazard.IDS}
    t = terrascore.compute(loc, got, reassess=False)
    assert t.grade == "—" and t.score is None


def test_co_khi_hau_nen_thi_van_cham_binh_thuong(tan_tru, monkeypatch):
    """Có khí hậu nền: lũ chấm trên thang hiệu chuẩn — dữ liệu thật, không báo động với mưa ~10 mm/ngày."""
    dist = sorted((i / 2000) ** 2 * 400.0 for i in range(2000))
    monkeypatch.setattr(cal, "climatology", lambda *a, **k: dist)
    a = get_module("flood").assess(Location(lat=LAT, lon=LON))
    assert a.status != "need_data" and a.is_real is True and a.risk_level == "safe"
