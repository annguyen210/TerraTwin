"""CHẠM LÀ CÓ RANH — đề xuất ranh thửa từ một điểm chạm, bằng chuỗi ảnh Sentinel-2.

TRẠNG THÁI: THỬ NGHIỆM ĐÃ THẤT BẠI (4/10/2026) — KHÔNG có API, KHÔNG hiện cho người dùng.
Kiểm định theo giao thức đặt trước (data/eval/autoboundary_protocol.json) trên 77 ranh
OpenStreetMap: IoU trung vị toàn bộ 0,0; trên 12 lượt có đề xuất 0,38 (ngưỡng bật 0,60,
ngưỡng thử nghiệm 0,50). Kết quả đầy đủ: data/eval/autoboundary_result.json. Giữ mã để
lần sau so sánh, không chỉnh tham số trên chính bộ đó.

VÌ SAO: bước khó nhất của hồ sơ EUDR với nông hộ là VẼ RANH đúng chuẩn EU (đa giác
toạ độ 6 chữ số, bắt buộc với thửa > 4 ha). Người trồng cà phê 60 tuổi không vẽ đa giác
trên điện thoại được; họ CHẠM được vào vườn của mình.

CÁCH LÀM (thị giác máy tính trên chuỗi thời gian, không phải một tấm ảnh):
  1. Cửa sổ ~800 m quanh điểm chạm, lấy tới 8 cảnh Sentinel-2 L2A quang mây trong
     12 tháng (Planetary Computer, miễn phí), cùng một lưới điểm ảnh 10 m.
  2. Mỗi điểm ảnh là một VECTƠ: NDVI từng ngày + cận hồng ngoại + hồng ngoại sóng
     ngắn trung bình. Hai vườn liền kề trông giống nhau trên một ảnh nhưng khác nhịp
     sinh trưởng (tưới, tỉa cành, tuổi cây, thời điểm thu hoạch) — chuỗi thời gian
     tách được chúng, một ảnh đơn thì không.
  3. MỞ RỘNG VÙNG CÓ THỐNG KÊ từ điểm chạm: nhận điểm ảnh lân cận khi khoảng cách tới
     trung bình vùng (đã chuẩn hoá theo độ biến thiên của cả cửa sổ) dưới ngưỡng.
  4. Làm sạch hình thái (mở 3×3, lấp lỗ), giữ mảng chứa điểm chạm, đổi sang đa giác,
     làm đơn giản ~1 điểm ảnh, toạ độ 6 chữ số (Điều 2(28) Quy định (EU) 2023/1115).

GIỚI HẠN — NÓI RA, KHÔNG GIẤU:
  · Điểm ảnh 10 m: mép ranh lệch ±10–20 m là bình thường. Thửa < 0,1 ha (dưới ~10
    điểm ảnh) không tách được.
  · Hai vườn cùng giống, cùng tuổi, cùng chăm sóc có thể bị gộp làm một.
  · Đây là RANH ĐỀ XUẤT để người dùng kiểm và chỉnh trên ảnh nền — không phải đo đạc
    địa chính, và không thay ranh trên sổ đỏ.
Độ tin cậy trả về là ĐỘ TÁCH BIỆT đo được giữa trong và ngoài ranh, không phải xác
suất đúng; chưa có bộ ranh chuẩn đối chiếu nên CHƯA công bố độ chính xác (IoU).
"""
from __future__ import annotations

import io
import math
import urllib.parse
import urllib.request
from collections import deque
from datetime import date, timedelta

import numpy as np

from app.services import mpc
from app.services.reqlang import tr

