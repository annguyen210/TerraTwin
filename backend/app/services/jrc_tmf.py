"""RỪNG ẨM NHIỆT ĐỚI CỦA EU — JRC Tropical Moist Forest (TMF), bản đồ biến động TỪNG NĂM 1990–2025, 30 m
(nâng cấp 25/11/2026).

Vì sao: cùng Trung tâm Nghiên cứu Chung (JRC) làm GFC2020; TMF là bộ dữ liệu EU Observatory on Deforestation dùng để
theo dõi phá rừng nhiệt đới. Mỗi năm, mỗi điểm ảnh Landsat 30 m được xếp một trong 6 lớp — nên trả lời thẳng câu hỏi
EUDR: "điểm ảnh là rừng năm 2020 có bị PHÁ hay SUY THOÁI sau mốc không, năm nào".

Lớp AnnualChange (Vancutsem et al. 2021, Science Advances 7: eabe1603; hướng dẫn dữ liệu JRC):
    1 rừng ẩm nguyên vẹn (0,90,0)   2 rừng ẩm suy thoái (100,155,35)   3 đất đã mất rừng (255,135,15)
    4 rừng tái sinh (210,250,60)    5 mặt nước (0,140,190)              6 đất khác (255,255,255)

Đọc qua WMS công khai của JRC (không khoá), khung ảnh căn đúng lưới gốc 0,00025° nên mỗi điểm ảnh PNG là đúng một điểm
ảnh dữ liệu (máy chủ lấy mẫu gần nhất, không trộn màu — đếm được 6 màu chuẩn). Chỉ tải năm 2020 và năm mới nhất; có
điểm ảnh rừng 2020 đổi lớp thì mới tải các năm giữa để định NĂM.

Giới hạn: TMF chỉ vẽ RỪNG ẨM thường xanh/nửa rụng lá — rừng khộp khô (Tây Nguyên: Yok Đôn, Ea Súp) thường bị xếp "đất
khác", nên 0% ở đó KHÔNG có nghĩa "không có rừng". Hiện như bản đồ THAM CHIẾU, không bỏ phiếu ở quy tắc v1.
Nguồn: https://forobs.jrc.ec.europa.eu/TMF — © European Union, JRC.
"""
from __future__ import annotations

import io
import math
import urllib.parse
import urllib.request

from app.services import cache_store, eudr_geo

WMS = "https://ies-ows.jrc.ec.europa.eu/iforce/tmf_v1/wms.py"
NAME = "JRC TMF — rừng ẩm nhiệt đới từng năm 1990–2025 của EU (30 m)"
NAME_EN = "JRC TMF — the EU's annual tropical moist forest map 1990–2025 (30 m)"
PIX = 0.00025
BASE_YEAR = 2020
LAST_YEAR = 2025
CLASSES = {(0, 90, 0): 1, (100, 155, 35): 2, (255, 135, 15): 3, (210, 250, 60): 4, (0, 140, 190): 5,
           (255, 255, 255): 6}
FOREST = (1, 2)
MAX_PX = 2_048
_TTL = 365 * 86400
_CACHE_V = 1
_UA = {"User-Agent": "TerraTwin/1.0 (EUDR screening; +https://terratwin-web.vercel.app)"}


def _png(layer: str, bbox: tuple[float, float, float, float], w: int, h: int, timeout: float = 60.0) -> bytes | None:
    q = {"SERVICE": "WMS", "VERSION": "1.1.1", "REQUEST": "GetMap", "LAYERS": layer, "STYLES": "",
         "SRS": "EPSG:4326", "BBOX": ",".join(f"{v:.6f}" for v in bbox), "WIDTH": w, "HEIGHT": h,
         "FORMAT": "image/png", "TRANSPARENT": "TRUE"}
    req = urllib.request.Request(WMS + "?" + urllib.parse.urlencode(q), headers=_UA)
    for _ in range(2):                          # 25/11/2026: WMS của JRC thỉnh thoảng lỡ một lượt rồi trả bình thường
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                if "image/png" not in (r.headers.get("Content-Type") or ""):
                    return None                 # WMS trả lỗi dạng XML — thử lại cũng vậy
                return r.read()
        except Exception:  # noqa: BLE001 — nguồn ngoài hỏng thì "chưa đọc được", không làm hỏng sàng lọc
            continue
    return None


def grid(bounds: tuple[float, float, float, float]) -> tuple[tuple[float, float, float, float], int, int]:
    """Khung căn lưới gốc 0,00025° phủ trọn thửa + số điểm ảnh ngang, dọc."""
    x0, y0, x1, y1 = bounds
    eps = 1e-9
    gx0, gy0 = math.floor(x0 / PIX + eps) * PIX, math.floor(y0 / PIX + eps) * PIX
    gx1, gy1 = math.ceil(x1 / PIX - eps) * PIX, math.ceil(y1 / PIX - eps) * PIX
    w, h = max(1, round((gx1 - gx0) / PIX)), max(1, round((gy1 - gy0) / PIX))
    return (gx0, gy0, gx0 + w * PIX, gy0 + h * PIX), w, h


