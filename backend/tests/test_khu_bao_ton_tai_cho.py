"""Kiểm A–Z 24/11/2026: sàng lọc EUDR ra "Chưa kiểm được khu bảo tồn (OpenStreetMap không phản hồi)" — kể cả điểm trong
VQG Yok Đôn — vì hỏi Overpass mỗi lần. Ranh OSM tải sẵn (ops/osm_protected_fetch.py), tra tại chỗ; Overpass dự phòng."""
from __future__ import annotations

import json

import pytest

from app.services import eudr_forest, osm, protected_areas as pa

YOK_DON = {"osm": "relation/1", "name": "Vườn quốc gia Yok Đôn", "kind": "national_park", "protect_class": "2",
           "bbox": [107.5, 12.7, 107.9, 13.1],
           "geometry": {"type": "Polygon", "coordinates": [[[107.5, 12.7], [107.9, 12.7], [107.9, 13.1], [107.5, 13.1], [107.5, 12.7]]]}}


@pytest.fixture
def du_lieu(tmp_path, monkeypatch):
    f = tmp_path / "osm_protected_vn.json"
    f.write_text(json.dumps({"fetched": "2026-11-24", "count": 1, "areas": [YOK_DON]}), encoding="utf-8")
    monkeypatch.setattr(pa, "DATA", f)
    monkeypatch.setattr(pa, "MIN_AREAS", 1)
    pa._load.cache_clear()
    yield f
    pa._load.cache_clear()


def test_diem_trong_vqg_tra_tai_cho_khong_goi_overpass(du_lieu, monkeypatch):
    def _cam(q):
        raise AssertionError("có danh sách tải sẵn thì không gọi Overpass")
    monkeypatch.setattr(osm, "_query", _cam)
    r = eudr_forest.protected_areas(12.88, 107.75)
    assert r["checked"] is True and r["inside"] == ["Vườn quốc gia Yok Đôn"]
    assert "2026-11-24" in r["source"]
    assert eudr_forest.protected_areas(12.73, 108.05) == {"checked": True, "inside": [],
                                                           "source": "OpenStreetMap (ranh tải 2026-11-24)"}


def test_thieu_tep_thi_quay_ve_overpass(tmp_path, monkeypatch):
    monkeypatch.setattr(pa, "DATA", tmp_path / "khong_co.json")
    pa._load.cache_clear()
    try:
        assert pa.inside(12.88, 107.75) is None
        assert eudr_forest.protected_areas(12.88, 107.75)["checked"] is False      # Overpass bị chặn trong test
    finally:
        pa._load.cache_clear()


def test_tep_that_trong_kho_doc_duoc_neu_co():
    pa._load.cache_clear()
    if not pa.DATA.exists():
        pytest.skip("chưa tải ranh khu bảo tồn")
    assert pa.inside(12.88, 107.75) is not None


def test_tep_thieu_khu_coi_nhu_khong_co(du_lieu, monkeypatch):
    """Một gương Overpass trả dở dang 13 khu: thà "chưa kiểm được" còn hơn báo sai "không nằm trong khu bảo tồn"."""
    monkeypatch.setattr(pa, "MIN_AREAS", 60)
    pa._load.cache_clear()
    assert pa.inside(12.88, 107.75) is None
