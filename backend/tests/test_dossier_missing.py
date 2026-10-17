"""Hồ sơ phát hành khi lịch sử nước radar CHƯA đọc xong phải ghi mục đó là thiếu (18/10/2026) — trước đây im lặng."""
from __future__ import annotations

import pytest


@pytest.fixture
def stub(monkeypatch):
    from app.services import landuse, passport
    monkeypatch.setattr(passport, "build", lambda lat, lon: {"available": True, "terrain": {"elevation_m": 2.0},
                                                             "history": {"flood": {"events": 1}}, "caveat": "c"})
    monkeypatch.setattr(landuse, "composition", lambda lat, lon: {"label": "Đất trồng trọt"})


def test_chua_doc_radar_thi_ghi_thieu_va_loi_dien_giai_noi_ro(stub, monkeypatch):
    from app import routes_water
    from app.services import dossier, narrative
    monkeypatch.setattr(routes_water, "gate", lambda: {"passed": True})
    monkeypatch.setattr(dossier, "_water_section", lambda lat, lon: None)
    f = dossier.build_facts(16.6, 107.4, None, None)
    assert f["missing"] == ["water_history_radar"] and f["water_history_radar"] is None
    v = narrative.catalog({**f, "terrain": None, "history_10y": None}, "vi")["missing"]["value"]
    assert v == "lịch sử nước radar (chưa đọc xong lúc phát hành)"


def test_da_doc_radar_hoac_cong_chua_dat_thi_khong_ghi_thieu(stub, monkeypatch):
    from app import routes_water
    from app.services import dossier
    monkeypatch.setattr(routes_water, "gate", lambda: {"passed": True})
    monkeypatch.setattr(dossier, "_water_section", lambda lat, lon: {"events": [], "n_events": 0})
    assert dossier.build_facts(16.6, 107.4, None, None)["missing"] == []
    monkeypatch.setattr(routes_water, "gate", lambda: {"passed": False})
    monkeypatch.setattr(dossier, "_water_section", lambda lat, lon: None)
    assert dossier.build_facts(16.6, 107.4, None, None)["missing"] == []      # tính năng tắt → không phải "thiếu"


def test_khoa_cu_giu_nguyen_chu(stub):
    """Hồ sơ cũ thiếu land_use: lời diễn giải vẫn ghi đúng chữ cũ (đổi chữ = tệp thật cũ bị kiểm chứng báo đỏ)."""
    from app.services import narrative
    cat = narrative.catalog({"schema": "terratwin.dossier/1", "lang": "vi", "location": {"lat": 16.6, "lon": 107.4},
                             "missing": ["land_use", "passport"], "sources": [], "disclaimer": "d"}, "vi")
    assert cat["missing"]["value"] == "land_use, passport"


def test_ho_chieu_co_nhung_tung_phan_hong_thi_ghi_dung_phan(monkeypatch):
    """Lỗi thật 18/10/2026: ERA5 bị chặn → mục "Mười năm hiểm hoạ" trống mà `missing` không ghi gì."""
    from app import routes_water
    from app.services import dossier, landuse, narrative, passport
    monkeypatch.setattr(passport, "build", lambda lat, lon: {"available": True, "terrain": {"elevation_m": 2.0}, "history": None})
    monkeypatch.setattr(landuse, "composition", lambda lat, lon: {"label": "Đất trồng trọt"})
    monkeypatch.setattr(routes_water, "gate", lambda: {"passed": True})
    monkeypatch.setattr(dossier, "_water_section", lambda lat, lon: {"events": [], "n_events": 0})
    f = dossier.build_facts(16.6, 107.4, None, None)
    assert f["missing"] == ["history_10y"]
    f2 = {**f, "terrain": None, "water_history_radar": None}
    assert narrative.catalog(f2, "vi")["missing"]["value"] == "mười năm hiểm hoạ (ERA5)"
