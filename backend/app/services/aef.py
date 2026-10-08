"""ALPHAEARTH FOUNDATIONS — embedding vệ tinh 64 chiều của Google DeepMind (2025), mỗi điểm 10 m.

MÔ HÌNH NỀN TẢNG, KHÔNG PHẢI MỘT CHỈ SỐ. AlphaEarth học từ hàng chục nguồn (Sentinel-1/2, Landsat,
radar, khí hậu, địa hình…) và nén CẢ NĂM của mỗi điểm 10 m thành một vectơ đơn vị 64 chiều. Hai
nơi có vectơ gần nhau là hai nơi "giống nhau quanh năm" — đúng thứ cần để tách rừng với vườn cây
lâu năm, chỗ ba bản đồ rừng 2020 gục (kiểm định v2: 12/16 ô sai là cây trồng sau 2000).

ĐỌC THẲNG BẢN GEOZARR CÔNG KHAI (source.coop/tge-labs/aef-mosaic, CC-BY 4.0, miễn phí, không khoá):
mảng [năm 2017–2025, 64 kênh, y, x] lưới kinh/vĩ độ ~10 m; mỗi shard 4096×4096 chia 256 khối con
256×256 nén zstd, bảng chỉ mục ở CUỐI shard. Không dùng bản COG theo vùng UTM: COG lưu THEO KÊNH
(64 khối riêng cho một điểm, đo 81–148 s/điểm); khối con của Zarr chứa đủ 64 kênh → ~1 lượt tải
nhỏ cho mỗi vùng 2,5 km. Bộ đọc này chỉ cần numpy + zstandard — không kéo GDAL lên máy chủ free.

Giải lượng tử: int8 → ((x/127.5)^2)·dấu(x); -128 là ô trống.
Ghi công bắt buộc: "The AlphaEarth Foundations Satellite Embedding dataset is produced by Google and
Google DeepMind."
"""
from __future__ import annotations

import struct
import threading
import urllib.error
import urllib.request
from collections import OrderedDict

import numpy as np

BASE = "https://data.source.coop/tge-labs/aef-mosaic"
ATTRIBUTION = "The AlphaEarth Foundations Satellite Embedding dataset is produced by Google and Google DeepMind."
YEARS = list(range(2017, 2026))            # trục thời gian của mảng (9 năm) — xem kiểm thử _check_time
GSD = 8.983111749910169e-05                # độ / điểm ảnh
X0, Y0 = -180.0, 83.68570533713473         # góc trên-trái
SHARD = 4096
INNER = 256
PER = SHARD // INNER                       # 16 khối con mỗi chiều
NODATA = -128
_MISSING = (1 << 64) - 1
_UA = {"User-Agent": "TerraTwin/aef (+https://terratwin-web.onrender.com)"}

_LOCK = threading.Lock()
_INDEX: OrderedDict[str, bytes] = OrderedDict()            # shard → bảng chỉ mục (4 KB)
_CHUNK: OrderedDict[tuple, np.ndarray] = OrderedDict()     # (shard, iy, ix) → int8 [64,256,256] (4 MB)
_MAX_INDEX, _MAX_CHUNK = 256, 12                           # ~48 MB trần bộ nhớ khối con


def _get(url: str, rng: str | None = None, timeout: float = 90.0, tries: int = 3) -> bytes:
    """Tải (một đoạn) tệp; thử lại khi mạng chập chờn — 404 thì trả ngay cho người gọi xử lý."""
    import time
    h = dict(_UA)
    if rng:
        h["Range"] = rng
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError:
            raise
        except (TimeoutError, OSError):
            if k == tries - 1:
                raise
            time.sleep(2 * (k + 1))
    raise RuntimeError("unreachable")


def pixel(lat: float, lon: float) -> tuple[int, int]:
    """(hàng, cột) toàn cầu của điểm ảnh chứa (lat, lon)."""
    return int((Y0 - lat) / GSD), int((lon - X0) / GSD)


def _shard_url(t: int, sy: int, sx: int) -> str:
    return f"{BASE}/embeddings/c/{t}/0/{sy}/{sx}"