METHOD = "terratwin.autoboundary/1"
WINDOW_M = 400.0                 # bán kính cửa sổ → ô 800 m
PX_M = 10.0
SIZE = int(2 * WINDOW_M / PX_M)  # 80 × 80 điểm ảnh, CÙNG lưới cho mọi cảnh
MAX_SCENES = 8
PROBE = 16
SCENE_CLEAR_MIN = 0.7            # cảnh dùng được khi ≥ 70% cửa sổ quang mây
# Ngưỡng mở rộng (RMS theo chiều, đơn vị độ lệch chuẩn của cửa sổ). KHÔNG đặt cố định —
# chọn bằng tiêu chí VÙNG ỔN ĐỊNH CỰC ĐẠI (cùng ý với MSER, Matas 2002): ranh thật của
# một vườn là ranh mà nới ngưỡng thêm thì diện tích gần như KHÔNG đổi (bị bờ vườn chặn
# lại); ranh ngẫu nhiên thì phình đều. Đã thử và BỎ: ngưỡng cố định 2,2 (Đắk Lắk tràn
# 30 ha) và "tách biệt trong/ngoài lớn nhất" (luôn thiên về vùng 0,1–0,2 ha).
GROW_KS = tuple(round(0.30 + 0.08 * i, 2) for i in range(16))     # 0,30 … 1,50
STABLE_MAX = 0.35        # tăng diện tích tương đối qua hai bước ngưỡng, tối đa
NDVI_VEG = 0.35         # dưới mức này là mái nhà/sân/nước, không phải vườn
EDGE_MIN = 1.25          # tương phản mép tối thiểu (cặp điểm ảnh qua ranh / bên trong)
GROW_K = 0.8
MIN_HA, MAX_HA = 0.1, 30.0
_SCL_OK = np.array(mpc.SCL_CLEAR)
_BASE = "https://planetarycomputer.microsoft.com/api/data/v1/item/bbox"


def _fetch(item_id: str, box: list[float]) -> np.ndarray | None:
    """(5, SIZE, SIZE): B04, B08, B11, SCL, mặt nạ. None nếu gọi hỏng."""
    from app.services import jobs
    b = ",".join(f"{v:.6f}" for v in box)
    q = urllib.parse.urlencode({"collection": mpc.COLLECTION, "item": item_id,
                                "assets": ["B04", "B08", "B11", "SCL"],
                                "resampling": "nearest"}, doseq=True)
    url = f"{_BASE}/{b}/{SIZE}x{SIZE}.npy?{q}"
    with jobs.upstream() as allowed:
        if not allowed:
            return None
        try:
            req = urllib.request.Request(url, headers={"User-Agent": mpc.USER_AGENT})
            with urllib.request.urlopen(req, timeout=40) as r:
                a = np.load(io.BytesIO(r.read()), allow_pickle=False)
        except Exception:
            return None
    return a if a.shape == (5, SIZE, SIZE) else None


def _scenes(box: list[float]) -> tuple[list[np.ndarray], list[str]] | None:
    from app.services import jobs
    end = date.today()
    items = mpc.search(box, end - timedelta(days=365), end, max_cloud=60.0, limit=400)
    if items is None:
        return None
    items = mpc._one_per_date(items)
    probe = mpc._spread(items, min(PROBE, len(items)))
    got = jobs.gather([lambda it=it: (it, _fetch(it["id"], box)) for it in probe])
    good = []
    for res in got:
        if not res or res[1] is None:
            continue
        it, a = res
        clear = np.isin(a[3], _SCL_OK) & (a[4] > 0)
        frac = float(clear.mean())
        if frac >= SCENE_CLEAR_MIN:
            good.append((frac, it["properties"]["datetime"][:10], a, clear))
    good.sort(key=lambda g: -g[0])
    good = sorted(good[:MAX_SCENES], key=lambda g: g[1])
    return [(g[2], g[3]) for g in good], [g[1] for g in good]


def _features(scenes) -> np.ndarray:
    """(F, H, W) đã chuẩn hoá z-score theo cửa sổ. Điểm mây lấp bằng trung vị cảnh."""
    ndvi, nir, swir = [], [], []
    for a, clear in scenes:
        red, b08, b11 = (a[0].astype(np.float64), a[1].astype(np.float64), a[2].astype(np.float64))
        nd = (b08 - red) / np.maximum(b08 + red, 1.0)
        for arr, out in ((nd, ndvi), (b08 / 10000.0, nir), (b11 / 10000.0, swir)):
            v = arr.copy()
            med = float(np.median(arr[clear])) if clear.any() else 0.0
            v[~clear] = med
            out.append(v)
    feats = ndvi + [np.mean(nir, axis=0), np.mean(swir, axis=0)]
    f = np.stack(feats)
    mu = f.reshape(len(feats), -1).mean(1)[:, None, None]
    sd = f.reshape(len(feats), -1).std(1)[:, None, None]
    return (f - mu) / np.maximum(sd, 1e-6)


