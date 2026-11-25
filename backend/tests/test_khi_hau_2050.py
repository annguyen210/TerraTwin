"""Khí hậu 2050 của thửa (nâng cấp 24/11/2026): chỉ số theo năm, hiệu số so với chính mô hình, dải giữa mô hình,
nước biển dâng cho thửa ven biển thấp, nhớ đệm chỉ số (không lưu chuỗi thô) và hạn mức vùng mới."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.services import cache_store, climate_2050 as c, reqlang


def _days(y0, y1, tmax, pr):
    d0, out = date(y0, 1, 1), []
    while d0.year <= y1:
        out.append(d0.isoformat())
        d0 += timedelta(days=1)
    return out, [tmax(i, x) for i, x in enumerate(out)], [pr(i, x) for i, x in enumerate(out)]


def test_chi_so_theo_nam():
    dates, t, p = _days(2001, 2010, lambda i, d: 36.0 if d[5:7] == "05" and int(d[8:]) <= 10 else 30.0,
                        lambda i, d: 60.0 if d[5:] in ("09-15", "10-02") else (0.0 if d[5:7] in ("01", "02") else 5.0))
    r = c.yearly_indicators(dates, t, p)
    assert r["years"] == 10 and r["tx35"] == 10 and r["r50"] == 2 and r["rx1day"] == 60.0
    assert r["cdd"] >= 59                                # tháng 1–2 khô liền
    assert c.yearly_indicators(dates[:100], t[:100], p[:100]) is None      # quá ít năm


def test_delta_so_voi_chinh_mo_hinh_va_dai():
    base = {m: {"tx35": 7.0, "r50": 1.5, "rx1day": 60.0, "cdd": 30.0, "prcptot": 1600.0} for m in c.MODELS}
    fut = {"EC_Earth3P_HR": {"tx35": 18.0, "r50": 1.0, "rx1day": 66.0, "cdd": 31.0, "prcptot": 1700.0},
           "MRI_AGCM3_2_S": {"tx35": 20.0, "r50": 2.0, "rx1day": 54.0, "cdd": 32.0, "prcptot": 1580.0},
           "MPI_ESM1_2_XR": {"tx35": 25.0, "r50": 1.8, "rx1day": 75.0, "cdd": 40.0, "prcptot": 1650.0}}
    rows = {r["id"]: r for r in c.combine(base, fut)}
    assert rows["tx35"]["delta"] == 13.0 and rows["tx35"]["delta_min"] == 11.0 and rows["tx35"]["agree"] is True
    assert rows["rx1day"]["how"] == "pct" and rows["rx1day"]["delta"] == 10.0 and rows["rx1day"]["agree"] is False
    assert c.combine({"EC_Earth3P_HR": base["EC_Earth3P_HR"]}, fut) is None      # < 2 mô hình


def _fake_api(monkeypatch, calls):
    def fetch(lat, lon, period):
        calls.append(period)
        y0, y1 = int(period[0][:4]), int(period[1][:4])
        hot = 36.0 if y0 >= 2041 else 30.0
        dates, t, p = _days(y0, min(y1, y0 + 6), lambda i, d: hot if d[5:7] == "06" else 30.0, lambda i, d: 3.0)
        return {"daily": {"time": dates, **{f"temperature_2m_max_{m}": t for m in c.MODELS},
                          **{f"precipitation_sum_{m}": p for m in c.MODELS}}}
    monkeypatch.setattr(c, "_fetch_period", fetch)


def test_nho_dem_chi_so_khong_luu_chuoi_tho_va_ven_bien(monkeypatch):
    from app.services import datasources as ds
    reqlang.set_lang("vi")
    kho, calls = {}, []
    monkeypatch.setattr(cache_store, "get", lambda k: kho.get(k))
    monkeypatch.setattr(cache_store, "put", lambda k, v, ttl_seconds=None: kho.__setitem__(k, v))
    _fake_api(monkeypatch, calls)
    monkeypatch.setattr(ds, "elevation_proxy", lambda la, lo: 2.0)
    a = c.assess(10.04427, 106.5902)                         # Ba Tri: ven biển, thấp, ĐBSCL
    assert a["available"] and len(calls) == 2
    tx = next(i for i in a["indicators"] if i["id"] == "tx35")
    assert tx["delta"] == 30.0 and "cùng chiều" in tx["trend"]
    assert "0.23 m" in a["sea_level"]["text"] and "lún" in a["sea_level"]["text"]
    assert all("daily" not in str(v) for v in kho.values())   # chỉ lưu chỉ số
    c.assess(10.2, 106.7)                                    # cùng ô 0,5° → không gọi lại
    assert len(calls) == 2
    inland = c.assess(21.03, 105.85)                         # Hà Nội: không phần nước biển
    assert "sea_level" not in inland


def test_nguon_hong_thi_noi_ro(monkeypatch):
    reqlang.set_lang("vi")
    monkeypatch.setattr(cache_store, "get", lambda k: None)
    monkeypatch.setattr(c, "_fetch_period", lambda *a: None)
    r = c.assess(20.9716, 106.2834)
    assert r["available"] is False and "thử lại" in r["message"]


def test_api_ngoai_viet_nam_va_han_muc(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services import quota
    monkeypatch.setattr(cache_store, "get", lambda k: None)
    monkeypatch.setattr(c, "assess", lambda lat, lon: {"available": True})
    cl = TestClient(app)
    assert cl.get("/api/climate2050?lat=48.8&lon=2.3").status_code == 422
    monkeypatch.setattr(quota, "take", lambda *a, **k: 120)
    r = cl.get("/api/climate2050?lat=20.97&lon=106.28")
    assert r.status_code == 429 and r.headers.get("Retry-After") == "120"


def test_gia_tri_2050_luon_khop_con_so_thay_doi():
    """Bộ chấm trợ lý v4 25/11/2026: trung vị riêng rẽ có thể ngược chiều (31.9 → 30.4 mm mà +8.1%)."""
    from app.services import climate_2050 as c
    r = {"indicators": [{"id": "rx1day", "unit": "mm", "how": "pct", "base": 31.9, "future": 30.4, "delta": 8.1,
                         "delta_min": -3.0, "delta_max": 12.0, "agree": False},
                        {"id": "cdd", "unit": "days", "how": "abs", "base": 54.5, "future": 48.9, "delta": 1.2,
                         "delta_min": -6.0, "delta_max": 4.0, "agree": False}], "models": list(c.MODELS)}
    out = c.localize(r, 12.73, 108.05)
    rx, cdd = out["indicators"]
    assert rx["future"] == 34.5 and rx["future_median"] == 30.4 and "34.5" in rx["future_txt"]
    assert cdd["future"] == 55.7 and "55.7" in cdd["future_txt"]
