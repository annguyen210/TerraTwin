"""A8 — tự vẽ ranh thửa bằng watershed trên độ dốc NDVI quanh điểm bấm.

Ý TƯỞNG. Nội bộ một thửa, NDVI biến thiên ÊM (cùng loại cây, cùng giai đoạn
sinh trưởng). Ranh giới thửa — bờ ruộng, đường mòn, đổi loại cây — là nơi
NDVI đổi ĐỘT NGỘT. Coi |∇NDVI| (độ lớn gradient) như một mặt địa hình giả lập:
đáy thung lũng (dốc thấp) là NỘI BỘ thửa, sống núi (dốc cao) là RANH GIỚI.
Từ điểm người dùng bấm (một "hạt giống"), "ngập nước" dần từ đáy — lấy đúng
những điểm dốc thấp lân cận trước, dừng lại khi gặp sống núi — chính là thuật
toán watershed nguồn gốc từ Vincent & Soille (1991), rút gọn cho MỘT hạt
giống (không cần nhiều nhãn tranh nhau như watershed phân đoạn ảnh đầy đủ).

HAI PHẦN TÁCH RIÊNG (giống change_detect.py) để phần lõi test được không
chạm mạng:
  · watershed_from_seed() — thuật toán thuần, nhận mảng NDVI 2D có sẵn.
  · extract_boundary()    — mặt tiền, tự tải ảnh NDVI thật qua Planetary
    Computer (PNG xám, KHÔNG colormap — để đọc lại đúng giá trị NDVI thay vì
    phải đảo ngược bảng màu RdYlGn mà imagery.py dùng để HIỂN THỊ).

KHÔNG dùng scipy/skimage (không có trong requirements.txt, xem ghi chú ở
change_detect.py) — decode PNG bằng zlib (thư viện chuẩn) + tự lật filter
scanline, watershed bằng heapq (thư viện chuẩn).
"""
from __future__ import annotations

import heapq
import struct
import zlib

import numpy as np


# ---------------------------------------------------------------------------
# Decode PNG xám 8-bit thuần Python (không Pillow/opencv) — chỉ chunk IHDR/IDAT,
# color type 0 (xám) hoặc 2 (RGB, lấy trung bình kênh phòng khi titiler trả RGB).
# ---------------------------------------------------------------------------

_PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def decode_png_grayscale(data: bytes) -> np.ndarray:
    """Trả mảng (H, W) float64 trong [0,255] — GIÁ TRỊ THÔ của kênh (không tự
    rescale về NDVI, người gọi tự làm việc đó vì biết rescale range đã yêu cầu)."""
    if data[:8] != _PNG_SIG:
        raise ValueError("Không phải file PNG hợp lệ.")

    pos = 8
    width = height = bit_depth = color_type = None
    idat = bytearray()
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        ctype = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        if ctype == b"IHDR":
            width, height, bit_depth, color_type = struct.unpack(">IIBB", chunk[:10])
        elif ctype == b"IDAT":
            idat += chunk
        elif ctype == b"IEND":
            break
        pos += 8 + length + 4   # 4 = CRC

    if width is None:
        raise ValueError("Thiếu IHDR — file PNG hỏng.")
    if bit_depth != 8 or color_type not in (0, 2):
        raise ValueError(f"Chỉ hỗ trợ PNG xám/RGB 8-bit, gặp depth={bit_depth} type={color_type}.")

    channels = 1 if color_type == 0 else 3
    raw = zlib.decompress(bytes(idat))
    stride = width * channels
    out = np.zeros((height, width, channels), dtype=np.float64)
    prev = np.zeros(stride, dtype=np.int64)
    off = 0
    for y in range(height):
        ftype = raw[off]
        off += 1
        line = np.frombuffer(raw, dtype=np.uint8, count=stride, offset=off).astype(np.int64)
        off += stride

        if ftype == 0:      # None
            recon = line
        elif ftype == 1:    # Sub
            recon = line.copy()
            for i in range(channels, stride):
                recon[i] = (recon[i] + recon[i - channels]) & 0xFF
        elif ftype == 2:    # Up
            recon = (line + prev) & 0xFF
        elif ftype == 3:    # Average
            recon = line.copy()
            for i in range(stride):
                left = recon[i - channels] if i >= channels else 0
                recon[i] = (recon[i] + (left + prev[i]) // 2) & 0xFF
        elif ftype == 4:    # Paeth
            recon = line.copy()
            for i in range(stride):
                left = recon[i - channels] if i >= channels else 0
                up = prev[i]
                up_left = prev[i - channels] if i >= channels else 0
                recon[i] = (recon[i] + _paeth(int(left), int(up), int(up_left))) & 0xFF
        else:
            raise ValueError(f"Kiểu filter PNG không hỗ trợ: {ftype}")

        out[y] = recon.reshape(width, channels)
        prev = recon

    return out.mean(axis=2) if channels == 3 else out[:, :, 0]


# ---------------------------------------------------------------------------
# Watershed một hạt giống trên độ dốc NDVI.
# ---------------------------------------------------------------------------

# Bội số độ lệch chuẩn cục bộ quanh hạt giống dùng làm ngưỡng "sống núi".
# Cao hơn → thửa vẽ được RỘNG hơn (dễ tràn qua ranh thật); thấp hơn → hẹp hơn
# (dễ dừng sớm trong nội bộ thửa). 2,5 là điểm cân bằng thấy được qua thử
# nghiệm với dữ liệu giả lập — biên rõ (bờ ruộng thật) tách khỏi nhiễu nội bộ.
GRADIENT_SIGMA_MULT = 2.5
MAX_AREA_PX_RATIO = 0.85   # trần an toàn: không để "tràn" chiếm gần hết khung


def watershed_from_seed(ndvi: np.ndarray, seed_rc: tuple[int, int]) -> np.ndarray:
    """Trả mảng boolean (H, W) — True = thuộc thửa chứa điểm hạt giống.

    KHÔNG chạm mạng — nhận sẵn mảng NDVI (2D). Test bằng dữ liệu giả lập, xem
    tests/test_watershed.py.
    """
    h, w = ndvi.shape
    r0, c0 = seed_rc
    if not (0 <= r0 < h and 0 <= c0 < w):
        raise ValueError("Điểm hạt giống nằm ngoài khung ảnh.")

    gy, gx = np.gradient(ndvi.astype(np.float64))
    grad = np.hypot(gy, gx)

    # Ngưỡng "sống núi" ước lượng từ độ dốc TRONG một ô nhỏ quanh hạt giống —
    # đại diện cho độ nhiễu nội bộ BÌNH THƯỜNG của chính thửa này, không phải
    # một hằng số cứng áp cho mọi nơi (đất khô hạn và ruộng lúa có độ nhiễu
    # NDVI nội bộ khác hẳn nhau).
    pr0, pr1 = max(0, r0 - 3), min(h, r0 + 4)
    pc0, pc1 = max(0, c0 - 3), min(w, c0 + 4)
    patch = grad[pr0:pr1, pc0:pc1]
    threshold = float(patch.mean() + GRADIENT_SIGMA_MULT * patch.std())
    threshold = max(threshold, 1e-6)   # tránh ngưỡng 0 khi vùng quanh hạt giống phẳng tuyệt đối

    included = np.zeros((h, w), dtype=bool)
    visited = np.zeros((h, w), dtype=bool)
    heap: list[tuple[float, int, int]] = [(float(grad[r0, c0]), r0, c0)]
    visited[r0, c0] = True
    max_px = int(h * w * MAX_AREA_PX_RATIO)

    while heap and included.sum() < max_px:
        g, r, c = heapq.heappop(heap)
        if g > threshold:
            break   # gặp sống núi — dừng lan, phần còn lại trong heap còn dốc hơn nữa
        included[r, c] = True
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < h and 0 <= nc < w and not visited[nr, nc]:
                visited[nr, nc] = True
                heapq.heappush(heap, (float(grad[nr, nc]), nr, nc))

    return included


def mask_to_area_ha(mask: np.ndarray, pixel_size_m: float) -> float:
    return float(mask.sum()) * (pixel_size_m ** 2) / 10_000.0


def extract_boundary(lat: float, lon: float, buffer_m: float = 500.0,
                     size_px: int = 100) -> dict:
    """A8 — mặt tiền: tải PNG xám (không colormap) qua MPC, đọc lại NDVI, chạy
    watershed từ tâm ảnh (điểm người dùng bấm), trả diện tích + đa giác lưới
    thô (danh sách toạ độ hàng-cột) cho frontend vẽ lên bản đồ."""
    import urllib.parse
    import urllib.request

    from app.services import mpc

    # DATA của mpc.py trỏ endpoint /statistics (số liệu) — ảnh crop dùng
    # endpoint /bbox khác, đúng cái imagery.py đã dùng để hiện ảnh cho người
    # xem (chỉ khác: ở đây KHÔNG colormap, để đọc lại đúng giá trị NDVI).
    CROP_DATA = "https://planetarycomputer.microsoft.com/api/data/v1/item/bbox"

    box = mpc.bbox_around(lat, lon, buffer_m)
    from datetime import date, timedelta
    items = mpc.search(box, date.today() - timedelta(days=60), date.today(),
                       max_cloud=mpc.MAX_CLOUD, limit=5)
    if not items:
        return {"available": False, "reason": "no_imagery",
                "message": "Không có ảnh Sentinel-2 đủ quang mây gần đây cho vị trí này."}
    item = items[0]

    rescale_lo, rescale_hi = -0.2, 0.9
    q = urllib.parse.urlencode({
        "collection": mpc.COLLECTION, "item": item["id"],
        "expression": mpc.EXPR["NDVI"], "asset_as_band": "true",
        "width": size_px, "height": size_px,
        "rescale": f"{rescale_lo},{rescale_hi}",
        # CỐ Ý không có colormap_name — PNG xám tuyến tính, đọc lại được đúng
        # giá trị NDVI qua rescale, không phải đảo bảng màu.
    })
    bb = ",".join(f"{v:.5f}" for v in box)
    url = f"{CROP_DATA}/{bb}.png?{q}"

    try:
        with urllib.request.urlopen(url, timeout=mpc.TIMEOUT) as r:
            png_bytes = r.read()
    except Exception as e:
        return {"available": False, "reason": "fetch_failed",
                "message": f"Không tải được ảnh: {type(e).__name__}"}

    try:
        raw = decode_png_grayscale(png_bytes)
    except Exception as e:
        return {"available": False, "reason": "decode_failed",
                "message": f"Không đọc được PNG: {type(e).__name__}"}

    ndvi = rescale_lo + (raw / 255.0) * (rescale_hi - rescale_lo)
    seed = (ndvi.shape[0] // 2, ndvi.shape[1] // 2)   # điểm bấm luôn ở tâm khung crop
    mask = watershed_from_seed(ndvi, seed)

    pixel_size_m = (buffer_m * 2.0) / size_px
    area_ha = mask_to_area_ha(mask, pixel_size_m)

    # Đường viền thô: với mỗi hàng có điểm thuộc thửa, lấy cột trái/phải cùng —
    # đủ để frontend vẽ một đa giác gần đúng lên bản đồ, không cần contour-
    # tracing đầy đủ (Moore-Neighbor…) cho bản MVP này.
    rows_with = np.where(mask.any(axis=1))[0]
    outline_px = []
    for row in rows_with:
        cols = np.where(mask[row])[0]
        outline_px.append((int(row), int(cols.min()), int(cols.max())))

    return {
        "available": True,
        "area_ha": round(area_ha, 3),
        "pixel_size_m": round(pixel_size_m, 2),
        "grid_size": ndvi.shape[0],
        "scene": item["id"],
        "scene_date": item["properties"]["datetime"][:10],
        "outline_rows": outline_px,   # [(hàng, cột_trái, cột_phải), ...]
        "message": f"Ranh thửa tự vẽ ~{round(area_ha, 2)} ha từ ảnh {item['properties']['datetime'][:10]}.",
    }
