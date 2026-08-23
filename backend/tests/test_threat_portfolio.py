"""Cờ `threat` và tổng quan danh mục theo vùng.

BỐI CẢNH — một lỗi thật đã sửa: `risk_level` chỉ có nghĩa "mức trên thang của
chính mô-đun đó". Điện mặt trời trả "danger" khi bức xạ ở mức TRUNG BÌNH; bảo
hiểm tham số trả "danger" khi ĐÃ KÍCH HOẠT CHI TRẢ — tin tốt. Trộn chúng vào
danh sách cảnh báo làm rà soát nền gửi email lúc ba giờ sáng báo "điện mặt
trời: nguy hiểm".

Vài lần như thế là người dùng tắt thông báo, và lần thứ mười hai — lần lũ thật
— họ không còn nhận được nữa. Toàn bộ lời hứa "báo động giả 3%" sụp ở đúng chỗ
này, nên nó có bộ test riêng.
"""
from __future__ import annotations

import pytest

from app.schemas import Location


# ---------------------------------------------------------------- cờ threat

def test_mo_dun_co_hoi_khong_duoc_tinh_la_de_doa():
    from app.modules.registry import get_module

    for mid in ("solar", "parametric_insurance", "yield", "land_risk"):
        m = get_module(mid)
        assert m is not None, mid
        assert m.threat is False, f"{mid} không phải mối đe doạ"


def test_moi_hiem_hoa_that_deu_duoc_danh_dau_de_doa():
    from app.modules.registry import get_module
    from app.services import hazard

    for mid in hazard.IDS:
        assert get_module(mid).threat is True, mid
    for mid in ("salinity", "aquaculture", "storm_damage", "upstream_flood",
                "urban", "mining", "supply_chain"):
        assert get_module(mid).threat is True, mid


def test_co_threat_lo_ra_api():
    from app.modules.registry import list_modules

    infos = {m.id: m for m in list_modules()}
    assert infos["solar"].threat is False
    assert infos["flood"].threat is True


# ---------------------------------------------- lọc trong danh sách cảnh báo

class _Fake:
    """Kết quả assess giả, đủ thuộc tính mà scan() đọc tới."""

    def __init__(self, mid, level, real=True):
        self.module_id, self.risk_level, self.is_real = mid, level, real
        self.module_name, self.headline = mid, f"{mid} {level}"
        self.recommendation, self.score = "làm gì đó", None
        self.status, self.metrics, self.confidence = "ok", {}, 0.7
        self.forecast, self.data_sources, self.detail = [], [], ""


@pytest.fixture
def fake_scan(monkeypatch):
    """Ép mọi mô-đun trả 'danger' để chỉ còn bộ lọc quyết định kết quả."""
    from app.modules.registry import get_module, list_modules

    for info in list_modules():
        m = get_module(info.id)
        monkeypatch.setattr(
            m, "assess",
            (lambda mid: lambda loc: _Fake(mid, "danger"))(info.id))
    from app.schemas import TerraScoreResult
    monkeypatch.setattr(
        "app.services.terrascore.compute",
        lambda loc, assessments=None: TerraScoreResult(
            location=loc, score=50, grade="C", summary="giả lập",
            real_data_ratio=1.0))


def test_dien_mat_troi_khong_bao_gio_vao_danh_sach_canh_bao(fake_scan):
    """Chốt chặn cho email lúc ba giờ sáng."""
    from app.services import scan

    r = scan.scan(Location(lat=10.0, lon=106.0))
    ids = {a.id for a in r.alerts}
    assert "solar" not in ids
    assert "parametric_insurance" not in ids
    assert "yield" not in ids
    assert "land_risk" not in ids
    # Nhưng hiểm họa thật thì PHẢI có, không thì bộ lọc quá tay.
    assert "flood" in ids and "drought" in ids


