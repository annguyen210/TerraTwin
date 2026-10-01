"""Phát hiện thay đổi lớp phủ sau 2021 — mô hình học sâu + WorldCover.

Không chạm mạng, không cần tệp mô hình: landcover/landuse/recent_patch giả lập.
"""
from __future__ import annotations

import numpy as np
import pytest

from app.services import landchange, reqlang


@pytest.fixture(autouse=True)
def _vi():
    reqlang.set_lang("vi")


def test_tru_do_lech_1000_cho_anh_tu_2022():
    """Baseline ≥04.00 (từ 25/01/2022) ESA cộng 1000 vào mọi giá trị L2A. Ảnh
    2026 phải trừ lại — nếu không, mô hình học trên 2021 thấy mọi thứ sáng hơn."""
    dn = np.full((4, 2, 2), 1500, dtype=np.uint16)
    assert np.allclose(landchange.harmonize(dn, "05.11"), 0.05)   # (1500-1000)/10000
    assert np.allclose(landchange.harmonize(dn, "03.00"), 0.15)   # ảnh cũ: không trừ
    assert np.allclose(landchange.harmonize(np.full((1, 1, 1), 500, np.uint16), "05.11"), 0.0)


@pytest.fixture
def fake(monkeypatch):
    state = {"now": {"built": 80.0, "crop": 20.0}}
    monkeypatch.setattr(landchange.landcover, "status",
                        lambda: {"available": True, "miou_holdout": 0.41,
                                 "iou_per_class": [], "holdout_provinces": ["Huế"]})
    monkeypatch.setattr(landchange.landuse, "composition", lambda lat, lon: {
        "source": "ESA WorldCover 2021 v200 (10 m)", "group_pct": {"crop": 90.0, "built": 10.0}})
    monkeypatch.setattr(landchange, "recent_patch", lambda lat, lon: (
        np.zeros((4, 256, 256), np.float32), {"item": "S2X", "date": "2026-09-01",
                                              "clear_pct_at_plot": 100.0,
                                              "processing_baseline": "05.11",
                                              "offset_removed": True}))
    monkeypatch.setattr(landchange.landcover, "classify_window",
                        lambda patch, px: {"groups_pct": state["now"], "classes_pct": {}})
    return state


def test_ruong_thanh_nha_bi_bat(fake):
    r = landchange.detect(16.46, 107.59)
    assert r["available"] and r["changed"]
    assert r["delta_pts"]["built"] == 70.0 and r["delta_pts"]["crop"] == -70.0
    assert "xây dựng mới" in r["headline"]
    assert any("chuyển mục đích" in f for f in r["flags"])
    assert r["model"]["miou_holdout"] == 0.41 and "WorldCover" in r["caveat"]
    assert r["now"]["image"]["offset_removed"] is True


def test_khong_doi_thi_noi_khong_doi(fake):
    fake["now"] = {"crop": 85.0, "built": 15.0}
    r = landchange.detect(16.46, 107.59)
    assert r["available"] and not r["changed"] and r["flags"] == []


def test_mo_hinh_chua_bat_thi_noi_ro(monkeypatch):
    monkeypatch.setattr(landchange.landcover, "status", lambda: {"available": False})
    r = landchange.detect(16.46, 107.59)
    assert r["available"] is False and "chưa bật" in r["reason"]


def test_khong_co_anh_quang_may(fake, monkeypatch):
    monkeypatch.setattr(landchange, "recent_patch", lambda lat, lon: None)
    r = landchange.detect(16.46, 107.59)
    assert r["available"] is False and "quang mây" in r["reason"]
