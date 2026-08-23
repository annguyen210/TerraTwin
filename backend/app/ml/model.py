"""Mô hình bất thường đa biến theo vùng khí hậu — huấn luyện và suy luận.

VÁ ĐÚNG MỘT ĐIỂM YẾU THẬT CỦA HỆ HIỆN TẠI. Bây giờ mỗi biến được xét riêng:
mưa vượt P97 thì báo, nhiệt vượt P97 thì báo. Cách đó bỏ sót loại nguy hiểm
phổ biến nhất — TỔ HỢP xấu mà không biến nào cực đoan một mình. Đất đã ngấm
nước 15 ngày (P80), thêm một trận mưa vừa (P85), thêm gió mạnh (P75): không có
gì chạm P97, nhưng sườn núi thì sập.

BA QUYẾT ĐỊNH THIẾT KẾ, và lý do:

① CHUẨN HOÁ Z THEO TỪNG ĐỊA PHƯƠNG TRƯỚC KHI GỘP.
   Nếu gộp thô, mô hình sẽ học rằng "mưa nhiều = Huế" và coi mọi ngày ở Phan
   Rang là bất thường. Sau khi mỗi nơi được chuẩn hoá bằng chính lịch sử của
   nó, thứ còn lại là HÌNH DẠNG lệch chuẩn — và hình dạng đó chuyển giao được
   sang nơi chưa từng huấn luyện. Đây là lý do mô hình dùng được cho cả nước
   chứ không chỉ 16 điểm.

② PHÂN VỊ THEO PHÂN BỐ KINH NGHIỆM, KHÔNG THEO CHI-BÌNH-PHƯƠNG.
   Lý thuyết bảo d² tuân theo chi-bình-phương nếu dữ liệu Gaussian. Dữ liệu khí
   tượng KHÔNG Gaussian — đuôi dày hơn nhiều. Dùng công thức lý thuyết sẽ đánh
   giá thấp mức hiếm của đúng những ngày ta cần bắt. Nên lưu thẳng lưới phân vị
   đo được từ dữ liệu huấn luyện.

③ SỐ VÙNG NHỎ (k=4). 16 điểm không nuôi nổi nhiều vùng: mỗi vùng cần đủ ngày
   để ước lượng ma trận 8×8 cho ổn định. k lớn nghe có vẻ tinh vi hơn nhưng
   cho ra hiệp phương sai nhiễu, và mô hình sẽ tệ đi ở nơi chưa từng thấy.
"""
from __future__ import annotations

import json
import math
import os

from app.ml import dataset, linalg

MODEL_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "data", "anomaly_model.json")

K_REGIMES = 4
GRID_STEPS = 1001          # lưới phân vị 0 → 100, bước 0,1%
_SEED = 20260823           # cố định để huấn luyện lại cho ra đúng kết quả cũ


# ─────────────────────────── chữ ký khí hậu ───────────────────────────

def signature(rows: list[dict]) -> list[float]:
    """Chữ ký khí hậu của một nơi: trung bình và độ lệch chuẩn của 8 đặc trưng.

    16 số này là thứ dùng để xếp một địa điểm vào vùng, kể cả địa điểm chưa bao
    giờ xuất hiện lúc huấn luyện.
    """
    vecs = [dataset.vector(r) for r in rows]
    mu = linalg.mean(vecs)
    sd = linalg.stdev(vecs, mu)
    return mu + sd


def local_stats(rows: list[dict]) -> tuple[list[float], list[float]]:
    vecs = [dataset.vector(r) for r in rows]
    mu = linalg.mean(vecs)
    return mu, linalg.stdev(vecs, mu)


# ──────────────────────────────── k-means ────────────────────────────────

def _rng(seed: int):
    """Bộ sinh số giả ngẫu nhiên tự chứa, để kết quả không phụ thuộc phiên bản
    thư viện random của Python."""
    state = seed & 0xFFFFFFFF

    def nxt() -> float:
        nonlocal state
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        return state / 0x7FFFFFFF
    return nxt


def _dist2(a: list[float], b: list[float]) -> float:
    return sum((a[i] - b[i]) ** 2 for i in range(len(a)))


def kmeans(points: list[list[float]], k: int, iters: int = 100) -> tuple[list[list[float]], list[int]]:
    """k-means++ khởi tạo, lặp Lloyd. Hạt giống cố định → tái lập được."""
    n = len(points)
    k = min(k, n)
    rnd = _rng(_SEED)

    centers = [list(points[int(rnd() * n) % n])]
    while len(centers) < k:
        d2 = [min(_dist2(p, c) for c in centers) for p in points]
        total = sum(d2)
        if total <= 0:
            centers.append(list(points[len(centers) % n]))
            continue
        target = rnd() * total
        acc = 0.0
        for i, v in enumerate(d2):
            acc += v
            if acc >= target:
                centers.append(list(points[i]))
                break
        else:
            centers.append(list(points[-1]))

    labels = [0] * n
    for _ in range(iters):
        moved = False
        for i, p in enumerate(points):
            best = min(range(k), key=lambda c: _dist2(p, centers[c]))
            if best != labels[i]:
                labels[i] = best
                moved = True
        for c in range(k):
            members = [points[i] for i in range(n) if labels[i] == c]
            if members:
                centers[c] = linalg.mean(members)
        if not moved:
            break
    return centers, labels


