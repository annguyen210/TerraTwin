"""Nâng cấp 25/11/2026 — hai bản đồ MẤT RỪNG SAU MỐC 31/12/2020 theo năm trong sàng lọc EUDR (tham chiếu, không bỏ
phiếu): JRC TMF (rừng ẩm nhiệt đới của EU, 1990–2025) và Hansen/UMD GFC v1.12 (năm mất tán cây 2001–2024).

Đo thật 25/11/2026: Lâm Đồng 11,465/107,505 (ô 1,1 × 1,1 km) — TMF 32,7% rừng ẩm 2020, mất 6,8% (2021–2023); Hansen
mất tán cây 25,2% (2021–2024). Rừng Cát Tiên 89% rừng ẩm, mất 0%; cà phê Buôn Ma Thuột 0,2%. Bộ đọc Hansen khớp từng
điểm ảnh với GDAL/rasterio trên khung 80 × 80 (cả lossyear lẫn treecover2000)."""
from __future__ import annotations

import io
import os

import numpy as np
import pytest
from PIL import Image
from shapely.geometry import box

from app.services import cache_store, eudr_forest as ef
from app.services import hansen_gfc, jrc_tmf, reqlang


# ------------------------------------------------------------------ Hansen: đọc GeoTIFF bằng HTTP Range

def _fake_tiff(a: np.ndarray) -> bytes:
    b = io.BytesIO()
    Image.fromarray(a).save(b, format="TIFF", compression="tiff_lzw", tiffinfo={278: 1})   # 1 hàng/dải như Hansen
    return b.getvalue()


def test_doc_dung_cac_hang_can_bang_range(monkeypatch):
    a = (np.arange(400 * 400) % 251).astype(np.uint8).reshape(400, 400)
    data = _fake_tiff(a)
    asked = []

    def rng(url, x, y, timeout=40.0):
        asked.append((x, y))
        return data[x:y] if y <= len(data) else data[x:] + b"\0" * (y - len(data))

    monkeypatch.setattr(hansen_gfc, "TILE_PX", 400)
    monkeypatch.setattr(hansen_gfc, "_range", rng)
    hansen_gfc._layout.cache_clear()
    assert (hansen_gfc.read_rows("lossyear", "t", 10, 30, 5, 50) == a[10:30, 5:50]).all()
    assert (hansen_gfc.read_rows("lossyear", "t", 399, 400, 0, 400) == a[399:400]).all()   # một hàng (TIFF 1 dải)
    # Không tải cả tệp: đoạn dữ liệu lớn nhất chỉ cỡ các hàng cần đọc.
    assert max(y - x for x, y in asked) < len(data) / 4
    hansen_gfc._layout.cache_clear()


def test_tu_choi_bo_cuc_la_thay_vi_doc_sai(monkeypatch):
    data = _fake_tiff(np.zeros((300, 300), dtype=np.uint8))          # sai kích thước ô
    monkeypatch.setattr(hansen_gfc, "_range", lambda url, x, y, timeout=40.0: (data + b"\0" * y)[x:y])
    hansen_gfc._layout.cache_clear()
    with pytest.raises(ValueError):
        hansen_gfc._layout("u")
    hansen_gfc._layout.cache_clear()


def test_ten_o_10_do():
    assert hansen_gfc.tile_name(12.7, 108.0)[0] == "20N_100E"
    assert hansen_gfc.tile_name(21.0, 105.8)[0] == "30N_100E"
    assert hansen_gfc.tile_name(9.5, 105.0)[0] == "10N_100E"
    assert hansen_gfc.tile_name(16.5, 112.0)[0] == "20N_110E"


def _fake_rows(cover_fn, year_fn):
    """read_rows giả: giá trị theo toạ độ tâm điểm ảnh."""
    def read(layer, tile, r0, r1, c0, c1):
        top = int(tile[:2]) * (1 if tile[2] == "N" else -1)
        left = int(tile[4:7])
        lat = top - (np.arange(r0, r1) + 0.5) * hansen_gfc.PIX
        lon = left + (np.arange(c0, c1) + 0.5) * hansen_gfc.PIX
        gx, gy = np.meshgrid(lon, lat)
        return (cover_fn if layer == "treecover2000" else year_fn)(gx, gy).astype(np.uint8)
    return read


