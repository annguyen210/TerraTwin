"""A5 — NGUỒN GỐC DỮ LIỆU & TÁI LẬP cho một cảnh báo.

"Vì sao tin con số này?" — câu trả lời đầy đủ không phải "mô hình nói thế", mà là:
dữ liệu nào vào, ngưỡng nào, hiệu chuẩn ra sao, và LÀM THẾ NÀO để chạy lại y hệt.
Đây là nền bắt buộc cho G2/G3 (EUDR, tín chỉ carbon): bên thứ ba phải tái lập
được, không thể tin suông.

Không lưu thêm bảng: cảnh báo đã đủ để tái dựng (thửa, mô-đun, thời điểm, cửa sổ),
phần còn lại là hằng số mô hình đang chạy — nên lineage LUÔN khớp mô hình thật.
"""
from __future__ import annotations

import hashlib
import json

from sqlalchemy.orm import Session

from app.db import Alert, Plot

# Nguồn dữ liệu trình duyệt/bên thứ ba kiểm chứng được, theo từng mô-đun.
_SOURCES = {
    "flood": ["Open-Meteo Forecast (mưa 7 ngày)",
              "Open-Meteo Archive / ERA5 (10 năm hiệu chuẩn)",
              "DEM Open-Meteo (cao độ tương đối)"],
    "landslide": ["Open-Meteo Forecast (mưa)",
                  "Open-Meteo Archive / ERA5 (10 năm)",
                  "Độ dốc từ DEM Open-Meteo"],
    "drought": ["Open-Meteo Forecast (mưa, ET₀)",
                "Open-Meteo Archive / ERA5 (10 năm)"],
    "wildfire": ["Open-Meteo Forecast (nhiệt, độ ẩm, gió, mưa)",
                 "Open-Meteo Archive / ERA5 (10 năm)"],
}


def for_alert(db: Session, alert_id: int) -> dict | None:
    """Toàn bộ chuỗi nguồn gốc + công thức chạy lại cho đúng cảnh báo này."""
    from app.services import calibration as cal, hazard

    a = db.get(Alert, alert_id)
    if a is None:
        return None
    plot = db.get(Plot, a.plot_id) if a.plot_id is not None else None
    lat = plot.lat if plot else None
    lon = plot.lon if plot else None

    inputs = {
        "module_id": a.module_id,
        "lat": lat, "lon": lon,
        "created_at": a.created_at.isoformat(timespec="seconds"),
        "window_days": a.window_days,
        "risk_level": a.risk_level,
        "observed_peak": a.observed_peak,
    }
    model = {
        "index": "hazard.index_series (tuyệt đối + hiệu chuẩn theo phân vị)",
        "thresholds": {"safe": hazard.SAFE, "warning": hazard.WARNING},
        "calibration": {
            "window_days": cal._WINDOW,
            "years": cal._YEARS,
            "lag_days": cal._LAG_DAYS,
            "national_p97": cal.NATIONAL_P97.get(a.module_id),
            "floor": cal._FLOOR.get(a.module_id, 0.0),
        },
        "note": ("Ngưỡng cảnh báo là phân vị của CHÍNH điểm này trên 10 năm ERA5, "
                 "không phải ngưỡng chung cả nước — đó là lý do báo động giả thấp."),
    }
    sources = _SOURCES.get(a.module_id, ["Open-Meteo"])

    reproduce = None
    if lat is not None and lon is not None:
        reproduce = {
            "steps": [
                "1. Lấy 10 năm thời tiết ERA5 tại toạ độ này (Open-Meteo Archive).",
                "2. Chạy hazard.index_series cho mô-đun trên chuỗi đó → phân bố nền.",
                "3. Lấy dự báo 7 ngày (Open-Meteo Forecast), tính chỉ số đỉnh.",
                "4. So đỉnh với ngưỡng hiệu chuẩn (phân vị) của chính điểm này.",
            ],
            "verify_api": f"POST /api/assess/{a.module_id}  body {{\"lat\":{lat},\"lon\":{lon}}}",
            "backtest_api": "GET /api/backtest — kiểm mô hình trên thiên tai lịch sử thật",
        }

    verification = {
        "outcome": a.outcome,
        "verified_at": a.verified_at.isoformat(timespec="seconds") if a.verified_at else None,
        "source": a.verify_source or None,
        "note": a.verify_note or None,
    }

    body = {"inputs": inputs, "model": model, "sources": sources,
            "reproduce": reproduce, "verification": verification}
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=False).encode("utf-8")).hexdigest()
    return {"alert_id": alert_id, **body, "lineage_hash": digest,
            "lineage_short": digest[:16]}
