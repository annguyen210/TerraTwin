"""MÔ HÌNH "RỪNG HAY VƯỜN CÂY?" — học yếu giám sát từ BẤT ĐỒNG giữa các bản đồ.

BÀI TOÁN THẬT, ĐO ĐƯỢC. Sàng lọc EUDR (services/eudr_forest.py) cho ba bản đồ rừng
2020 bỏ phiếu. Đo thật ở vườn cà phê Buôn Ma Thuột: WorldCover vẽ 76% "tán cây",
radar ALOS và Impact Observatory 0% rừng. Một bản đồ thì bỏ phiếu loại được; nhưng
khi HAI bản đồ cùng sai (cà phê che bóng muồng đen, cao su già) thì thửa thành "Cần
xem lại" dù không có rừng nào. Cần một tín hiệu ĐỘC LẬP với các bản đồ: chuỗi ảnh
Sentinel-2 12 tháng — rừng thường xanh giữ NDVI cao quanh năm, vườn cà phê có nhịp
riêng (tưới mùa khô, thu hoạch tháng 11–1, ra hoa sau tưới), cao su rụng lá tháng 1–2.

NHÃN YẾU (programmatic labeling, kiểu Snorkel) — không ai vẽ tay nhãn cho hàng nghìn
ô, nên lấy nhãn ở NƠI CÁC BẢN ĐỒ ĐỒNG Ý:
  rừng       WorldCover ≥80% tán cây VÀ ALOS ≥80% rừng VÀ Impact Observatory ≥80% cây
             (TB 2018–2020)
  vườn cây   WorldCover ≥60% tán cây NHƯNG ALOS ≤10% rừng VÀ IO ≤10% cây
Đặc trưng CHỈ lấy từ Sentinel-2 (không dùng chính các bản đồ hay radar ALOS làm đầu
vào — tránh rò nhãn: mô hình phải học từ ảnh, không học lại bản đồ).

TÁCH THEO VÙNG (không trộn ngẫu nhiên — ô kề nhau giống nhau, trộn là ăn gian):
  huấn luyện  vĩ độ 12,0–14,2 (Đắk Lắk, Gia Lai)
  kiểm định   vĩ độ 14,2–15,0 (Kon Tum)          — chọn mô hình ở đây
  kiểm tra    vĩ độ 11,3–12,0 (Lâm Đồng, Đắk Nông) — chấm MỘT lần
Ngưỡng đặt TRƯỚC (data/ml/foc_protocol.json): độ chính xác cân bằng ≥ 0,85 VÀ độ
nhạy với rừng ≥ 0,90 trên tập kiểm tra. Không đạt → không bật, công bố như U-Net.

GIỚI HẠN NÓI TRƯỚC: tập kiểm tra cũng là nhãn yếu (nơi bản đồ đồng ý) — tức là ca
"dễ". Ca khó thật (bản đồ bất đồng) chưa có nhãn mặt đất; sẽ thu dần từ ảnh thực địa.

    python -m app.ml.forest_or_crop protocol    # ghi giao thức (commit TRƯỚC khi chạy)
    python -m app.ml.forest_or_crop fetch [--windows 200] [--smoke]
    python -m app.ml.forest_or_crop train
"""
from __future__ import annotations

import argparse
import io
import json
import os
import random
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "..", "data", "ml")
PROTOCOL = os.path.join(OUT, "foc_protocol.json")
PARTS = os.path.join(OUT, "foc_parts")
DATASET = os.path.join(OUT, "foc_dataset.npz")
RUNS = os.path.join(OUT, "foc_runs.json")
MODEL = os.path.join(OUT, "foc_model.json")

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
NPY = "https://planetarycomputer.microsoft.com/api/data/v1/item/bbox"
UA = "TerraTwin/0.8 (Vietnam land digital twin; research)"
S2_BANDS = ("B02", "B03", "B04", "B08", "B11", "B12")
SCL_OK = (4, 5, 6, 7, 11)
WIN_PX = 200                 # 2 km ở 10 m
BLOCK = 10                   # ô 100 m × 100 m ≈ 1 ha — cỡ một vườn nông hộ
YEAR = 2020
SCENES_PER_MONTH = 3
CAP_PER_CLASS_PER_WINDOW = 15

