"""Các endpoint của VÒNG LẶP TIN CẬY — sổ điểm, một chạm, bản đồ độ tin cậy.

Gom riêng một file vì ba tính năng này chia nhau một nguyên tắc mà phần còn lại
của API không có: **phần lớn ở đây KHÔNG cần đăng nhập.**

  · Sổ điểm công khai vì một sổ điểm chỉ chủ nhà xem được thì không phải sổ
    điểm. Ý nghĩa của nó nằm ở chỗ người ngoài — người dùng đang phân vân, ban
    giám khảo, khách hàng — kiểm tra được mà không cần xin phép ai.
  · Đường một chạm công khai vì bắt người nông dân đăng nhập trước khi họ được
    phép nói cho ta biết ruộng đã ngập là điểm chết của cả vòng lặp. Nó được
    bảo vệ bằng token ký số, không phải bằng phiên đăng nhập — xem onetap.py.

Chỉ hai endpoint chạy việc nặng (`/api/verify/run`, `/api/verify/misses`) là
đòi đăng nhập, vì chúng gọi mạng ra ngoài và không được để ai gõ URL cũng kích
hoạt được.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth
from app.db import Alert, User, get_session
from app.services import onetap, scorecard, verify

router = APIRouter(tags=["trust"])


# ---------------------------------------------------------------------------
# SỔ ĐIỂM — công khai
# ---------------------------------------------------------------------------

@router.get("/api/scorecard")
def get_scorecard(days: int = 90, db: Session = Depends(get_session)) -> dict:
    """Sổ điểm tự chấm. Không cần đăng nhập — đó là điểm mấu chốt.

    Con số này do phần mềm tự chấm về chính mình và không sửa được từ giao diện.
    """
    days = max(7, min(days, 3650))
    s = scorecard.summary(db, days)
    s["by_module"] = scorecard.by_module(db, days)
    s["ground_truth"] = scorecard.ground_truth(db)
    return s


@router.get("/api/scorecard/timeline")
def get_timeline(days: int = 180, buckets: int = 12,
                 db: Session = Depends(get_session)) -> dict:
    """Sổ điểm theo thời gian — để thấy nó đang tốt lên hay xấu đi."""
    return {"buckets": scorecard.timeline(db, max(14, min(days, 3650)),
                                          max(3, min(buckets, 40)))}


@router.get("/api/reliability")
def get_reliability(days: int = 365, module_id: str | None = None,
                    db: Session = Depends(get_session)) -> dict:
    """Phần mềm chính xác Ở ĐÂU — theo ô lưới 0,5°."""
    return scorecard.reliability(db, max(30, min(days, 3650)), module_id)


# ---------------------------------------------------------------------------
# MỘT CHẠM — công khai, bảo vệ bằng token ký số
# ---------------------------------------------------------------------------

class TapIn(BaseModel):
    answer: str = Field(..., description="yes | no | unsure")


def _alert_from_token(token: str, db: Session) -> Alert:
    aid = onetap.read_token(token)
    if aid is None:
        raise HTTPException(
            404, "Liên kết không hợp lệ hoặc đã hết hạn (45 ngày).")
    a = db.get(Alert, aid)
    if a is None:
        raise HTTPException(404, "Cảnh báo này không còn nữa.")
    return a


@router.get("/api/tap/{token}")
def read_question(token: str, db: Session = Depends(get_session)) -> dict:
    """Câu hỏi sau liên kết một chạm. KHÔNG cần đăng nhập.

    Token chỉ mở đúng một câu hỏi về đúng một cảnh báo — không đọc được thửa,
    không xem được cảnh báo khác, không đổi được gì trong tài khoản.
    """
    return onetap.question(_alert_from_token(token, db), db)


@router.post("/api/tap/{token}")
def send_answer(token: str, body: TapIn,
                db: Session = Depends(get_session)) -> dict:
    """Ghi nhận câu trả lời. KHÔNG cần đăng nhập."""
    a = _alert_from_token(token, db)
    try:
        res = onetap.answer(a, body.answer, db)
    except ValueError as e:
        raise HTTPException(422, str(e))
    db.commit()
    return res


@router.get("/api/questions")
def my_questions(limit: int = 5, user: User = Depends(auth.current_user),
                 db: Session = Depends(get_session)) -> dict:
    """Câu hỏi đang chờ chính người này trả lời, để hiện ngay trong app.

    Người chưa nối kênh nhận tin vẫn phải có đường đóng vòng lặp — nếu không
    thì kho quan sát chỉ lớn được nhờ những người đã bật thông báo.
    """
    qs = onetap.pending_questions(db, user.id, max(1, min(limit, 20)))
    return {"questions": qs, "count": len(qs)}


# ---------------------------------------------------------------------------
# CHẠY TAY — đòi đăng nhập vì gọi mạng ra ngoài
# ---------------------------------------------------------------------------

@router.post("/api/verify/run")
def run_verify(limit: int = 100, user: User = Depends(auth.current_user),
               db: Session = Depends(get_session)) -> dict:
    """Chấm ngay những cảnh báo đã tới hạn, không đợi lượt quét nền."""
    return verify.sweep(db, max(1, min(limit, 500)))


@router.get("/api/plots/{plot_id}/timeline")
def plot_timeline(plot_id: int, days: int = 90, limit: int = 30,
                  user: User = Depends(auth.current_user),
                  db: Session = Depends(get_session)) -> dict:
    """Dòng thời gian của MỘT thửa — lý do để mở lại phần mềm vào ngày mai.

    Phép đo cho thấy 58 người dùng nhưng chỉ 9 thửa được lưu: 84% chưa từng lưu
    gì, nên radar không có gì để quét cho họ, nên họ không bao giờ nhận được
    cảnh báo, nên họ không quay lại. Một công cụ TRA CỨU thì dùng một lần rồi
    quên; một thửa đất ĐANG ĐƯỢC TRÔNG COI thì được mở mỗi sáng.

    Endpoint này là mặt sau của chuyện đó: gộp vào một chỗ những gì đã báo, cái
    nào hoá ra đúng, cái nào hụt, và câu nào đang chờ người ta trả lời — kể cả
    những lần bỏ sót, vì giấu chúng đi thì dòng thời gian sẽ chỉ là một danh
    sách thành tích.
    """
    from datetime import datetime, timedelta, timezone

    from app.db import Plot

    p = db.get(Plot, plot_id)
    if p is None or p.user_id != user.id:
        raise HTTPException(404, "Không tìm thấy thửa này.")

    since = (datetime.now(timezone.utc).replace(tzinfo=None)
             - timedelta(days=max(1, min(days, 3650))))
    rows = db.execute(
        select(Alert).where(Alert.plot_id == p.id, Alert.created_at >= since)
        .order_by(Alert.created_at.desc()).limit(max(1, min(limit, 200)))
    ).scalars().all()

    events = [{
        "alert_id": a.id,
        "at": a.created_at.isoformat(timespec="seconds"),
        "module_id": a.module_id,
        "risk_level": a.risk_level,
        "headline": a.headline,
        "recommendation": a.recommendation,
        # was_warned = False nghĩa là hàng hồi cứu: chuyện đã xảy ra thật mà
        # phần mềm im lặng. Nói thẳng ra chứ không lặng lẽ bỏ khỏi danh sách.
        "was_warned": not a.retro,
        "outcome": a.outcome,
        "observed_peak": a.observed_peak,
        "verify_source": a.verify_source or "",
        "verify_note": a.verify_note or "",
    } for a in rows]

    tally = {"hit": 0, "miss": 0, "false_alarm": 0, "expired": 0, "pending": 0}
    for e in events:
        key = e["outcome"] or "pending"
        tally[key] = tally.get(key, 0) + 1

    qs = [q for q in onetap.pending_questions(db, user.id, limit=20)
          if q.get("alert_id") in {a.id for a in rows}]

    return {
        "plot": {"id": p.id, "name": p.name, "lat": p.lat, "lon": p.lon,
                 "area_ha": p.area_ha, "score": p.score, "grade": p.grade,
                 "saved_at": p.created_at.isoformat(timespec="seconds")},
        "window_days": days,
        "events": events,
        "tally": tally,
        "questions": qs,
        "watching_since": p.created_at.isoformat(timespec="seconds"),
    }


@router.post("/api/verify/misses")
def run_misses(days: int = verify.MISS_LOOKBACK_DAYS,
               user: User = Depends(auth.current_user),
               db: Session = Depends(get_session)) -> dict:
    """Quét ngược lịch sử tìm những đợt hiểm họa phần mềm đã BỎ SÓT.

    Nặng hơn `/api/verify/run` (một lời gọi mạng mỗi thửa) nhưng là thứ khiến
    sổ điểm không phải một lời tự khen.
    """
    return verify.sweep_misses(db, max(14, min(days, 730)))
