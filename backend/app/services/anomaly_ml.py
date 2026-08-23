"""Lớp chấm bất thường bằng mô hình đã huấn luyện — dùng khi chạy thật.

VAI TRÒ ĐÚNG CỦA LỚP NÀY LÀ ĐỐI CHIẾU, KHÔNG PHẢI THAY THẾ.
Đánh giá trên 5 năm chưa từng thấy cho kết quả HOÀ với cách xét từng biến ở mức
vận hành 2% (3/3 sự kiện cả hai bên). Mô hình chỉ nhỉnh hơn khi siết ngưỡng
xuống 1% — lúc đó cách cũ bỏ sót sạt lở Trà Leng còn nó vẫn bắt được. Vì vậy nó
KHÔNG được quyền tự nâng mức rủi ro của module nào. Nó chỉ trả thêm một câu:
"tổ hợp hôm nay hiếm tới mức nào so với lịch sử nơi này".

Toàn bộ con số đứng sau kết luận đó nằm trong data/anomaly_model.json, mục
metrics — kể cả những mức mà mô hình KHÔNG thắng.

Trả None khi chưa huấn luyện hoặc thiếu dữ liệu. Không có nhánh giả lập.
"""
from __future__ import annotations

import time
from datetime import date, timedelta

from app.ml import dataset, model
from app.services import realdata

_MODEL: model.Model | None = None
_LOADED = False

_STATS: dict[tuple, tuple] = {}         # (lat,lon) → (mu, sd, regime, ts)
_STATS_TTL = 30 * 86400                 # khí hậu 10 năm không đổi trong một tháng

_YEARS = 8                              # số năm lịch sử để dựng nền cho một điểm


def _model() -> model.Model | None:
    global _MODEL, _LOADED
    if not _LOADED:
        _MODEL = model.load()
        _LOADED = True
    return _MODEL


def available() -> bool:
    m = _model()
    return m is not None and bool(m.blob.get("metrics", {}).get("enabled"))


def model_card() -> dict:
    """Thẻ mô hình — công bố cả chỗ thua, không chỉ chỗ thắng."""
    m = _model()
    if m is None:
        return {"available": False,
                "message": "Chưa huấn luyện. Chạy: python -m app.ml.train"}
    mt = m.blob.get("metrics", {})
    return {
        "available": True,
        "enabled": bool(mt.get("enabled")),
        "trained_at": mt.get("trained_at"),
        "train_period": m.blob.get("train_period"),
        "test_period": m.blob.get("test_period"),
        "sites": mt.get("sites"),
        "train_days": mt.get("train_days"),
        "test_days": mt.get("test_days"),
        "features": m.features,
        "regimes": [{"id": r["id"], "days": r["n"], "sites": r["sites"]}
                    for r in m.regimes],
        "comparison": mt.get("comparison"),
        "leave_one_out": mt.get("leave_one_out"),
        "verdict": mt.get("verdict"),
        "role": ("Đối chiếu, không thay thế. Ở mức vận hành 2% mô hình HOÀ với "
                 "cách xét từng biến; chỉ nhỉnh hơn khi siết xuống 1%."),
        "method": ("Mahalanobis đa biến theo vùng khí hậu, huấn luyện tự giám sát "
                   "trên ERA5 2015–2019, kiểm tra trên 2020–2024 và trên tỉnh "
                   "chưa từng huấn luyện."),
    }


def _archive(lat: float, lon: float, start: str, end: str):
    url = ("https://archive-api.open-meteo.com/v1/archive"
           f"?latitude={lat}&longitude={lon}"
           f"&start_date={start}&end_date={end}"
           f"&daily={dataset._DAILY}&timezone=auto")
    d = realdata._get(url, timeout=25.0)
    if not d or "daily" not in d:
        return None
    dd = d["daily"]
    try:
        return [{"date": dd["time"][i],
                 "precip": dataset._f(dd["precipitation_sum"], i),
                 "et0": dataset._f(dd["et0_fao_evapotranspiration"], i),
                 "tmax": dataset._f(dd["temperature_2m_max"], i),
                 "tmin": dataset._f(dd["temperature_2m_min"], i),
                 "wind": dataset._f(dd["wind_speed_10m_max"], i)}
                for i in range(len(dd["time"]))]
    except (KeyError, TypeError, IndexError):
        return None


def _local(lat: float, lon: float):
    """Nền khí hậu của MỘT điểm: trung bình, độ lệch chuẩn, và vùng được xếp vào.

    Một lượt gọi mạng, giữ 30 ngày. Chuẩn hoá theo chính nơi này là điều kiện để
    mô hình huấn luyện ở 16 điểm dùng được cho cả nước.
    """
    key = (round(lat, 2), round(lon, 2))
    hit = _STATS.get(key)
    if hit and time.time() - hit[3] < _STATS_TTL:
        return hit[0], hit[1], hit[2]

    m = _model()
    if m is None:
        return None, None, None

    end = date.today() - timedelta(days=8)          # ERA5 trễ khoảng một tuần
    start = end - timedelta(days=365 * _YEARS)
    rows = _archive(lat, lon, start.isoformat(), end.isoformat())
    if not rows or len(rows) < 365 * 3:
        return None, None, None

    feats = dataset.build_features(rows)
    if len(feats) < 800:
        return None, None, None

    mu, sd = model.local_stats(feats)
    reg = m.assign(model.signature(feats))
    _STATS[key] = (mu, sd, reg, time.time())
    return mu, sd, reg


def score(lat: float, lon: float) -> dict | None:
    """Chấm ngày gần nhất có dữ liệu. Trả None nếu chưa huấn luyện/thiếu dữ liệu."""
    m = _model()
    if m is None or not available():
        return None

    mu, sd, reg = _local(lat, lon)
    if mu is None:
        return None

    end = date.today() - timedelta(days=8)
    start = end - timedelta(days=dataset.WARMUP + 5)
    rows = _archive(lat, lon, start.isoformat(), end.isoformat())
    if not rows:
        return None
    feats = dataset.build_features(rows)
    if not feats:
        return None

    latest = feats[-1]
    out = m.score(latest, mu, sd, reg)
    pct = out["percentile"]

    if pct >= 99.0:
        verdict = "Tổ hợp điều kiện hiếm — 1% số ngày hiếm nhất tại chính nơi này"
    elif pct >= 98.0:
        verdict = "Tổ hợp bất thường — nằm trong 2% số ngày hiếm nhất"
    elif pct >= 95.0:
        verdict = "Hơi khác thường, chưa tới ngưỡng đáng lo"
    else:
        verdict = "Tổ hợp nằm trong dải bình thường của nơi này"

    return {
        "available": True,
        "date": latest["date"],
        "percentile": pct,
        "verdict": verdict,
        "regime": reg,
        "top_drivers": out["top_drivers"],
        "role": ("Chỉ số đối chiếu — KHÔNG thay đổi mức rủi ro của module nào. "
                 "Ở mức vận hành 2%, mô hình này hoà với cách xét từng biến."),
        "caveat": ("Đo độ hiếm của TỔ HỢP, không đo mức nguy hiểm. Một tổ hợp "
                   "hiếm có thể vô hại; một ngày bão điển hình có thể không "
                   "hiếm. Đọc cùng cảnh báo của module, đừng đọc thay."),
    }
