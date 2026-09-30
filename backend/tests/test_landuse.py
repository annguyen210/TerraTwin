"""Loại đất THẬT tại thửa (ESA WorldCover) và "Kế hoạch thửa" dựa trên nó.

Lỗi gốc (29/9/2026): điểm giữa phố Huế vẫn được tính "~20 triệu/ha đang chịu
rủi ro" theo cây LÚA — vì kế hoạch mặc định lúa cho mọi nơi. Không chạm mạng:
mpc._call và scan.scan đều được giả lập.
"""
from __future__ import annotations

import pytest

from app.schemas import Location, ScanModule, ScanResult, TerraScoreResult
from app.services import advisor, cache_store, landuse, reqlang


def _raw(hist: dict[int, float]) -> dict:
    return {"item": "ESA_WorldCover_10m_2021_v200_N15E105",
            "hist": {str(k): v for k, v in hist.items()}}


@pytest.fixture(autouse=True)
def _vi():
    reqlang.set_lang("vi")
    cache_store.clear_prefix("landuse")
    yield
    cache_store.clear_prefix("landuse")


def test_pho_hue_la_dat_xay_dung_khong_tinh_lua():
    lu = landuse.describe(_raw({50: 196}))
    assert lu["dominant_group"] == "built" and lu["dominant_pct"] == 100.0
    assert lu["year"] == "2021" and "WorldCover" in lu["source"]
    fit = landuse.crop_applicability(lu)
    assert fit["applicable"] is False and fit["default_crop"] is None
    assert "xây dựng" in fit["reason"]


def test_ruong_lua_mac_dinh_lua():
    fit = landuse.crop_applicability(landuse.describe(_raw({40: 150, 10: 46})))
    assert fit == {"applicable": True, "default_crop": "lua", "reason": None}


def test_dat_hon_hop_hoi_nguoi_dung_khong_doan():
    lu = landuse.describe(_raw({40: 90, 90: 60, 10: 46}))
    assert lu["dominant_group"] == "mixed"
    fit = landuse.crop_applicability(lu)
    assert fit["applicable"] is False and fit["default_crop"] is None
    assert "Chọn loại canh tác" in fit["reason"]


def test_mat_nuoc_goi_y_thuy_san():
    fit = landuse.crop_applicability(landuse.describe(_raw({80: 120, 50: 20})))
    assert fit["applicable"] is False and "thuỷ sản" in fit["reason"]


def test_khong_goi_duoc_worldcover_thi_noi_ro_dang_gia_dinh():
    fit = landuse.crop_applicability(None)
    assert fit["applicable"] is True and fit["default_crop"] == "lua"
    assert "Chưa xác định" in fit["reason"]


def test_ten_lop_theo_ngon_ngu_luc_goi():
    reqlang.set_lang("en")
    lu = landuse.describe(_raw({50: 196}))
    assert lu["classes"][0]["name"] == "Built-up"
    assert "built-up" in landuse.crop_applicability(lu)["reason"]


def test_fetch_raw_goi_mang_mot_lan_roi_dung_cache(monkeypatch):
    calls = []

    def fake_call(url, payload=None, timeout=60.0):
        calls.append(url)
        if "stac" in url:
            return {"features": [
                {"id": "ESA_WorldCover_10m_2020_v100_N15E105",
                 "properties": {"start_datetime": "2020-01-01T00:00:00Z"}},
                {"id": "ESA_WorldCover_10m_2021_v200_N15E105",
                 "properties": {"start_datetime": "2021-01-01T00:00:00Z"}}]}
        assert "item=ESA_WorldCover_10m_2021_v200" in url, "phải dùng bản MỚI NHẤT"
        return {"properties": {"statistics": {"map": {
            "histogram": [[100.0, 96.0], [50.0, 10.0]]}}}}

    monkeypatch.setattr(landuse.mpc, "_call", fake_call)
    a = landuse.composition(16.46, 107.59)
    b = landuse.composition(16.46, 107.59)
    assert a == b and a["dominant_group"] == "built" and a["dominant_pct"] == 51.0
    assert len(calls) == 2, "lần hai phải trúng cache, không gọi mạng"


def test_worldcover_hong_tra_none(monkeypatch):
    monkeypatch.setattr(landuse.mpc, "_call", lambda *a, **k: None)
    assert landuse.composition(16.46, 107.59) is None


# ---------------------------------------------------------------- Kế hoạch thửa

@pytest.fixture
def fake_scan(monkeypatch):
    """Một cảnh báo lũ thật trong 7 ngày tới."""
    from datetime import date, timedelta

    d = (date.today() + timedelta(days=2)).isoformat()
    flood = ScanModule(id="flood", name="Lũ", icon="", group="B", risk_level="danger",
                       headline="Lũ", recommendation="Kê cao đồ", is_real=True,
                       risk_dates=[d], peak_date=d)

    def fake(loc, include_heavy=False):
        ts = TerraScoreResult(location=loc, score=50, grade="C", summary="t")
        return ScanResult(location=loc, terrascore=ts, modules=[flood], alerts=[flood],
                          real_data_ratio=1.0, generated_at="2026-09-30T00:00:00")

    monkeypatch.setattr(advisor.scan, "scan", fake)


def _with_land(monkeypatch, hist):
    monkeypatch.setattr(advisor.landuse, "fetch_raw",
                        lambda lat, lon, radius_m=landuse.RADIUS_M: _raw(hist) if hist else None)


def test_ke_hoach_giua_pho_khong_quy_ra_tien_lua(fake_scan, monkeypatch):
    _with_land(monkeypatch, {50: 196})
    v = advisor.build(Location(lat=16.46, lon=107.59))["value"]
    assert v["applicable"] is False and v["crop"] is None
    assert v["items"] == [] and v["worst_hi"] == 0
    assert "xây dựng" in v["assumption"]
    assert v["land_use"]["dominant_group"] == "built"


def test_ke_hoach_ruong_lua_van_tinh_nhu_cu(fake_scan, monkeypatch):
    _with_land(monkeypatch, {40: 180, 10: 16})
    v = advisor.build(Location(lat=10.40, lon=105.20))["value"]
    assert v["applicable"] is True and v["crop"] == "lua"
    assert v["items"] and v["items"][0]["id"] == "flood" and v["worst_hi"] > 0
    assert v["land_use_note"] is None


def test_nguoi_dung_chu_dong_chon_cay_tren_dat_xay_dung_van_tinh_nhung_noi_ra(fake_scan, monkeypatch):
    _with_land(monkeypatch, {50: 196})
    v = advisor.build(Location(lat=16.46, lon=107.59), crop="raumau")["value"]
    assert v["applicable"] is True and v["crop"] == "raumau" and v["items"]
    assert v["land_use_note"] and "xây dựng" in v["land_use_note"]


def test_worldcover_hong_thi_ke_hoach_van_chay(fake_scan, monkeypatch):
    _with_land(monkeypatch, None)
    out = advisor.build(Location(lat=16.46, lon=107.59))
    assert out["value"]["crop"] == "lua" and out["value"]["land_use"] is None
    assert out["actions"] and out["safe_window"]["days"]
