"""A8 — kiểm chứng watershed + decode PNG bằng dữ liệu GIẢ LẬP, không chạm
mạng (extract_boundary() cần ảnh Sentinel-2 thật qua Planetary Computer — chỉ
watershed_from_seed() và decode_png_grayscale() được test ở đây, đúng như
change_detect.py tách detect_from_series() ra để test được).

Tiêu chí "done when" của yêu cầu gốc: sai số diện tích < 15% so với vẽ tay.
Vì không có "vẽ tay" thật trong test tự động, mô phỏng bằng SỰ THẬT ĐÃ BIẾT:
vẽ một hình chữ nhật NDVI đồng nhất trong mảng giả lập, diện tích hình đó
CHÍNH LÀ "vẽ tay đúng" — so sánh diện tích watershed trả về với con số đó.
"""
from __future__ import annotations

import struct
import zlib

import numpy as np
import pytest

from app.services import watershed as ws
from app.services.watershed import (
    decode_png_grayscale, mask_to_area_ha, watershed_from_seed,
)

RNG = np.random.default_rng(7)


# ---------------------------------------------------------------------------
# decode_png_grayscale — mã hoá tay một PNG xám tối giản để test giải mã.
# ---------------------------------------------------------------------------

def _encode_png_grayscale(arr: np.ndarray) -> bytes:
    """Mã hoá PNG xám 8-bit, filter type 0 (None) cho mọi hàng — đủ để kiểm
    tra decode_png_grayscale() đọc lại đúng, không cần các filter phức tạp."""
    h, w = arr.shape
    raw = bytearray()
    for row in arr.astype(np.uint8):
        raw.append(0)   # filter type 0 = None
        raw += row.tobytes()
    idat = zlib.compress(bytes(raw))

    def chunk(ctype: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + ctype + data
               + struct.pack(">I", zlib.crc32(ctype + data)))

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
           + chunk(b"IDAT", idat) + chunk(b"IEND", b""))


def test_decode_png_grayscale_doc_dung_gia_tri():
    arr = np.array([[0, 64, 128], [192, 255, 32]], dtype=np.uint8)
    png = _encode_png_grayscale(arr)
    out = decode_png_grayscale(png)
    assert out.shape == (2, 3)
    np.testing.assert_array_almost_equal(out, arr.astype(np.float64))


def test_decode_png_grayscale_khung_lon_hon():
    arr = (RNG.uniform(0, 255, size=(20, 30))).astype(np.uint8)
    png = _encode_png_grayscale(arr)
    out = decode_png_grayscale(png)
    np.testing.assert_array_almost_equal(out, arr.astype(np.float64))


def test_decode_png_khong_phai_png_thi_bao_loi():
    with pytest.raises(ValueError):
        decode_png_grayscale(b"khong phai png")


# ---------------------------------------------------------------------------
# watershed_from_seed — tiêu chí "done when": sai số diện tích < 15%.
# ---------------------------------------------------------------------------

def _field_grid(h: int, w: int, r0: int, r1: int, c0: int, c1: int,
                field_ndvi: float = 0.62, outside_ndvi: float = 0.22,
                noise: float = 0.015) -> np.ndarray:
    """Một 'thửa' hình chữ nhật NDVI đồng nhất [r0:r1, c0:c1], xung quanh khác
    hẳn — mô phỏng ranh giới thật (bờ ruộng) giữa hai vùng đồng nhất."""
    g = np.full((h, w), outside_ndvi) + RNG.normal(0, noise, (h, w))
    g[r0:r1, c0:c1] = field_ndvi + RNG.normal(0, noise, (r1 - r0, c1 - c0))
    return g


