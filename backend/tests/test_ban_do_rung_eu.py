"""Nâng cấp 24/11/2026 — bản đồ rừng 2020 của chính EU (JRC GFC2020 v4) làm bản đồ THAM CHIẾU trong sàng lọc EUDR.

Đo thật 24/11/2026: cà phê Buôn Ma Thuột "Rủi ro phá rừng" (3 bản đồ: 100/89/68%), cao su Bình Phước "Cần xem lại"
(100/100/100%) — GFC2020 v4 thấy 0% rừng cả hai. Quy tắc v1 chốt trước kiểm định nên KHÔNG đổi mức; chỉ nói rõ khi bất đồng."""
from __future__ import annotations

import io

import pytest

from app.services import eudr_forest as ef
from app.services import jrc_gfc, reqlang


def test_bat_dong_thi_noi_ro_nhung_khong_doi_muc():
    reqlang.set_lang("vi")
    n = ef.eu_reference_note("high", 0.0)
    assert "chỉ thấy 0% rừng" in n and "CHƯA đổi" in n
    assert "nên xem lại" in ef.eu_reference_note("low", 42.0)
    assert "cùng chiều" in ef.eu_reference_note("review", 95.0)
    assert ef.eu_reference_note("high", None) is None and ef.eu_reference_note("unknown", 0.0) is None


def test_localize_giu_muc_them_ly_do_va_tin_hieu():
    reqlang.set_lang("vi")
    raw = {"forest_2020": [{"id": "wc2020", "pct": 100.0}, {"id": "alos2020", "pct": 89.0}, {"id": "io", "pct": 68.0}],
           "io_trajectory": [{"year": y, "tree_pct": v} for y, v in ((2018, 68), (2019, 68), (2020, 68), (2022, 0), (2023, 0))],
           "s2": {"before": None, "after": None}, "protected": {"checked": True, "inside": []},
           "plot": {"geometry_used": "polygon"},
           "eu_reference": {"id": "jrc2020", "name": jrc_gfc.NAME, "pct": 0.0, "pixels": 132}}
    out = ef._localize(raw)
    assert out["level"] == "high"                                  # quy tắc v1 giữ nguyên
    assert any("JRC GFC2020 v4" in r for r in out["reasons"]) and out["signals"]["eu_reference_pct"] == 0.0
    raw["eu_reference"] = None
    out = ef._localize(raw)
    assert out["signals"]["eu_reference_pct"] is None and any("JRC" in c for c in out["caveats"])


def _png(w, h, forest_cols):
    from PIL import Image
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for x in forest_cols:
        for y in range(h):
            im.putpixel((x, y), (*jrc_gfc.FOREST_RGB, 255))
    b = io.BytesIO()
    im.save(b, format="PNG")
    return b.getvalue()


@pytest.mark.goi_jrc_that
def test_dem_diem_anh_rung_trong_ranh(monkeypatch):
    """Nửa trái khung là rừng → 50%; điểm ảnh ngoài ranh (tam giác) không được đếm."""
    from shapely.geometry import box, Polygon
    from app.services import cache_store
    monkeypatch.setattr(cache_store, "get", lambda k: None)
    monkeypatch.setattr(cache_store, "put", lambda *a, **k: None)
    seen = {}

    def fake(bbox, w, h, timeout=45.0):
        seen["wh"] = (w, h)
        return _png(w, h, range(w // 2))
    monkeypatch.setattr(jrc_gfc, "_png", fake)
    r = jrc_gfc.forest_share(box(107.749, 12.879, 107.751, 12.881))
    assert abs(r["pct"] - 50.0) < 6 and r["pixels"] > 100 and r["layer"] == "gfc2020_v4"
    tri = Polygon([(107.749, 12.879), (107.751, 12.879), (107.749, 12.881)])       # nghiêng về nửa trái
    assert jrc_gfc.forest_share(tri)["pct"] > 60
    monkeypatch.setattr(jrc_gfc, "_png", lambda *a, **k: None)                     # WMS hỏng
    assert jrc_gfc.forest_share(box(107.0, 12.0, 107.001, 12.001)) is None
