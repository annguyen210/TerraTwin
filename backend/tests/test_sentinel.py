"""Lớp ảnh Sentinel-2 và 4 mũi nhọn quang học dựng trên nó.

Không có khóa Copernicus trong CI nên test giả lập ở tầng THẤP NHẤT có thể —
hàm `_post` gửi HTTP — chứ không giả lập `optical.stress()`. Giả lập càng gần
lớp mạng thì càng nhiều mã thật được chạy: parse phản hồi Statistics API, lọc
mây theo coverage, tính z-score, tính độ loang lổ, dựng Assessment.

Giả lập ở tầng cao (patch thẳng optical.stress) sẽ xanh cả khi parser hỏng —
đúng loại test cho cảm giác an toàn giả.
"""
from __future__ import annotations

import os
from datetime import date, timedelta

import pytest

from app.schemas import Location
from app.services import optical, sentinel


# ---------------------------------------------------------------- tiện ích

def _interval(day: date, mean: float, std: float = 0.05,
              total: int = 3600, nodata: int = 0) -> dict:
    """Một khoảng trong phản hồi Statistics API thật."""
    return {
        "interval": {"from": f"{day.isoformat()}T00:00:00Z",
                     "to": f"{day.isoformat()}T23:59:59Z"},
        "outputs": {"index": {"bands": {"B0": {"stats": {
            "min": round(mean - 2 * std, 4), "max": round(mean + 2 * std, 4),
            "mean": mean, "stDev": std,
            "sampleCount": total, "noDataCount": nodata,
        }}}}},
    }


def _fake_post(intervals):
    """Thay hàm gửi HTTP bằng một hàm trả sẵn phản hồi."""
    def _post(url, payload):
        return {"data": list(intervals)}
    return _post


@pytest.fixture
def with_key(monkeypatch):
    monkeypatch.setenv("TERRATWIN_COPERNICUS_ID", "test-id")
    monkeypatch.setenv("TERRATWIN_COPERNICUS_SECRET", "test-secret")
    # Cache dùng chung database nên phải tắt, không thì test này đọc phải kết
    # quả test khác vừa ghi.
    monkeypatch.setattr("app.services.cache_store.get", lambda k: None)
    monkeypatch.setattr("app.services.cache_store.put", lambda k, v, t: None)
    return True


def _series(monkeypatch, values, start_days_ago=120, step=10, nodata_at=()):
    """Dựng chuỗi NDVI giả với `values` cách nhau `step` ngày."""
    today = date.today()
    ivs = []
    for i, v in enumerate(values):
        d = today - timedelta(days=start_days_ago - i * step)
        nd = 3600 if i in nodata_at else 0
        std = v[1] if isinstance(v, tuple) else 0.05
        mean = v[0] if isinstance(v, tuple) else v
        ivs.append(_interval(d, mean, std, nodata=nd))
    monkeypatch.setattr(sentinel, "_post", _fake_post(ivs))


# ---------------------------------------------------------------- cấu hình

def test_chua_co_khoa_thi_moi_thu_tra_none(monkeypatch):
    monkeypatch.delenv("TERRATWIN_COPERNICUS_ID", raising=False)
    monkeypatch.delenv("TERRATWIN_COPERNICUS_SECRET", raising=False)
    assert sentinel.configured() is False
    assert sentinel.index_series(10.0, 106.0) is None
    assert optical.stress(10.0, 106.0) is None
    assert optical.growth(10.0, 106.0) is None
    assert optical.vegetation_loss(10.0, 106.0) is None
    assert optical.new_construction(10.0, 106.0) is None


def test_status_khong_bao_gio_lo_secret(monkeypatch):
    monkeypatch.setenv("TERRATWIN_COPERNICUS_ID", "abcdef123456")
    monkeypatch.setenv("TERRATWIN_COPERNICUS_SECRET", "SIEU-BI-MAT")
    s = sentinel.status()
    assert s["configured"] is True
    assert "SIEU-BI-MAT" not in repr(s)
    assert s["client_id_hint"] == "abcdef…"


