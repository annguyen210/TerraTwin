"""XÁC SUẤT CẢNH BÁO ĐÃ HIỆU CHUẨN (mục 7, 25/11/2026) — tra bảng data/alert_calibration.json do ops/alert_calibration.py
dựng trên dự báo LƯU TRỮ (Open-Meteo Previous Runs, độ trễ 0–6 ngày) đối chiếu ERA5, giao thức đăng ký trước
data/eval/alert_calibration_protocol.json.

Bảng CHỈ chứa module đã qua cổng trên tập điểm giữ riêng (Brier tốt hơn khí hậu và quy tắc thô, ECE ≤ 0,05, dải 90% phủ
≥ 87%). Module không có trong bảng → None → không hiện xác suất nào (không bịa con số cho module trượt).

Ý nghĩa đúng của con số: "trong các lần dự báo cho đỉnh chỉ số 7 ngày bằng chừng này, bao nhiêu % lần chỉ số THỰC ĐO
(ERA5) đạt ngưỡng 'có chuyện' (≥ 40, như verify.py chấm cảnh báo)". Không phải xác suất ngập tại thửa.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.services.reqlang import tr

TABLE = Path(__file__).resolve().parents[2] / "data" / "alert_calibration.json"


@lru_cache(maxsize=1)
def _table() -> dict:
    try:
        return json.loads(TABLE.read_text(encoding="utf-8")).get("modules") or {}
    except (OSError, ValueError):
        return {}


def calibrated(module_id: str, forecast_peak: float) -> dict | None:
    m = _table().get(module_id)
    if not m or forecast_peak is None:
        return None
    x = float(forecast_peak)
    p = m["steps"][-1][1]
    for xm, pv in m["steps"]:
        if x <= xm:
            p = pv
            break
    bins = m["bins"]
    b = next((i for i in range(len(bins) - 1) if bins[i] <= x < bins[i + 1]), len(bins) - 2)
    hw = m["halfwidth_by_bin"].get(str(b))
    if hw is None:
        hw = max(m["halfwidth_by_bin"].values())
    return {"p_hit": round(float(p), 3), "lo": round(max(0.0, x - hw), 0), "hi": round(min(100.0, x + hw), 0),
            "hit_threshold": m.get("hit_threshold", 40.0), "n_test": m.get("n_test"), "brier_skill": m.get("brier_skill"),
            "coverage": m.get("coverage")}


def sentence(c: dict) -> str:
    pct = round(100 * c["p_hit"])
    return tr(f"Xác suất đã hiệu chuẩn: với mức dự báo này, {pct}% lần chỉ số thực đo đạt ngưỡng {c['hit_threshold']:g} "
              f"(kiểm trên {c['n_test']} cửa sổ ở các tỉnh giữ riêng, dự báo lưu trữ 2024–2025); chỉ số thực đo 7 ngày tới "
              f"90% nằm trong {c['lo']:g}–{c['hi']:g}.",
              f"Calibrated probability: at this forecast level, the measured index reached {c['hit_threshold']:g} in {pct}% "
              f"of cases (tested on {c['n_test']} windows in held-out provinces, archived forecasts 2024–2025); the measured "
              f"7-day index falls within {c['lo']:g}–{c['hi']:g} 90% of the time.")
