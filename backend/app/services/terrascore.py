"""TerraScore — điểm an toàn tổng hợp 0-100 cho một vị trí.

Chỉ gộp các hiểm họa có DỮ LIỆU THẬT (is_real). Dữ liệu mock/ước lượng chưa
hiệu chỉnh KHÔNG được phép ảnh hưởng con số lớn nhất màn hình — đồng bộ với
nguyên tắc lọc mock ở scan.alerts.
"""
from __future__ import annotations

from app.schemas import Assessment, Location, TerraScoreResult

_HAZARDS = ["salinity", "drought", "flood", "landslide", "wildfire"]
_PEN = {"danger": 22, "warning": 11, "safe": 0, "unknown": 0}


def compute(
    loc: Location,
    assessments: dict[str, Assessment] | None = None,
) -> TerraScoreResult:
    """Chấm điểm. Nếu truyền sẵn `assessments` (id→Assessment) thì tái dùng,
    tránh assess lại (dùng trong /api/scan)."""
    from app.modules.registry import get_module  # tránh import vòng

    penalty = 0
    breakdown: dict[str, int] = {}
    used = 0
    for hid in _HAZARDS:
        a = (assessments or {}).get(hid)
        if a is None:
            module = get_module(hid)
            if module is None:
                continue
            a = module.assess(loc)
        if not a.is_real:
            continue  # bỏ qua hiểm họa mock/ước lượng chưa hiệu chỉnh
        p = _PEN.get(a.risk_level, 0)
        penalty += p
        breakdown[hid] = p
        used += 1

    ratio = round(used / len(_HAZARDS), 2)

    from app.services.reqlang import tr
    if used == 0:
        # Offline hoặc không có nguồn thật nào → không chấm điểm khống.
        return TerraScoreResult(
            location=loc, score=0, grade="—",
            summary=tr("Chưa đủ dữ liệu thật để chấm điểm (kiểm tra kết nối nguồn dữ liệu).",
                       "Not enough real data to score (check data-source connection)."),
            breakdown={}, real_data_ratio=0.0,
        )

    score = max(0, 100 - penalty)
    if score >= 80:
        grade, summary = "A", tr("Đất an toàn — rủi ro tự nhiên thấp.", "Safe land — low natural risk.")
    elif score >= 60:
        grade, summary = "B", tr("Khá an toàn — có vài rủi ro cần theo dõi.", "Fairly safe — a few risks to watch.")
    elif score >= 40:
        grade, summary = "C", tr("Rủi ro trung bình–cao — cân nhắc kỹ.", "Medium–high risk — weigh carefully.")
    else:
        grade, summary = "D", tr("Rủi ro cao — nhiều mối nguy chồng lấn.", "High risk — multiple overlapping hazards.")

    summary += tr(f" (chấm từ {used}/{len(_HAZARDS)} hiểm họa có dữ liệu thật)",
                  f" (scored from {used}/{len(_HAZARDS)} hazards with real data)")
    return TerraScoreResult(
        location=loc, score=score, grade=grade, summary=summary,
        breakdown=breakdown, real_data_ratio=ratio,
    )