def test_bbox_dung_kich_thuoc():
    bbox = sentinel.bbox_around(10.0, 106.0, buffer_m=300.0)
    minx, miny, maxx, maxy = bbox
    # 600 m theo vĩ độ ≈ 0,00539°
    assert abs((maxy - miny) - 0.00539) < 0.0002
    assert maxx > minx and maxy > miny


def test_evalscript_co_loc_may():
    js = sentinel._evalscript("NDVI")
    assert "SCL" in js and "dataMask" in js
    # 8, 9, 10 = mây trung bình/cao/ti tầng — thiếu là đọc mây thành cây chết
    assert "8, 9, 10" in js


def test_index_khong_ho_tro_thi_bao_loi():
    with pytest.raises(ValueError):
        sentinel.index_series(10.0, 106.0, index="KHONG-CO-CHI-SO-NAY")


# ---------------------------------------------------------------- parse

def test_parse_thong_ke_va_do_phu(with_key, monkeypatch):
    today = date.today()
    monkeypatch.setattr(sentinel, "_post", _fake_post([
        _interval(today - timedelta(days=20), 0.72, 0.04),
        _interval(today - timedelta(days=10), 0.68, 0.05, nodata=3600),  # toàn mây
    ]))
    s = sentinel.index_series(10.0, 106.0, days=30, interval_days=10)
    assert len(s) == 2
    assert s[0]["mean"] == 0.72 and s[0]["coverage_pct"] == 100.0
    # Khoảng toàn mây phải giữ lại nhưng mean = None, KHÔNG được thành 0.0
    assert s[1]["mean"] is None and s[1]["coverage_pct"] == 0.0


def test_latest_clear_bo_qua_ky_bi_may(with_key, monkeypatch):
    today = date.today()
    monkeypatch.setattr(sentinel, "_post", _fake_post([
        _interval(today - timedelta(days=20), 0.70),
        _interval(today - timedelta(days=10), 0.66, nodata=3600),
    ]))
    s = sentinel.index_series(10.0, 106.0, days=30, interval_days=10)
    assert sentinel.latest_clear(s)["mean"] == 0.70


def test_goi_hong_tra_none_chu_khong_no(with_key, monkeypatch):
    monkeypatch.setattr(sentinel, "_post", lambda u, p: None)
    assert sentinel.index_series(10.0, 106.0) is None


# ---------------------------------------------------------------- sâu bệnh

def test_stress_khoe_manh_thi_an_toan(with_key, monkeypatch):
    _series(monkeypatch, [0.70, 0.71, 0.69, 0.72, 0.70, 0.71])
    r = optical.stress(10.0, 106.0)
    assert r["level"] == "safe"
    assert r["cause_hint"] is None


def test_stress_giam_manh_thi_bao_dong(with_key, monkeypatch):
    _series(monkeypatch, [0.70, 0.71, 0.69, 0.72, 0.70, 0.40])
    r = optical.stress(10.0, 106.0)
    assert r["level"] == "danger"
    assert r["change_pct"] < -25


def test_loang_lo_goi_y_sau_benh(with_key, monkeypatch):
    # Trung bình giảm VÀ std tăng gấp 4 → dấu hiệu ổ bệnh, không phải hạn.
    _series(monkeypatch, [(0.70, 0.04), (0.71, 0.04), (0.69, 0.04),
                          (0.72, 0.04), (0.70, 0.04), (0.55, 0.16)])
    r = optical.stress(10.0, 106.0)
    assert r["level"] in ("warning", "danger")
    assert r["patchiness_ratio"] >= 1.4
    assert "LOANG LỔ" in r["cause_hint"]


def test_giam_deu_goi_y_nguyen_nhan_toan_vung(with_key, monkeypatch):
    # Trung bình giảm nhưng std KHÔNG đổi → hợp với hạn/mặn hơn là sâu bệnh.
    _series(monkeypatch, [(0.70, 0.05), (0.71, 0.05), (0.69, 0.05),
                          (0.72, 0.05), (0.70, 0.05), (0.55, 0.04)])
    r = optical.stress(10.0, 106.0)
    assert r["patchiness_ratio"] <= 0.9
    assert "ĐỀU" in r["cause_hint"]


