"""Giảm lưu lượng ra khỏi Neon (17/11/2026): cache_store nén khối lớn khi ghi và nhớ đệm trong tiến trình khi đọc.
Tháng 11 dự án Neon hết 5 GB truyền dữ liệu miễn phí vào ngày 16 — mỗi lượt mở thửa kéo lại nguyên khối JSON từ CSDL."""
from __future__ import annotations

import json
from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import db as dbmod
from app.db import KVCache
from app.services import cache_store


def _db(monkeypatch):
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    KVCache.metadata.create_all(eng)
    Session = sessionmaker(bind=eng, future=True)
    calls = {"n": 0}

    def counted():
        calls["n"] += 1
        return Session()

    monkeypatch.setattr(dbmod, "SessionLocal", counted)
    return Session, calls


def _raw(Session, key):
    with Session() as s:
        return s.get(KVCache, key).value


BIG = {"days": [{"date": f"2024-{m:02d}-{d:02d}", "precip": 1.5, "et0": 3.2, "ghi_chú": "mưa"}
                for m in range(1, 13) for d in range(1, 29)]}


def test_nen_khoi_lon_va_doc_lai_dung(monkeypatch):
    Session, _ = _db(monkeypatch)
    cache_store.put("realdata:a", BIG, ttl_seconds=100)
    raw = _raw(Session, "realdata:a")
    assert raw.startswith("z1:") and len(raw) * 2 < len(json.dumps(BIG, ensure_ascii=False))
    cache_store.memo_clear()                                   # buộc đọc lại từ CSDL, giải nén
    assert cache_store.get("realdata:a") == BIG


def test_khoi_nho_khong_nen_va_gia_tri_cu_van_doc_duoc(monkeypatch):
    Session, _ = _db(monkeypatch)
    cache_store.put("k:nho", [1, 2, 3], ttl_seconds=100)
    assert _raw(Session, "k:nho") == "[1, 2, 3]"
    with Session() as s:                                       # dòng ghi trước bản vá: JSON thường, không nén
        s.add(KVCache(key="k:cu", value=json.dumps(BIG), expires_at=cache_store._now() + timedelta(hours=1)))
        s.commit()
    assert cache_store.get("k:cu") == BIG


def test_doc_lai_khong_hoi_csdl_va_tra_ban_moi(monkeypatch):
    _, calls = _db(monkeypatch)
    cache_store.put("water:x", {"events": [1]}, ttl_seconds=100)
    n = calls["n"]
    a = cache_store.get("water:x")
    a["events"].append(99)                                     # nơi gọi sửa dict trả về…
    b = cache_store.get("water:x")
    assert calls["n"] == n and b == {"events": [1]}            # …không hỏi CSDL, không nhận bản đã bị sửa


def test_xoa_va_xoa_nhom_bo_ca_nho_dem(monkeypatch):
    _db(monkeypatch)
    cache_store.put("p:1", 1, ttl_seconds=100)
    cache_store.put("p:2", 2, ttl_seconds=100)
    cache_store.put("q:1", 3, ttl_seconds=100)
    cache_store.delete("p:1")
    assert cache_store.get("p:1") is None
    assert cache_store.clear_prefix("p") == 1
    assert cache_store.get("p:2") is None and cache_store.get("q:1") == 3


def test_het_han_thi_khong_tra_tu_nho_dem(monkeypatch):
    _db(monkeypatch)
    cache_store.put("t:1", "x", ttl_seconds=100)
    assert cache_store.get("t:1") == "x"
    later = cache_store._now() + timedelta(seconds=200)
    monkeypatch.setattr(cache_store, "_now", lambda: later)
    assert cache_store.get("t:1") is None


def test_doi_csdl_thi_bo_nho_dem(monkeypatch):
    _db(monkeypatch)
    cache_store.put("d:1", "csdl-1", ttl_seconds=100)
    assert cache_store.get("d:1") == "csdl-1"
    _db(monkeypatch)                                           # CSDL khác (test khác, hay đổi CSDL lúc chạy)
    assert cache_store.get("d:1") is None


def test_nho_dem_co_tran_byte(monkeypatch):
    _, calls = _db(monkeypatch)
    monkeypatch.setattr(cache_store, "_MEMO_MAX", 4000)
    for i in range(10):
        cache_store.put(f"b:{i}", "x" * 500, ttl_seconds=100)
    assert cache_store._memo_size <= 4000 and "b:0" not in cache_store._MEMO and "b:9" in cache_store._MEMO
    n = calls["n"]
    assert cache_store.get("b:0") == "x" * 500 and calls["n"] == n + 1   # bị đẩy khỏi nhớ đệm thì đọc lại CSDL