def _grow(f: np.ndarray, seed: tuple[int, int], k: float = GROW_K,
          max_px: int | None = None) -> np.ndarray:
    """Mở rộng vùng 4-lân cận; so với trung bình VÙNG cập nhật dần."""
    F, H, W = f.shape
    max_px = max_px or int(MAX_HA * 10_000 / PX_M ** 2) + 1
    r0, c0 = seed
    win = f[:, max(0, r0 - 1):r0 + 2, max(0, c0 - 1):c0 + 2].reshape(F, -1)
    s = win.sum(1)
    n = win.shape[1]
    mask = np.zeros((H, W), dtype=bool)
    mask[r0, c0] = True
    q = deque([(r0, c0)])
    thr2 = (k ** 2) * F
    while q:
        r, c = q.popleft()
        for rr, cc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
            if 0 <= rr < H and 0 <= cc < W and not mask[rr, cc]:
                v = f[:, rr, cc]
                d2 = float(((v - s / n) ** 2).sum())
                if d2 <= thr2:
                    mask[rr, cc] = True
                    s = s + v
                    n += 1
                    q.append((rr, cc))
                    if n > max_px:
                        return mask
    return mask


def _touches_edge(m: np.ndarray) -> bool:
    return bool(m[0].any() or m[-1].any() or m[:, 0].any() or m[:, -1].any())


def _shift(m: np.ndarray, dr: int, dc: int) -> np.ndarray:
    out = np.zeros_like(m)
    H, W = m.shape
    out[max(0, dr):H + min(0, dr), max(0, dc):W + min(0, dc)] = \
        m[max(0, -dr):H - max(0, dr), max(0, -dc):W - max(0, dc)]
    return out


def _clean(mask: np.ndarray, seed: tuple[int, int]) -> np.ndarray:
    """Mở 3×3 (bỏ gai/cầu nối 1 điểm ảnh), giữ mảng chứa điểm chạm, lấp lỗ."""
    nb = [(dr, dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1)]
    er = np.logical_and.reduce([_shift(mask, dr, dc) for dr, dc in nb])
    op = np.logical_or.reduce([_shift(er, dr, dc) for dr, dc in nb]) & mask
    if not op[seed]:
        op = mask
    comp = _component(op, seed)
    outside = _component(~comp, None)     # nền nối với mép cửa sổ
    return ~outside


def _component(m: np.ndarray, seed: tuple[int, int] | None) -> np.ndarray:
    H, W = m.shape
    out = np.zeros_like(m)
    if seed is None:
        starts = [(r, c) for r in range(H) for c in (0, W - 1)] + \
                 [(r, c) for c in range(W) for r in (0, H - 1)]
    else:
        starts = [seed]
    q = deque(p for p in starts if m[p])
    for p in q:
        out[p] = True
    while q:
        r, c = q.popleft()
        for rr, cc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
            if 0 <= rr < H and 0 <= cc < W and m[rr, cc] and not out[rr, cc]:
                out[rr, cc] = True
                q.append((rr, cc))
    return out


def _polygon(mask: np.ndarray, box: list[float]):
    """Mặt nạ điểm ảnh → shapely Polygon theo kinh/vĩ độ."""
    from shapely.geometry import box as sbox
    from shapely.ops import unary_union
    H, W = mask.shape
    rows = []
    for r in range(H):
        cols = np.flatnonzero(mask[r])
        if cols.size == 0:
            continue
        start = prev = cols[0]
        for c in cols[1:]:
            if c != prev + 1:
                rows.append(sbox(start, r, prev + 1, r + 1))
                start = c
            prev = c
        rows.append(sbox(start, r, prev + 1, r + 1))
    geom = unary_union(rows).simplify(0.8, preserve_topology=True)
    if geom.geom_type == "MultiPolygon":
        geom = max(geom.geoms, key=lambda g: g.area)
    minx, miny, maxx, maxy = box
    sx, sy = (maxx - minx) / W, (maxy - miny) / H

    def tf(x, y):                               # hàng 0 = phía BẮC của ô
        return round(minx + x * sx, 6), round(maxy - y * sy, 6)

    from shapely.geometry import Polygon
    shell = [tf(x, y) for x, y in geom.exterior.coords]
    return Polygon(shell).buffer(0)