def test_hansen_ty_le_theo_nam_va_nguong_tan(monkeypatch):
    # Nửa tây có tán 80% (nửa đông 10% — dưới ngưỡng 30% nên không tính); trong nửa tây: góc tây-bắc mất 2022,
    # góc tây-nam mất 2015 (trước mốc).
    g = box(108.0, 12.0, 108.01, 12.01)
    monkeypatch.setattr(hansen_gfc, "read_rows", _fake_rows(
        lambda x, y: np.where(x < 108.005, 80, 10),
        lambda x, y: np.where((x < 108.0025) & (y > 12.005), 22, np.where((x < 108.0025) & (y <= 12.005), 15, 0))))
    r = hansen_gfc._measure(g)
    assert r["pixels"] == 40 * 40
    assert r["treecover2000_pct"] == 50.0
    assert r["loss_after_2020_pct"] == 12.5 and r["loss_by_year"] == {"2022": 12.5}
    assert r["loss_2001_2020_pct"] == 12.5
    assert 14.5 < r["loss_after_2020_ha"] < 15.8                    # 200 điểm ảnh × ~0,0757 ha (ô 0,01° ≈ 121 ha)


def test_hansen_qua_ranh_hai_o(monkeypatch):
    seen = set()
    base = _fake_rows(lambda x, y: np.full(x.shape, 90), lambda x, y: np.where(y > 10.0, 23, 0))

    def read(layer, tile, *a):
        seen.add(tile)
        return base(layer, tile, *a)
    monkeypatch.setattr(hansen_gfc, "read_rows", read)
    r = hansen_gfc._measure(box(106.0, 9.995, 106.01, 10.005))      # cắt vĩ tuyến 10°N
    assert seen == {"10N_100E", "20N_100E"}
    assert r["pixels"] == 40 * 40 and r["loss_by_year"] == {"2023": 50.0}


@pytest.mark.goi_jrc_that                                   # dùng hansen_gfc.loss thật (conftest không thay)
def test_hansen_loi_nguon_tra_none_va_khong_nho_dem(monkeypatch):
    def boom(*a, **k):
        raise OSError("GCS 503")
    put = []
    monkeypatch.setattr(hansen_gfc, "read_rows", boom)
    monkeypatch.setattr(cache_store, "get", lambda k: None)
    monkeypatch.setattr(cache_store, "put", lambda *a, **k: put.append(a))
    assert hansen_gfc.loss(box(108.0, 12.0, 108.01, 12.01)) is None
    assert put == []


# ------------------------------------------------------------------ JRC TMF: WMS căn lưới gốc

def _png(cls: np.ndarray) -> bytes:
    rgb = {k: v for v, k in jrc_tmf.CLASSES.items()}
    a = np.zeros((*cls.shape, 4), dtype=np.uint8)
    for k, v in rgb.items():
        a[cls == k] = (*v, 255)
    b = io.BytesIO()
    Image.fromarray(a, "RGBA").save(b, format="PNG")
    return b.getvalue()


def test_khung_can_luoi_goc():
    bbox, w, h = jrc_tmf.grid((107.40001, 11.42001, 107.40999, 11.42999))
    assert (w, h) == (40, 40)
    assert abs(bbox[0] - 107.40) < 1e-9 and abs(bbox[3] - 11.43) < 1e-9


def test_tmf_mat_va_suy_thoai_theo_nam(monkeypatch):
    g = box(107.40, 11.42, 107.41, 11.43)                           # 40 × 40 điểm ảnh
    asked = []

    def png(layer, bbox, w, h, timeout=60.0):
        y = int(layer.split("_")[1])
        asked.append(y)
        c = np.full((h, w), 1, dtype=np.uint8)                      # 2020: toàn rừng nguyên vẹn
        c[:, 30:] = 6                                               # 1/4 phía đông: đất khác (không phải rừng 2020)
        if y >= 2022:
            c[:10, :30] = 3                                         # 2022: mất 10 hàng × 30 cột
        if y >= 2024:
            c[10:20, :30] = 2                                       # 2024: suy thoái 10 × 30
        if y >= 2025:
            c[:10, :30] = 4                                         # 2025: chỗ mất đã tái sinh — vẫn tính mất từ 2022
        return _png(c)
    monkeypatch.setattr(jrc_tmf, "_png", png)
    r = jrc_tmf._measure(g)
    assert r["forest2020_pct"] == 75.0 and r["undisturbed2020_pct"] == 75.0
    assert r["lost_after_2020_pct"] == 18.8 and r["lost_by_year"] == {"2022": 18.8}
    assert r["degraded_after_2020_pct"] == 18.8 and r["degraded_by_year"] == {"2024": 18.8}
    assert sorted(set(asked)) == [2020, 2021, 2022, 2023, 2024, 2025]


