"""Sổ điểm tách theo GIAI ĐOẠN nguồn mưa dự báo (18/10/2026): đổi nguồn là đổi thứ đang được chấm — không được trộn."""
from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def Session(tmp_path, monkeypatch):
    from app import db as dbmod
    from app.services import scorecard
    engine = create_engine(f"sqlite:///{tmp_path/'s.db'}", connect_args={"check_same_thread": False})
    S = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    dbmod.Base.metadata.create_all(engine)
    monkeypatch.setattr(scorecard, "_now", lambda: datetime(2026, 11, 30))
    return S


def _alerts(S, rows):
    from app.db import Alert, Plot, User
    s = S()
    u = User(email="reg@nong.vn", password_hash="x", name="N")
    s.add(u)
    s.commit()
    for i, (when, outcome, retro, src) in enumerate(rows):
        p = Plot(user_id=u.id, name=f"T{i}", lat=10.0 + i * 0.01, lon=106.0)
        s.add(p)
        s.commit()
        s.add(Alert(user_id=u.id, plot_id=p.id, module_id="flood", risk_level="danger", headline="h",
                    created_at=datetime.fromisoformat(when), outcome=outcome, retro=retro, forecast_source=src))
    s.commit()
    return s


def test_tach_truoc_sau_moc_ca_bo_sot_hoi_cuu(Session):
    from app.services import scorecard
    s = _alerts(Session, [("2026-09-20T03:00", "hit", 0, "open-meteo"),
                          ("2026-10-05T03:00", "false_alarm", 0, "open-meteo"),
                          ("2026-10-25T03:00", "hit", 0, "open-meteo-blend"),
                          ("2026-11-10T03:00", "miss", 1, None),            # bỏ sót hồi cứu: không có nguồn, có ngày
                          ("2026-11-12T03:00", "false_alarm", 0, "metno")])
    out = scorecard.summary(s, days=120)
    reg = {r["id"]: r for r in out["regimes"]}
    assert reg["best_match"]["counts"] == {"hit": 1, "miss": 0, "false_alarm": 1}
    assert reg["aifs_blend"]["counts"] == {"hit": 1, "miss": 1, "false_alarm": 1}
    assert reg["aifs_blend"]["pod_pct"] == 50.0 and reg["aifs_blend"]["to"] is None
    assert reg["best_match"]["to"] == "2026-10-18" and reg["best_match"]["enough"] is False
    assert out["forecast_sources"] == {"open-meteo": 2, "open-meteo-blend": 1, "metno": 1}   # retro không tính
    # Tổng vẫn như cũ (tách không làm mất gì)
    assert out["counts"]["hit"] == 2 and out["counts"]["miss"] == 1 and out["counts"]["false_alarm"] == 2


def test_cua_so_ngan_chi_hien_giai_doan_giao_nhau(Session):
    from app.services import scorecard
    s = _alerts(Session, [("2026-11-20T03:00", "hit", 0, "open-meteo-blend")])
    out = scorecard.summary(s, days=20)
    assert [r["id"] for r in out["regimes"]] == ["aifs_blend"]


def test_phat_canh_bao_ghi_nguon_mua(monkeypatch):
    from app.services import radar, realdata
    monkeypatch.setattr(realdata, "weather_7d", lambda la, lo: [{"precip": 1.0, "source": "open-meteo-blend"}])
    assert radar._forecast_source(16.5, 107.5) == "open-meteo-blend"
    monkeypatch.setattr(realdata, "weather_7d", lambda la, lo: None)
    assert radar._forecast_source(16.5, 107.5) is None

    def boom(la, lo):
        raise RuntimeError("mạng")
    monkeypatch.setattr(realdata, "weather_7d", boom)
    assert radar._forecast_source(16.5, 107.5) is None          # lỗi không chặn phát cảnh báo
