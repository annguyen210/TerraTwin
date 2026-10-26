"""Kiểm chứng tin đăng: tách câu khẳng định (có dấu/không dấu), đối chiếu số đo, lời văn trung lập, không lưu."""
from __future__ import annotations

import pytest

TIN = """Bán gấp lô đất 500m2 thổ cư 100%, sổ hồng riêng.
Đất cao ráo, không bao giờ ngập nước, view sông thoáng mát.
Mặt bằng vuông vức, bằng phẳng; nuoc ngot quanh nam."""


def test_tach_dung_cac_cau_khang_dinh_ca_khong_dau():
    from app.services import listing_check as lc
    types = sorted({c["type"] for c in lc.extract(TIN)})
    assert types == ["flat", "fresh_water", "high_ground", "near_river", "no_flood", "residential"]


@pytest.mark.parametrize("text,typ", [
    ("Đất chưa từng bị ngập", "no_flood"), ("khong lo ngap", "no_flood"), ("nền cao hơn mặt đường", "high_ground"),
    ("cách biển 2km", "near_sea"), ("không sạt lở", "no_landslide"), ("giáp kênh thủy lợi", "near_river"),
])
def test_nhan_dien_tung_loai(text, typ):
    from app.services import listing_check as lc
    assert typ in {c["type"] for c in lc.extract(text)}


def test_moi_khang_dinh_trich_dung_ve_cua_no():
    """Mục 7 báo cáo 12/10/2026: mỗi loại trích ĐÚNG vế của nó, không phải cụm đầu của tin."""
    from app.services import listing_check as lc
    got = {c["type"]: c["sentence"] for c in lc.extract(TIN)}
    assert got["high_ground"] == "Đất cao ráo"
    assert got["no_flood"] == "không bao giờ ngập nước"
    assert got["near_river"] == "view sông thoáng mát"
    assert got["flat"] == "bằng phẳng" and got["fresh_water"] == "nuoc ngot quanh nam"   # "vuông vức" là hình dáng (cổng GĐ3 lần 1)
    got = {c["type"]: c["sentence"] for c in lc.extract("Bán đất thổ cư, gần sông mát mẻ, không lo ngập")}
    assert got == {"residential": "Bán đất thổ cư", "near_river": "gần sông mát mẻ", "no_flood": "không lo ngập"}


@pytest.mark.parametrize("text,typ,want", [
    # Lần 5 (26/10/2026): hai KIỂU nói vòng mà lần 4 (tin Facebook) bỏ sót — và các câu gần giống KHÔNG được tính.
    ("Đất đẹp, cao ngang mặt đường, thoáng mát", "high_ground", True),
    ("nền đất bằng mặt đường nhựa", "high_ground", True),
    ("đất ngang với mặt đường, không phải đổ thêm", "high_ground", True),
    ("Lô đất ngang 5m mặt đường 12m", "high_ground", False),
    ("Ra biển và Đồi Rồng chỉ 3 phút", "near_sea", True),
    ("chỉ 5 phút ra biển", "near_sea", True),
    ("10 phút chạy xe ra bãi tắm", "near_sea", False),       # cụm giữa số và "ra" dài hơn mẫu cho phép — chấp nhận sót
    ("đường ra biển đang mở rộng, hai làn xe", "near_sea", False),       # không có số phút → mẫu mới không bắt
    ("Hướng Đông Nam, mặt tiền 6m", "near_sea", False),
])
def test_cach_noi_vong_lan_5(text, typ, want):
    from app.services import listing_check as lc
    assert (typ in {c["type"] for c in lc.extract(text)}) is want


def test_cau_khong_khang_dinh_gi_thi_khong_bat_bua():
    from app.services import listing_check as lc
    assert lc.extract("Liên hệ chính chủ, giá thương lượng, xem đất thứ Bảy.") == []


