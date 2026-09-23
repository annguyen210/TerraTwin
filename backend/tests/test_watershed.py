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
