"""A12 — HỌC CHỦ ĐỘNG: hỏi đúng câu đáng hỏi nhất.

Tài nguyên khan hiếm nhất của cả sản phẩm là số lần được phép HỎI người dùng —
hỏi nhiều thì họ tắt thông báo. onetap.pending_questions() trước đây chọn theo
thứ tự thời gian, tức hỏi gần như ngẫu nhiên. Câu đáng giá nhất là câu mô hình
đang PHÂN VÂN nhất, ở VÙNG đang ĐÓI dữ liệu nhất, và nơi các tầng BẤT ĐỒNG nhất.
"""
from __future__ import annotations

import math

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import Alert, Observation, Plot

# Ngưỡng mà mô hình coi là "có báo" (federated dùng 40). Gần ngưỡng = phân vân.
_THRESHOLD = 40.0


def _peak(a: Alert) -> float:
    """Chỉ số model lúc phát cảnh báo; suy từ mức báo nếu chưa lưu observed_peak."""
    if a.observed_peak is not None:
        return float(a.observed_peak)
    return {"danger": 75.0, "warning": 50.0}.get(a.risk_level, 25.0)


def _expected(a: Alert) -> float:
    return {"danger": 75.0, "warning": 50.0}.get(a.risk_level, 25.0)


def value_of_asking(a: Alert, db: Session) -> float:
    """Điểm 0..1 — càng cao càng đáng hỏi. Cộng ba thành phần có trọng số.

    1. ĐỘ PHÂN VÂN — khoảng cách từ chỉ số tới ngưỡng 40. Ở đúng ngưỡng thì một
       câu trả lời của người lật được cả phán quyết; xa ngưỡng thì đã chắc rồi.
    2. ĐÓI DỮ LIỆU VÙNG — ô lưới đó có bao nhiêu quan sát (federated.cell_of).
       Ô trống thì mỗi câu trả lời đáng hơn nhiều so với ô đã đủ mẫu.
    3. BẤT ĐỒNG TẦNG — chỉ số đo được lệch với mức đã báo bao nhiêu; lệch nhiều
       nghĩa là các tầng nói khác nhau, đúng chỗ cần người phân xử.
    """
    from app.services import federated

    peak = _peak(a)
    uncertainty = max(0.0, 1.0 - abs(peak - _THRESHOLD) / _THRESHOLD)

    hunger = 1.0
    plot = db.get(Plot, a.plot_id) if a.plot_id is not None else None
    if plot is not None:
        g = federated.GRID
        glat = math.floor(plot.lat / g) * g
        glon = math.floor(plot.lon / g) * g
        n = db.execute(
            select(func.count(Observation.id)).where(
                Observation.module_id == a.module_id,
                Observation.lat >= glat, Observation.lat < glat + g,
                Observation.lon >= glon, Observation.lon < glon + g)
        ).scalar_one()
        hunger = federated.MIN_OBS / (federated.MIN_OBS + float(n))

    disagree = 0.0
    if a.observed_peak is not None:
        disagree = min(1.0, abs(a.observed_peak - _expected(a)) / 50.0)

    return round(0.5 * uncertainty + 0.35 * hunger + 0.15 * disagree, 4)
