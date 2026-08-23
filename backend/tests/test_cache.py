"""#3a — cache khí hậu BỀN: sống qua restart, không nã lại ERA5 mỗi lần."""
from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import db as dbmod
from app.db import KVCache
from app.services import cache_store


def test_cache_store_roundtrip(monkeypatch):
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    KVCache.metadata.create_all(eng)
    monkeypatch.setattr(dbmod, "SessionLocal", sessionmaker(bind=eng, future=True))
    cache_store.put("k1", [1.0, 2.0, 3.0], ttl_seconds=100)
    assert cache_store.get("k1") == [1.0, 2.0, 3.0]
    assert cache_store.get("missing") is None


def test_climatology_survives_restart(monkeypatch):
    """L1 mất (giả lập restart) → L2 (kv_cache) phải phục vụ, KHÔNG fetch lại ERA5."""
    from app.services import calibration as cal

    cal._CACHE.clear()
    store: dict = {}
    monkeypatch.setattr(cache_store, "get", lambda k: store.get(k))
    monkeypatch.setattr(cache_store, "put",
                        lambda k, v, ttl_seconds: store.__setitem__(k, v))

    calls = {"n": 0}

    def fake_hist(lat, lon, start, end):
        calls["n"] += 1
        d, d1 = date.fromisoformat(start), date.fromisoformat(end)
        rows, i = [], 0
        while d <= d1:
            rows.append({"day": i, "date": d.isoformat(),
                         "precip": 5.0 + (i % 30), "et0": 3.0, "tmax": 32.0})
            i += 1
            d += timedelta(days=1)
        return rows

    monkeypatch.setattr(cal.realdata, "historical_weather", fake_hist)
    # Chặn NỐT đường cao độ. Trước đây chỉ chặn historical_weather, nên
    # climatology() vẫn lặng lẽ gọi thật api.open-meteo.com/elevation qua
    # datasources.elevation_proxy. Test vẫn xanh chừng nào mạng còn nhanh —
    # đến lúc nhà cung cấp chặn thì nó không đỏ mà TREO, kéo cả bộ test từ
    # 144 giây lên hơn hai mươi phút. Một test "offline" mà còn sót một
    # đường ra mạng thì không phải test offline.
    monkeypatch.setattr(cal.realdata, "elevation_m", lambda la, lo: 5.0)
    monkeypatch.setattr(cal.realdata, "slope_deg", lambda la, lo, **k: None)

    when = date(2024, 6, 1)
    dist1 = cal.climatology("flood", 10.0, 106.0, today=when)
    assert dist1 and calls["n"] == 1
    assert store, "phải ghi vào cache bền (L2)"

    cal._CACHE.clear()                       # giả lập restart: L1 biến mất
    dist2 = cal.climatology("flood", 10.0, 106.0, today=when)
    assert dist2 == dist1
    assert calls["n"] == 1, "L2 phải phục vụ, KHÔNG được fetch lại ERA5"