def test_tmf_khong_doi_lop_chi_tai_hai_nam(monkeypatch):
    asked = []

    def png(layer, bbox, w, h, timeout=60.0):
        asked.append(layer)
        return _png(np.full((h, w), 6, dtype=np.uint8))
    monkeypatch.setattr(jrc_tmf, "_png", png)
    r = jrc_tmf._measure(box(108.04, 12.72, 108.05, 12.73))
    assert r["forest2020_pct"] == 0.0 and r["lost_after_2020_pct"] == 0.0
    assert asked == ["AnnualChange_2020", "AnnualChange_2025"]


def test_tmf_ngoai_vung_phu_hoac_loi(monkeypatch):
    monkeypatch.setattr(jrc_tmf, "_png", lambda *a, **k: _png(np.zeros((40, 40), dtype=np.uint8)))
    assert jrc_tmf._measure(box(107.40, 11.42, 107.41, 11.43)) is None   # trong suốt hết = ngoài vùng phủ
    monkeypatch.setattr(jrc_tmf, "_png", lambda *a, **k: None)
    assert jrc_tmf._measure(box(107.40, 11.42, 107.41, 11.43)) is None


# ------------------------------------------------------------------ câu đối chiếu: nói rõ, KHÔNG đổi mức

TMF_LOST = {"id": "jrc_tmf", "name": jrc_tmf.NAME, "pixels": 1600, "forest2020_pct": 32.7, "undisturbed2020_pct": 12.0,
            "lost_after_2020_pct": 6.8, "lost_after_2020_ha": 8.2, "degraded_after_2020_pct": 3.4,
            "lost_by_year": {"2021": 3.9, "2022": 2.5, "2023": 0.4}, "degraded_by_year": {"2022": 1.7}}
HAN_LOST = {"id": "hansen_gfc", "name": hansen_gfc.NAME, "pixels": 1600, "treecover2000_pct": 99.6,
            "loss_2001_2020_pct": 34.4, "loss_after_2020_pct": 25.2, "loss_after_2020_ha": 30.59,
            "loss_by_year": {"2021": 8.8, "2022": 9.2, "2023": 6.8, "2024": 0.4}, "last_year": 2024}
TMF_NONE = {**TMF_LOST, "forest2020_pct": 89.2, "lost_after_2020_pct": 0.0, "lost_after_2020_ha": 0.0,
            "degraded_after_2020_pct": 0.7, "lost_by_year": {}, "degraded_by_year": {"2024": 0.7}}
HAN_NONE = {**HAN_LOST, "loss_after_2020_pct": 0.4, "loss_after_2020_ha": 0.5, "loss_by_year": {"2022": 0.4}}


def test_cau_doi_chieu():
    reqlang.set_lang("vi")
    n = ef.loss_reference_note("low", {"tmf": TMF_LOST, "hansen": HAN_LOST})
    assert "trái với kết luận" in n and "6.8% thửa" in n and "2021, 2022, 2023" in n and "25.2%" in n
    assert "suy thoái" in n and "CHƯA đổi" in n
    n = ef.loss_reference_note("high", {"tmf": TMF_LOST, "hansen": None})
    assert "trái với" not in n and "JRC TMF" in n and "Hansen" not in n
    n = ef.loss_reference_note("review", {"tmf": TMF_NONE, "hansen": HAN_NONE})
    assert "không thấy mất rừng" in n and "kèm" in n                  # dưới 1% = nhiễu, không gọi là mất
    assert "cùng không thấy" in ef.loss_reference_note("low", {"tmf": TMF_NONE, "hansen": None})
    # Ca Cát Tiên (đo thật 25/11/2026): chỉ TMF thấy suy thoái 1,1%, Hansen 0% — không được nói "thu hoạch", và
    # suy thoái không được gọi là "mất".
    n = ef.loss_reference_note("review", {"tmf": {**TMF_NONE, "degraded_after_2020_pct": 1.1,
                                                  "degraded_by_year": {"2024": 1.1}},
                                          "hansen": {**HAN_NONE, "loss_after_2020_pct": 0.0, "loss_by_year": {}}})
    assert "không thấy mất rừng" in n and "riêng JRC TMF" in n and "suy thoái" in n and "thu hoạch" not in n
    assert ef.loss_reference_note("unknown", {"tmf": TMF_LOST, "hansen": HAN_LOST}) is None
    assert ef.loss_reference_note("low", {"tmf": None, "hansen": None}) is None
    assert ef.loss_reference_note("low", None) is None
    reqlang.set_lang("en")
    assert "contradicting" in ef.loss_reference_note("low", {"tmf": TMF_LOST, "hansen": HAN_LOST})
    reqlang.set_lang("vi")


