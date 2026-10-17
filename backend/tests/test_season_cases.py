"""Việc 5 (v3, 17/10/2026): "ruộng có ngập thật" rơi vào đợt radar v1 "ngoài mùa" → lưu làm ca kiểm thật cho v4."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.mua_lu_that
LAT, LON = 16.52, 107.59


@pytest.fixture
def env(monkeypatch):
    from app.db import SessionLocal
    from app.services import cache_store, flood_season as fs, water_history as wh
    hist = {"available": True, "events": [{"start": "2024-09-19", "end": "2024-09-19"}, {"start": "2023-10-19", "end": "2023-10-19"}]}
    key = wh.cache_key(LAT, LON)
    real = cache_store.get
    monkeypatch.setattr(cache_store, "get", lambda k: hist if k == key else real(k))
    monkeypatch.setattr(fs, "season", lambda la, lo: {"months": [1, 10, 11, 12]})
    db = SessionLocal()
    yield db
    db.rollback()
    db.close()


def _obs(**kw):
    from app.db import Observation
    base = dict(user_id=None, plot_id=None, lat=LAT, lon=LON, module_id="flood", observed_on="2024-09-21",
                outcome="occurred", note="", source="onetap")
    return Observation(**{**base, **kw})


def test_ngap_that_roi_vao_dot_ngoai_mua_thanh_ca_v4(env):
    from app.services import season_cases
    row = season_cases.capture(env, _obs())
    assert row is not None and row.event_start == "2024-09-19" and row.v1_label == "out" and row.season_months == "1,10,11,12"


def test_khong_luu_khi_dot_trong_mua_khong_ngap_hoac_khong_co_dot(env):
    from app.services import season_cases
    assert season_cases.capture(env, _obs(observed_on="2023-10-20")) is None       # đợt TRONG mùa lũ
    assert season_cases.capture(env, _obs(outcome="none")) is None                 # người dùng nói không ngập
    assert season_cases.capture(env, _obs(observed_on="2022-06-01")) is None       # radar không có đợt gần ngày đó
    assert season_cases.capture(env, _obs(module_id="drought")) is None
