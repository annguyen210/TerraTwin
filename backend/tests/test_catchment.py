"""Mưa thượng nguồn — lũ đến từ nước rơi Ở TRÊN CAO.

Giả lập ở tầng `realdata.elevation_multi` / `weather_multi` chứ không giả lập
`catchment.upstream()`, để phần hình học nan quạt, lọc điểm cao hơn, tính trọng
số theo độ dốc và so với mưa tại chỗ đều được chạy thật.

Điều quan trọng nhất mà bộ test này giữ: **hàm phải TỪ CHỐI trả lời ở đồng
bằng**. Chênh cao vài mét nằm trong sai số đứng của DEM toàn cầu; trả một con
số "mưa thượng nguồn" ở Bến Tre là bịa ra tín hiệu từ nhiễu, và nó sẽ trông y
hệt một cảnh báo thật.
"""
from __future__ import annotations

import pytest

from app.schemas import Location
from app.services import catchment, realdata


def _flat_terrain(pts):
    """Đồng bằng: chênh cao vài mét, dưới sai số DEM."""
    return [3.0 + (i % 4) for i in range(len(pts))]


def _valley(pts):
    """Thung lũng: điểm giữa thấp, xung quanh cao dần theo vòng."""
    out = [12.0]                      # chính thửa, dưới đáy
    n = catchment.BEARINGS
    for ring, _km in enumerate(catchment.RADII_KM):
        for _ in range(n):
            out.append(12.0 + 150.0 * (ring + 1))
    return out[:len(pts)]


def _hilltop(pts):
    """Đỉnh đồi: thửa cao nhất, xung quanh thấp dần."""
    out = [500.0]
    n = catchment.BEARINGS
    for ring, _km in enumerate(catchment.RADII_KM):
        for _ in range(n):
            out.append(500.0 - 120.0 * (ring + 1))
    return out[:len(pts)]


def _rain(mm):
    def _w(pts):
        return [[{"day": i, "date": f"2026-08-{20 + i:02d}", "precip": mm / 7.0,
                  "et0": 3.0, "tmax": 30.0} for i in range(7)]
                for _ in pts]
    return _w


@pytest.fixture
def no_cache(monkeypatch):
    monkeypatch.setattr(realdata, "_CACHE", {})
    return True


# ---------------------------------------------------------------- hình học

def test_nan_quat_dung_so_diem():
    pts = catchment._fan(10.0, 106.0)
    assert len(pts) == 1 + catchment.BEARINGS * len(catchment.RADII_KM)
    assert pts[0] == (10.0, 106.0)


def test_diem_lay_mau_dung_khoang_cach():
    from app.services import datasources as ds

    for km in catchment.RADII_KM:
        la, lo = catchment._offset(10.0, 106.0, km, 0.0)
        assert abs(ds._haversine_km(10.0, 106.0, la, lo) - km) < 0.3


# ------------------------------------------------- từ chối khi địa hình phẳng

def test_dong_bang_thi_TU_CHOI_tra_ket_qua(no_cache, monkeypatch):
    """Chốt chặn quan trọng nhất của tệp này.

    Ở ĐBSCL chênh cao nằm trong sai số DEM. Trả một con số ở đó là biến nhiễu
    thành tín hiệu, và người dùng không có cách nào phân biệt với cảnh báo thật.
    """
    monkeypatch.setattr(realdata, "elevation_multi", _flat_terrain)
    monkeypatch.setattr(realdata, "weather_multi", _rain(500.0))
    monkeypatch.setattr(realdata, "weather_7d", lambda la, lo: None)

    r = catchment.upstream(10.24, 106.38)
    assert r["available"] is False
    assert r["reason"] == "flat"
    assert "upstream_rain_mm" not in r
    assert "đê bao" in r["message"]


def test_dinh_doi_thi_bao_khong_co_suon_do_ve(no_cache, monkeypatch):
    monkeypatch.setattr(realdata, "elevation_multi", _hilltop)
    monkeypatch.setattr(realdata, "weather_multi", _rain(400.0))
    monkeypatch.setattr(realdata, "weather_7d", lambda la, lo: None)

    r = catchment.upstream(15.0, 108.0)
    assert r["available"] is False
    assert r["reason"] == "no_upslope"
    assert "tin tốt" in r["message"]


# ---------------------------------------------------------------- thung lũng

def test_thung_lung_mua_lon_tren_cao_thi_bao_dong(no_cache, monkeypatch):
    monkeypatch.setattr(realdata, "elevation_multi", _valley)
    monkeypatch.setattr(realdata, "weather_multi", _rain(300.0))
    # Tại chỗ khô ráo — đây chính là ca mà module này tồn tại để bắt.
    monkeypatch.setattr(realdata, "weather_7d", lambda la, lo: [
        {"day": i, "date": f"2026-08-{20 + i:02d}", "precip": 0.0,
         "et0": 3.0, "tmax": 30.0} for i in range(7)])

    r = catchment.upstream(15.36, 107.90)
    assert r["available"] is True
    assert r["level"] == "danger"
    assert r["upstream_rain_mm"] == pytest.approx(300.0, abs=1.0)
    assert r["local_rain_mm"] == 0.0
    assert r["extra_vs_local_mm"] > 250
    assert r["upslope_points"] == catchment.BEARINGS * len(catchment.RADII_KM)


