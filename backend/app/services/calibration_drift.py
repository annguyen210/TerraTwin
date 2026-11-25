"""GIÁM SÁT TRÔI XÁC SUẤT ĐÃ HIỆU CHUẨN (MLOps, nâng cấp 25/11/2026).

Bảng hiệu chuẩn (alert_prob) học trên dự báo 2024–2025. Thời tiết, mô hình dự báo nguồn, hay cách người dùng chọn thửa
có thể đổi — xác suất từng đúng có thể "trôi". Mỗi cảnh báo nay lưu xác suất đã hứa (`Alert.p_calibrated`); khi cảnh báo
được chấm (verify.py: hit / false_alarm), so tỉ lệ trúng THỰC TẾ với tổng xác suất đã hứa:

    kỳ vọng E = Σ p_i,  phương sai V = Σ p_i (1 − p_i)  (tổng các biến Bernoulli độc lập),
    z = (số trúng − E) / √V.

Đủ ≥ MIN_N cảnh báo đã chấm mà |z| > Z_MAX → TRÔI: alert_prob ngừng hiện xác suất (tự tắt, không chờ người sửa) và thẻ
mô hình ghi rõ. Chưa đủ mẫu → "chưa đủ dữ liệu để kết luận", vẫn hiện. Kiểm lại mỗi giờ.
"""
from __future__ import annotations

import math
import time

MIN_N = 30
Z_MAX = 2.0
_CACHE: dict = {"at": 0.0, "val": None}
_TTL_S = 3600.0


def evaluate(rows: list[tuple[float, int]]) -> dict:
    """Thuần: rows = [(p đã hứa, 1 nếu trúng / 0 nếu báo bừa)]. → {n, expected, observed, z, drift, enough}."""
    n = len(rows)
    if n == 0:
        return {"n": 0, "enough": False, "drift": False, "expected": None, "observed": None, "z": None}
    e = sum(p for p, _ in rows)
    v = sum(p * (1 - p) for p, _ in rows)
    k = sum(y for _, y in rows)
    z = (k - e) / math.sqrt(v) if v > 0 else 0.0
    enough = n >= MIN_N
    return {"n": n, "enough": enough, "drift": enough and abs(z) > Z_MAX, "expected": round(e / n, 3),
            "observed": round(k / n, 3), "z": round(z, 2)}


def status(db=None) -> dict:
    """Trạng thái hiện tại (đệm 1 giờ). Không đọc được CSDL → coi như chưa đủ dữ liệu (không tắt nhầm)."""
    now = time.time()
    if _CACHE["val"] is not None and now - _CACHE["at"] < _TTL_S and db is None:
        return _CACHE["val"]
    try:
        from sqlalchemy import select

        from app import db as _db
        from app.db import Alert
        own = db is None
        s = db or _db.SessionLocal()
        try:
            q = s.execute(select(Alert.p_calibrated, Alert.outcome).where(
                Alert.p_calibrated.is_not(None), Alert.outcome.in_(("hit", "false_alarm")))).all()
        finally:
            if own:
                s.close()
        val = evaluate([(float(p), 1 if o == "hit" else 0) for p, o in q])
    except Exception:  # noqa: BLE001
        val = evaluate([])
    _CACHE.update(at=now, val=val)
    return val


def drifted() -> bool:
    return bool(status().get("drift"))
