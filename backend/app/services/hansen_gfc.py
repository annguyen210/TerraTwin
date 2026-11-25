"""NĂM MẤT TÁN CÂY — Hansen / UMD Global Forest Change v1.12 (2001–2024), 30 m (nâng cấp 25/11/2026).

Vì sao: sàng lọc EUDR hỏi "rừng năm 2020 có bị mất SAU 31/12/2020 không". Ba bản đồ đang bỏ phiếu chỉ cho trạng thái
quanh 2020 + Impact Observatory 2022–2023; bản đồ này cho NĂM CỤ THỂ mất tán cây (2021, 2022, 2023, 2024) ở từng điểm
ảnh 30 m — đúng lớp "tree cover loss" mà Global Forest Watch hiển thị, nhà nhập khẩu châu Âu nào cũng mở ra xem.

Giới hạn phải nói: "mất tán cây" là mọi lần cây bị thay thế cả tán (chặt, cháy, bão đổ), KỂ CẢ thu hoạch rừng trồng
(keo, bạch đàn) hay tái canh vườn cao su, cà phê — không đồng nghĩa phá rừng theo EUDR. Mỗi điểm ảnh chỉ ghi MỘT năm.

Đọc thẳng tệp GeoTIFF công khai trên Google Cloud Storage (ô 10°×10°, 40 000 × 40 000 điểm ảnh, mỗi dải 1 hàng nén
LZW): chỉ tải bảng vị trí và đúng các hàng phủ thửa bằng yêu cầu HTTP Range, giải nén bằng Pillow — không cần GDAL,
không tải cả tệp (lossyear 115 MB, treecover2000 495 MB). Dữ liệu không đổi đến bản kế tiếp → nhớ đệm dài.

Nguồn: Hansen, M. C. et al. (2013) Science 342: 850–853; bản v1.12 (Univ. of Maryland, 2025) — CC BY 4.0,
https://storage.googleapis.com/earthenginepartners-hansen/GFC-2024-v1.12/download.html
"""
from __future__ import annotations

import io
import math
import struct
import urllib.request
from functools import lru_cache

from app.services import cache_store, eudr_geo

VERSION = "GFC-2024-v1.12"
URL = ("https://storage.googleapis.com/earthenginepartners-hansen/" + VERSION + "/Hansen_" + VERSION +
       "_{layer}_{tile}.tif")
NAME = "Hansen/UMD Global Forest Change v1.12 — năm mất tán cây 2001–2024 (30 m, lớp Global Forest Watch dùng)"
NAME_EN = "Hansen/UMD Global Forest Change v1.12 — tree-cover loss year 2001–2024 (30 m, the layer Global Forest Watch shows)"
PIX = 0.00025                 # 1/4000 độ ≈ 27–28 m ở Việt Nam
TILE_DEG = 10
TILE_PX = 40_000
CANOPY_MIN = 30               # ngưỡng tán cây năm 2000 mặc định của Global Forest Watch
LAST_YEAR = 2024
MAX_ROWS = 2_000              # ~55 km Bắc–Nam — lớn hơn thì không phải "một thửa"
_CHUNK = 96                   # số hàng giải nén một lượt (giữ bộ nhớ ~4 MB/lớp)
_TTL = 365 * 86400
_CACHE_V = 1
_UA = {"User-Agent": "TerraTwin/1.0 (EUDR screening; +https://terratwin-web.vercel.app)"}


def tile_name(lat: float, lon: float) -> tuple[str, int, int]:
    """Ô chứa điểm: tên theo góc TRÊN-TRÁI (vd "20N_100E" phủ 10–20°N, 100–110°E), (vĩ độ trên, kinh độ trái)."""
    top = int(math.floor(lat / TILE_DEG) + 1) * TILE_DEG
    left = int(math.floor(lon / TILE_DEG)) * TILE_DEG
    ns = f"{abs(top):02d}{'N' if top >= 0 else 'S'}"
    ew = f"{abs(left):03d}{'E' if left >= 0 else 'W'}"
    return f"{ns}_{ew}", top, left