def test_moi_canh_bao_deu_la_de_doa_that(fake_scan):
    from app.modules.registry import get_module
    from app.services import scan

    r = scan.scan(Location(lat=10.0, lon=106.0))
    assert r.alerts, "phải còn cảnh báo, không được lọc sạch"
    for a in r.alerts:
        assert get_module(a.id).threat is True, a.id


def test_mo_dun_khong_de_doa_van_hien_trong_luoi(fake_scan):
    """Lọc khỏi CẢNH BÁO, không phải giấu khỏi giao diện.

    Người dùng vẫn cần xem được tiềm năng điện mặt trời — chỉ là đừng đánh thức
    họ lúc nửa đêm vì nó.
    """
    from app.services import scan

    r = scan.scan(Location(lat=10.0, lon=106.0))
    assert "solar" in {m.id for m in r.modules}


# ---------------------------------------------------------------- danh mục

class _Plot:
    def __init__(self, pid, name, lat, lon, ha=None):
        self.id, self.name, self.lat, self.lon = pid, name, lat, lon
        self.area_ha = ha


def test_danh_muc_rong_noi_ro_phai_lam_gi():
    from app.services import portfolio

    d = portfolio.overview([])
    assert d["available"] is False
    assert "Bấm bản đồ" in d["message"]


def test_gop_theo_vung_va_xep_vung_nang_nhat_len_dau(monkeypatch):
    from app.services import portfolio

    # Hai thửa cùng một ô 0,1°, một thửa ở ô khác.
    plots = [_Plot(1, "A", 10.24, 106.38, 2.0),
             _Plot(2, "B", 10.26, 106.39, 3.0),
             _Plot(3, "C", 21.03, 105.85, 1.0)]

    def fake_scan(loc, include_heavy=False):
        # Ô 10,2/106,3 nguy hiểm; ô Hà Nội an toàn.
        lvl = "danger" if loc.lat < 15 else "safe"
        mods = [type("M", (), {"id": "flood", "name": "Lũ", "icon": "🌊",
                               "group": "B", "risk_level": lvl,
                               "headline": f"lũ {lvl}", "is_real": True,
                               "threat": True, "score": None})()]
        return type("R", (), {
            "modules": mods, "alerts": [],
            "terrascore": type("T", (), {"score": 40, "grade": "C"})()})()

    monkeypatch.setattr("app.services.scan.scan", fake_scan)
    d = portfolio.overview(plots)

    assert d["available"] is True
    assert d["plots_scanned"] == 3
    assert d["counts"]["danger"] == 2 and d["counts"]["safe"] == 1
    assert d["total_ha"] == 6.0 and d["at_risk_ha"] == 5.0
    # Vùng nặng nhất phải đứng đầu
    assert d["cells"][0]["danger"] == 2
    assert d["cells"][0]["at_risk_pct"] == 100.0
    assert d["cells"][0]["top_driver"] == "flood"
    # Thửa nguy hiểm xếp trước thửa an toàn
    assert d["plots"][0]["risk_level"] == "danger"
    assert d["plots"][-1]["risk_level"] == "safe"


def test_bbox_bao_tron_moi_thua(monkeypatch):
    from app.services import portfolio

    plots = [_Plot(1, "A", 9.0, 105.0), _Plot(2, "B", 22.0, 107.0)]

    def fake_scan(loc, include_heavy=False):
        return type("R", (), {
            "modules": [], "alerts": [],
            "terrascore": type("T", (), {"score": 80, "grade": "A"})()})()

    monkeypatch.setattr("app.services.scan.scan", fake_scan)
    b = portfolio.overview(plots)["bbox"]
    assert b["min_lat"] == 9.0 and b["max_lat"] == 22.0
    assert b["min_lon"] == 105.0 and b["max_lon"] == 107.0