def test_dien_tich_watershed_sai_so_duoi_15_phan_tram():
    h, w = 60, 60
    r0, r1, c0, c1 = 15, 45, 12, 48   # thửa 30×36 điểm ảnh = 1080 px
    grid = _field_grid(h, w, r0, r1, c0, c1)
    seed = ((r0 + r1) // 2, (c0 + c1) // 2)   # điểm bấm ở giữa thửa

    mask = watershed_from_seed(grid, seed)
    true_area_px = (r1 - r0) * (c1 - c0)
    got_area_px = int(mask.sum())

    err = abs(got_area_px - true_area_px) / true_area_px
    assert err < 0.15, (
        f"Sai số diện tích {err:.1%} vượt ngưỡng 15% "
        f"(thật {true_area_px}px, watershed {got_area_px}px)")

    # Điểm hạt giống PHẢI nằm trong vùng trả về — nếu không thì thuật toán sai
    # về nguyên tắc, bất kể diện tích có tình cờ đúng hay không.
    assert mask[seed]


def test_dien_tich_ha_tinh_dung_theo_kich_thuoc_pixel():
    mask = np.zeros((10, 10), dtype=bool)
    mask[2:5, 2:5] = True   # 9 px
    area = mask_to_area_ha(mask, pixel_size_m=10.0)   # mỗi px = 100 m²
    assert area == pytest.approx(9 * 100 / 10_000, rel=1e-6)


def test_watershed_khong_tran_khi_khong_co_ranh_gioi_ro():
    """Toàn khung đồng nhất (không có bờ ruộng nào) — watershed phải dừng lại
    ở trần an toàn (MAX_AREA_PX_RATIO), không được trả về TOÀN BỘ khung như
    thể cả khung là một thửa (mất ý nghĩa của việc 'vẽ ranh')."""
    h, w = 40, 40
    grid = np.full((h, w), 0.5) + RNG.normal(0, 0.01, (h, w))
    mask = watershed_from_seed(grid, (20, 20))
    assert mask.sum() < h * w   # không chiếm toàn bộ khung
    assert mask.sum() > 0


def test_seed_ngoai_khung_bao_loi():
    grid = np.full((10, 10), 0.5)
    with pytest.raises(ValueError):
        watershed_from_seed(grid, (20, 20))


# ---------------------------------------------------------------------------
# _grow_from_ndvi() — chốt chặn: chạm trần an toàn hoặc diện tích phi lý thì
# PHẢI trả ok=False, không được trả một con số như thể đó là kết quả đo được.
# Đây là lỗi thật đã đo trên production: 500m/150m/1000m đều ra đúng
# MAX_AREA_PX_RATIO × khung, nghĩa là watershed chưa từng thực sự dừng ở bờ
# ruộng — extract_boundary() cũ vẫn trả "available": True với con số đó.
# ---------------------------------------------------------------------------

def test_grow_tu_choi_khi_cham_tran_an_toan():
    """Khung đồng nhất hoàn toàn (không có bờ ruộng nào) — mô phỏng đúng
    triệu chứng thật: vùng lan luôn chạm trần MAX_AREA_PX_RATIO."""
    h, w = 40, 40
    grid = np.full((h, w), 0.5) + RNG.normal(0, 0.01, (h, w))
    out = ws._grow_from_ndvi(grid, buffer_m=300.0, size_px=w)
    assert out["ok"] is False
    assert out["reason"] == "hit_safety_cap"


def test_grow_thanh_cong_voi_thua_sach_ro_rang():
    h, w = 60, 60
    r0, r1, c0, c1 = 15, 45, 12, 48
    grid = _field_grid(h, w, r0, r1, c0, c1)
    out = ws._grow_from_ndvi(grid, buffer_m=300.0, size_px=w)
    assert out["ok"] is True
    assert 0 < out["area_ha"] < 20.0


def test_grow_tu_choi_khi_dien_tich_phi_ly_du_bien_sach():
    """Một 'thửa' sạch, ranh rõ ràng, nhưng chiếm gần hết khung rộng (buffer
    lớn) → diện tích quy đổi vượt MAX_PLAUSIBLE_HA dù không chạm trần pixel
    (vùng chỉ chiếm ~70% khung, dưới 0.85) — vẫn phải bị từ chối vì không còn
    giống một thửa canh tác nhỏ."""
    h, w = 100, 100
    r0, r1, c0, c1 = 5, 95, 5, 75   # ~63% khung — dưới trần pixel 0.85
    grid = _field_grid(h, w, r0, r1, c0, c1, noise=0.01)
    buffer_m = 2000.0   # khung rộng 4km → mỗi pixel ~40m → thửa quy đổi rất lớn
    out = ws._grow_from_ndvi(grid, buffer_m=buffer_m, size_px=w)
    assert out["ok"] is False
    assert out["reason"] == "implausibly_large"


def test_grow_tu_choi_khi_chiem_qua_nua_khung_du_nho_va_sach():
    """Kẽ hở thật đo trên production: buffer 150m → 7,04 ha trong khung 9 ha
    (chiếm 78%) — dưới CẢ HAI trần cũ (MAX_PLAUSIBLE_HA=20 và
    MAX_AREA_PX_RATIO=0,85 điểm ảnh) nên lọt lưới, dù rõ ràng vẫn là tràn.
    Mô phỏng đúng tỉ lệ: khung nhỏ (buffer 150m → mỗi pixel 5m, khung 9 ha),
    thửa sạch nhưng chiếm ~63% khung.

    Dùng RNG RIÊNG (không phải RNG dùng chung ở đầu file) — kết quả của test
    này không được phụ thuộc thứ tự chạy trước nó bao nhiêu test khác đã rút
    số ngẫu nhiên từ RNG dùng chung."""
    local_rng = np.random.default_rng(2024)
    h, w = 60, 60
    # 79% khung — watershed (có blur) thường VẼ HẸP HƠN hình chữ nhật thật một
    # chút, nên cần biên dư so với ngưỡng 50% để không phụ thuộc may rủi RNG.
    r0, r1, c0, c1 = 2, 58, 2, 52
    g = np.full((h, w), 0.22) + local_rng.normal(0, 0.01, (h, w))
    g[r0:r1, c0:c1] = 0.62 + local_rng.normal(0, 0.01, (r1 - r0, c1 - c0))
    out = ws._grow_from_ndvi(g, buffer_m=150.0, size_px=w)   # khung 9 ha, đúng ca thật
    assert out["ok"] is False
    assert out["reason"] == "too_large_fraction_of_frame"


def test_box_blur3_giu_nguyen_mang_dong_nhat():
    a = np.full((10, 10), 0.42)
    np.testing.assert_array_almost_equal(ws._box_blur3(a), a)


def test_box_blur3_lam_muot_nhieu_diem_don():
    a = np.zeros((5, 5))
    a[2, 2] = 9.0   # một điểm nhiễu đơn lẻ
    out = ws._box_blur3(a)
    assert out[2, 2] < 9.0   # chính điểm đó bị pha loãng bởi 8 láng giềng = 0
    assert out[2, 2] == pytest.approx(1.0, rel=1e-6)   # 9/9


# ---------------------------------------------------------------------------
# extract_boundary() — kiểm chứng đối chiếu hai cỡ khung, không chạm mạng
# (monkeypatch _fetch_ndvi_crop trả sẵn NDVI giả lập cho từng buffer_m).
# ---------------------------------------------------------------------------

def _field_grid_for_area(h: int, w: int, buffer_m: float, size_px: int,
                         area_ha: float, noise: float = 0.01) -> np.ndarray:
    """Dựng thửa vuông ở giữa khung sao cho diện tích THẬT (quy đổi theo
    buffer_m/size_px) đúng bằng area_ha — dùng để mô phỏng CÙNG một thửa vật
    lý ở hai cỡ khung khác nhau (thửa vật lý không đổi kích thước chỉ vì
    khung tìm rộng hay hẹp hơn)."""
    pixel_size_m = (buffer_m * 2.0) / size_px
    side_px = int(round((area_ha * 10_000) ** 0.5 / pixel_size_m))
    side_px = max(2, min(side_px, min(h, w) - 4))
    r0 = h // 2 - side_px // 2
    c0 = w // 2 - side_px // 2
    return _field_grid(h, w, r0, r0 + side_px, c0, c0 + side_px, noise=noise)


def test_extract_boundary_tu_choi_khi_hai_co_khung_lech_nhau(monkeypatch):
    h, w = 80, 80
    # Lần đo thứ nhất (buffer 500m) "thấy" thửa 3 ha THẬT; lần đối chiếu
    # (buffer 300m) lại "thấy" một thửa 12 ha — hai lần đo mâu thuẫn nhau,
    # đúng triệu chứng rò nhiễu đã đo trên production.
    grids = [
        _field_grid_for_area(h, w, 500.0, w, area_ha=3.0),
        _field_grid_for_area(h, w, 300.0, w, area_ha=12.0),
    ]
    calls = {"n": 0}

    def fake_fetch(lat, lon, buffer_m, size_px):
        grid = grids[calls["n"]]
        calls["n"] += 1
        return grid, {"id": "fake-scene", "properties": {"datetime": "2026-01-01T00:00:00Z"}}

    monkeypatch.setattr(ws, "_fetch_ndvi_crop", fake_fetch)
    out = ws.extract_boundary(16.0, 107.0, buffer_m=500.0, size_px=w)
    assert out["available"] is False
    assert out["reason"] == "unstable_across_scale"
    assert calls["n"] == 2   # phải thật sự gọi lần đo đối chiếu thứ hai


def test_extract_boundary_thanh_cong_khi_hai_co_khung_khop_nhau(monkeypatch):
    h, w = 80, 80
    # CÙNG một thửa vật lý 3 ha, chỉ khác cỡ khung tìm — hai lần đo phải
    # khớp nhau và extract_boundary phải trả kết quả.
    grids_by_buffer = {
        500.0: _field_grid_for_area(h, w, 500.0, w, area_ha=3.0),
        300.0: _field_grid_for_area(h, w, 300.0, w, area_ha=3.0),
    }

    def fake_fetch(lat, lon, buffer_m, size_px):
        return grids_by_buffer[buffer_m], {"id": "fake-scene",
                                           "properties": {"datetime": "2026-01-01T00:00:00Z"}}

    monkeypatch.setattr(ws, "_fetch_ndvi_crop", fake_fetch)
    out = ws.extract_boundary(16.0, 107.0, buffer_m=500.0, size_px=w)
    assert out["available"] is True
    assert 0 < out["area_ha"] < 20.0
    assert out["scene"] == "fake-scene"
