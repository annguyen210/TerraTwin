"""U-Net radar (Sen1Floods11) làm Ý KIẾN THỨ HAI cho từng đợt nước của lịch sử nước — giao thức
backend/data/ml/s1_unet_confirm_protocol.json.

Mô hình: s1_water_unet (đạt cổng GĐ5: IoU test 0,668 / Bolivia 0,681 / Mekong 0,851, hơn ngưỡng −18 dB), chuyển ONNX.
Không thay danh sách đợt của phương pháp ngưỡng (cổng GĐ2 giữ nguyên) — chỉ đọc ảnh VV/VH ĐÚNG ngày của một đợt, chạy
U-Net trên khung 1.280 m quanh thửa và báo tỉ lệ nước trong khung thửa ở giữa. Máy chủ miễn phí không đủ sức chạy U-Net
cho ~460 cảnh mỗi thửa, nên chỉ tính khi được hỏi (một đợt một lần, có cache).

Chỉ bật (`available()`) khi có tệp ONNX + onnxruntime + kết quả phép kiểm đăng ký trước ĐẠT. Chỉ là tham khảo: không vào
nội dung ký của hồ sơ, không đổi danh sách đợt.
"""
from __future__ import annotations

import io
import json
import os
import threading
import urllib.parse
import urllib.request

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "ml")
MODEL_PATH = os.path.join(DATA, "s1_water_unet.onnx")
RESULT_PATH = os.path.join(DATA, "s1_unet_confirm_result.json")
BBOX_URL = "https://planetarycomputer.microsoft.com/api/data/v1/item/bbox"
PX = 128                       # 128 điểm ảnh × ~10 m
CONTEXT_M = 640.0              # nửa cạnh khung đọc → 1.280 m
CONFIRM_SHARE = 0.10           # bằng mức phủ thấp nhất '10–25%' của phương pháp ngưỡng
_lock = threading.Lock()
_sess = None
_norm = None


def _load_norm() -> tuple[list[float], list[float]]:
    global _norm
    if _norm is None:
        r = json.load(open(os.path.join(DATA, "s1_water_result.json"), encoding="utf-8"))
        _norm = (r["norm"]["mean"], r["norm"]["std"])
    return _norm


def gate_passed() -> bool:
    try:
        return json.load(open(RESULT_PATH, encoding="utf-8")).get("passed") is True
    except (OSError, ValueError):
        return False


def available() -> bool:
    if v3_available():
        return True
    if os.environ.get("TERRATWIN_S1_UNET", "1") == "0" or not os.path.exists(MODEL_PATH) or not gate_passed():
        return False
    try:
        import onnxruntime  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


def _session():
    global _sess
    if _sess is None:
        import onnxruntime as ort
        o = ort.SessionOptions()
        o.intra_op_num_threads = 1
        o.inter_op_num_threads = 1
        _sess = ort.InferenceSession(MODEL_PATH, sess_options=o, providers=["CPUExecutionProvider"])
    return _sess


def center_px(radius_m: float = 100.0) -> int:
    """Nửa cạnh khung thửa tính bằng điểm ảnh (bán kính 100 m → 10 → khung 20 × 20 ở giữa)."""
    return max(1, int(round(radius_m / (2 * CONTEXT_M / PX))))


