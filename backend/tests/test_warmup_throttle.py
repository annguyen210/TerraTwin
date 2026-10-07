"""Render free dậy nhiều lần mỗi ngày: hâm nóng chỉ chạy một lần mỗi N giờ (mốc nằm trong CSDL)."""
from __future__ import annotations

import asyncio

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def test_hai_lan_khoi_dong_lien_nhau_chi_ham_nong_mot_lan(tmp_path, monkeypatch):
    from app import db as dbmod, main, warm
    engine = create_engine(f"sqlite:///{tmp_path/'w.db'}", connect_args={"check_same_thread": False})
    dbmod.Base.metadata.create_all(engine)
    monkeypatch.setattr(dbmod, "engine", engine)
    monkeypatch.setattr(dbmod, "SessionLocal", sessionmaker(bind=engine, autoflush=False, expire_on_commit=False))
    calls = []
    monkeypatch.setattr(warm, "DEMO", [(16.46, 107.59, "Huế"), (21.03, 105.85, "Hà Nội")])
    monkeypatch.setattr(warm, "warm_one", lambda lat, lon: (calls.append((lat, lon)), (18, 18))[1])
    monkeypatch.setattr(main, "_WARMUP_EVERY_H", 6.0)

    async def no_sleep(_s):
        return None
    monkeypatch.setattr(asyncio, "sleep", no_sleep)

    asyncio.run(main._startup_warmup())
    assert len(calls) == 2
    asyncio.run(main._startup_warmup())          # Render vừa ngủ dậy lần nữa
    assert len(calls) == 2, "lần dậy thứ hai trong 6 giờ không được dội nguồn dữ liệu"

    monkeypatch.setattr(main, "_WARMUP_EVERY_H", 0.0)   # 0 = luôn hâm (giữ hành vi cũ khi cần)
    asyncio.run(main._startup_warmup())
    assert len(calls) == 4
