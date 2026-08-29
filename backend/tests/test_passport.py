"""Hồ sơ thửa đất — và cái bẫy con số trông như sự thật nhưng là hằng số.

Nhóm test quan trọng nhất ở đây là test_khong_dung_nguong_hieu_chuan_de_dem.
Bản đầu của tính năng này đếm số lần vượt ngưỡng SAU hiệu chuẩn, mà hiệu chuẩn
định nghĩa ngưỡng là phân vị 97 của chính nơi đó — nên theo đúng định nghĩa
luôn ra ~3% số cửa sổ, ở bất kỳ đâu. Huế 109, Bến Tre cũng 109. Con số trông
như một sự thật về thửa đất nhưng thực chất là hằng số của thuật toán.
"""
from __future__ import annotations

import pytest

from app.services import calibration as cal, passport


@pytest.fixture(autouse=True)
def _khong_ra_mang(monkeypatch):
    """Chặn MỌI đường ra mạng của lớp này.

    test_dem_theo_nguong_chung_cho_ra_so_KHAC_NHAU từng TREO cả bộ test hơn
    bốn mươi phút: nó chặn climatology và historical_weather, nhưng
    passport.history() gọi raw_series() cho lũ và sạt lở, mà hai cái đó tra cao
    độ và độ dốc THẬT. Một test tự nhận là "offline" mà còn sót một đường ra
    mạng thì không phải test offline — đúng lỗi đã gặp ở test_cache.py, và tôi
    tự mắc lại y hệt khi viết tệp này.

    Chặn ở cả hai tầng (datasources và realdata) vì mỗi mô-đun đi một đường
    khác nhau; chặn một tầng thôi thì đường còn lại vẫn hở.
    """
    from app.services import datasources as ds, realdata
    monkeypatch.setattr(ds, "elevation_proxy", lambda la, lo: 8.0)
    monkeypatch.setattr(ds, "slope_context", lambda la, lo: (2.0, "giả lập"))
    monkeypatch.setattr(realdata, "elevation_m", lambda la, lo: 8.0)
    monkeypatch.setattr(realdata, "slope_deg", lambda la, lo, **k: 2.0)
    monkeypatch.setattr(realdata, "elevation_multi", lambda pts: [8.0] * len(pts))


def test_diem_lay_mau_phu_deu_quanh_thua():
    pts = passport._ring_points(10.0, 106.0)
    assert len(pts) == 1 + len(passport.RINGS_KM) * passport.PER_RING
    assert pts[0] == (10.0, 106.0)


def test_thua_trung_thi_noi_nuoc_don_ve(monkeypatch):
    # thửa 1 m, xung quanh toàn 20 m
    monkeypatch.setattr(passport.realdata, "elevation_multi",
                        lambda pts: [1.0] + [20.0] * (len(pts) - 1))
    monkeypatch.setattr(passport.realdata, "slope_deg", lambda *a, **k: 0.5)
    t = passport.terrain(10.0, 106.0)
    assert t["lower_than_pct"] == 100
    assert "TRŨNG" in t["meaning"] and "dồn về đây" in t["meaning"]


def test_thua_cao_thi_noi_nguoc_lai(monkeypatch):
    monkeypatch.setattr(passport.realdata, "elevation_multi",
                        lambda pts: [50.0] + [5.0] * (len(pts) - 1))
    monkeypatch.setattr(passport.realdata, "slope_deg", lambda *a, **k: 3.0)
    t = passport.terrain(10.0, 106.0)
    assert t["lower_than_pct"] == 0
    assert "CAO hơn" in t["meaning"]


def test_thieu_cao_do_thi_tra_none_chu_khong_doan(monkeypatch):
    monkeypatch.setattr(passport.realdata, "elevation_multi", lambda pts: None)
    assert passport.terrain(10.0, 106.0) is None


def test_khong_dung_nguong_hieu_chuan_de_dem():
    """CANH ĐÚNG CÁI BẪY ĐÃ SẬP MỘT LẦN.

    Đếm theo ngưỡng hiệu chuẩn cho ra cùng một con số ở mọi nơi (~3% số cửa sổ),
    vì ngưỡng đó ĐƯỢC ĐỊNH NGHĨA là phân vị 97 của chính nơi đó. Phải đếm theo
    ngưỡng chung cả nước thì con số mới phân biệt được nơi này với nơi khác.
    """
    import inspect
    src = inspect.getsource(passport.history)
    assert "NATIONAL_P97" in src, "phải đếm theo ngưỡng chung cả nước"
    assert "map_percentile" not in src, (
        "không được đếm theo ngưỡng đã hiệu chuẩn — sẽ ra cùng con số ở mọi nơi")


def test_dem_theo_nguong_chung_cho_ra_so_KHAC_NHAU(monkeypatch):
    """Hai nơi khí hậu khác nhau phải ra hai con số khác nhau."""
    def rows_for(muc):
        return [{"day": i, "date": f"20{15 + i // 365:02d}-06-{1 + i % 28:02d}",
                 "precip": muc, "et0": 3.0, "tmax": 32.0} for i in range(1200)]

    monkeypatch.setattr(cal, "climatology", lambda *a, **k: [1.0] * 100)
    monkeypatch.setattr(passport.realdata, "historical_weather",
                        lambda la, lo, s, e: rows_for(60.0 if la > 15 else 2.0))
    mua_nhieu = passport.history(16.0, 107.0)
    mua_it = passport.history(10.0, 106.0)
    assert mua_nhieu["flood"]["events"] > mua_it["flood"]["events"], (
        "nơi mưa nhiều phải ra số lần lớn hơn hẳn")


def test_luon_kem_muc_nang_nhat_va_ngay(monkeypatch):
    rows = [{"day": i, "date": f"2020-06-{1 + i % 28:02d}", "precip": 5.0 + i % 50,
             "et0": 3.0, "tmax": 32.0} for i in range(1200)]
    monkeypatch.setattr(cal, "climatology", lambda *a, **k: [1.0] * 100)
    monkeypatch.setattr(passport.realdata, "historical_weather",
                        lambda la, lo, s, e: rows)
    h = passport.history(10.0, 106.0)
    for v in h.values():
        assert v["worst_value"] > 0 and v["worst_date"]


def test_ho_so_luon_kem_canh_bao_gioi_han(monkeypatch):
    monkeypatch.setattr(passport, "terrain", lambda la, lo: {
        "elevation_m": 5.0, "lower_than_pct": 80, "radius_km": 3.0,
        "slope_deg": 0.2, "meaning": "x", "neighbours_sampled": 24,
        "around_min_m": 1.0, "around_max_m": 9.0})
    monkeypatch.setattr(passport, "history", lambda la, lo, years=10: None)
    from app.services import cache_store
    monkeypatch.setattr(cache_store, "get", lambda k: None)
    monkeypatch.setattr(cache_store, "put", lambda *a, **k: None)
    d = passport.build(10.0, 106.0)
    assert "90 m" in d["caveat"], "phải nói rõ độ thô của mô hình độ cao"
    assert "không phải số trận lụt được ghi nhận chính thức" in d["caveat"]
