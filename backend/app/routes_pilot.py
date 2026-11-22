"""THÍ ĐIỂM — phiếu góp ý của nông hộ, hợp tác xã, doanh nghiệp, người định mua đất và môi giới sau khi dùng thử.

Đây là chỗ đo xem sản phẩm có dùng được ngoài đời không: mất bao nhiêu phút cho một hồ
sơ, bước nào khó nhất, có tin kết quả không, có dùng tiếp không. Gửi phiếu KHÔNG cần
đăng nhập (nông hộ ở buổi tập huấn không có tài khoản); cán bộ HTX đăng nhập thì nhập
lại được cả xấp phiếu giấy (source="paper"). Chỉ quản trị viên xem tổng hợp.
"""
from __future__ import annotations

import csv
import io
import statistics
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth
from app.db import PilotFeedback, User, get_session
from app.services import quota, reqlang
from app.services.reqlang import tr

router = APIRouter(tags=["pilot"])

# 30/10/2026: thêm người ĐỊNH MUA đất và môi giới (trang /dung-thu) — luồng "kiểm lời rao trước khi xuống tiền"; hai bước
# của luồng đó là kiểm tin đăng (listing) và đọc lịch sử nước của thửa (water).
ROLES = ("farmer", "coop", "exporter", "buyer", "broker", "other")
STEPS = ("boundary", "screen", "dossier", "lot", "verify", "listing", "water", "none")


class FeedbackIn(BaseModel):
    role: Literal["farmer", "coop", "exporter", "buyer", "broker", "other"]
    ease: int = Field(ge=1, le=5)
    trust: int = Field(ge=1, le=5)
    # Kiểm A–Z 21/11/2026: BẮT BUỘC cả hai — bản cũ để hardest mặc định "none" và giao diện chọn sẵn would_use="yes",
    # nên phiếu chỉ chấm điểm rồi gửi đã ghi "sẽ dùng" + "không có chỗ khó". Thiếu → 422, không điền hộ.
    would_use: Literal["yes", "maybe", "no"]
    hardest: Literal["boundary", "screen", "dossier", "lot", "verify", "listing", "water", "none"]
    minutes: int | None = Field(default=None, ge=0, le=600)
    region: str = Field(default="", max_length=80)
    comment: str = Field(default="", max_length=2000)
    contact: str = Field(default="", max_length=120)
    consent_contact: bool = False
    source: Literal["web", "paper"] = "web"


@router.post("/api/pilot/feedback")
def submit_feedback(body: FeedbackIn, request: Request, lang: str = "vi",
                    user: User | None = Depends(auth.optional_user),
                    db: Session = Depends(get_session)) -> dict:
    reqlang.set_lang(lang)
    contact = body.contact.strip()
    if contact and not body.consent_contact:
        raise HTTPException(422, tr(
            "Có ghi cách liên hệ nhưng chưa đánh dấu đồng ý cho liên hệ lại — đánh dấu, hoặc xoá ô liên hệ.",
            "Contact given but consent to be contacted is not ticked — tick it, or clear the contact field."))
    if body.source == "paper" and user is None:
        raise HTTPException(401, tr(
            "Nhập lại phiếu giấy cần đăng nhập (để biết cán bộ nào nhập).",
            "Entering paper forms requires signing in (so we know who entered them)."))
    from app.main import _client_ip
    wait = quota.take("feedback", f"u{user.id}" if user else f"ip{_client_ip(request)}", user is not None)
    if wait is not None:
        raise HTTPException(429, tr("Đã gửi nhiều phiếu hôm nay — cảm ơn bạn, thử lại sau.",
                                    "Many forms sent today — thank you, try again later."),
                            headers={"Retry-After": str(wait)})
    row = PilotFeedback(source=body.source, role=body.role, region=body.region.strip(),
                        hardest=body.hardest, ease=body.ease, trust=body.trust,
                        minutes=body.minutes, would_use=body.would_use,
                        comment=body.comment.strip(), contact=contact,
                        user_id=user.id if user else None)
    db.add(row)
    db.commit()
    return {"ok": True, "id": row.id,
            "message": tr("Đã nhận góp ý. Cảm ơn bạn!", "Feedback received. Thank you!")}


def _median(xs: list[int]) -> float | None:
    return round(statistics.median(xs), 1) if xs else None


def _mean(xs: list[int]) -> float | None:
    return round(sum(xs) / len(xs), 2) if xs else None