PROTOCOL_DOC = {
    "title": "Mô hình Rừng hay vườn cây — giao thức đặt trước",
    "registered": "2026-10-03",
    "region": {"lat": [11.3, 15.0], "lon": [107.2, 109.0]},
    "split_by_latitude": {"train": [12.0, 14.2], "val": [14.2, 15.0], "test": [11.3, 12.0]},
    "labels": {
        "forest": "WorldCover2020 tán cây ≥80% VÀ ALOS FNF 2020 rừng ≥80% VÀ IO TB 2018–2020 cây ≥80%",
        "tree_crop": "WorldCover2020 tán cây ≥60% VÀ ALOS rừng ≤10% VÀ IO cây ≤10%",
    },
    "features": "chỉ Sentinel-2 L2A năm 2020: NDVI, NDMI từng tháng (12+12), trung vị năm 6 kênh, NDVI min mùa khô / max mùa mưa / biên độ, độ lệch chuẩn NDVI trong ô",
    "candidates": ["logistic regression", "MLP 2 lớp ẩn", "1D-CNN trên chuỗi 12 tháng"],
    "selection": "độ chính xác cân bằng cao nhất trên tập kiểm định",
    "pass": {"balanced_accuracy_test": 0.85, "forest_recall_test": 0.90},
    "seed": 20261003, "windows": 200,
    "decision": "Đạt cả hai → xuất mô hình, hiện như tín hiệu THAM KHẢO trong sàng lọc (không vào hồ sơ ký). Không đạt → không bật, công bố.",
}


# ------------------------------------------------------------------ mạng

