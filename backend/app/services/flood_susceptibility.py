"""KHẢ NĂNG NGẬP THEO ĐỊA HÌNH — mô hình học máy (mục 6, 25/11/2026), giao thức data/eval/flood_susceptibility_protocol.json.

Hồi quy logistic trên 5 đặc trưng địa hình (độ cao, độ dốc, chênh cao cục bộ, khoảng cách biển, khoảng cách sông), nhãn =
radar Sentinel-1 có thấy nước phủ ≥ 1 đợt 2017–2025 ở 200 điểm ngẫu nhiên. Tệp data/ml/flood_susceptibility.json CHỈ được
ghi khi mô hình qua cổng trên các tỉnh giữ riêng — không có tệp thì mọi hàm trả None (không hiện gì).

Ý nghĩa đúng: XẾP HẠNG so với các điểm mẫu ("thuộc nhóm X% dễ ngập nhất theo địa hình"), không phải xác suất ngập năm
tới; không biết đê, kênh, cống, san lấp — lịch sử radar của chính thửa luôn đáng tin hơn.
"""
from __future__ import annotations

import bisect
import json
import math
from functools import lru_cache
from pathlib import Path

from app.services.reqlang import tr

MODEL = Path(__file__).resolve().parents[2] / "data" / "ml" / "flood_susceptibility.json"


@lru_cache(maxsize=1)
def _model() -> dict | None:
    try:
        m = json.loads(MODEL.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return m if m.get("w") and m.get("ref_scores") else None


def features(lat: float, lon: float) -> list[float] | None:
    """Cùng định nghĩa ops/flood_susceptibility.py; DEM 5 điểm dùng chung URL (và nhớ đệm) với realdata.slope_deg."""
    from app.services import datasources as ds, realdata, river_grid
    step = 500.0
    dlat = step / 111_320.0
    dlon = step / (111_320.0 * max(0.1, math.cos(math.radians(lat))))
    lats = [lat, lat + dlat, lat - dlat, lat, lat]
    lons = [lon, lon, lon, lon + dlon, lon - dlon]
    d = realdata._get("https://api.open-meteo.com/v1/elevation?latitude=" + ",".join(f"{v:.5f}" for v in lats)
                      + "&longitude=" + ",".join(f"{v:.5f}" for v in lons))
    try:
        e = [float(x) for x in d["elevation"]]
    except (KeyError, TypeError, ValueError):
        return None
    slope = math.degrees(math.atan(math.hypot((e[1] - e[2]) / (2 * step), (e[3] - e[4]) / (2 * step))))
    river = river_grid.nearest_km(lat, lon)
    river = min(3.0, river) if river is not None and math.isfinite(river) else 3.0
    return [math.log1p(max(0.0, e[0] + 5)), slope, math.log1p(max(e) - min(e)),
            math.log1p(ds.distance_to_coast_km(lat, lon)), math.log1p(river)]


def assess(lat: float, lon: float) -> dict | None:
    m = _model()
    if m is None:
        return None
    x = features(lat, lon)
    if x is None:
        return None
    z = m["w"][0] + sum(w * (v - mu) / sd for w, v, mu, sd in zip(m["w"][1:], x, m["mu"], m["sd"]))
    p = 1 / (1 + math.exp(-z))
    ref = m["ref_scores"]
    top_pct = max(1, round(100 * (1 - bisect.bisect_left(ref, p) / len(ref))))
    return {"score": round(p, 3), "top_pct": top_pct, "auc_test": m.get("auc_test"), "n_ref": len(ref)}


def sentence(r: dict) -> str:
    return tr(f"Theo địa hình (mô hình học máy, AUC {r['auc_test']} trên các tỉnh giữ riêng), thửa thuộc nhóm {r['top_pct']}% dễ "
              f"có nước phủ nhất trong {r['n_ref']} điểm mẫu toàn quốc — không biết đê, kênh, san lấp; lịch sử radar của chính "
              "thửa đáng tin hơn.",
              f"By terrain (machine-learning model, AUC {r['auc_test']} on held-out provinces), the plot is in the top "
              f"{r['top_pct']}% most water-prone of {r['n_ref']} nationwide sample points — dykes, canals and fill are unknown; "
              "the plot's own radar history is more reliable.")