def test_mua_thuong_nguon_bang_tai_cho_thi_KHONG_bao(no_cache, monkeypatch):
    """Mưa đều cả vùng thì thượng nguồn không thêm thông tin gì.

    Đây là chỗ dễ sai nhất: 200 mm ở thượng nguồn nghe rất đáng sợ, nhưng nếu
    tại chỗ cũng 200 mm thì module Lũ đã bắt rồi — báo thêm lần nữa chỉ làm
    tăng tỉ lệ báo động giả mà không thêm một thông tin nào.
    """
    monkeypatch.setattr(realdata, "elevation_multi", _valley)
    monkeypatch.setattr(realdata, "weather_multi", _rain(200.0))
    monkeypatch.setattr(realdata, "weather_7d", lambda la, lo: [
        {"day": i, "date": f"2026-08-{20 + i:02d}", "precip": 200.0 / 7,
         "et0": 3.0, "tmax": 30.0} for i in range(7)])

    r = catchment.upstream(15.36, 107.90)
    assert r["available"] is True
    assert r["level"] == "safe"
    assert abs(r["extra_vs_local_mm"]) < 5


def test_thuong_nguon_kho_hon_tai_cho(no_cache, monkeypatch):
    monkeypatch.setattr(realdata, "elevation_multi", _valley)
    monkeypatch.setattr(realdata, "weather_multi", _rain(10.0))
    monkeypatch.setattr(realdata, "weather_7d", lambda la, lo: [
        {"day": i, "date": f"2026-08-{20 + i:02d}", "precip": 20.0,
         "et0": 3.0, "tmax": 30.0} for i in range(7)])

    r = catchment.upstream(15.36, 107.90)
    assert r["level"] == "safe"
    assert r["extra_vs_local_mm"] < -20
    assert "khô hơn" in r["verdict"]


def test_diem_gan_va_cao_duoc_can_nang_hon(no_cache, monkeypatch):
    """Trọng số là mét chênh cao trên mỗi km — gần và dốc thì nặng ký hơn."""
    monkeypatch.setattr(realdata, "elevation_multi", _valley)
    monkeypatch.setattr(realdata, "weather_multi", _rain(100.0))
    monkeypatch.setattr(realdata, "weather_7d", lambda la, lo: None)

    r = catchment.upstream(15.36, 107.90)
    # _valley cho vòng ngoài cao hơn nhưng xa hơn; sườn "dốc nhất" phải là một
    # điểm có tỉ số chênh-cao/khoảng-cách lớn nhất, không phải điểm cao nhất.
    assert r["steepest"]["km"] <= catchment.RADII_KM[1]


def test_mat_du_lieu_tra_none(no_cache, monkeypatch):
    monkeypatch.setattr(realdata, "elevation_multi", lambda pts: [])
    assert catchment.upstream(15.0, 108.0) is None

    monkeypatch.setattr(realdata, "elevation_multi",
                        lambda pts: [None] * len(pts))
    assert catchment.upstream(15.0, 108.0) is None


# ---------------------------------------------------------------- mô-đun

def test_module_bao_dong_khi_tai_cho_chua_mua(no_cache, monkeypatch):
    from app.modules.registry import get_module

    monkeypatch.setattr(realdata, "elevation_multi", _valley)
    monkeypatch.setattr(realdata, "weather_multi", _rain(300.0))
    monkeypatch.setattr(realdata, "weather_7d", lambda la, lo: [
        {"day": i, "date": f"2026-08-{20 + i:02d}", "precip": 0.0,
         "et0": 3.0, "tmax": 30.0} for i in range(7)])

    a = get_module("upstream_flood").assess(Location(lat=15.36, lon=107.90))
    assert a.status == "ok" and a.is_real is True
    assert a.risk_level == "danger"
    assert "NGAY CẢ KHI" in a.recommendation
    assert a.metrics["mua_tai_cho_mm"] == 0.0


def test_module_o_dong_bang_tra_loi_day_du_chu_khong_phai_thieu_du_lieu(
        no_cache, monkeypatch):
    """Phẳng không phải "chưa đủ dữ liệu" — là một câu trả lời hoàn chỉnh."""
    from app.modules.registry import get_module

    monkeypatch.setattr(realdata, "elevation_multi", _flat_terrain)
    monkeypatch.setattr(realdata, "weather_multi", _rain(300.0))
    monkeypatch.setattr(realdata, "weather_7d", lambda la, lo: None)

    a = get_module("upstream_flood").assess(Location(lat=10.24, lon=106.38))
    assert a.status == "ok"          # KHÔNG phải need_data
    assert a.risk_level == "safe"
    assert "phẳng" in a.headline


def test_module_duoc_danh_dau_nang():
    """Nếu ai đó bỏ cờ này, quét toàn cảnh sẽ chậm gấp hơn ba mươi lần."""
    from app.modules.registry import get_module
    assert get_module("upstream_flood").heavy is True


def test_quet_toan_canh_bo_qua_nhung_ra_soat_nen_thi_khong():
    """Duyệt bản đồ phải nhanh; rà soát nền phải đủ.

    Đây là chỗ đánh đổi có chủ đích: lũ từ thượng nguồn ập tới lúc ba giờ sáng,
    không phải lúc người dùng đang mở app.
    """
    from pathlib import Path

    app = Path(__file__).resolve().parent.parent / "app"
    radar = (app / "services" / "radar.py").read_text(encoding="utf-8")
    assert "include_heavy=True" in radar

    scan_src = (app / "services" / "scan.py").read_text(encoding="utf-8")
    assert "include_heavy: bool = False" in scan_src


def test_module_lu_khong_tu_goi_catchment():
    """Module Lũ phải giữ nguyên tốc độ — không được lén gọi nan quạt.

    Đã đo: nhét catchment vào module Lũ làm quét toàn cảnh từ 2,5 s lên 82 s.
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parent.parent / "app" / "modules"
           / "group_b.py").read_text(encoding="utf-8")
    flood = src[src.index("class FloodModule"):src.index("class LandslideModule")]
    assert "catchment" not in flood or "KHÔNG nằm ở đây" in flood