def test_mo_dun_cho_anh_ve_tinh_khong_lam_ban_danh_muc(monkeypatch):
    """"Chưa đủ dữ liệu" không phải một đánh giá — không được tính vào mức."""
    from app.services import portfolio

    def fake_scan(loc, include_heavy=False):
        mods = [
            type("M", (), {"id": "pest", "name": "Sâu bệnh", "icon": "🌾",
                           "group": "A", "risk_level": "unknown",
                           "headline": "chưa đủ dữ liệu", "is_real": False,
                           "threat": True, "score": None})(),
            type("M", (), {"id": "flood", "name": "Lũ", "icon": "🌊",
                           "group": "B", "risk_level": "safe",
                           "headline": "an toàn", "is_real": True,
                           "threat": True, "score": None})(),
        ]
        return type("R", (), {
            "modules": mods, "alerts": [],
            "terrascore": type("T", (), {"score": 80, "grade": "A"})()})()

    monkeypatch.setattr("app.services.scan.scan", fake_scan)
    d = portfolio.overview([_Plot(1, "A", 10.0, 106.0)])
    assert d["counts"]["safe"] == 1
    assert d["counts"]["unknown"] == 0


def test_danh_muc_qua_lon_thi_cat_bot_va_noi_ro(monkeypatch):
    from app.services import portfolio

    def fake_scan(loc, include_heavy=False):
        return type("R", (), {
            "modules": [], "alerts": [],
            "terrascore": type("T", (), {"score": 80, "grade": "A"})()})()

    monkeypatch.setattr("app.services.scan.scan", fake_scan)
    plots = [_Plot(i, f"P{i}", 10.0 + i * 0.001, 106.0) for i in range(400)]
    d = portfolio.overview(plots)
    assert d["truncated"] is True
    assert d["plots_scanned"] == portfolio.MAX_PLOTS
    assert d["plots_total"] == 400
    assert "hạn mức" in d["caveat"]


# ---------------------------------------------------------------- hạn mức khoá

def test_khoa_api_dem_luot_va_chan_khi_vuot(monkeypatch):
    """Khóa bị lộ mà không có trần sẽ đốt hạn mức nguồn dữ liệu của cả hệ thống."""
    import time

    from fastapi.testclient import TestClient

    monkeypatch.setenv("TERRATWIN_KEY_MONTHLY_QUOTA", "3")
    from app.main import app

    with TestClient(app) as c:
        em = f"quota{int(time.time() * 1000)}@example.com"
        tok = c.post("/api/auth/register",
                     json={"email": em, "password": "MatKhau123!",
                           "name": "Q"}).json()["access_token"]
        h = {"Authorization": "Bearer " + tok}
        k = c.post("/api/keys?label=Thu", headers=h).json()
        assert k["monthly_quota"] == 3

        codes = [c.get("/api/plots", headers={"X-API-Key": k["key"]}).status_code
                 for _ in range(5)]
        assert codes[:3] == [200, 200, 200]
        assert codes[3:] == [429, 429]

        row = c.get("/api/keys", headers=h).json()[0]
        assert row["calls_total"] == 5
        assert row["calls_period"] == 5


def test_khoa_api_khong_gioi_han_khi_dat_0(monkeypatch):
    import time

    from fastapi.testclient import TestClient

    monkeypatch.setenv("TERRATWIN_KEY_MONTHLY_QUOTA", "0")
    from app.main import app

    with TestClient(app) as c:
        em = f"unl{int(time.time() * 1000)}@example.com"
        tok = c.post("/api/auth/register",
                     json={"email": em, "password": "MatKhau123!",
                           "name": "U"}).json()["access_token"]
        h = {"Authorization": "Bearer " + tok}
        k = c.post("/api/keys", headers=h).json()
        for _ in range(6):
            assert c.get("/api/plots",
                         headers={"X-API-Key": k["key"]}).status_code == 200


def test_di_tru_them_cot_chay_duoc_hai_lan():
    """init_db phải chạy lại được mà không đổ — deploy nào cũng gọi nó."""
    from app.db import init_db

    init_db()
    init_db()