# ─────────────────────────── mô hình một vùng ───────────────────────────

def fit_regime(z_rows: list[list[float]]) -> dict | None:
    """Khớp Gaussian đa biến trên các ngày ĐÃ chuẩn hoá z theo địa phương.

    Trả None nếu hiệp phương sai không nghịch đảo được — vùng đó bị loại thay
    vì được vá bằng ma trận đơn vị.
    """
    if len(z_rows) < 400:
        return None
    mu = linalg.mean(z_rows)
    cov = linalg.ridge(linalg.covariance(z_rows))
    inv = linalg.inverse(cov)
    if inv is None:
        return None

    d2 = sorted(linalg.mahalanobis_sq(r, mu, inv) for r in z_rows)
    grid = [linalg.quantile(d2, 100.0 * i / (GRID_STEPS - 1)) for i in range(GRID_STEPS)]
    return {"mu": mu, "inv": inv, "grid": grid, "n": len(z_rows)}


def percentile(reg: dict, d2: float) -> float:
    """d² → phân vị 0–100 bằng tra lưới, nội suy tuyến tính giữa hai bước."""
    grid = reg["grid"]
    if d2 <= grid[0]:
        return 0.0
    if d2 >= grid[-1]:
        return 100.0
    lo, hi = 0, len(grid) - 1
    while lo < hi - 1:
        mid = (lo + hi) // 2
        if grid[mid] <= d2:
            lo = mid
        else:
            hi = mid
    span = grid[hi] - grid[lo]
    frac = 0.0 if span <= 0 else (d2 - grid[lo]) / span
    return 100.0 * (lo + frac) / (len(grid) - 1)


# ─────────────────────────────── suy luận ───────────────────────────────

class Model:
    """Mô hình đã huấn luyện. Chỉ Python thuần — không cần thư viện nào."""

    def __init__(self, blob: dict):
        self.blob = blob
        self.features = blob["features"]
        self.regimes = blob["regimes"]
        self.sig_mu = blob["signature_mu"]
        self.sig_sd = blob["signature_sd"]

    def assign(self, sig: list[float]) -> int:
        """Xếp một nơi vào vùng gần nhất, trong không gian chữ ký đã chuẩn hoá."""
        z = [(sig[i] - self.sig_mu[i]) / self.sig_sd[i] for i in range(len(sig))]
        return min(range(len(self.regimes)),
                   key=lambda c: _dist2(z, self.regimes[c]["centroid"]))

    def score(self, feats: dict, loc_mu: list[float], loc_sd: list[float],
              regime_id: int) -> dict:
        """Chấm một ngày. Trả phân vị bất thường của TỔ HỢP, kèm biến đóng góp nhiều nhất."""
        reg = self.regimes[regime_id]
        x = dataset.vector(feats)
        z = [(x[i] - loc_mu[i]) / loc_sd[i] for i in range(len(x))]
        d2 = linalg.mahalanobis_sq(z, reg["mu"], reg["inv"])
        pct = percentile(reg, d2)

        # Biến nào đẩy d² lên cao nhất — để giải thích được, không phải hộp đen.
        contrib = []
        for i in range(len(z)):
            dv = [z[j] - reg["mu"][j] for j in range(len(z))]
            share = dv[i] * sum(reg["inv"][i][j] * dv[j] for j in range(len(z)))
            contrib.append((self.features[i], share))
        contrib.sort(key=lambda t: -t[1])

        return {
            "d2": round(d2, 3),
            "percentile": round(pct, 2),
            "regime": regime_id,
            "top_drivers": [{"feature": f, "share": round(s / d2, 3) if d2 > 0 else 0.0}
                            for f, s in contrib[:3] if s > 0],
        }


def load(path: str = MODEL_PATH) -> Model | None:
    """Nạp mô hình. Trả None nếu chưa huấn luyện — KHÔNG có nhánh giả lập.

    Cùng kỷ luật với lớp vệ tinh: thiếu thì nói thiếu, không bịa.
    """
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            blob = json.load(f)
    except (OSError, ValueError):
        return None
    if blob.get("version") != 1 or not blob.get("regimes"):
        return None
    return Model(blob)


def save(blob: dict, path: str = MODEL_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(blob, f, separators=(",", ":"))
