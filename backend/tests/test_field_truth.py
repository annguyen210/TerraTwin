"""Kiểm thực địa bộ phát hiện đợt nước — đúng giao thức đăng ký trước (data/eval/water_field_protocol.json)."""
from __future__ import annotations

import importlib.util
import os

import pytest

HERE = os.path.dirname(__file__)


@pytest.fixture
def db(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app import db as dbmod
    from app.services import field_truth
    engine = create_engine(f"sqlite:///{tmp_path/'f.db'}", connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    dbmod.Base.metadata.create_all(engine)
    monkeypatch.setattr(dbmod, "SessionLocal", Session)
    monkeypatch.setattr(field_truth, "RESULT", str(tmp_path / "water_field_result.json"))
    monkeypatch.setenv("TERRATWIN_ADMIN_EMAILS", "chu@nong.vn")
    s = Session()
    yield s
    s.close()


def _user(db, email, role="user"):
    from app.db import User
    u = User(email=email, password_hash="x", name="N", role=role)
    db.add(u)
    db.flush()
    return u


def _ans(db, u, lat, lon, start, answer, v1="in"):
    from app.db import WaterConfirm
    db.add(WaterConfirm(user_id=u.id, lat=lat, lon=lon, cell=f"{lat:.3f},{lon:.3f}", event_start=start, answer=answer, v1_label=v1))
    db.flush()


def test_loc_tai_khoan_thu_quan_tri_khong_ro_va_hoa(db):
    from app.services import field_truth as ft
    a, b = _user(db, "a@nong.vn"), _user(db, "b@nong.vn")
    _ans(db, a, 16.5, 107.5, "2020-10-10", "yes")
    _ans(db, b, 16.5, 107.5, "2020-10-10", "no")            # hoà 1–1 → loại
    _ans(db, a, 16.6, 107.5, "2021-10-17", "unsure")        # không rõ → bỏ
    _ans(db, _user(db, "qa@vd.vn"), 16.7, 107.5, "2021-10-17", "yes")              # tài khoản thử
    _ans(db, _user(db, "chu@nong.vn"), 16.8, 107.5, "2021-10-17", "yes")           # email quản trị
    _ans(db, _user(db, "x@nong.vn", role="admin"), 16.9, 107.5, "2021-10-17", "yes")
    _ans(db, b, 10.0, 106.0, "2022-05-01", "no", v1="out")
    ev = ft.labelled(db)
    assert [(e["event_start"], e["label"]) for e in ev] == [("2022-05-01", "not_flooded")]


def test_moi_nguoi_toi_da_20_dot(db):
    from app.services import field_truth as ft
    u = _user(db, "nhieu@nong.vn")
    for i in range(25):
        _ans(db, u, 16.0 + i * 0.01, 107.0, "2020-10-10", "yes")
    assert len(ft.labelled(db)) == 20


def test_chua_du_co_mau_thi_khong_cham_va_script_khong_ghi(db, capsys):
    from app.services import field_truth as ft
    u = _user(db, "mot@nong.vn")
    _ans(db, u, 16.5, 107.5, "2020-10-10", "yes")
    db.commit()
    st = ft.status(db)
    assert st["have"]["labelled_events"] == 1 and st["ready"] is False and st["need"]["labelled_events"] == 30
    spec = importlib.util.spec_from_file_location("g", os.path.join(HERE, "..", "..", "ops", "water_field_gate.py"))
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)
    assert g.main([]) == 0 and not os.path.exists(ft.RESULT)
    assert "Chưa đủ cỡ mẫu" in capsys.readouterr().out


def test_du_mau_cham_mot_lan_wilson_va_tach_mua(db):
    from app.services import field_truth as ft
    users = [_user(db, f"n{i}@nong.vn") for i in range(10)]
    cells = [(16.5, 107.5), (10.2, 106.3), (21.1, 105.8)]
    for i in range(30):
        la, lo = cells[i % 3]
        _ans(db, users[i % 10], la + i * 0.001, lo, "2020-10-10", "yes" if i < 24 else "no", v1="in" if i % 2 else "out")
    db.commit()
    r = ft.score(db)
    assert r["ready"] and r["precision"] == 0.8 and r["flooded"] == 24
    lo, hi = r["wilson95"]
    assert 0.62 < lo < 0.64 and 0.90 < hi < 0.92 and r["outcome"] == "confirmed"
    assert r["by_v1_season"]["in"]["n"] + r["by_v1_season"]["out"]["n"] == 30
    assert set(r["events_per_1deg_cell"]) == {"16,107", "10,106", "21,105"}


def test_wilson_bien():
    from app.services import field_truth as ft
    assert ft.wilson(0, 0) == (0.0, 1.0)
    lo, hi = ft.wilson(15, 30)
    assert lo < 0.5 < hi


def test_the_mo_hinh_va_api_bao_cho_du_lieu():
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services import model_cards
    with TestClient(app) as c:
        j = c.get("/api/water/field-check").json()
    assert j["need"] == {"labelled_events": 30, "distinct_users": 10, "distinct_1deg_cells": 3} and j["result"] is None
    card = next(x for x in model_cards.cards() if x["id"] == "water_radar")
    m = card["metrics"][-1]
    assert m["passed"] is None and "/30" in m["value"]
