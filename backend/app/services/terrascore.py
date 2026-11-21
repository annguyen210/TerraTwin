"""TerraScore — điểm HIỂM HOẠ THIÊN TAI 7 NGÀY TỚI, 0-100 (cao = ít hiểm hoạ), cho một vị trí.

Gộp 5 hiểm hoạ theo dự báo 7 ngày: mặn, hạn, lũ, sạt lở, cháy — đổi theo thời tiết từng ngày. KHÔNG phải đánh giá
nền đất khi mua (đó là mô-đun land_risk "Nền đất khi mua", cố định theo địa hình) và KHÔNG phải lịch sử ngập (đó là
"Lịch sử nước" radar 2017→nay). Trước 16/10/2026 hạng A ghi "Đất an toàn" — cùng toạ độ giữa sông Hội An hiện
"100/100 Đất an toàn" cạnh "Điểm an toàn đất 49/100": hai con số đo hai thứ khác nhau mà cùng gọi là "an toàn".

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
    reassess: bool = True,
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
            if module is None or not reassess:
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
    scope = tr("Hiểm hoạ thiên tai 7 ngày tới (mặn, hạn, lũ, sạt lở, cháy) theo dự báo — đổi theo thời tiết từng ngày. "
               "Không phải đánh giá nền đất khi mua, không phải lịch sử ngập.",
               "Natural-hazard outlook for the next 7 days (salinity, drought, flood, landslide, wildfire) from forecasts — "
               "changes with the weather. Not a land-purchase assessment, not a flood history.")
    if used == 0:
        # Offline hoặc không có nguồn thật nào → không chấm điểm khống.
        return TerraScoreResult(
            location=loc, score=None, grade="—",
            summary=tr("Chưa đủ dữ liệu thật để chấm điểm (kiểm tra kết nối nguồn dữ liệu).",
                       "Not enough real data to score (check data-source connection)."),
            breakdown={}, real_data_ratio=0.0, scope=scope,
        )

    score = max(0, 100 - penalty)
    if score >= 80:
        grade, summary = "A", tr("Hiểm hoạ thiên tai 7 ngày tới: thấp.", "Natural hazards over the next 7 days: low.")
    elif score >= 60:
        grade, summary = "B", tr("Hiểm hoạ 7 ngày tới: có vài mối cần theo dõi.", "Next 7 days: a few hazards to watch.")
    elif score >= 40:
        grade, summary = "C", tr("Hiểm hoạ 7 ngày tới: trung bình–cao — theo dõi sát.", "Next 7 days: medium–high hazard — watch closely.")
    else:
        grade, summary = "D", tr("Hiểm hoạ 7 ngày tới: cao — nhiều mối nguy chồng lấn.", "Next 7 days: high — multiple overlapping hazards.")

    summary += tr(f" (chấm từ {used}/{len(_HAZARDS)} hiểm họa có dữ liệu thật)",
                  f" (scored from {used}/{len(_HAZARDS)} hazards with real data)")
    return TerraScoreResult(
        location=loc, score=score, grade=grade, summary=summary,
        breakdown=breakdown, real_data_ratio=ratio, scope=scope,
    )


def with_other_threats(ts: TerraScoreResult, alerts) -> TerraScoreResult:
    """Câu tóm tắt của thẻ thửa phải nói cả mối đe doạ NGOÀI 5 hiểm hoạ thời tiết (kiểm A–Z 21/11/2026, P1-1).

    Quảng Điền: thẻ ghi "100/A — Hiểm hoạ thiên tai 7 ngày tới: thấp" trong khi lũ từ thượng nguồn (mô-đun nặng, lượt
    quét sâu) báo NGUY HIỂM. Điểm số vẫn chỉ chấm 5 hiểm hoạ thời tiết (định nghĩa dùng chung cho backtest, lịch sử
    điểm) — nhưng câu chữ không được nói "thấp" khi còn một mối đang cảnh báo: nói mối đó TRƯỚC, và gọi đúng phạm vi
    của phần "thấp" là 5 hiểm hoạ thời tiết. `alerts` = mô-đun thật, threat=True, mức cảnh báo/nguy hiểm (scan.alerts)."""
    from app.services.reqlang import tr
    other = [a for a in alerts if a.id not in _HAZARDS and a.risk_level in ("danger", "warning")]
    if not other or ts.score is None:
        return ts
    muc = {"danger": tr("nguy hiểm", "danger"), "warning": tr("cảnh báo", "warning")}
    names = ", ".join(f"{a.name[:1].lower() + a.name[1:]} ({muc[a.risk_level]})" for a in other)
    nguy = any(a.risk_level == "danger" for a in other)
    lead = (tr(f"Hiểm hoạ 7 ngày tới: có mối NGUY HIỂM — {names}.", f"Next 7 days: a DANGER — {names}.") if nguy else
            tr(f"Hiểm hoạ 7 ngày tới: còn {len(other)} mối cần theo dõi — {names}.",
               f"Next 7 days: {len(other)} more threat(s) to watch — {names}."))
    # phần còn lại của câu cũ: đổi "Hiểm hoạ thiên tai 7 ngày tới: thấp." thành phạm vi đúng của nó
    rest = ts.summary.replace(tr("Hiểm hoạ thiên tai 7 ngày tới: thấp.", "Natural hazards over the next 7 days: low."),
                              tr("5 hiểm hoạ thời tiết chính chưa đáng lo", "The 5 main weather hazards are not a concern"))
    ts.summary = f"{lead} {rest}"
    return ts