def test_stress_can_it_nhat_4_quan_sat(with_key, monkeypatch):
    _series(monkeypatch, [0.70, 0.68])
    assert optical.stress(10.0, 106.0) is None


def test_nen_so_sanh_la_chinh_thua_khong_phai_nguong_co_dinh(with_key, monkeypatch):
    # Vườn NDVI thấp tự nhiên (0,35) nhưng ỔN ĐỊNH → không được báo động chỉ vì
    # con số thấp hơn ngưỡng "cây khỏe" chung.
    _series(monkeypatch, [0.35, 0.34, 0.36, 0.35, 0.34, 0.35])
    r = optical.stress(10.0, 106.0)
    assert r["level"] == "safe"


# ---------------------------------------------------------------- năng suất

def test_growth_dang_len(with_key, monkeypatch):
    _series(monkeypatch, [0.20, 0.28, 0.38, 0.50, 0.62, 0.72],
            start_days_ago=180, step=30)
    r = optical.growth(10.0, 106.0)
    assert "sinh trưởng" in r["stage"]
    assert r["trend_per_10d"] > 0


def test_growth_dang_chin(with_key, monkeypatch):
    _series(monkeypatch, [0.30, 0.55, 0.75, 0.80, 0.66, 0.50],
            start_days_ago=180, step=30)
    r = optical.growth(10.0, 106.0)
    assert "chín" in r["stage"]
    assert r["days_since_peak"] > 0
    assert r["ndvi_peak"] == 0.80


def test_growth_khong_bao_gio_tra_tan_tren_ha(with_key, monkeypatch):
    """Ràng buộc trung thực: không có hệ số hiệu chuẩn thì không có tấn/ha."""
    _series(monkeypatch, [0.30, 0.55, 0.75, 0.80, 0.66, 0.50],
            start_days_ago=180, step=30)
    r = optical.growth(10.0, 106.0)
    blob = repr(r).lower()
    assert "tấn/ha" not in blob or "KHÔNG quy ra tấn/ha" in r["caveat"]
    assert not any(k.startswith("yield_t") or "tan_ha" in k for k in r)


def test_growth_dat_trong(with_key, monkeypatch):
    _series(monkeypatch, [0.60, 0.55, 0.40, 0.25, 0.15, 0.12],
            start_days_ago=180, step=30)
    r = optical.growth(10.0, 106.0)
    assert "trống" in r["stage"]


# ---------------------------------------------------------------- thay đổi

def test_mat_tham_thuc_vat(with_key, monkeypatch):
    calls = {"n": 0}

    def _post(url, payload):
        calls["n"] += 1
        mean = 0.75 if calls["n"] == 1 else 0.30      # kỳ trước rồi kỳ sau
        return {"data": [_interval(date.today(), mean)]}

    monkeypatch.setattr(sentinel, "_post", _post)
    r = optical.vegetation_loss(10.0, 106.0)
    assert r["level"] == "danger"
    assert r["delta"] < -0.25
    assert "bão hoặc gió mạnh" in r["possible_causes"]
    # Phải nói rõ vệ tinh không biết nguyên nhân
    assert "không tự biết nguyên nhân" in r["caveat"]


def test_khong_doi_thi_khong_bao(with_key, monkeypatch):
    monkeypatch.setattr(sentinel, "_post",
                        lambda u, p: {"data": [_interval(date.today(), 0.70)]})
    r = optical.vegetation_loss(10.0, 106.0)
    assert r["level"] == "safe"
    assert r["possible_causes"] == []