def fetch(item: str, lat: float, lon: float):
    """Mảng (2, PX, PX) VV/VH tuyến tính của cảnh `item` quanh thửa, hoặc None."""
    import numpy as np

    from app.services import jobs, mpc
    b = mpc.bbox_around(lat, lon, CONTEXT_M)
    q = urllib.parse.urlencode([("collection", "sentinel-1-rtc"), ("item", item), ("assets", "vv"), ("assets", "vh")])
    url = f"{BBOX_URL}/{b[0]:.6f},{b[1]:.6f},{b[2]:.6f},{b[3]:.6f}/{PX}x{PX}.npy?{q}"
    with jobs.upstream("pc") as allowed:
        if not allowed:
            return None
        try:
            req = urllib.request.Request(url, headers={"User-Agent": mpc.USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as r:
                arr = np.load(io.BytesIO(r.read()), allow_pickle=False)
        except Exception:  # noqa: BLE001
            return None
    if arr.ndim != 3 or arr.shape[0] < 2:
        return None
    return arr[:2].astype("float32")


def prepare(arr):
    """Tuyến tính → dB → chuẩn hoá đúng như lúc huấn luyện (to_tensor của ml/kaggle/s1_water_seg.py)."""
    import numpy as np
    m, s = _load_norm()
    out = np.empty_like(arr, dtype=np.float32)
    for b in range(2):
        v = arr[b].astype(np.float64)
        ok = np.isfinite(v) & (v > 0)
        db = np.where(ok, 10.0 * np.log10(np.maximum(v, 1e-6)), m[b])
        out[b] = ((np.clip(db, -50, 5) - m[b]) / s[b]).astype(np.float32)
    return out[None]


def plot_share(mask, radius_m: float = 100.0) -> float:
    h, w = mask.shape
    k = center_px(radius_m)
    cy, cx = h // 2, w // 2
    win = mask[cy - k:cy + k, cx - k:cx + k]
    return round(float(win.mean()), 3)


def infer(arr, radius_m: float = 100.0) -> float:
    """Tỉ lệ điểm ảnh nước trong khung thửa ở giữa."""
    import numpy as np
    with _lock:
        logit = _session().run(None, {"s1": prepare(arr)})[0][0, 0]
    return plot_share((1.0 / (1.0 + np.exp(-logit))) > 0.5, radius_m)


def water_share(lat: float, lon: float, day: str, radius_m: float = 100.0, force: bool = False) -> dict | None:
    """U-Net trên cảnh ngày `day` của thửa. force=True dùng cho phép kiểm (bỏ qua điều kiện bật)."""
    from app.services import cache_store, water_history as wh
    if v3_available():                                   # bản 3 ĐẠT (s1_unet_v3_protocol.json): mức vượt nền mùa khô
        key = cache_store.make_key("s1unet", round(lat, 4), round(lon, 4), day, "v3")
        hit = cache_store.get(key)
        if hit is not None:
            return hit
        hist = cache_store.get(wh.cache_key(lat, lon, radius_m))
        if not hist or not hist.get("available"):
            return None
        out = v3_judge(lat, lon, day, hist)
        if out is not None:
            cache_store.put(key, out, 400 * 24 * 3600)
        return out
    if not force and not available():
        return None
    key = cache_store.make_key("s1unet", round(lat, 4), round(lon, 4), day, "v1")
    hit = cache_store.get(key)
    if hit is not None:
        return hit
    sc = wh.scene(lat, lon, day)
    if not sc:
        return None
    arr = fetch(sc["item"], lat, lon)
    if arr is None:
        return None
    share = infer(arr, radius_m)
    out = {"date": sc["date"], "item": sc["item"], "share": share, "confirmed": share >= CONFIRM_SHARE,
           "model": "s1_water_unet (Sen1Floods11)", "rule": f"xác nhận khi ≥ {int(CONFIRM_SHARE * 100)}% khung thửa là nước"}
    cache_store.put(key, out, 400 * 24 * 3600)
    return out



# ───────────── Bản 2 (s1_unet_vn_protocol.json): tinh chỉnh trên ruộng Việt Nam + mặt nạ địa hình ─────────────
# Dùng CHUNG cho bộ dữ liệu (ops/s1_unet_v2_data.py), phép kiểm (ops/s1_unet_v2_gate.py) và sản phẩm, để thứ được
# chấm đúng là thứ chạy thật: khung bám lưới UTM 10 m GỐC của cảnh S1 RTC (không lấy mẫu lại radar), độ dốc từ
# Copernicus DEM GLO-30 trên cùng lưới, ô dốc > 5° không bao giờ là nước (nước không đọng trên sườn dốc — chữa lỗi
# bóng radar ở đồi thông Thiên An của bản 1).

V2_MODEL_PATH = os.path.join(DATA, "s1_water_unet_vn.onnx")
V2_RESULT_PATH = os.path.join(DATA, "s1_unet_vn_result.json")
SLOPE_MAX_DEG = 5.0
STAC_ITEM = "https://planetarycomputer.microsoft.com/api/stac/v1/collections/{c}/items/{i}"
_sess2 = None


def s1_grid_box(item: dict, lat: float, lon: float, px: int = PX) -> tuple[int, list[float]]:
    """(epsg, [x0, y0, x1, y1]) — khung px × px ô quanh điểm, bám đúng lưới của cảnh S1 RTC (proj:transform, 10 m)."""
    import math

    from app.services import s2_sharpen
    p = item.get("properties") or {}
    epsg = int(p["proj:epsg"])
    tr = p["proj:transform"]
    res, gx, gy = float(tr[0]), float(tr[2]), float(tr[5])
    e, n = s2_sharpen.to_utm(lat, lon, epsg)
    half = px * res / 2.0
    x0 = gx + res * math.floor((e - half - gx) / res)
    y1 = gy - res * math.floor((gy - (n + half)) / res)
    return epsg, [x0, y1 - px * res, x0 + px * res, y1]


def _npy(collection: str, item_id: str, assets: list[str], epsg: int, box: list[float], size: int,
         resampling: str = "nearest", timeout: float = 90.0):
    import numpy as np

    from app.services import jobs, mpc
    q = [("collection", collection), ("item", item_id), ("coord_crs", f"EPSG:{epsg}"), ("dst_crs", f"EPSG:{epsg}"),
         ("resampling", resampling)] + [("assets", a) for a in assets]
    url = f"{BBOX_URL}/{','.join(f'{v:.1f}' for v in box)}/{size}x{size}.npy?{urllib.parse.urlencode(q)}"
    with jobs.upstream("pc") as allowed:
        if not allowed:
            return None
        try:
            req = urllib.request.Request(url, headers={"User-Agent": mpc.USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return np.load(io.BytesIO(r.read()), allow_pickle=False)
        except Exception:  # noqa: BLE001
            return None


def fetch_grid(item: dict, epsg: int, box: list[float]):
    """(2, PX, PX) VV/VH tuyến tính đúng điểm ảnh gốc của cảnh, hoặc None."""
    a = _npy("sentinel-1-rtc", item["id"], ["vv", "vh"], epsg, box, PX)
    if a is None or a.ndim != 3 or a.shape[0] < 2:
        return None
    return a[:2].astype("float32")


def slope_deg(epsg: int, box: list[float], lat: float, lon: float):
    """(PX, PX) độ dốc (độ) từ Copernicus DEM GLO-30 trên cùng lưới, hoặc None."""
    import numpy as np

    from app.services import mpc
    r = mpc._call(mpc.STAC, {"collections": ["cop-dem-glo-30"], "bbox": mpc.bbox_around(lat, lon, PX * 10.0), "limit": 4})
    feats = (r or {}).get("features") or []
    if not feats:
        return None
    z = _npy("cop-dem-glo-30", feats[0]["id"], ["data"], epsg, box, PX, "bilinear")
    if z is None:
        return None
    gy, gx = np.gradient(z[0].astype(np.float64), 10.0)
    return np.degrees(np.arctan(np.hypot(gx, gy)))


def s2_label(item: dict, epsg: int, box: list[float]):
    """(PX, PX) uint8: 1 nước (MNDWI > 0), 0 không, 255 bỏ qua (mây/bóng/không dữ liệu) — nhãn TỰ ĐỘNG, không phải người."""
    import numpy as np

    from app.services import mpc
    a = _npy("sentinel-2-l2a", item["id"], ["B03", "B11", "SCL"], epsg, box, PX)
    if a is None or a.shape[0] < 3:
        return None
    off = mpc.BOA_OFFSET if mpc.has_offset(item) else 0
    b03, b11 = [(a[i].astype(np.float64) - off) / 10000.0 for i in (0, 1)]
    ok = np.isin(a[2], (4, 5, 6, 7))
    if a.shape[0] > 3:
        ok &= a[-1] > 0
    lab = ((b03 - b11) / np.maximum(b03 + b11, 1e-4) > 0).astype(np.uint8)
    lab[~ok] = 255
    return lab


def predict_mask(logit, slope):
    """Mặt nạ nước của bản 2: sigmoid > 0,5 VÀ không dốc quá 5°."""
    import numpy as np
    m = logit > 0.0
    if slope is not None:
        m &= ~(slope > SLOPE_MAX_DEG)
    return m


def v2_gate_passed() -> bool:
    try:
        return json.load(open(V2_RESULT_PATH, encoding="utf-8")).get("passed") is True
    except (OSError, ValueError):
        return False


def v2_available() -> bool:
    if os.environ.get("TERRATWIN_S1_UNET", "1") == "0" or not os.path.exists(V2_MODEL_PATH) or not v2_gate_passed():
        return False
    try:
        import onnxruntime  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


def v2_session(path: str | None = None):
    global _sess2
    if path is not None or _sess2 is None:
        import onnxruntime as ort
        o = ort.SessionOptions()
        o.intra_op_num_threads = 1
        o.inter_op_num_threads = 1
        s = ort.InferenceSession(path or V2_MODEL_PATH, sess_options=o, providers=["CPUExecutionProvider"])
        if path is not None:
            return s
        _sess2 = s
    return _sess2


# ───────────── Bản 3 (s1_unet_v3_protocol.json, ĐẠT 22/10/2026): trọng số bản 2 + quy tắc MỨC VƯỢT nền ─────────────
# Chẩn đoán bản 2: mô hình đọc đúng nước, nhưng "≥ 10% khung là nước" đếm cả hồ thường trực (Thiên An). Bản 3 so cảnh của
# đợt với TRUNG VỊ 6 cảnh mùa khô của chính thửa (cùng quỹ đạo, cách ngày đợt > 30 ngày) — cùng ý với lịch sử nước.

V3_RESULT_PATH = os.path.join(DATA, "s1_unet_v3_result.json")
V3_K, V3_EXCESS, V3_GAP_DAYS = 6, 0.10, 30
_slope_memo: dict = {}


def v3_gate_passed() -> bool:
    try:
        return json.load(open(V3_RESULT_PATH, encoding="utf-8")).get("passed") is True
    except (OSError, ValueError):
        return False


def v3_available() -> bool:
    if os.environ.get("TERRATWIN_S1_UNET", "1") == "0" or not os.path.exists(V2_MODEL_PATH) or not v3_gate_passed():
        return False
    try:
        import onnxruntime  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


def _item(item_id: str) -> dict | None:
    from app.services import mpc
    return mpc._call(STAC_ITEM.format(c="sentinel-1-rtc", i=item_id))


def share_on_day(lat: float, lon: float, day: str) -> tuple[float | None, str | None]:
    """(tỉ lệ nước khung tâm, mã cảnh) của bản 2 + mặt nạ dốc trên cảnh ngày `day` của chuỗi thửa."""
    from app.services import water_history as wh
    sc = wh.scene(lat, lon, day)
    it = _item(sc["item"]) if sc else None
    if not it:
        return None, None
    epsg, box = s1_grid_box(it, lat, lon)
    arr = fetch_grid(it, epsg, box)
    key = (epsg, tuple(round(v) for v in box))
    if key not in _slope_memo:
        _slope_memo[key] = slope_deg(epsg, box, lat, lon)
    if arr is None or _slope_memo[key] is None:
        return None, it["id"]
    with _lock:
        logit = v2_session().run(None, {"s1": prepare(arr)})[0][0, 0]
    return plot_share(predict_mask(logit, _slope_memo[key])), it["id"]


def v3_judge(lat: float, lon: float, day: str, hist: dict) -> dict | None:
    """Ý kiến thứ hai cho đợt ngày `day`: tỉ lệ nước − nền mùa khô ≥ 0,10 thì xác nhận. None nếu không đọc được."""
    import random
    import statistics
    from datetime import date
    from app.services import flood_season as fs
    d = date.fromisoformat(day)
    m = (hist.get("flood_season") or {}).get("months") or (fs.season(lat, lon) or {}).get("months")
    if not m:
        return None                                       # không biết mùa lũ thì không có "nền mùa khô" — không đoán
    months = set(m)
    dry = [s for s, *_ in hist.get("series") or [] if int(s[5:7]) not in months
           and abs((date.fromisoformat(s) - d).days) > V3_GAP_DAYS]
    if len(dry) < V3_K:
        return None
    s, item = share_on_day(lat, lon, day)
    if s is None:
        return None
    seed = int(f"{abs(round(lat * 1e4))}{abs(round(lon * 1e4))}{d.toordinal()}") % (2 ** 31)
    vals = [share_on_day(lat, lon, x)[0] for x in sorted(random.Random(seed).sample(sorted(dry), V3_K))]
    vals = [v for v in vals if v is not None]
    if len(vals) < 4:
        return None
    base = statistics.median(vals)
    return {"date": day, "item": item, "share": s, "baseline": round(base, 3), "excess": round(s - base, 3),
            "confirmed": s - base >= V3_EXCESS, "model": "s1_water_unet_vn (Sen1Floods11 + ruộng Việt Nam) · bản 3",
            "rule": f"xác nhận khi tỉ lệ nước vượt nền mùa khô của chính thửa ≥ {int(V3_EXCESS * 100)}%"}