def test_doi_chieu_khong_ngap_voi_lich_su_nuoc_radar():
    from app.services import listing_check as lc
    wet = {"water": {"n_events": 3, "first": "2017-01-11", "n_scenes": 300,
                     "events": [{"start": "2019-11-02"}, {"start": "2020-10-10"}, {"start": "2025-11-01"}]}}
    v, msg, src = lc.judge("no_flood", wet)
    assert v == "contradicted" and "3 đợt" in msg and "2025-11-01" in msg and "Sentinel-1" in src
    dry = {"water": {"n_events": 0, "first": "2017-01-11", "n_scenes": 300, "events": []}}
    assert lc.judge("no_flood", dry)[0] == "consistent"
    assert lc.judge("no_flood", {"water": None})[0] == "insufficient"       # chưa đọc radar → không đoán


def test_cao_rao_dua_tren_dia_hinh_va_nuoc():
    from app.services import listing_check as lc
    low = {"terrain": {"lower_than_pct": 80, "elevation_m": 3, "slope_deg": 0.5}, "water": None}
    assert lc.judge("high_ground", low)[0] == "contradicted"
    high = {"terrain": {"lower_than_pct": 10, "elevation_m": 40, "slope_deg": 2}, "water": {"n_events": 0}}
    assert lc.judge("high_ground", high)[0] == "consistent"
    mid = {"terrain": {"lower_than_pct": 50, "elevation_m": 10, "slope_deg": 1}, "water": None}
    assert lc.judge("high_ground", mid)[0] == "insufficient"


def test_loai_dat_phap_ly_va_nuoc_ngot_luon_noi_thang_la_khong_kiem_duoc():
    from app.services import listing_check as lc
    assert lc.judge("residential", {})[0] == "insufficient"
    assert lc.judge("fresh_water", {})[0] == "insufficient"


def test_api_kiem_tin_dang_khong_luu_noi_dung(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services import listing_check as lc, quota
    quota.reset()
    monkeypatch.setattr(lc, "evidence", lambda lat, lon, types: {"water": None, "terrain": {"lower_than_pct": 85,
                                                                  "elevation_m": 2, "slope_deg": 0.3}})
    with TestClient(app) as c:
        r = c.post("/api/listing/check", json={"text": TIN, "lat": 16.575, "lon": 107.495}).json()
        assert c.post("/api/listing/check", json={"text": "x" * 5001, "lat": 16.5, "lon": 107.5}).status_code == 422
    v = {x["type"]: x["verdict"] for x in r["claims"]}
    assert v["high_ground"] == "contradicted" and v["flat"] == "consistent" and v["residential"] == "insufficient"
    assert "không được lưu" in r["note"]


def test_luoi_song_kenh_tinh_tra_khoang_cach_khong_can_overpass(monkeypatch, tmp_path):
    """Mục 8 báo cáo 12/10/2026: Overpass không gọi được (Render) thì vẫn có khoảng cách tới sông từ lưới đóng gói."""
    import json as _json
    import numpy as np
    from app.services import listing_check as lc, osm, river_grid
    rows, cols, cell = 200, 200, 0.001
    grid = np.zeros((rows, cols), dtype=bool)
    grid[:, 120] = True                                   # một con kênh chạy bắc–nam ở kinh độ 105.1205
    p = tmp_path / "g.npz"
    meta = {"lat0": 10.0, "lon0": 105.0, "cell_deg": cell, "rows": rows, "cols": cols, "built": "2026-10-12"}
    np.savez_compressed(p, bits=np.packbits(grid, axis=None), meta=np.array(_json.dumps(meta)))
    monkeypatch.setattr(river_grid, "_PATH", str(p))
    monkeypatch.setattr(river_grid, "_g", None)
    monkeypatch.setattr(river_grid, "_missing", False)
    monkeypatch.setattr(osm, "_query", lambda q: (_ for _ in ()).throw(AssertionError("không được gọi Overpass")))
    km = lc._nearest_river_km(10.1, 105.1105)               # cách kênh 0,01° kinh độ ≈ 1,09 km
    assert 1.0 <= km <= 1.2
    assert lc._nearest_river_km(10.1, 105.02, radius_m=3000.0) == float("inf")   # ~11 km → ngoài 3 km
    assert river_grid.nearest_km(20.0, 105.1) is None       # ngoài lưới → để Overpass lo