def test_xay_dung_moi_can_ca_hai_tin_hieu(with_key, monkeypatch):
    """NDBI tăng một mình KHÔNG đủ — mùa khô cũng làm NDBI tăng."""
    calls = {"n": 0}

    def _post(url, payload):
        calls["n"] += 1
        # thứ tự gọi: NDBI trước, NDBI sau, NDVI trước, NDVI sau
        mean = {1: 0.10, 2: 0.30, 3: 0.55, 4: 0.54}[calls["n"]]
        return {"data": [_interval(date.today(), mean)]}

    monkeypatch.setattr(sentinel, "_post", _post)
    r = optical.new_construction(10.0, 106.0)
    assert r["built_up_signal"] is True
    assert r["vegetation_loss_signal"] is False
    assert r["both_signals"] is False
    assert r["level"] == "safe"          # không kết luận khi chỉ có một tín hiệu


def test_xay_dung_moi_khi_du_hai_tin_hieu(with_key, monkeypatch):
    calls = {"n": 0}

    def _post(url, payload):
        calls["n"] += 1
        mean = {1: 0.05, 2: 0.28, 3: 0.60, 4: 0.25}[calls["n"]]
        return {"data": [_interval(date.today(), mean)]}

    monkeypatch.setattr(sentinel, "_post", _post)
    r = optical.new_construction(10.0, 106.0)
    assert r["both_signals"] is True
    assert r["level"] == "danger"
    assert "KHÔNG PHẢI KẾT LUẬN PHÁP LÝ" in r["caveat"]


# ---------------------------------------------------------------- module

def test_module_pest_dung_anh_that(with_key, monkeypatch):
    from app.modules.registry import get_module
    _series(monkeypatch, [0.70, 0.71, 0.69, 0.72, 0.70, 0.42])
    a = get_module("pest").assess(Location(lat=10.0, lon=106.0))
    assert a.status == "ok"
    assert a.is_real is True
    assert a.risk_level == "danger"
    assert "Sentinel-2" in a.data_sources[0]


def test_module_pest_thieu_khoa_thi_noi_ro_cach_sua(monkeypatch):
    from app.modules.registry import get_module
    monkeypatch.delenv("TERRATWIN_COPERNICUS_ID", raising=False)
    monkeypatch.delenv("TERRATWIN_COPERNICUS_SECRET", raising=False)
    a = get_module("pest").assess(Location(lat=10.0, lon=106.0))
    assert a.status == "need_data"
    assert a.risk_level == "unknown"
    assert "dataspace.copernicus.eu" in a.recommendation


def test_module_yield_dung_anh_that(with_key, monkeypatch):
    from app.modules.registry import get_module
    _series(monkeypatch, [0.20, 0.35, 0.55, 0.72, 0.80, 0.78],
            start_days_ago=180, step=30)
    a = get_module("yield").assess(Location(lat=10.0, lon=106.0))
    assert a.status == "ok" and a.is_real is True
    assert "ndvi_dinh" in a.metrics


def test_thong_bao_phan_biet_thieu_khoa_va_thieu_anh(with_key, monkeypatch):
    """Hai nguyên nhân khác nhau phải cho ra hai lời nhắc khác nhau."""
    from app.modules.registry import get_module
    monkeypatch.setattr(sentinel, "_post", lambda u, p: None)   # có khóa, hỏng ảnh
    a = get_module("pest").assess(Location(lat=10.0, lon=106.0))
    assert "đã có khóa nhưng chưa lấy được ảnh" in a.headline
    assert "bay qua mỗi khoảng 5 ngày" in a.recommendation


def test_khong_co_nhanh_gia_lap_trong_ma_nguon():
    """Chốt chặn: không được có chế độ 'demo' sinh NDVI giả.

    Một chỉ số NDVI bịa trông y hệt NDVI thật. Nếu ai đó sau này thêm nhánh
    fallback sinh số cho đẹp demo, test này phải đỏ.
    """
    src = open(os.path.join(os.path.dirname(__file__), "..", "app",
                            "services", "sentinel.py"), encoding="utf-8").read()
    for banned in ("random", "fake", "demo_ndvi", "mock"):
        assert banned not in src.lower(), f"sentinel.py không được chứa '{banned}'"
