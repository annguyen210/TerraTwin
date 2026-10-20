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

