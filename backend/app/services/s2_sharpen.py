"""S10 ① — LÀM SẮC băng SWIR B11 từ 20 m xuống 10 m để vẽ độ ẩm thực vật NDMI 10 m trong thửa.

VÌ SAO KHÔNG PHẢI "BỊA": Sentinel-2 đo B02/B03/B04/B08 ở 10 m và B11 ở 20 m, CÙNG lúc, CÙNG chỗ. Chi tiết
không gian chuyển từ các băng 10 m ĐÃ ĐO sang B11; rồi bước chiếu ngược (back-projection) ép kết quả sao cho thu
nhỏ lại 2×2 thì RA ĐÚNG ảnh 20 m gốc — mỗi ô 20 m giữ nguyên giá trị đo, chỉ phân bố lại bên trong ô. Không có
mô hình sinh nào; phần dưới 10 m (diffusion) vẫn TỪ CHỐI (roadmap S10).

Giao thức đăng ký trước: backend/data/ml/s2_sharpen_protocol.json (phép kiểm Wald — thu nhỏ ảnh thật một bậc
40 m → 20 m, làm sắc, so với B11 20 m THẬT). Chỉ bật (`available()`) khi kết quả đạt.

S10 ② — DỮ LIỆU TỔNG HỢP để huấn luyện: phương pháp "học" (ml) học trên các cặp tổng hợp đó (ảnh thật thu nhỏ),
không bao giờ hiện cho người dùng; chỉ hệ số học được đi vào sản phẩm.

Lưới: đọc thẳng theo lưới UTM gốc của cảnh (dst_crs = EPSG của cảnh, khung bám đúng lưới 20 m) để mỗi ô 20 m trùng
khít 2×2 ô 10 m — đọc theo kinh/vĩ độ thì máy chủ lấy mẫu lại, phép thu nhỏ 2×2 mất nghĩa.
"""
from __future__ import annotations

import io
import json
import math
import os
import urllib.parse
import urllib.request

import numpy as np

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "ml")
PROTOCOL_PATH = os.path.join(DATA, "s2_sharpen_protocol.json")
RESULT_PATH = os.path.join(DATA, "s2_sharpen_result.json")
BBOX_URL = "https://planetarycomputer.microsoft.com/api/data/v1/item/bbox"
FINE = ("B02", "B03", "B04", "B08")         # 10 m, đã đo
SCL_CLEAR = (4, 5, 6, 7)                    # thực vật · đất trần · nước · chưa phân loại
BP_ITERS = 20                               # số vòng chiếu ngược
EPS = 0.01


# ───────────────────────────── toạ độ UTM ─────────────────────────────

def to_utm(lat: float, lon: float, epsg: int) -> tuple[float, float]:
    """Kinh/vĩ WGS84 → UTM (E, N) bắc bán cầu, chuỗi Krüger bậc 3 (sai < 1 mm trong múi)."""
    zone = int(epsg) - 32600
    if not 1 <= zone <= 60:
        raise ValueError(f"EPSG {epsg} không phải UTM bắc")
    a, f = 6378137.0, 1 / 298.257223563
    n = f / (2 - f)
    A = a / (1 + n) * (1 + n ** 2 / 4 + n ** 4 / 64)
    al = (n / 2 - 2 * n ** 2 / 3 + 5 * n ** 3 / 16, 13 * n ** 2 / 48 - 3 * n ** 3 / 5, 61 * n ** 3 / 240)
    phi, lam = math.radians(lat), math.radians(lon - ((zone - 1) * 6 - 180 + 3))
    c = 2 * math.sqrt(n) / (1 + n)
    t = math.sinh(math.atanh(math.sin(phi)) - c * math.atanh(c * math.sin(phi)))
    xi, eta = math.atan2(t, math.cos(lam)), math.atanh(math.sin(lam) / math.sqrt(1 + t * t))
    E = 500000.0 + 0.9996 * A * (eta + sum(al[j] * math.cos(2 * (j + 1) * xi) * math.sinh(2 * (j + 1) * eta) for j in range(3)))
    N = 0.9996 * A * (xi + sum(al[j] * math.sin(2 * (j + 1) * xi) * math.cosh(2 * (j + 1) * eta) for j in range(3)))
    return E, N


