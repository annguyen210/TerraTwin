"""AI "RỪNG HAY VƯỜN CÂY?" phía máy chủ — chỉ BẬT khi có mô hình đã qua ngưỡng đặt trước.

Huấn luyện ở app/ml/forest_or_crop.py (máy của chủ dự án). Tệp mô hình data/ml/
foc_model.json CHỈ được ghi khi lần chạy đạt ngưỡng; không có tệp → trả trạng thái
"chưa bật" kèm lịch sử các lần chạy (kể cả lần trượt), giống landcover.py với U-Net.

Kết quả là DỰ ĐOÁN (nhãn tin cậy "predicted"): hiện như tín hiệu tham khảo trên trang
sàng lọc, KHÔNG vào hồ sơ ký số (quy tắc: hồ sơ chỉ chứa số đo và số tính lại được).
"""
from __future__ import annotations

import json
import os
from functools import lru_cache

from app.services.reqlang import tr

_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "ml")


@lru_cache(maxsize=1)
def _model() -> dict | None:
    try:
        with open(os.path.join(_DIR, "foc_model.json"), encoding="utf-8") as f:
            m = json.load(f)
        return m if (m.get("run") or {}).get("status") == "accepted" else None
    except (OSError, ValueError):
        return None


def runs() -> list[dict]:
    try:
        with open(os.path.join(_DIR, "foc_runs.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def status() -> dict:
    m = _model()
    if m is None:
        rs = runs()
        last = rs[-1] if rs else None
        return {"available": False, "runs": rs, "message": tr(
            "Mô hình chưa bật: " + (f"lần chạy ngày {last['date']} không đạt ngưỡng đặt trước "
                                    f"(độ chính xác cân bằng {last['test']['balanced_accuracy']}, độ nhạy rừng "
                                    f"{last['test']['forest_recall']})." if last else "chưa huấn luyện."),
            "Model not enabled: " + (f"the {last['date']} run missed the pre-set bar (balanced accuracy "
                                     f"{last['test']['balanced_accuracy']}, forest recall {last['test']['forest_recall']})."
                                     if last else "not trained yet."))}
    return {"available": True, "kind": m["kind"], "run": m["run"], "runs": runs()}


def predict(geometry_plot: dict) -> dict:
    """Xác suất 'là rừng' cho một thửa (đặc trưng 12 tháng năm 2020 trên khung thửa)."""
    import math

    import numpy as np

    from app.ml import forest_or_crop as foc
    from app.services import eudr_geo

    m = _model()
    if m is None:
        return {**status(), "probability_forest": None}
    g = eudr_geo.shapely_geom(geometry_plot)
    x0, y0, x1, y1 = g.bounds
    lat = (y0 + y1) / 2
    side_m = max((x1 - x0) * 111_320 * math.cos(math.radians(lat)), (y1 - y0) * 111_320, 100.0)
    px = int(min(200, max(10, round(side_m / 10))))
    box = foc.window_box(lat, (x0 + x1) / 2, px)
    comp = foc.monthly_composite(box, size=px)
    F, ok = foc.block_features(comp, block=px)
    if not ok[0]:
        return {"available": True, "probability_forest": None, "message": tr(
            "Không đủ tháng ảnh quang mây năm 2020 trên thửa để mô hình dự đoán.",
            "Not enough cloud-free months in 2020 over the plot for the model.")}
    p = float(foc._np_forward(m, F[:1])[0])
    return {"available": True, "probability_forest": round(p, 3), "evidence_class": "predicted",
            "model": {"kind": m["kind"], "test": m["run"]["test"], "date": m["run"]["date"]},
            "label": tr(f"AI tham khảo: {p * 100:.0f}% khả năng là rừng tự nhiên (năm 2020), {100 - p * 100:.0f}% là vườn cây lâu năm.",
                        f"AI reference: {p * 100:.0f}% likely natural forest (2020), {100 - p * 100:.0f}% tree crop.")}