@router.get("/api/admin/pilot/feedback")
def feedback_summary(_: User = Depends(auth.require_admin),
                     db: Session = Depends(get_session)) -> dict:
    """Tổng hợp thật, không làm tròn cho đẹp: n nhỏ thì nói n nhỏ. Phiếu ĐÃ LOẠI (thử nội bộ, rác) không vào số đếm, nhưng
    được kể riêng — "đã loại N phiếu (lý do…)" — để ai đọc số cũng kiểm được."""
    all_rows = db.execute(select(PilotFeedback).order_by(PilotFeedback.id.desc())).scalars().all()
    rows = [r for r in all_rows if r.excluded_at is None]
    gone = [r for r in all_rows if r.excluded_at is not None]

    def block(sub):
        return {"n": len(sub),
                "ease_mean": _mean([r.ease for r in sub]),
                "trust_mean": _mean([r.trust for r in sub]),
                "minutes_median": _median([r.minutes for r in sub if r.minutes is not None]),
                "would_use": {k: sum(1 for r in sub if r.would_use == k) for k in ("yes", "maybe", "no")},
                "hardest": {k: sum(1 for r in sub if r.hardest == k) for k in STEPS}}

    reasons: dict[str, int] = {}
    for r in gone:
        reasons[r.exclude_reason or "?"] = reasons.get(r.exclude_reason or "?", 0) + 1
    return {"all": block(rows),
            "by_role": {k: block([r for r in rows if r.role == k]) for k in ROLES},
            "note": ("Dưới 30 phiếu thì mọi tỷ lệ chỉ là dấu hiệu, chưa phải kết luận."
                     if len(rows) < 30 else ""),
            "excluded": {"n": len(gone), "by_reason": [{"reason": k, "n": v} for k, v in reasons.items()],
                         "note": (f"Đã loại {len(gone)} phiếu khỏi số liệu ("
                                  + "; ".join(f"{k}: {v}" for k, v in reasons.items()) + ")") if gone else ""},
            "latest": [{"id": r.id, "created_at": r.created_at.isoformat() if r.created_at else None,
                        "source": r.source, "role": r.role, "region": r.region, "ease": r.ease,
                        "trust": r.trust, "minutes": r.minutes, "would_use": r.would_use,
                        "hardest": r.hardest, "comment": r.comment, "contact": r.contact}
                       for r in rows[:100]],
            "excluded_latest": [{"id": r.id, "created_at": r.created_at.isoformat() if r.created_at else None,
                                 "excluded_at": r.excluded_at.isoformat() if r.excluded_at else None,
                                 "reason": r.exclude_reason, "role": r.role}
                                for r in gone[:50]]}


class ExcludeIn(BaseModel):
    reason: str = Field(min_length=3, max_length=200)


@router.post("/api/admin/pilot/feedback/{fid}/exclude")
def feedback_exclude(fid: int, body: ExcludeIn, admin: User = Depends(auth.require_admin),
                     db: Session = Depends(get_session)) -> dict:
    """LOẠI một phiếu khỏi số liệu (xoá MỀM, kiểm A–Z lần 2): phiếu vẫn còn trong CSDL và CSV, ghi rõ ai loại, khi nào,
    lý do (bắt buộc, vd "phiếu thử nội bộ"). Thay cho xoá cứng ở PR #58 — số liệu thí điểm phải kiểm toán được."""
    from datetime import datetime, timezone
    row = db.get(PilotFeedback, fid)
    if row is None:
        raise HTTPException(404, tr("Không có phiếu này.", "No such feedback."))
    if row.excluded_at is not None:
        raise HTTPException(409, tr("Phiếu này đã được loại trước đó.", "This feedback was already excluded."))
    row.excluded_at = datetime.now(timezone.utc)
    row.excluded_by = admin.id
    row.exclude_reason = body.reason.strip()
    db.commit()
    from app.safelog import log
    log(f"[TerraTwin] admin #{admin.id} loai phieu gop y #{fid} khoi so lieu")
    return {"ok": True, "excluded": fid, "reason": row.exclude_reason}


@router.get("/api/admin/pilot/feedback.csv")
def feedback_csv(_: User = Depends(auth.require_admin),
                 db: Session = Depends(get_session)) -> Response:
    rows = db.execute(select(PilotFeedback).order_by(PilotFeedback.id)).scalars().all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "created_at", "source", "role", "region", "ease", "trust", "minutes",
                "would_use", "hardest", "comment", "contact", "excluded_at", "exclude_reason"])

    def safe(v):
        # Chặn chèn công thức khi mở bằng Excel (=, +, -, @ ở đầu ô).
        s = "" if v is None else str(v)
        return "'" + s if s[:1] in ("=", "+", "-", "@") else s
    for r in rows:
        w.writerow([r.id, r.created_at.isoformat() if r.created_at else "", r.source, r.role,
                    safe(r.region), r.ease, r.trust, "" if r.minutes is None else r.minutes,
                    r.would_use, r.hardest, safe(r.comment), safe(r.contact),
                    r.excluded_at.isoformat() if r.excluded_at else "", safe(r.exclude_reason or "")])
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="gop-y-thi-diem.csv"'})
