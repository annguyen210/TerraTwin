"""Hộ chiếu thửa ghép 10 năm tròn (cache dùng chung) + đoạn đuôi — số liệu từng ngày y hệt một yêu cầu dài (18/10/2026)."""
from __future__ import annotations

from datetime import date, timedelta


def _series(a: str, b: str):
    d, e, out = date.fromisoformat(a), date.fromisoformat(b), []
    while d <= e:
        out.append({"day": len(out), "date": d.isoformat(), "precip": (d.toordinal() % 17) * 1.5, "et0": 3.0, "tmax": 30.0})
        d += timedelta(days=1)
    return out


def test_ghep_y_het_mot_yeu_cau_dai_va_dung_url_co_dinh(monkeypatch):
    from app.services import realdata
    calls = []

    def fake(lat, lon, start, end):
        calls.append((start, end))
        return _series(start, end)
    monkeypatch.setattr(realdata, "historical_weather", fake)
    last = date.today().year - 1
    start, end = f"{last - 9}-10-08", (date.today() - timedelta(days=10)).isoformat()
    got = realdata.historical_weather_stitched(16.5, 107.5, start, end)
    assert got == _series(start, end)                                     # cùng ngày, cùng giá trị, cùng chỉ số "day"
    assert calls == [(f"{last - 9}-01-01", f"{last}-12-31"), (f"{last + 1}-01-01", end)]   # khung cố định + đuôi


def test_khung_ngoai_10_nam_tron_goi_thang(monkeypatch):
    from app.services import realdata
    calls = []
    monkeypatch.setattr(realdata, "historical_weather", lambda la, lo, s, e: calls.append((s, e)) or _series(s, e))
    realdata.historical_weather_stitched(16.5, 107.5, "2001-01-01", "2003-12-31")
    assert calls == [("2001-01-01", "2003-12-31")]


def test_doan_duoi_hong_thi_quay_ve_mot_yeu_cau(monkeypatch):
    from app.services import realdata
    last = date.today().year - 1
    calls = []

    def fake(lat, lon, start, end):
        calls.append((start, end))
        return None if start == f"{last + 1}-01-01" else _series(start, end)
    monkeypatch.setattr(realdata, "historical_weather", fake)
    start, end = f"{last - 9}-06-01", (date.today() - timedelta(days=10)).isoformat()
    assert realdata.historical_weather_stitched(16.5, 107.5, start, end) == _series(start, end)
    assert calls[-1] == (start, end)