def _index(url: str) -> bytes | None:
    with _LOCK:
        if url in _INDEX:
            _INDEX.move_to_end(url)
            return _INDEX[url]
    try:
        raw = _get(url, f"bytes=-{PER * PER * 16 + 4}")
    except urllib.error.HTTPError as e:
        if e.code == 404:                  # shard không tồn tại (biển, ngoài phủ) → toàn ô trống
            raw = b""
        else:
            raise
    with _LOCK:
        _INDEX[url] = raw
        while len(_INDEX) > _MAX_INDEX:
            _INDEX.popitem(last=False)
    return raw or None


def _chunk(t: int, sy: int, sx: int, iy: int, ix: int) -> np.ndarray | None:
    key = (t, sy, sx, iy, ix)
    with _LOCK:
        if key in _CHUNK:
            _CHUNK.move_to_end(key)
            return _CHUNK[key]
    url = _shard_url(t, sy, sx)
    idx = _index(url)
    if not idx:
        return None
    off, nb = struct.unpack_from("<QQ", idx, (iy * PER + ix) * 16)
    if off == _MISSING and nb == _MISSING:
        return None
    import zstandard
    raw = _get(url, f"bytes={off}-{off + nb - 1}")
    arr = np.frombuffer(zstandard.ZstdDecompressor().decompress(raw, max_output_size=64 * INNER * INNER),
                        dtype="<i1").reshape(64, INNER, INNER)
    with _LOCK:
        _CHUNK[key] = arr
        while len(_CHUNK) > _MAX_CHUNK:
            _CHUNK.popitem(last=False)
    return arr


def dequantize(v: np.ndarray) -> np.ndarray:
    f = v.astype("float32") / 127.5
    return f * f * np.sign(f)


def window(lat0: float, lon0: float, lat1: float, lon1: float, year: int) -> np.ndarray:
    """Mọi vectơ (đã giải lượng tử, bỏ ô trống) trong hộp — mảng [n, 64]. Hộp nhỏ (≤ vài km)."""
    if year not in YEARS:
        raise ValueError(f"AlphaEarth có các năm {YEARS[0]}–{YEARS[-1]}")
    t = YEARS.index(year)
    r0, c0 = pixel(max(lat0, lat1), min(lon0, lon1))
    r1, c1 = pixel(min(lat0, lat1), max(lon0, lon1))
    out = []
    for r in range(r0, r1 + 1):
        # gom theo khối con để không lặp tra cứu
        for c in range(c0, c1 + 1):
            sy, sx = r // SHARD, c // SHARD
            iy, ix = (r % SHARD) // INNER, (c % SHARD) // INNER
            ch = _chunk(t, sy, sx, iy, ix)
            if ch is None:
                continue
            v = ch[:, r % INNER, c % INNER]
            if (v == NODATA).any():
                continue
            out.append(v)
    return dequantize(np.array(out, dtype="<i1")) if out else np.zeros((0, 64), "float32")


def mean_embedding(lat0: float, lon0: float, lat1: float, lon1: float, year: int) -> tuple[np.ndarray | None, int]:
    """Vectơ đại diện của một vùng: trung bình các vectơ đơn vị rồi chuẩn hoá lại (cách tổng hợp
    khuyến nghị cho embedding đơn vị). Trả (vectơ hoặc None nếu không có ô hợp lệ, số điểm ảnh)."""
    w = window(lat0, lon0, lat1, lon1, year)
    if len(w) == 0:
        return None, 0
    m = w.mean(axis=0)
    n = float(np.linalg.norm(m))
    return (m / n if n > 0 else m), len(w)


def around(lat: float, lon: float, year: int, half_px: int = 1) -> tuple[np.ndarray | None, int]:
    """Vectơ đại diện cho một điểm: trung bình (2·half_px+1)² điểm ảnh quanh nó."""
    d = half_px * GSD
    return mean_embedding(lat - d, lon - d, lat + d, lon + d, year)


def clear_cache() -> None:
    with _LOCK:
        _INDEX.clear()
        _CHUNK.clear()
