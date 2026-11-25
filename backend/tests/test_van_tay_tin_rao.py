"""Nâng cấp 25/11/2026 — dấu vân tay tin rao: MinHash phát hiện tin chép/đăng lại; Isolation Forest chấm tin khác thường."""
from __future__ import annotations

import random

from app.services import listing_print as lp

A = ("Bán gấp lô đất thổ cư 120m2, cao ráo, không bao giờ ngập, cách sông 50m, sổ hồng riêng, đường ô tô tới nơi. "
     "Liên hệ 0912 345 678 anh Tâm.")


def test_minhash_giong_khac():
    a = lp.minhash(lp.shingles(A))
    b = lp.minhash(lp.shingles(A.replace("0912 345 678", "0987 111 222").replace("anh Tâm", "chị Lan")))
    c = lp.minhash(lp.shingles("Cho thuê nhà nguyên căn 3 tầng gần chợ, giá 8 triệu một tháng, ưu tiên gia đình nhỏ."))
    assert lp.similarity(a, b) >= 0.8          # chỉ đổi số điện thoại + tên → vẫn là cùng một bài
    assert lp.similarity(a, c) < 0.2
    assert len(a) == lp.K and lp.minhash(set()) == []


def test_khong_luu_chu_cua_tin():
    import json
    sig = lp.minhash(lp.shingles(A))
    blob = json.dumps(sig)
    assert set(blob) <= set("0123456789[], ")                 # chỉ là các số băm — không có chữ nào của tin


def test_isolation_forest_bat_diem_khac_thuong():
    rnd = random.Random(3)
    X = [[rnd.gauss(1, 0.5), rnd.gauss(0, 0.3), rnd.gauss(2, 0.5), 0, 0, 3.5, 0, 3] for _ in range(200)]
    m = lp.fit_iforest(X)
    normal = lp.iforest_score(m, [1, 0, 2, 0, 0, 3.5, 0, 3])
    odd = lp.iforest_score(m, [9, 6, 0, 5, 4, 6.5, 12, 15])
    assert odd > lp.IF_SCORE > normal


def test_ghi_va_so_trong_kho(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app import db as dbmod
    engine = create_engine(f"sqlite:///{tmp_path/'l.db'}")
    dbmod.Base.metadata.create_all(engine)
    monkeypatch.setattr(dbmod, "SessionLocal", sessionmaker(bind=engine, expire_on_commit=False))
    r1 = lp.record_and_compare(A, 16.46, 107.59, {"counts": {"contradicted": 1}})
    assert r1["reuse"] == []
    r2 = lp.record_and_compare(A, 16.461, 107.591, {})                  # kiểm lại cùng chỗ → không báo
    assert r2["reuse"] == []
    r3 = lp.record_and_compare(A.replace("anh Tâm", "chú Hai"), 10.24, 106.38, {})   # cùng bài, cách ~700 km
    assert r3["reuse"] and r3["reuse"][0]["similarity"] >= 0.8 and r3["reuse"][0]["km"] > 500
    assert r3["anomaly"] is None                                          # < 50 tin → chưa chấm khác thường
