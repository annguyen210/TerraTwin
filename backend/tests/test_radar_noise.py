"""Rà soát nền không được sinh cảnh báo NHIỄU.

Ca thật đo 27/9: lưu thử 3 thửa (Huế, Trà Leng, Bến Tre) → radar ra 5 cảnh
báo, 4 là nhiễu. Ba nguồn nhiễu, mỗi nguồn một nhóm test ở đây:

  a) sâu bệnh báo "danger" vì NDVI TUYỆT ĐỐI thấp (điểm giữa phố) — xem
     test_sentinel.py (test_o_giua_pho_..., test_pest_module_khong_ap_dung_...).
  b) mô-đun thông tin (carbon/MRV, supply_chain/doanh nghiệp) lọt vào danh
     sách cảnh báo trên thửa nông dân.
  c) cùng một tình trạng không đổi bị báo lại mỗi 12 giờ.

Không chạm mạng: scan được giả lập, CSDL SQLite riêng cho mỗi test.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def db(tmp_path, monkeypatch):
    from app import db as dbmod

    engine = create_engine(f"sqlite:///{tmp_path/'r.db'}",
                           connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    dbmod.Base.metadata.create_all(engine)
    monkeypatch.setattr(dbmod, "engine", engine)
    monkeypatch.setattr(dbmod, "SessionLocal", Session)
    with Session() as s:
        u = dbmod.User(email="radar@example.com", password_hash="x", name="R")
        s.add(u)
        s.commit()
        s.add(dbmod.Plot(user_id=u.id, name="Ruộng", lat=10.24, lon=106.37))
        s.commit()
        uid = u.id
    return Session, uid


def _fake_scan(monkeypatch, level_by_module: dict[str, str]):
    """scan() trả đúng các mô-đun/mức cho trước — dựng qua ĐÚNG bộ lọc thật
    của scan.alerts (is_real + threat + danger/warning), không tự lọc hộ."""
    from app.modules.registry import get_module
    from app.schemas import ScanModule, ScanResult, TerraScoreResult
    from app.services import scan as scan_svc

    def fake(loc, include_heavy=False, deadline=None):
        mods = [ScanModule(id=mid, name=mid, icon="", group="X", risk_level=lv,
                           headline=f"{mid} {lv}", recommendation="",
                           is_real=True, threat=get_module(mid).threat)
                for mid, lv in level_by_module.items()]
        alerts = [m for m in mods
                  if m.is_real and m.threat and m.risk_level in ("danger", "warning")]
        ts = TerraScoreResult(location=loc, score=50, grade="C", summary="t")
        return ScanResult(location=loc, terrascore=ts, modules=mods, alerts=alerts,
                          real_data_ratio=1.0, generated_at="2026-09-28T00:00:00")

    monkeypatch.setattr(scan_svc, "scan", fake)


def _sweep(db):
    from app.services import radar
    Session, uid = db
    with Session() as s:
        return radar.sweep_user(uid, s)


# ---------------------------------------------------------------- (b)

def test_carbon_va_supply_chain_khong_phai_moi_de_doa():
    from app.modules.registry import get_module
    assert get_module("carbon").threat is False
    assert get_module("supply_chain").threat is False


def test_carbon_supply_chain_danger_khong_thanh_canh_bao(db, monkeypatch):
    """Cả hai ra "danger" trên thang của chính nó mà rà soát nền vẫn im lặng;
    chỉ hiểm hoạ thật của thửa (lũ) thành cảnh báo."""
    _fake_scan(monkeypatch, {"carbon": "danger", "supply_chain": "danger",
                             "flood": "danger"})
    r = _sweep(db)
    assert [a["module_id"] for a in r["alerts"]] == ["flood"]


# ---------------------------------------------------------------- (c)

def test_tinh_trang_khong_doi_khong_bao_lai(db, monkeypatch):
    _fake_scan(monkeypatch, {"flood": "warning"})
    assert _sweep(db)["new_alerts"] == 1
    assert _sweep(db)["new_alerts"] == 0, "cùng mức, trong 72h → không báo lại"


def test_muc_tang_thi_bao_ngay(db, monkeypatch):
    _fake_scan(monkeypatch, {"flood": "warning"})
    assert _sweep(db)["new_alerts"] == 1
    _fake_scan(monkeypatch, {"flood": "danger"})
    assert _sweep(db)["new_alerts"] == 1, "warning → danger là tin mới, phải báo ngay"


def test_muc_giam_roi_quay_lai_khong_bao_lai_trong_cua_so(db, monkeypatch):
    _fake_scan(monkeypatch, {"flood": "danger"})
    assert _sweep(db)["new_alerts"] == 1
    _fake_scan(monkeypatch, {"flood": "warning"})
    assert _sweep(db)["new_alerts"] == 0, "giảm mức không phải tin mới"
    _fake_scan(monkeypatch, {"flood": "danger"})
    assert _sweep(db)["new_alerts"] == 0, "đã báo danger trong 72h rồi"


def test_qua_72h_thi_nhac_lai(db, monkeypatch):
    from app.db import Alert
    Session, _ = db
    _fake_scan(monkeypatch, {"flood": "warning"})
    assert _sweep(db)["new_alerts"] == 1

    with Session() as s:   # đẩy lần báo trước lùi về 73 giờ trước
        old = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=73)
        for a in s.query(Alert).all():
            a.created_at = old
        s.commit()
    assert _sweep(db)["new_alerts"] == 1, "quá 72h vẫn còn rủi ro → nhắc lại"


def test_moc_12h_cu_khong_con_ap_dung(db, monkeypatch):
    """13 giờ sau (qua mốc 12h cũ, chưa tới 72h) — bản cũ báo lại, bản mới không."""
    from app.db import Alert
    Session, _ = db
    _fake_scan(monkeypatch, {"flood": "warning"})
    assert _sweep(db)["new_alerts"] == 1
    with Session() as s:
        old = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=13)
        for a in s.query(Alert).all():
            a.created_at = old
        s.commit()
    assert _sweep(db)["new_alerts"] == 0