def item_epsg(item: dict) -> int:
    p = item.get("properties") or {}
    if p.get("proj:epsg"):
        return int(p["proj:epsg"])
    code = str(p.get("proj:code") or (item.get("assets", {}).get("B11", {}) or {}).get("proj:code") or "")
    return int(code.split(":")[-1])


def grid_box(item: dict, lat: float, lon: float, n20: int) -> tuple[int, list[float]]:
    """(epsg, [x0, y0, x1, y1]) — khung n20 × n20 ô 20 m quanh điểm, bám ĐÚNG lưới 20 m của cảnh."""
    epsg = item_epsg(item)
    tr = (item.get("assets", {}).get("B11", {}) or {}).get("proj:transform") or [20, 0, 0, 0, -20, 0]
    gx, gy = float(tr[2]), float(tr[5])
    E, N = to_utm(lat, lon, epsg)
    half = n20 * 10.0
    x0 = gx + 20.0 * math.floor((E - half - gx) / 20.0)
    y1 = gy - 20.0 * math.floor((gy - (N + half)) / 20.0)
    return epsg, [x0, y1 - 20.0 * n20, x0 + 20.0 * n20, y1]


def fetch(item: dict, lat: float, lon: float, n20: int, timeout: float = 90.0) -> dict | None:
    """Phản xạ thật (đã trừ lệch 1000 nếu có): fine (4, 2n, 2n) ở 10 m, b11 (n, n) và scl (n, n) ở 20 m."""
    from app.services import jobs, mpc
    epsg, box = grid_box(item, lat, lon, n20)
    off = mpc.BOA_OFFSET if mpc.has_offset(item) else 0
    bb = ",".join(f"{v:.1f}" for v in box)

    def get(assets, size):
        q = [("collection", mpc.COLLECTION), ("item", item["id"]), ("coord_crs", f"EPSG:{epsg}"),
             ("dst_crs", f"EPSG:{epsg}"), ("resampling", "nearest")] + [("assets", a) for a in assets]
        url = f"{BBOX_URL}/{bb}/{size}x{size}.npy?{urllib.parse.urlencode(q)}"
        with jobs.upstream("pc") as allowed:
            if not allowed:
                return None
            try:
                req = urllib.request.Request(url, headers={"User-Agent": mpc.USER_AGENT})
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    return np.load(io.BytesIO(r.read()), allow_pickle=False)
            except Exception:  # noqa: BLE001
                return None

    s = get(["B11", "SCL"], n20)
    if s is None or s.shape[0] < 2:
        return None
    f = get(list(FINE), 2 * n20)
    if f is None or f.shape[0] < 4:
        return None
    refl = lambda x: (x.astype(np.float64) - off) / 10000.0  # noqa: E731
    return {"fine": refl(f[:4]), "b11": refl(s[0]), "scl": s[1].astype(np.int16),
            "valid": (s[-1] > 0) if s.shape[0] > 2 else np.ones_like(s[0], bool),
            "epsg": epsg, "box": box, "offset": off, "item": item["id"],
            "date": (item.get("properties") or {}).get("datetime", "")[:10]}


# ───────────────────────────── toán tử ×2 ─────────────────────────────

def _keys(x: np.ndarray) -> np.ndarray:
    a, x = -0.5, np.abs(x)
    return np.where(x <= 1, (a + 2) * x ** 3 - (a + 3) * x ** 2 + 1,
                    np.where(x < 2, a * x ** 3 - 5 * a * x ** 2 + 8 * a * x - 4 * a, 0.0))


_UM: dict[int, np.ndarray] = {}


def _up_matrix(n: int) -> np.ndarray:
    """Ma trận (2n × n) phóng bậc ba (Keys a = −0,5), tâm điểm ảnh khớp nhau, mép kẹp."""
    if n not in _UM:
        M = np.zeros((2 * n, n))
        for j in range(2 * n):
            u = (j + 0.5) / 2.0 - 0.5
            k0 = math.floor(u)
            for k in range(k0 - 1, k0 + 3):
                M[j, min(max(k, 0), n - 1)] += _keys(np.array(u - k))
        _UM[n] = M
    return _UM[n]


def up(x: np.ndarray) -> np.ndarray:
    M = _up_matrix(x.shape[-1])
    return M @ x @ M.T


