"""Kiểm A–Z 21/11/2026, P2-2 — câu "thổ cư/quy hoạch → Không đủ dữ liệu" phải chỉ đúng bước tiếp theo: cổng tra quy hoạch
CHÍNH THỨC (.gov.vn) của tỉnh, hoặc hướng dẫn hỏi Văn phòng đăng ký đất đai. Không trang tư nhân."""
from __future__ import annotations

from app.services import listing_check, zoning_portals


def test_chi_cong_nha_nuoc_da_kiem():
    for prov, p in zoning_portals.PORTALS.items():
        host = p["url"].split("/")[2]
        assert host.endswith(".gov.vn"), (prov, host)
        assert p["checked"]


def test_ha_noi_va_tphcm_co_cong():
    hn = zoning_portals.for_point(21.1405, 105.8468)          # Đông Anh
    assert hn["province"] == "Hà Nội" and hn["portal"]["url"] == "https://qhkhsdd.hanoi.gov.vn"
    assert "không kiểm quy hoạch" in hn["note"] and "cổng chính thức" in hn["note"]
    hcm = zoning_portals.for_point(10.7769, 106.7009)         # quận 1
    assert hcm["province"] == "TP Hồ Chí Minh" and hcm["portal"]["url"].endswith("hochiminhcity.gov.vn")


def test_khanh_hoa_co_cong_gis_cua_tinh():
    """Kiểm A–Z lần 2 (22/11/2026): thêm đúng một tỉnh đã tự mở kiểm (.gov.vn, có ngày kiểm)."""
    z = zoning_portals.for_point(12.2388, 109.1967)          # Nha Trang
    assert z["province"] == "Khánh Hòa" and z["portal"]["url"] == "https://gis.khanhhoa.gov.vn/public/8192/"
    assert z["portal"]["checked"] == "2026-11-22"


def test_tinh_chua_co_cong_thi_huong_dan_hoi_vp_dang_ky():
    z = zoning_portals.for_point(20.9716, 106.2834)           # Tuệ Tĩnh (thửa demo)
    assert z["portal"] is None and "Văn phòng đăng ký đất đai" in z["note"]


def test_kiem_tin_kem_buoc_tiep_va_khong_vao_ho_so(monkeypatch):
    monkeypatch.setattr(listing_check, "evidence", lambda lat, lon, types: {})
    r = listing_check.check("Bán lô đất 100m2 thổ cư 100%, sổ đỏ chính chủ.", 21.1405, 105.8468)
    assert any(c["type"] == "residential" and c["verdict"] == "insufficient" for c in r["claims"])
    assert r["zoning"]["portal"]["url"] == "https://qhkhsdd.hanoi.gov.vn"
    assert all("zoning" not in c for c in r["claims"])         # không nằm trong câu → không vào hồ sơ ký
    r2 = listing_check.check("Đất cao ráo, gần sông.", 21.1405, 105.8468)
    assert r2["zoning"] is None                                 # không có câu thổ cư → không chèn gì
    from app.services import dossier
    monkeypatch.setattr(listing_check, "check", lambda text, lat, lon: r)
    sec = dossier.listing_section("x", 21.1405, 105.8468)
    assert "zoning" not in sec and all("zoning" not in c for c in sec["claims"])