def _edge_contrast(f: np.ndarray, mask: np.ndarray) -> float | None:
    """Khác biệt trung bình của cặp điểm ảnh kề nhau NẰM HAI BÊN ranh, chia cho cặp kề
    nhau cùng nằm TRONG vùng. ≈1: ranh vẽ qua giữa một vùng đồng nhất; ≫1: bờ thật."""
    F = f.shape[0]
    cross, inner = [], []
    for dr, dc in ((1, 0), (0, 1)):
        a = mask[: mask.shape[0] - dr, : mask.shape[1] - dc]
        b = mask[dr:, dc:]
        d = np.sqrt(((f[:, : f.shape[1] - dr, : f.shape[2] - dc] - f[:, dr:, dc:]) ** 2).sum(0) / F)
        cross.append(d[a ^ b])
        inner.append(d[a & b])
    c, i = np.concatenate(cross), np.concatenate(inner)
    if c.size < 8 or i.size < 8:
        return None
    return float(c.mean() / max(i.mean(), 1e-6))


def _separability(f: np.ndarray, mask: np.ndarray) -> float | None:
    """Khoảng cách trung bình VÀNH NGOÀI (2 điểm ảnh) tới tâm vùng, chia cho độ phân tán
    trong vùng. ≫1: ranh rõ; ≈1: vùng không khác xung quanh."""
    F = f.shape[0]
    ring = mask.copy()
    for _ in range(2):
        ring = ring | _shift(ring, 1, 0) | _shift(ring, -1, 0) | _shift(ring, 0, 1) | _shift(ring, 0, -1)
    ring &= ~mask
    if mask.sum() < 4 or ring.sum() < 4:
        return None
    inside = f[:, mask].T
    outside = f[:, ring].T
    mu = inside.mean(0)
    d_in = np.sqrt(((inside - mu) ** 2).sum(1) / F).mean()
    d_out = np.sqrt(((outside - mu) ** 2).sum(1) / F).mean()
    return float(d_out / max(d_in, 1e-6))