def down(x: np.ndarray) -> np.ndarray:
    """Thu nhỏ 2×2 bằng trung bình (ô 20 m = trung bình 4 ô 10 m)."""
    h, w = x.shape[-2:]
    return x.reshape(*x.shape[:-2], h // 2, 2, w // 2, 2).mean(axis=(-3, -1))


def back_project(p: np.ndarray, c: np.ndarray, iters: int = BP_ITERS) -> np.ndarray:
    """Ép thu nhỏ lại 2×2 của kết quả bằng ảnh thô đo được."""
    for _ in range(iters):
        p = p + up(c - down(p))
    return p


# ───────────────────────────── phương pháp ─────────────────────────────

def bicubic(fine: np.ndarray, c: np.ndarray) -> np.ndarray:   # noqa: ARG001 — mốc so sánh
    return up(c)


def sharpen_rg(fine: np.ndarray, c: np.ndarray) -> np.ndarray:
    """(rg) Hồi quy theo TỪNG khung: c ≈ a + Σ bᵢ·thu_nhỏ(băng 10 m ᵢ), áp ở 10 m, rồi chiếu ngược."""
    X = np.concatenate([np.ones((1,) + c.shape), down(fine)]).reshape(len(fine) + 1, -1).T
    coef, *_ = np.linalg.lstsq(X, c.ravel(), rcond=None)
    p0 = coef[0] + np.tensordot(coef[1:], fine, axes=1)
    return back_project(p0, c)


def ml_features(fine: np.ndarray, c: np.ndarray) -> np.ndarray:
    """(8, H, W): chi tiết cao tần của 4 băng 10 m, và chính chi tiết đó nhân tỉ lệ SWIR / băng ở thang thô."""
    uc = up(c)
    low = up(down(fine))
    h = fine - low
    return np.concatenate([h, h * uc / (low + EPS)])


def sharpen_ml(fine: np.ndarray, c: np.ndarray, w: np.ndarray) -> np.ndarray:
    """(ml) Hệ số chung học trên cặp TỔNG HỢP (ảnh thật thu nhỏ một bậc), rồi chiếu ngược."""
    return back_project(up(c) + np.tensordot(w, ml_features(fine, c), axes=1), c)


def ndmi(b08: np.ndarray, b11: np.ndarray) -> np.ndarray:
    return (b08 - b11) / np.maximum(b08 + b11, 1e-4)


def clear_mask(scl: np.ndarray, valid: np.ndarray | None = None) -> np.ndarray:
    m = np.isin(scl, SCL_CLEAR)
    return m & valid if valid is not None else m


# ───────────────────────────── bật / dùng ─────────────────────────────

def _result() -> dict | None:
    try:
        return json.load(open(RESULT_PATH, encoding="utf-8"))
    except (OSError, ValueError):
        return None


def available() -> bool:
    if os.environ.get("TERRATWIN_S2_SHARPEN", "1") == "0":
        return False
    r = _result()
    return bool(r and r.get("passed") is True)


def method() -> tuple[str, np.ndarray | None]:
    r = _result() or {}
    m = r.get("selected", "rg")
    return m, (np.array(r["ml_weights"], dtype=np.float64) if m == "ml" and r.get("ml_weights") else None)


def apply(fine: np.ndarray, c: np.ndarray) -> np.ndarray:
    m, w = method()
    return sharpen_ml(fine, c, w) if m == "ml" and w is not None else sharpen_rg(fine, c)


MAP_N20 = 32                  # khung 640 m: 32 × 32 ô 20 m → 64 × 64 ô 10 m
MAP_DAYS = 120
MAP_CLEAR_MIN = 0.80
MAP_PROBE = 8
DARK_MIN = 0.05               # B08 + B11 dưới mức này: NDMI không xác định (xem diagnosis_after_scoring)


def cache_key(lat: float, lon: float) -> str:
    from app.services import cache_store
    r = _result() or {}
    return cache_store.make_key("ndmi10", round(lat, 4), round(lon, 4), r.get("selected"), r.get("scored_at"))


def _grid(a: np.ndarray, ok: np.ndarray) -> list[list[float | None]]:
    return [[round(float(v), 3) if k else None for v, k in zip(row, okr)] for row, okr in zip(a, ok)]


def ndmi_map(lat: float, lon: float) -> dict | None:
    """NDMI 20 m gốc + NDMI 10 m đã làm sắc của cảnh quang mây gần nhất (≤ 120 ngày) quanh thửa. None nếu nguồn hỏng."""
    from datetime import date, timedelta

    from app.services import cache_store, mpc
    from app.services.reqlang import tr
    key = cache_key(lat, lon)
    hit = cache_store.get(key)
    if hit is not None:
        return hit
    end = date.today()
    items = mpc.search(mpc.bbox_around(lat, lon, MAP_N20 * 10.0), end - timedelta(days=MAP_DAYS), end, limit=80)
    if items is None:
        return None
    got = None
    for it in mpc._one_per_date(items)[:MAP_PROBE]:
        d = fetch(it, lat, lon, MAP_N20)
        if d is None:
            continue
        ok20 = clear_mask(d["scl"], d["valid"])
        if ok20.mean() >= MAP_CLEAR_MIN:
            got, d["ok20"] = it, ok20
            break
    if got is None:
        out = {"available": True, "found": False,
               "message": tr(f"Không có cảnh Sentinel-2 nào quang mây ≥ {int(MAP_CLEAR_MIN * 100)}% quanh thửa trong "
                             f"{MAP_DAYS} ngày qua (mùa mưa thường vậy). Thử lại sau vài ngày.",
                             f"No Sentinel-2 scene ≥ {int(MAP_CLEAR_MIN * 100)}% cloud-free around this plot in the last "
                             f"{MAP_DAYS} days (common in the rainy season). Try again in a few days.")}
        cache_store.put(key, out, ttl_seconds=6 * 3600)
        return out
    p10 = np.clip(apply(d["fine"], d["b11"]), 0.0, 1.0)
    b08_20 = down(d["fine"][3])
    # Mặt nước / bề mặt rất tối: B08 + B11 ≈ 0 → NDMI không xác định (chẩn đoán sau chấm, ô Quảng Nam) → che.
    clear_pct = round(100 * float(d["ok20"].mean()), 1)
    d["ok20"] = d["ok20"] & (b08_20 + d["b11"] >= DARK_MIN)
    ok10 = np.kron(d["ok20"], np.ones((2, 2), bool)) & (d["fine"][3] + p10 >= DARK_MIN)
    n10, n20 = ndmi(d["fine"][3], p10), ndmi(b08_20, d["b11"])
    c = n10.shape[0] // 2
    core = n10[c - 5:c + 5, c - 5:c + 5][ok10[c - 5:c + 5, c - 5:c + 5]]          # 100 × 100 m giữa khung
    m, w = method()
    r = _result() or {}
    out = {
        "available": True, "found": True, "date": d["date"], "item": d["item"], "epsg": d["epsg"],
        "box_utm": [round(v, 1) for v in d["box"]], "clear_pct": clear_pct,
        "method": m, "ndmi_10m": _grid(n10, ok10), "ndmi_20m": _grid(n20, d["ok20"]),
        "center_ndmi_10m": round(float(core.mean()), 3) if core.size else None,
        "center_spread_10m": round(float(np.percentile(core, 90) - np.percentile(core, 10)), 3) if core.size else None,
        "gate": {k: r.get("checks", {}).get(k) for k in ("g1_median_rel_gain", "g2_share_beats_bicubic", "g3_median_ndmi_rel_gain",
                                                          "n_test_scenes")},
        "note": tr("Chi tiết 10 m chuyển từ các băng 10 m ĐÃ ĐO (lam, lục, đỏ, cận hồng ngoại); trung bình mỗi ô 20 m vẫn "
                   "đúng bằng ảnh đo gốc. NDMI là lượng nước trong tán lá — không phải độ ẩm đất. Tham khảo, không vào hồ sơ ký.",
                   "10 m detail is transferred from the MEASURED 10 m bands (blue, green, red, near-infrared); each 20 m cell "
                   "still averages to the original measurement. NDMI is canopy water content — not soil moisture. "
                   "Reference only, not part of the signed dossier."),
    }
    cache_store.put(key, out, ttl_seconds=12 * 3600)
    return out
