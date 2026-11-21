"""Kiểm A–Z 21/11/2026, P1-5 — lần gọi đầu /api/scorecard?days=90 mất 40 s, /api/heatmap/flood 37 s. Mục tiêu < 5 s khi máy
chủ đã thức: trả ngay bản đã tính (bền, sống qua khởi động lại), cũ thì tính lại ở nền."""
from __future__ import annotations

import threading
import time

from app.services import cache_store


class _NgayLap:
    """Thay threading.Thread trong test: chạy đích ngay khi start() để kiểm kết quả tính lại."""
    def __init__(self, target, **k):
        self.target = target

    def start(self):
        self.target()


def test_swr_moi_cu_chua_co(monkeypatch):
    monkeypatch.setattr(threading, "Thread", _NgayLap)
    key = cache_store.make_key("swrtest", time.time())
    goi = []
    tinh = lambda: goi.append(1) or {"v": len(goi)}        # noqa: E731
    assert cache_store.swr(key, tinh, 60, 3600) == ({"v": 1}, "computed")
    assert cache_store.swr(key, tinh, 60, 3600) == ({"v": 1}, "fresh") and len(goi) == 1
    cache_store.put(key, {"at": time.time() - 120, "data": {"v": "cu"}}, 3600)      # đã cũ 2 phút
    d, st = cache_store.swr(key, tinh, 60, 3600)
    assert (d, st) == ({"v": "cu"}, "stale")                 # trả NGAY bản cũ…
    assert cache_store.swr(key, tinh, 60, 3600) == ({"v": 2}, "fresh")   # …và luồng nền đã tính lại


def test_swr_tinh_lai_hong_thi_giu_ban_cu(monkeypatch):
    monkeypatch.setattr(threading, "Thread", _NgayLap)
    key = cache_store.make_key("swrtest2", time.time())
    cache_store.put(key, {"at": time.time() - 999, "data": "cu"}, 3600)
    def hong():
        raise RuntimeError("mạng")
    assert cache_store.swr(key, hong, 60, 3600) == ("cu", "stale")
    assert cache_store.get(key)["data"] == "cu"


def test_so_diem_doc_ban_ben_sau_khi_khoi_dong_lai(monkeypatch):
    from fastapi.testclient import TestClient

    from app import routes_trust
    from app.main import app
    from app.services import scorecard
    dem = {"n": 0}
    real = scorecard.summary
    def dem_summary(db, *a, **k):
        if not k.get("module_id"):
            dem["n"] += 1
        return real(db, *a, **k)
    monkeypatch.setattr(scorecard, "summary", dem_summary)
    routes_trust._sc_clear()
    with TestClient(app) as c:
        a = c.get("/api/scorecard?days=90").json()
        routes_trust._SC_CACHE.clear()                       # giả lập khởi động lại: mất cache RAM, còn bản bền
        t = time.time()
        b = c.get("/api/scorecard?days=90").json()
        assert time.time() - t < 5
    assert dem["n"] == 1 and a == b


def test_ban_do_nhiet_cu_tra_ngay_kem_co_stale(monkeypatch):
    from app.services import heatmap
    monkeypatch.setattr(threading, "Thread", _NgayLap)
    goi = []
    monkeypatch.setattr(heatmap, "_build", lambda *a: goi.append(1) or {"cells": [], "headline": f"lần {len(goi)}"})
    r1 = heatmap.build("flood", 20.97, 106.28)
    assert r1["cached"] is False and r1["stale"] is False and len(goi) == 1
    key = cache_store.make_key("heatmap2", "flood", 20.97, 106.28, 8.0, 7)
    cache_store.put(key, {"at": time.time() - 7200, "data": {"cells": [], "headline": "cũ"}}, 86400)
    r2 = heatmap.build("flood", 20.97, 106.28)
    assert r2["headline"] == "cũ" and r2["stale"] is True and r2["cached"] is True
    assert heatmap.build("flood", 20.97, 106.28)["headline"] == "lần 2"