def propose(lat: float, lon: float) -> dict | None:
    """Ranh đề xuất quanh điểm chạm. None = nguồn ảnh không phản hồi (KHÁC 'không tách được')."""
    box = mpc.bbox_around(lat, lon, WINDOW_M)
    got = _scenes(box)
    if got is None:
        return None
    scenes, dates = got
    base = {"method": METHOD, "scenes": len(scenes), "dates": dates,
            "pixel_m": PX_M, "window_m": 2 * WINDOW_M}
    if len(scenes) < 3:
        return {**base, "ok": False, "reason": "cloud",
                "message": tr(f"Chỉ có {len(scenes)} cảnh quang mây trong 12 tháng — chưa đủ để tách vườn. Hãy vẽ ranh bằng tay hoặc đi bộ quanh vườn.",
                              f"Only {len(scenes)} cloud-free scenes in 12 months — not enough to separate plots. Draw the boundary by hand or walk the perimeter.")}
    f = _features(scenes)
    seed = (SIZE // 2, SIZE // 2)
    # Độ ổn định đo trên vùng MỞ RỘNG THÔ (trước làm sạch): phép mở hình thái có thể làm
    # vùng co lại khi nới ngưỡng, khiến "tăng diện tích" ra số âm — đo thật ở Cần Thơ.
    masks, areas = [], []
    for k in GROW_KS:
        raw = _grow(f, seed, k=k)
        a_ha = raw.sum() * PX_M ** 2 / 10_000.0
        if _touches_edge(raw) or a_ha > MAX_HA:
            break                                # ngưỡng lớn hơn chỉ tràn thêm
        masks.append((k, _clean(raw, seed)))
        areas.append(a_ha)
    best = None                                  # (độ ổn định, k, mặt nạ, tương phản mép)
    for i in range(1, len(masks) - 1):
        k, m = masks[i]
        if areas[i] < MIN_HA:
            continue
        stab = (areas[i + 1] - areas[i - 1]) / areas[i]
        edge_c = _edge_contrast(f, m)
        if stab > STABLE_MAX or edge_c is None or edge_c < EDGE_MIN:
            continue
        if best is None or stab < best[0] - 1e-9 or (abs(stab - best[0]) < 1e-9 and edge_c > best[3]):
            best = (stab, k, m, edge_c)
    if best is None:
        return {**base, "ok": False, "reason": "no_stable_edge",
                "message": tr("Không thấy bờ vườn rõ quanh điểm này trên chuỗi ảnh 10 m (vườn nhỏ, xen nhà cửa, hoặc giống hệt vườn bên cạnh). Hãy vẽ ranh bằng tay hoặc đi bộ quanh vườn.",
                              "No clear plot edge around this point in the 10 m image series (small plot, mixed with buildings, or identical to the neighbour). Draw by hand or walk the perimeter.")}
    mask = best[2]
    # Hàng EUDR (cà phê, cao su, ca cao, gỗ) là THẢM THỰC VẬT. Vùng NDVI trung bình thấp
    # là mái nhà, sân, mặt nước — không phải vườn (điểm thử giữa phố Buôn Ma Thuột).
    ndvi_in = float(np.mean([((a[1].astype(float) - a[0]) / np.maximum(a[1].astype(float) + a[0], 1.0))[mask].mean()
                             for a, _ in scenes]))
    if ndvi_in < NDVI_VEG:
        return {**base, "ok": False, "reason": "not_vegetation",
                "message": tr(f"Điểm chạm không nằm trên thảm thực vật (NDVI trung bình {ndvi_in:.2f}) — có thể là nhà cửa, sân bãi hoặc mặt nước. Hãy chạm vào giữa vườn.",
                              f"The tapped point isn't on vegetation (mean NDVI {ndvi_in:.2f}) — possibly buildings, yards or water. Tap the middle of the plot.")}
    px = int(mask.sum())
    area_ha = px * PX_M ** 2 / 10_000.0
    edge = _touches_edge(mask)
    if area_ha < MIN_HA:
        return {**base, "ok": False, "reason": "too_small",
                "message": tr("Không tách được vườn ở điểm này (nhỏ hơn ~0,1 ha hoặc lẫn với xung quanh). Hãy vẽ ranh bằng tay.",
                              "Couldn't separate a plot here (under ~0.1 ha or blends with surroundings). Draw it by hand.")}
    if edge or area_ha > MAX_HA:
        return {**base, "ok": False, "reason": "unbounded",
                "message": tr("Vùng giống nhau trải rộng quá cửa sổ 800 m (rừng liền khoảnh, cánh đồng lớn?) — không xác định được ranh vườn. Hãy vẽ ranh bằng tay.",
                              "The uniform area extends past the 800 m window (continuous forest, large field?) — can't delimit a plot. Draw it by hand.")}
    poly = _polygon(mask, box)
    sep = _separability(f, mask)
    # Độ tin cậy = tương phản mép quy về 0–1 (1,25 → 0; ≥ 2,5 → 1). KHÔNG phải xác suất đúng.
    conf = round(max(0.0, min(1.0, (best[3] - EDGE_MIN) / (2.5 - EDGE_MIN))), 2)
    return {
        **base, "ok": True,
        "geometry": {"type": "Polygon", "coordinates": [list(map(list, poly.exterior.coords))]},
        "area_ha": round(area_ha, 2), "pixels": px, "k": best[1],
        "stability": round(float(best[0]), 3), "ndvi": round(ndvi_in, 2), "edge_contrast": round(best[3], 2),
        "separability": None if sep is None else round(sep, 2), "confidence": conf,
        "message": tr(
            f"Ranh ĐỀ XUẤT từ {len(scenes)} cảnh Sentinel-2 (10 m) trong 12 tháng, ~{area_ha:.2f} ha. "
            "Mép có thể lệch 10–20 m — kéo các đỉnh cho khớp ảnh nền trước khi phát hành. "
            "Đây không phải đo đạc địa chính.",
            f"PROPOSED boundary from {len(scenes)} Sentinel-2 scenes (10 m) over 12 months, ~{area_ha:.2f} ha. "
            "Edges may be off by 10–20 m — drag the vertices to match the basemap before issuing. "
            "This is not a cadastral survey."),
    }