def _raw(lr):
    return {"forest_2020": [{"id": "wc2020", "pct": 0.0}, {"id": "alos2020", "pct": 0.0}, {"id": "io", "pct": 0.0}],
            "io_trajectory": [{"year": y, "tree_pct": 0.0} for y in ef.IO_YEARS],
            "s2": {"before": None, "after": None}, "protected": {"checked": True, "inside": []},
            "plot": {"geometry_used": "polygon"}, "eu_reference": None, "loss_reference": lr}


def test_muc_khong_doi_va_tin_hieu_co_so():
    reqlang.set_lang("vi")
    out = ef._localize(_raw({"tmf": TMF_LOST, "hansen": HAN_LOST}))
    assert out["level"] == "low"                                     # quy tắc v1 chốt trước — bản đồ tham chiếu không bỏ phiếu
    assert any("trái với kết luận" in r for r in out["reasons"])
    assert out["signals"]["tmf_lost_after_2020_pct"] == 6.8 and out["signals"]["hansen_loss_after_2020_pct"] == 25.2
    out = ef._localize(_raw({"tmf": None, "hansen": HAN_NONE}))
    assert any("JRC TMF" in c and "Chưa đọc được" in c for c in out["caveats"])
    out = ef._localize(_raw({"tmf": {**TMF_NONE, "forest2020_pct": 0.0}, "hansen": HAN_NONE}))
    assert any("rừng khộp khô" in c for c in out["caveats"])
    # Kết quả cũ (trước 25/11) không có khoá loss_reference: không câu, không chú thích thừa.
    old = _raw(None)
    del old["loss_reference"]
    out = ef._localize(old)
    assert not any("mất rừng theo năm" in c for c in out["caveats"])
    assert out["signals"]["tmf_lost_after_2020_pct"] is None


def test_ket_qua_nho_dem_cu_duoc_bo_sung(monkeypatch):
    """Kết quả sàng lọc nhớ đệm trước nâng cấp: chỉ đọc thêm hai bản đồ, không đo lại 14 nguồn."""
    old = _raw(None)
    del old["loss_reference"]
    monkeypatch.setattr(cache_store, "get", lambda k: dict(old) if k.startswith("eudr-screen") else None)
    monkeypatch.setattr(ef, "class_share", lambda *a, **k: pytest.fail("không được đo lại bản đồ"))
    monkeypatch.setattr(jrc_tmf, "change", lambda geom: TMF_LOST)
    monkeypatch.setattr(hansen_gfc, "loss", lambda geom: HAN_LOST)
    plot = {"kind": "polygon", "geometry": {"type": "Polygon", "coordinates": [[[107.5, 11.46], [107.51, 11.46],
                                                                                 [107.51, 11.47], [107.5, 11.47],
                                                                                 [107.5, 11.46]]]}}
    out = ef.screen(plot)
    assert out["loss_reference"]["tmf"]["lost_after_2020_pct"] == 6.8
    assert out["loss_reference"]["hansen"]["source"].startswith("Hansen et al. 2013")


def test_csv_co_cot_tham_chieu():
    from app.services import eudr
    plots = [{"index": 0, "ref": "A1", "kind": "polygon", "valid": True, "centroid": {"lat": 11.46, "lon": 107.5}}]
    r = ef._localize(_raw({"tmf": TMF_LOST, "hansen": HAN_LOST}))
    rows = eudr.to_csv(plots, {"0": r}).lstrip("﻿").splitlines()
    head, row = rows[0].split(","), rows[1]
    for c in ("jrc_gfc2020_forest_pct", "jrc_tmf_lost_after_2020_pct", "hansen_loss_after_2020_pct", "hansen_loss_years"):
        assert c in head
    assert "6.8" in row and "2021 2022 2023 2024" in row


@pytest.mark.goi_jrc_that
@pytest.mark.skipif(not os.environ.get("TERRATWIN_LIVE_TESTS"), reason="mạng thật — đặt TERRATWIN_LIVE_TESTS=1")
def test_nguon_that_lam_dong():
    """Chạy tay: TERRATWIN_LIVE_TESTS=1 pytest tests/test_mat_rung_sau_moc.py -k nguon_that"""
    g = box(107.50, 11.46, 107.51, 11.47)
    t, h = jrc_tmf._measure(g), hansen_gfc._measure(g)
    assert t is not None and t["forest2020_pct"] > 20 and t["lost_after_2020_pct"] > 1
    assert h is not None and h["loss_after_2020_pct"] > 5