def _get(url: str, payload: dict | None = None, timeout: float = 90.0):
    for k in range(4):
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode() if payload else None,
                                         headers={"User-Agent": UA, "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception:
            time.sleep(2 + 3 * k)
    return None


def _npy(box, collection: str, item: str, assets: tuple[str, ...], size: int = WIN_PX):
    import numpy as np
    q = urllib.parse.urlencode([("collection", collection), ("item", item)] + [("assets", a) for a in assets])
    b = _get(f"{NPY}/{box[0]},{box[1]},{box[2]},{box[3]}/{size}x{size}.npy?{q}")
    if b is None:
        return None
    try:
        a = np.load(io.BytesIO(b), allow_pickle=False)
        return a[:len(assets)]
    except Exception:
        return None


def _search(collection: str, box, dt: str, limit: int = 200, query: dict | None = None) -> list[dict]:
    body = {"collections": [collection], "bbox": list(box), "datetime": dt, "limit": limit}
    if query:
        body["query"] = query
    b = _get(STAC, body)
    try:
        return json.loads(b)["features"] if b else []
    except Exception:
        return []


def window_box(lat: float, lon: float, px: int = WIN_PX) -> list[float]:
    import math
    half = px * 10 / 2
    dlat = half / 111_320
    dlon = half / (111_320 * math.cos(math.radians(lat)))
    return [round(lon - dlon, 6), round(lat - dlat, 6), round(lon + dlon, 6), round(lat + dlat, 6)]


# ------------------------------------------------------------------ ảnh 12 tháng

def monthly_composite(box, year: int = YEAR, size: int = WIN_PX):
    """→ mảng (12, 6, H, W) float32 phản xạ 0–1 (NaN nếu tháng không có điểm quang)."""
    import numpy as np
    items = _search("sentinel-2-l2a", box, f"{year}-01-01/{year}-12-31", limit=250,
                    query={"eo:cloud_cover": {"lt": 70}})
    by_m: dict[int, list] = {}
    for it in items:
        m = int((it["properties"].get("datetime") or "0000-00")[5:7])
        by_m.setdefault(m, []).append(it)
    out = np.full((12, len(S2_BANDS), size, size), np.nan, dtype=np.float32)
    for m in range(1, 13):
        cand = sorted(by_m.get(m, []), key=lambda it: it["properties"].get("eo:cloud_cover", 100))[:SCENES_PER_MONTH]
        stack = []
        for it in cand:
            a = _npy(box, "sentinel-2-l2a", it["id"], S2_BANDS + ("SCL",), size)
            if a is None:
                continue
            base = it["properties"].get("s2:processing_baseline")
            x = a[:len(S2_BANDS)].astype(np.float32)
            try:
                if base and float(base) >= 4.0:
                    x = x - 1000.0
            except ValueError:
                pass
            x = np.clip(x / 10000.0, 0, 1)
            ok = np.isin(a[len(S2_BANDS)], SCL_OK)
            x[:, ~ok] = np.nan
            stack.append(x)
        if stack:
            with np.errstate(all="ignore"):
                out[m - 1] = np.nanmedian(np.stack(stack), axis=0)
    return out


def block_features(comp, block: int = BLOCK):
    """(12, 6, H, W) → (n_blocks, F) đặc trưng + mặt nạ ô đủ dữ liệu."""
    import warnings
    with warnings.catch_warnings():              # ô mây cả năm cho "All-NaN slice" — đã xử lý bằng mặt nạ `ok`
        warnings.simplefilter("ignore", RuntimeWarning)
        return _block_features(comp, block)


def _block_features(comp, block: int):
    import numpy as np
    eps = 1e-6
    b02, b03, b04, b08, b11, b12 = [comp[:, i] for i in range(6)]
    ndvi = (b08 - b04) / (b08 + b04 + eps)
    ndmi = (b08 - b11) / (b08 + b11 + eps)
    H, W = ndvi.shape[1:]
    by, bx = H // block, W // block

    def bmean(x):            # (12, H, W) → (12, by, bx) bỏ NaN
        r = x[:, :by * block, :bx * block].reshape(x.shape[0], by, block, bx, block)
        with np.errstate(all="ignore"):
            return np.nanmean(r, axis=(2, 4))
    nd_m, nm_m = bmean(ndvi), bmean(ndmi)
    with np.errstate(all="ignore"):
        tex = np.nanmean(np.nanstd(ndvi[:, :by * block, :bx * block].reshape(12, by, block, bx, block), axis=(2, 4)), axis=0)
        bands_med = np.stack([np.nanmedian(bmean(comp[:, i]), axis=0) for i in range(6)])     # (6, by, bx)
    valid_months = np.sum(~np.isnan(nd_m), axis=0)

    def fill(series):         # nội suy vòng 12 tháng cho tháng trống
        s = series.copy()
        idx = np.arange(12)
        for j in range(s.shape[1]):
            v = ~np.isnan(s[:, j])
            if v.sum() >= 2:
                s[~v, j] = np.interp(idx[~v], np.concatenate([idx[v] - 12, idx[v], idx[v] + 12]),
                                     np.tile(s[v, j], 3))
        return s
    nd = fill(nd_m.reshape(12, -1))
    nm = fill(nm_m.reshape(12, -1))
    dry = np.nanmin(nd[0:4], axis=0)            # tháng 1–4
    wet = np.nanmax(nd[5:10], axis=0)           # tháng 6–10
    F = np.concatenate([nd, nm, bands_med.reshape(6, -1), dry[None], wet[None], (wet - dry)[None],
                        tex.reshape(1, -1)], axis=0).T                  # (n_blocks, 12+12+6+4)
    ok = (valid_months.reshape(-1) >= 6) & np.all(np.isfinite(F), axis=1)
    return F.astype(np.float32), ok


FEATURE_NAMES = ([f"ndvi_m{m:02d}" for m in range(1, 13)] + [f"ndmi_m{m:02d}" for m in range(1, 13)] +
                 [f"{b}_median" for b in S2_BANDS] + ["ndvi_dry_min", "ndvi_wet_max", "ndvi_amplitude", "ndvi_texture"])


# ------------------------------------------------------------------ nhãn yếu

def _map_item(collection: str, box, year: int) -> str | None:
    for f in _search(collection, box, f"{year}-01-01T00:00:00Z/{year}-12-31T23:59:59Z", limit=10):
        p = f.get("properties") or {}
        if (p.get("start_datetime") or p.get("datetime") or "")[:4] == str(year):
            return f["id"]
    return None


def weak_labels(box, size: int = WIN_PX, block: int = BLOCK):
    """→ (nhãn mỗi ô: 1 rừng / 0 vườn cây / -1 bỏ, phần trăm từng bản đồ)."""
    import numpy as np

    def frac(arr, codes):
        a = arr[0] if arr.ndim == 3 else arr
        m = np.isin(a, codes).astype(np.float32)
        H, W = m.shape
        by, bx = H // block, W // block
        return m[:by * block, :bx * block].reshape(by, block, bx, block).mean(axis=(1, 3)).reshape(-1)
    wc_id = _map_item("esa-worldcover", box, 2020)
    al_id = _map_item("alos-fnf-mosaic", box, 2020)
    io_ids = [_map_item("io-lulc-annual-v02", box, y) for y in (2018, 2019, 2020)]
    if not wc_id or not al_id or not all(io_ids):
        return None
    wc = _npy(box, "esa-worldcover", wc_id, ("map",), size)
    al = _npy(box, "alos-fnf-mosaic", al_id, ("C",), size)
    ios = [_npy(box, "io-lulc-annual-v02", i, ("data",), size) for i in io_ids]
    if wc is None or al is None or any(x is None for x in ios):
        return None
    wc_t, al_f = frac(wc, (10, 95)), frac(al, (1, 2))
    io_t = np.mean([frac(x, (2,)) for x in ios], axis=0)
    lab = np.full(wc_t.shape, -1, dtype=np.int8)
    lab[(wc_t >= 0.8) & (al_f >= 0.8) & (io_t >= 0.8)] = 1
    lab[(wc_t >= 0.6) & (al_f <= 0.1) & (io_t <= 0.1)] = 0
    return lab, np.stack([wc_t, al_f, io_t], axis=1)


# ------------------------------------------------------------------ tải dữ liệu

def split_of(lat: float) -> str:
    s = PROTOCOL_DOC["split_by_latitude"]
    for k in ("train", "val", "test"):
        if s[k][0] <= lat < s[k][1] or (k == "val" and lat == s[k][1]):
            return k
    return "none"


def fetch_window(k: int, lat: float, lon: float) -> str:
    import numpy as np
    path = os.path.join(PARTS, f"w{k:04d}.npz")
    if os.path.exists(path):
        return "cached"
    box = window_box(lat, lon)
    wl = weak_labels(box)
    if wl is None:
        np.savez_compressed(path, X=np.zeros((0, len(FEATURE_NAMES)), np.float32), y=np.zeros(0, np.int8),
                            maps=np.zeros((0, 3), np.float32), lat=np.zeros(0), lon=np.zeros(0))
        return "no-maps"
    lab, maps = wl
    if not (lab >= 0).any():
        np.savez_compressed(path, X=np.zeros((0, len(FEATURE_NAMES)), np.float32), y=np.zeros(0, np.int8),
                            maps=np.zeros((0, 3), np.float32), lat=np.zeros(0), lon=np.zeros(0))
        return "no-labels"
    comp = monthly_composite(box)
    F, ok = block_features(comp)
    rng = random.Random(PROTOCOL_DOC["seed"] + k)
    keep = []
    for cls in (0, 1):
        idx = [i for i in range(len(lab)) if lab[i] == cls and ok[i]]
        rng.shuffle(idx)
        keep += idx[:CAP_PER_CLASS_PER_WINDOW]
    nb = WIN_PX // BLOCK
    lats = [box[3] - (i // nb + 0.5) * (box[3] - box[1]) / nb for i in keep]
    lons = [box[0] + (i % nb + 0.5) * (box[2] - box[0]) / nb for i in keep]
    np.savez_compressed(path, X=F[keep], y=lab[keep], maps=maps[keep], lat=np.array(lats), lon=np.array(lons))
    return f"{sum(lab[keep] == 1)} rừng / {sum(lab[keep] == 0)} vườn"


def fetch(n_windows: int, workers: int = 3, smoke: bool = False) -> None:
    import numpy as np
    os.makedirs(PARTS, exist_ok=True)
    rng = random.Random(PROTOCOL_DOC["seed"])
    R = PROTOCOL_DOC["region"]
    wins = [(k, rng.uniform(*R["lat"]), rng.uniform(*R["lon"])) for k in range(n_windows)]
    if smoke:
        wins = [(9999, 12.80, 108.20)]
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for i, (w, msg) in enumerate(zip(wins, ex.map(lambda a: fetch_window(*a), wins)), 1):
            print(f"  {i}/{len(wins)} cửa sổ {w[0]} ({w[1]:.3f}, {w[2]:.3f}) [{split_of(w[1])}]: {msg} · {time.time() - t0:.0f}s",
                  flush=True)
    if smoke:
        d = np.load(os.path.join(PARTS, "w9999.npz"))
        print("smoke:", d["X"].shape, "nhãn", np.bincount(d["y"].astype(int) + 1, minlength=3)[1:], flush=True)
        return
    Xs, ys, ms, las, los = [], [], [], [], []
    for k, _, _ in wins:
        d = np.load(os.path.join(PARTS, f"w{k:04d}.npz"))
        if len(d["y"]):
            Xs.append(d["X"]); ys.append(d["y"]); ms.append(d["maps"]); las.append(d["lat"]); los.append(d["lon"])
    np.savez_compressed(DATASET, X=np.concatenate(Xs), y=np.concatenate(ys), maps=np.concatenate(ms),
                        lat=np.concatenate(las), lon=np.concatenate(los), features=np.array(FEATURE_NAMES))
    y = np.concatenate(ys)
    print(f"Bộ dữ liệu: {len(y)} ô · {int((y == 1).sum())} rừng · {int((y == 0).sum())} vườn cây → {DATASET}", flush=True)


# ------------------------------------------------------------------ mô hình (numpy suy luận)

def _np_forward(model: dict, X):
    """Suy luận THUẦN numpy — chạy được trên máy chủ không có torch."""
    import numpy as np
    Z = (X - np.array(model["mean"])) / np.array(model["std"])
    kind = model["kind"]
    if kind == "logreg":
        z = Z @ np.array(model["w"]) + model["b"]
    elif kind == "mlp":
        h = Z
        for i, (W, b) in enumerate(model["layers"]):
            h = h @ np.array(W).T + np.array(b)
            if i < len(model["layers"]) - 1:
                h = np.maximum(h, 0)
        z = h[:, 0]
    else:                                           # cnn1d: chuỗi (N, 2, 12) ndvi/ndmi theo tháng + phần tĩnh
        h = np.stack([Z[:, :12], Z[:, 12:24]], axis=1)
        for W, b in model["convs"]:
            W, b = np.array(W), np.array(b)                              # (out, in, 3)
            p = np.pad(h, ((0, 0), (0, 0), (1, 1)), mode="wrap")         # tháng là VÒNG: tháng 12 kề tháng 1
            win = np.stack([p[:, :, k:k + 12] for k in range(3)], axis=-1)   # (N, in, 12, 3)
            h = np.maximum(np.einsum("nctk,ock->not", win, W) + b[None, :, None], 0)
        g = np.concatenate([h.mean(axis=2), Z[:, 24:]], axis=1)
        for i, (W, b) in enumerate(model["head"]):
            g = g @ np.array(W).T + np.array(b)
            if i < len(model["head"]) - 1:
                g = np.maximum(g, 0)
        z = g[:, 0]
    return 1.0 / (1.0 + np.exp(-z))


def _metrics(p, y, thr: float = 0.5) -> dict:
    import numpy as np
    pred = (p >= thr).astype(int)
    tp = int(((pred == 1) & (y == 1)).sum()); tn = int(((pred == 0) & (y == 0)).sum())
    fp = int(((pred == 1) & (y == 0)).sum()); fn = int(((pred == 0) & (y == 1)).sum())
    rec_f = tp / max(1, tp + fn); rec_c = tn / max(1, tn + fp)
    return {"balanced_accuracy": round((rec_f + rec_c) / 2, 4), "forest_recall": round(rec_f, 4),
            "tree_crop_recall": round(rec_c, 4), "n": int(len(y)), "confusion": {"tp": tp, "tn": tn, "fp": fp, "fn": fn},
            "accuracy": round(float((pred == y).mean()), 4) if len(y) else None}


def train() -> None:
    import numpy as np
    import torch
    from torch import nn

    d = np.load(DATASET)
    X, y, lat = d["X"].astype(np.float32), d["y"].astype(np.int64), d["lat"]
    sp = np.array([split_of(float(a)) for a in lat])
    tr, va, te = sp == "train", sp == "val", sp == "test"
    print(f"train {tr.sum()} · val {va.sum()} · test {te.sum()} · rừng {int((y == 1).sum())} · vườn {int((y == 0).sum())}")
    mean, std = X[tr].mean(0), X[tr].std(0) + 1e-6
    torch.manual_seed(PROTOCOL_DOC["seed"])
    Xt = torch.tensor((X - mean) / std)
    yt = torch.tensor(y, dtype=torch.float32)
    pos_w = torch.tensor(float((y[tr] == 0).sum()) / max(1, (y[tr] == 1).sum()))

    def fit(net, epochs=200, lr=1e-2, wd=1e-4):
        opt = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=wd)
        lossf = nn.BCEWithLogitsLoss(pos_weight=pos_w)
        idx = torch.tensor(np.nonzero(tr)[0])
        best, best_state = -1, None
        for ep in range(epochs):
            net.train()
            perm = idx[torch.randperm(len(idx))]
            for i in range(0, len(perm), 256):
                b = perm[i:i + 256]
                opt.zero_grad()
                lossf(net(Xt[b]).squeeze(-1), yt[b]).backward()
                opt.step()
            if ep % 10 == 9:
                net.eval()
                with torch.no_grad():
                    pv = torch.sigmoid(net(Xt[va]).squeeze(-1)).numpy()
                m = _metrics(pv, y[va])["balanced_accuracy"]
                if m > best:
                    best, best_state = m, {k: v.clone() for k, v in net.state_dict().items()}
        net.load_state_dict(best_state)
        return net, best

    class CNN(nn.Module):
        def __init__(self, nstat=X.shape[1] - 24):
            super().__init__()
            self.c1 = nn.Conv1d(2, 16, 3, padding=1, padding_mode="circular")
            self.c2 = nn.Conv1d(16, 16, 3, padding=1, padding_mode="circular")
            self.h1 = nn.Linear(16 + nstat, 32)
            self.h2 = nn.Linear(32, 1)

        def forward(self, z):
            s = torch.stack([z[:, :12], z[:, 12:24]], 1)
            h = torch.relu(self.c2(torch.relu(self.c1(s)))).mean(2)
            return self.h2(torch.relu(self.h1(torch.cat([h, z[:, 24:]], 1))))

    cands = {
        "logreg": nn.Sequential(nn.Linear(X.shape[1], 1)),
        "mlp": nn.Sequential(nn.Linear(X.shape[1], 64), nn.ReLU(), nn.Linear(64, 32), nn.ReLU(), nn.Linear(32, 1)),
        "cnn1d": CNN(),
    }
    results = {}
    for name, net in cands.items():
        net, val = fit(net)
        results[name] = {"net": net, "val_balanced_accuracy": round(val, 4)}
        print(f"  {name}: kiểm định {val:.4f}")
    best = max(results, key=lambda k: results[k]["val_balanced_accuracy"])
    net = results[best]["net"]
    sd = {k: v.numpy().tolist() for k, v in net.state_dict().items()}
    if best == "logreg":
        model = {"kind": "logreg", "w": np.array(sd["0.weight"])[0].tolist(), "b": float(sd["0.bias"][0])}
    elif best == "mlp":
        model = {"kind": "mlp", "layers": [[sd["0.weight"], sd["0.bias"]], [sd["2.weight"], sd["2.bias"]],
                                           [sd["4.weight"], sd["4.bias"]]]}
    else:
        model = {"kind": "cnn1d", "convs": [[sd["c1.weight"], sd["c1.bias"]], [sd["c2.weight"], sd["c2.bias"]]],
                 "head": [[sd["h1.weight"], sd["h1.bias"]], [sd["h2.weight"], sd["h2.bias"]]]}
    model.update(mean=mean.tolist(), std=std.tolist(), features=FEATURE_NAMES)
    # Kiểm khớp numpy ↔ torch trước khi chấm (suy luận máy chủ phải ra đúng như lúc huấn luyện).
    net.eval()
    with torch.no_grad():
        pt = torch.sigmoid(net(Xt[te]).squeeze(-1)).numpy()
    pn = _np_forward(model, X[te])
    drift = float(np.max(np.abs(pt - pn))) if len(pn) else 0.0
    test = _metrics(pn, y[te])                       # CHẤM MỘT LẦN
    P = PROTOCOL_DOC["pass"]
    passed = test["balanced_accuracy"] >= P["balanced_accuracy_test"] and test["forest_recall"] >= P["forest_recall_test"]
    run = {"date": time.strftime("%Y-%m-%d"), "chosen": best, "val": {k: v["val_balanced_accuracy"] for k, v in results.items()},
           "test": test, "pass_thresholds": P, "passed": passed, "numpy_vs_torch_max_diff": round(drift, 6),
           "n": {"train": int(tr.sum()), "val": int(va.sum()), "test": int(te.sum())},
           "status": "accepted" if passed else "rejected"}
    runs = json.load(open(RUNS, encoding="utf-8")) if os.path.exists(RUNS) else []
    runs.append(run)
    json.dump(runs, open(RUNS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if passed:
        json.dump({**model, "run": run}, open(MODEL, "w", encoding="utf-8"))
    print(json.dumps(run, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["protocol", "fetch", "train"])
    ap.add_argument("--windows", type=int, default=PROTOCOL_DOC["windows"])
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    if a.cmd == "protocol":
        json.dump(PROTOCOL_DOC, open(PROTOCOL, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("ghi", PROTOCOL)
    elif a.cmd == "fetch":
        fetch(a.windows, a.workers, a.smoke)
    else:
        train()