def _range(url: str, a: int, b: int, timeout: float = 40.0) -> bytes:
    """Byte [a, b) của tệp — ném lỗi nếu máy chủ không trả đúng đoạn."""
    req = urllib.request.Request(url, headers={**_UA, "Range": f"bytes={a}-{b - 1}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    if len(data) != b - a:
        raise OSError(f"Range {a}-{b}: nhận {len(data)} byte")
    return data


@lru_cache(maxsize=16)
def _layout(url: str) -> dict:
    """Đọc thư mục ảnh (IFD) đầu tệp TIFF: vị trí bảng StripOffsets/StripByteCounts và cách nén. Chỉ nhận đúng dạng
    Hansen phát hành (8 bit, 1 kênh, 1 hàng/dải, LZW hoặc Deflate, không predictor) — khác thì từ chối thay vì đọc sai."""
    head = _range(url, 0, 16_384)
    bo = {b"II": "<", b"MM": ">"}.get(head[:2])
    if bo is None or struct.unpack(bo + "H", head[2:4])[0] != 42:
        raise ValueError("không phải TIFF thường (có thể là BigTIFF)")
    off = struct.unpack(bo + "I", head[4:8])[0]

    def at(a: int, b: int) -> bytes:          # IFD có thể nằm cuối tệp (nhiều phần mềm ghi vậy) — tải riêng đoạn đó
        return head[a:b] if b <= len(head) else _range(url, a, b)

    n = struct.unpack(bo + "H", at(off, off + 2))[0]
    ifd = at(off + 2, off + 2 + 12 * n)
    tags: dict[int, tuple[int, int, int]] = {}
    for i in range(n):
        e = ifd[12 * i: 12 * i + 12]
        tag, typ, cnt = struct.unpack(bo + "HHI", e[:8])
        val = struct.unpack(bo + "H", e[8:10])[0] if typ == 3 and cnt == 1 else struct.unpack(bo + "I", e[8:12])[0]
        tags[tag] = (typ, cnt, val)
    width, height = tags[256][2], tags[257][2]
    comp, rps = tags[259][2], tags.get(278, (0, 0, height))[2]
    pred, bits, spp = tags.get(317, (0, 0, 1))[2], tags[258][2], tags.get(277, (0, 0, 1))[2]
    if (width, height) != (TILE_PX, TILE_PX) or rps != 1 or bits != 8 or spp != 1 or pred != 1 or comp not in (5, 8):
        raise ValueError(f"bố cục TIFF lạ: {width}x{height} rps={rps} bits={bits} spp={spp} pred={pred} comp={comp}")
    if tags[273][0] not in (3, 4) or tags[279][0] not in (3, 4):
        raise ValueError("bảng dải không phải SHORT/LONG")
    return {"bo": bo, "offsets_at": tags[273][2], "counts_at": tags[279][2], "comp": comp,
            "off_fmt": "H" if tags[273][0] == 3 else "I", "cnt_fmt": "H" if tags[279][0] == 3 else "I"}


def _mini_tiff(strips: list[bytes], width: int, comp: int) -> bytes:
    """TIFF nhỏ trong bộ nhớ gồm đúng các dải đã tải — để Pillow (libtiff) giải nén, không cần GDAL."""
    n = len(strips)
    ifd_len = 2 + 12 * 10 + 4
    tables = 8 + ifd_len
    body = tables + (8 * n if n > 1 else 0)
    offs, o = [], body
    for s in strips:
        offs.append(o)
        o += len(s)

    def ent(tag: int, typ: int, cnt: int, val: int) -> bytes:
        return struct.pack("<HHII", tag, typ, cnt, val) if typ == 4 else struct.pack("<HHIHH", tag, typ, cnt, val, 0)

    E = [ent(256, 4, 1, width), ent(257, 4, 1, n), ent(258, 3, 1, 8), ent(259, 3, 1, comp), ent(262, 3, 1, 1),
         ent(273, 4, n, tables if n > 1 else offs[0]), ent(277, 3, 1, 1), ent(278, 4, 1, 1),
         ent(279, 4, n, tables + 4 * n if n > 1 else len(strips[0])), ent(284, 3, 1, 1)]
    out = b"II*\x00" + struct.pack("<I", 8) + struct.pack("<H", len(E)) + b"".join(E) + struct.pack("<I", 0)
    if n > 1:
        out += struct.pack(f"<{n}I", *offs) + struct.pack(f"<{n}I", *[len(s) for s in strips])
    return out + b"".join(strips)


def read_rows(layer: str, tile: str, r0: int, r1: int, c0: int, c1: int):
    """Mảng uint8 hàng [r0, r1) × cột [c0, c1) của một lớp trong một ô."""
    import numpy as np
    from PIL import Image

    url = URL.format(layer=layer, tile=tile)
    lay = _layout(url)
    bo, n = lay["bo"], r1 - r0

    def table(at: int, fmt: str) -> tuple[int, ...]:
        k = struct.calcsize(fmt)
        return struct.unpack(f"{bo}{n}{fmt}", _range(url, at + k * r0, at + k * r1))

    counts = table(lay["counts_at"], lay["cnt_fmt"])
    offs = table(lay["offsets_at"], lay["off_fmt"])
    lo, hi = min(offs), max(o + c for o, c in zip(offs, counts))
    if hi - lo > 64 * sum(counts) + 1_000_000:          # dải không nằm liền nhau — đọc từng dải
        strips = [_range(url, o, o + c) for o, c in zip(offs, counts)]
    else:
        blob = _range(url, lo, hi, timeout=90.0)
        strips = [blob[o - lo:o - lo + c] for o, c in zip(offs, counts)]
    a = np.asarray(Image.open(io.BytesIO(_mini_tiff(strips, TILE_PX, lay["comp"]))))
    if a.shape != (n, TILE_PX):
        raise ValueError(f"giải nén ra {a.shape}")
    return a[:, c0:c1]


def _windows(bounds: tuple[float, float, float, float]):
    """Chia khung thửa theo ô 10° và theo lượt _CHUNK hàng: (tên ô, r0, r1, c0, c1, vĩ độ trên, kinh độ trái)."""
    x0, y0, x1, y1 = bounds
    eps = 1e-9
    lat_tops = range(int(math.floor(y0 / TILE_DEG) + 1) * TILE_DEG, int(math.floor((y1 - eps) / TILE_DEG) + 2) * TILE_DEG,
                     TILE_DEG)
    lon_lefts = range(int(math.floor(x0 / TILE_DEG)) * TILE_DEG, int(math.floor((x1 - eps) / TILE_DEG) + 1) * TILE_DEG,
                      TILE_DEG)
    for top in lat_tops:
        for left in lon_lefts:
            name = tile_name(top - TILE_DEG / 2, left + TILE_DEG / 2)[0]
            r0 = max(0, math.floor((top - y1) / PIX + eps))
            r1 = min(TILE_PX, math.ceil((top - y0) / PIX - eps))
            c0 = max(0, math.floor((x0 - left) / PIX + eps))
            c1 = min(TILE_PX, math.ceil((x1 - left) / PIX - eps))
            for a in range(r0, r1, _CHUNK):
                yield name, a, min(r1, a + _CHUNK), c0, c1, top, left


def _measure(geom) -> dict | None:
    import numpy as np
    import shapely

    x0, y0, x1, y1 = geom.bounds
    if (y1 - y0) / PIX > MAX_ROWS or (x1 - x0) / PIX > MAX_ROWS:
        return None
    n = tc = 0
    lost: dict[int, int] = {}
    for tile, r0, r1, c0, c1, top, left in _windows(geom.bounds):
        if r1 <= r0 or c1 <= c0:
            continue
        xs = left + (np.arange(c0, c1) + 0.5) * PIX
        ys = top - (np.arange(r0, r1) + 0.5) * PIX
        gx, gy = np.meshgrid(xs, ys)
        inside = shapely.contains_xy(geom, gx, gy)
        if not inside.any():
            continue
        cover = read_rows("treecover2000", tile, r0, r1, c0, c1)
        year = read_rows("lossyear", tile, r0, r1, c0, c1)
        treed = inside & (cover >= CANOPY_MIN)
        n += int(inside.sum())
        tc += int(treed.sum())
        vals, cnt = np.unique(year[treed], return_counts=True)
        for v, c in zip(vals.tolist(), cnt.tolist()):
            if v:
                lost[2000 + int(v)] = lost.get(2000 + int(v), 0) + int(c)
    if n == 0:
        return None
    pct = lambda k: round(100.0 * k / n, 1)  # noqa: E731
    after = {y: c for y, c in lost.items() if y > 2020}
    return {
        "pixels": n, "version": VERSION, "canopy_min": CANOPY_MIN,
        "treecover2000_pct": pct(tc),
        "loss_2001_2020_pct": pct(sum(c for y, c in lost.items() if y <= 2020)),
        "loss_after_2020_pct": pct(sum(after.values())),
        "loss_after_2020_ha": round(sum(after.values()) * _px_ha((y0 + y1) / 2), 2),
        "loss_by_year": {str(y): pct(c) for y, c in sorted(after.items())},
        "last_year": LAST_YEAR,
    }


def _px_ha(lat: float) -> float:
    return (PIX * 111_320.0) * (PIX * 111_320.0 * math.cos(math.radians(lat))) / 10_000.0


def loss(geom) -> dict | None:
    """Tán cây năm 2000 (≥30%) và mất tán cây theo năm trong ranh thửa. Thửa nhỏ hơn 3 điểm ảnh: nới ranh 40 m, ghi
    `buffered_m`. None nếu không đọc được (nguồn hỏng, thửa quá lớn) — người gọi ghi "chưa đọc được"."""
    key = cache_store.make_key("hansen-gfc", _CACHE_V, VERSION, eudr_geo.geojson_of(geom))
    hit = cache_store.get(key)
    if hit is not None:
        return hit
    try:
        got, buffered = _measure(geom), 0.0
        if got is None or got["pixels"] < 3:
            lon0 = geom.centroid.x
            buffered = 40.0
            got = _measure(eudr_geo.from_metric(eudr_geo.to_metric(geom, lon0).buffer(buffered), lon0))
    except Exception:  # noqa: BLE001 — nguồn ngoài hỏng thì "chưa đọc được", không làm hỏng sàng lọc
        return None
    if got is None:
        return None
    out = {**got, "buffered_m": buffered}
    cache_store.put(key, out, ttl_seconds=_TTL)
    return out
