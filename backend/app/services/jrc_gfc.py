"""BẢN ĐỒ RỪNG 2020 CỦA CHÍNH EU — JRC Global Forest Cover 2020 (GFC2020) v4, 10 m (nâng cấp 24/11/2026).

Vì sao: ba bản đồ đang bỏ phiếu (WorldCover, ALOS, Impact Observatory) đều vẽ cây trồng lâu năm thành "rừng". Đo
24/11/2026: vườn cà phê Buôn Ma Thuột 12.73,108.05 bị chấm "Rủi ro phá rừng" (WorldCover 100%, ALOS 89%, IO 68%),
cao su Bình Phước 11.75,106.90 "Cần xem lại" (3 bản đồ 100%) — trong khi GFC2020 v4 thấy 0,02% và 0% rừng. GFC2020 do
Trung tâm Nghiên cứu Chung (JRC) của Uỷ ban châu Âu làm riêng cho EUDR, theo đúng định nghĩa rừng của quy định (loại
trừ đất nông nghiệp có cây — cà phê, cao su, cây ăn quả). Bản đồ KHÔNG bắt buộc và không có giá trị pháp lý, nhưng là
thứ cơ quan EU và nhà nhập khẩu đang dùng để đối chiếu.

Đọc qua dịch vụ WMS công khai của JRC (không khoá): ảnh PNG của đúng khung thửa ở ~10 m/điểm ảnh, điểm ảnh rừng tô màu
cố định (77,146,33), không rừng trong suốt. Đếm điểm ảnh rừng nằm TRONG ranh. Bản đồ năm 2020 không đổi → nhớ đệm dài.

Nguồn: European Commission, Joint Research Centre — Global map of forest cover 2020, version 4
(https://forobs.jrc.ec.europa.eu/GFC). Không có trong 3 phiếu của quy tắc v1 — hiện như bản đồ THAM CHIẾU, xem
eudr_forest.eu_reference_note().
"""
from __future__ import annotations

import io
import math
import urllib.parse
import urllib.request

from app.services import cache_store, eudr_geo

WMS = "https://ies-ows.jrc.ec.europa.eu/iforce/gfc2020/wms.py"
LAYER = "gfc2020_v4"
NAME = "JRC GFC2020 v4 — bản đồ rừng 2020 của EU (10 m)"
NAME_EN = "JRC GFC2020 v4 — the EU's 2020 forest map (10 m)"
FOREST_RGB = (77, 146, 33)
RES_M = 10.0
MAX_PX = 1024
_TTL = 180 * 86400
_CACHE_V = 1


def _png(bbox: tuple[float, float, float, float], w: int, h: int, timeout: float = 45.0) -> bytes | None:
    q = {"SERVICE": "WMS", "VERSION": "1.1.1", "REQUEST": "GetMap", "LAYERS": LAYER, "STYLES": "",
         "SRS": "EPSG:4326", "BBOX": ",".join(f"{v:.7f}" for v in bbox), "WIDTH": w, "HEIGHT": h,
         "FORMAT": "image/png", "TRANSPARENT": "TRUE"}
    req = urllib.request.Request(WMS + "?" + urllib.parse.urlencode(q),
                                 headers={"User-Agent": "TerraTwin/1.0 (EUDR screening; +https://terratwin-web.vercel.app)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            if "image/png" not in (r.headers.get("Content-Type") or ""):
                return None                     # WMS trả lỗi dạng XML
            return r.read()
    except Exception:  # noqa: BLE001 — nguồn ngoài hỏng thì "không có bản đồ tham chiếu", không làm hỏng sàng lọc
        return None


def _share(geom) -> tuple[float, int] | None:
    """(% điểm ảnh rừng trong ranh, số điểm ảnh trong ranh) hoặc None."""
    import numpy as np
    import shapely
    from PIL import Image

    x0, y0, x1, y1 = geom.bounds
    lat = (y0 + y1) / 2
    m_lon = 111_320.0 * max(0.2, math.cos(math.radians(lat)))
    w = max(8, min(MAX_PX, math.ceil((x1 - x0) * m_lon / RES_M)))
    h = max(8, min(MAX_PX, math.ceil((y1 - y0) * 111_320.0 / RES_M)))
    raw = _png((x0, y0, x1, y1), w, h)
    if raw is None:
        return None
    try:
        a = np.asarray(Image.open(io.BytesIO(raw)).convert("RGBA"))
    except Exception:  # noqa: BLE001
        return None
    if a.shape[:2] != (h, w):
        return None
    # Tâm từng điểm ảnh (hàng 0 ở phía BẮC).
    xs = x0 + (np.arange(w) + 0.5) * (x1 - x0) / w
    ys = y1 - (np.arange(h) + 0.5) * (y1 - y0) / h
    gx, gy = np.meshgrid(xs, ys)
    inside = shapely.contains_xy(geom, gx, gy)
    n = int(inside.sum())
    if n == 0:
        return None
    forest = (a[..., 3] > 0) & (a[..., 0] == FOREST_RGB[0]) & (a[..., 1] == FOREST_RGB[1]) & (a[..., 2] == FOREST_RGB[2])
    return round(100.0 * float((forest & inside).sum()) / n, 1), n


def forest_share(geom) -> dict | None:
    """% diện tích thửa là rừng năm 2020 theo GFC2020 v4. Thửa nhỏ hơn vài điểm ảnh: mở rộng ranh 15 m, ghi `buffered_m`."""
    key = cache_store.make_key("jrc-gfc", _CACHE_V, LAYER, eudr_geo.geojson_of(geom))
    hit = cache_store.get(key)
    if hit is not None:
        return hit
    got, buffered = _share(geom), 0.0
    if got is not None and got[1] < 3:
        lon0 = geom.centroid.x
        buffered = RES_M * 1.5
        got = _share(eudr_geo.from_metric(eudr_geo.to_metric(geom, lon0).buffer(buffered), lon0))
    if got is None:
        return None
    out = {"pct": got[0], "pixels": got[1], "layer": LAYER, "buffered_m": buffered}
    cache_store.put(key, out, ttl_seconds=_TTL)
    return out
