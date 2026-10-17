"""Cảnh radar lỗi mạng KHÔNG được bỏ im lặng (18/10/2026): thử lại; còn lỗi thì ghi số cảnh thiếu vào kết quả."""
from __future__ import annotations

import pytest


def _items(n):
    return [{"id": f"S1_{i:03d}", "properties": {"datetime": f"2020-{1 + i // 28:02d}-{1 + i % 28:02d}T00:00:00Z"}} for i in range(n)]


@pytest.fixture
def env(monkeypatch):
    from app.services import cache_store, water_history as wh
    store, ttls = {}, {}
    monkeypatch.setattr(cache_store, "get", lambda k: store.get(k))

    def put(k, v, ttl_seconds=None):
        store[k] = v
        ttls[k] = ttl_seconds
    monkeypatch.setattr(cache_store, "put", put)
    monkeypatch.setattr(wh, "_items", lambda box, today: _items(30))
    monkeypatch.setattr(wh, "pick_track", lambda items: ("descending", 18, items))
    monkeypatch.setattr(wh.time, "sleep", lambda s: None)
    monkeypatch.setattr(wh, "_annotate", lambda r, lat=None, lon=None: r)
    return store, ttls


def _stats(v=-12.0):
    return {"properties": {"statistics": {"vv": {"percentile_10": 10 ** (v / 10), "percentile_25": 10 ** (v / 10),
                                                 "percentile_50": 10 ** (v / 10), "percentile_75": 10 ** (v / 10),
                                                 "mean": 10 ** (v / 10)}}}}


def test_canh_loi_lan_dau_duoc_doc_lai(env, monkeypatch):
    from app.services import mpc, water_history as wh
    calls = {}

    def call(url, payload=None, timeout=None):
        item = url.split("item=")[1].split("&")[0]
        calls[item] = calls.get(item, 0) + 1
        return None if item in ("S1_003", "S1_017") and calls[item] == 1 else _stats()   # lỗi một lần rồi được
    monkeypatch.setattr(mpc, "_call", call)
    r = wh.history(16.5, 107.5, use_cache=False)
    assert r["available"] and r["n_scenes"] == 30 and "n_failed" not in r
    store, ttls = env
    assert ttls[wh.cache_key(16.5, 107.5)] == wh._RESULT_TTL


def test_canh_loi_mai_ghi_vao_ket_qua_va_cache_ngan(env, monkeypatch):
    from app.services import mpc, water_history as wh
    monkeypatch.setattr(mpc, "_call", lambda url, payload=None, timeout=None: None if "item=S1_005" in url else _stats())
    r = wh.history(16.5, 107.5, use_cache=False)
    assert r["n_scenes"] == 29 and r["n_failed"] == 1 and r["failed_dates"] == ["2020-01-06"]
    assert "lọt" in r["failed_note"]
    store, ttls = env
    assert ttls[wh.cache_key(16.5, 107.5)] == wh._PARTIAL_TTL
    assert not any(k.startswith("s1vv") and "S1_005" in k for k in store)    # cảnh lỗi không bị cache thành "trống"


def test_canh_trong_khong_phai_loi(env, monkeypatch):
    from app.services import mpc, water_history as wh
    empty = {"properties": {"statistics": {"vv": {"percentile_10": None}}}}
    monkeypatch.setattr(mpc, "_call", lambda url, payload=None, timeout=None: empty if "item=S1_007" in url else _stats())
    r = wh.history(16.5, 107.5, use_cache=False)
    assert r["n_scenes"] == 29 and "n_failed" not in r