def classes(year: int, bbox, w: int, h: int):
    """Mảng lớp 0–6 (0 = ngoài vùng phủ / màu lạ) của AnnualChange_<năm>, hàng 0 ở phía BẮC; None nếu lỗi."""
    import numpy as np
    from PIL import Image

    raw = _png(f"AnnualChange_{year}", bbox, w, h)
    if raw is None:
        return None
    try:
        a = np.asarray(Image.open(io.BytesIO(raw)).convert("RGBA"))
    except Exception:  # noqa: BLE001
        return None
    if a.shape[:2] != (h, w):
        return None
    out = np.zeros((h, w), dtype=np.uint8)
    solid = a[..., 3] > 0
    for rgb, k in CLASSES.items():
        out[solid & (a[..., 0] == rgb[0]) & (a[..., 1] == rgb[1]) & (a[..., 2] == rgb[2])] = k
    return out


def _measure(geom) -> dict | None:
    import numpy as np
    import shapely

    bbox, w, h = grid(geom.bounds)
    if w > MAX_PX or h > MAX_PX:
        return None
    xs = bbox[0] + (np.arange(w) + 0.5) * PIX
    ys = bbox[3] - (np.arange(h) + 0.5) * PIX
    gx, gy = np.meshgrid(xs, ys)
    inside = shapely.contains_xy(geom, gx, gy)
    n = int(inside.sum())
    if n == 0:
        return {"pixels": 0}
    c0, c1 = classes(BASE_YEAR, bbox, w, h), classes(LAST_YEAR, bbox, w, h)
    if c0 is None or c1 is None:
        return None
    known = inside & (c0 > 0)
    if int(known.sum()) < 0.5 * n:             # ngoài vùng phủ của TMF (> ±30° vĩ độ) hoặc ảnh lỗi
        return None
    forest = inside & np.isin(c0, FOREST)
    undisturbed = inside & (c0 == 1)
    changed = forest & (c1 != c0)
    lost_year: dict[int, int] = {}
    degraded_year: dict[int, int] = {}
    if changed.any():
        # Có điểm ảnh rừng 2020 đổi lớp: tải các năm giữa để biết NĂM đầu tiên rời khỏi rừng / bị suy thoái.
        prev_lost = np.zeros_like(forest)
        prev_deg = np.zeros_like(forest)
        for y in range(BASE_YEAR + 1, LAST_YEAR + 1):
            cy = c1 if y == LAST_YEAR else classes(y, bbox, w, h)
            if cy is None:
                return None
            lost = forest & (cy > 0) & ~np.isin(cy, FOREST)
            deg = undisturbed & (cy == 2)
            lost_year[y] = int((lost & ~prev_lost).sum())
            degraded_year[y] = int((deg & ~prev_deg & ~lost).sum())
            prev_lost |= lost
            prev_deg |= deg
        lost_any, deg_any = prev_lost, prev_deg & ~prev_lost
    else:
        lost_any = deg_any = np.zeros_like(forest)
    pct = lambda k: round(100.0 * k / n, 1)  # noqa: E731
    lat = (bbox[1] + bbox[3]) / 2
    px_ha = (PIX * 111_320.0) ** 2 * math.cos(math.radians(lat)) / 10_000.0
    return {
        "pixels": n, "base_year": BASE_YEAR, "last_year": LAST_YEAR,
        "forest2020_pct": pct(int(forest.sum())),
        "undisturbed2020_pct": pct(int(undisturbed.sum())),
        "lost_after_2020_pct": pct(int(lost_any.sum())),
        "lost_after_2020_ha": round(int(lost_any.sum()) * px_ha, 2),
        "degraded_after_2020_pct": pct(int(deg_any.sum())),
        "lost_by_year": {str(y): pct(c) for y, c in lost_year.items() if c},
        "degraded_by_year": {str(y): pct(c) for y, c in degraded_year.items() if c},
    }


def change(geom) -> dict | None:
    """Rừng ẩm năm 2020 trong ranh và phần bị mất / suy thoái sau mốc, theo năm. Thửa nhỏ hơn 3 điểm ảnh: nới ranh
    40 m (`buffered_m`). None nếu dịch vụ JRC không phản hồi hoặc thửa nằm ngoài vùng phủ."""
    key = cache_store.make_key("jrc-tmf", _CACHE_V, LAST_YEAR, eudr_geo.geojson_of(geom))
    hit = cache_store.get(key)
    if hit is not None:
        return hit
    got, buffered = _measure(geom), 0.0
    if got is not None and got["pixels"] < 3:
        lon0 = geom.centroid.x
        buffered = 40.0
        got = _measure(eudr_geo.from_metric(eudr_geo.to_metric(geom, lon0).buffer(buffered), lon0))
    if got is None or not got.get("pixels"):
        return None
    out = {**got, "buffered_m": buffered}
    cache_store.put(key, out, ttl_seconds=_TTL)
    return out
