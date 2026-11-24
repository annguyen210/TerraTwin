"""Kiểm A–Z 24/11/2026: "Độ hiếm tổ hợp thời tiết" mất 19 s ở thửa mới — mỗi thửa (toạ độ thô) một lượt tải 8 năm ERA5,
nền chỉ giữ trong tiến trình (Render khởi động lại là mất). Nay: ô 0,1°, nền lưu bền trong cache_store."""
from __future__ import annotations

from app.services import anomaly_ml, cache_store


def test_nen_khi_hau_dung_chung_o_va_song_qua_khoi_dong_lai(monkeypatch):
    if anomaly_ml._model() is None:
        import pytest
        pytest.skip("chưa có mô hình độ hiếm")
    kho, goi = {}, []
    monkeypatch.setattr(cache_store, "get", lambda k: kho.get(k))
    monkeypatch.setattr(cache_store, "put", lambda k, v, ttl_seconds=None: kho.__setitem__(k, v))
    from datetime import date, timedelta
    d0 = date(2018, 1, 1)
    rows = [{"date": (d0 + timedelta(days=i)).isoformat(), "precip": (i * 7) % 23 * 1.0, "et0": 3.5, "tmax": 30.0 + (i % 5),
             "tmin": 22.0, "wind": 10.0 + (i % 3)} for i in range(365 * 8)]

    def fake(lat, lon, start, end):
        goi.append((lat, lon))
        return rows
    monkeypatch.setattr(anomaly_ml, "_archive", fake)
    anomaly_ml._STATS.clear()
    a = anomaly_ml._local(20.9716, 106.2834)
    anomaly_ml._STATS.clear()                                   # "khởi động lại"
    b = anomaly_ml._local(20.9804, 106.2611)                    # thửa lân cận, cùng ô 0,1°
    assert a[0] is not None and len(goi) == 1 and a[2] == b[2]
