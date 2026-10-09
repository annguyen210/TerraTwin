"""GĐ6 — nhật ký thửa ("từ lần mở trước có gì đổi") và so sánh 2–4 thửa.

Xem services/plot_journal.py và services/plot_compare.py.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app import auth
from app.db import Plot, User, get_session
from app.services import plot_compare, plot_journal, reqlang

router = APIRouter(tags=["journal"])


def _own(db: Session, user: User, plot_id: int) -> Plot:
    p = db.get(Plot, plot_id)
    if p is None or p.user_id != user.id:
        raise HTTPException(404, reqlang.tr("Không tìm thấy thửa này.", "Plot not found."))
    return p


@router.get("/api/plots/{plot_id}/journal")
def get_journal(plot_id: int, fast: bool = False, since: str | None = None, lang: str = "vi",
                user: User = Depends(auth.current_user), db: Session = Depends(get_session)) -> dict:
    """Nhật ký thửa từ lần mở trước. `fast=1`: chỉ sự kiện trong CSDL (cảm biến, câu trả lời, ảnh, cảnh
    báo) — giao diện gọi mỗi vài giây để số đo cảm biến hiện lên trong 10 giây."""
    reqlang.set_lang(lang)
    p = _own(db, user, plot_id)
    when = None
    if since:
        try:
            when = datetime.fromisoformat(since.rstrip("Z"))
        except ValueError:
            raise HTTPException(422, reqlang.tr("Thời điểm không hợp lệ.", "Invalid timestamp."))
    return plot_journal.journal(db, user.id, p, since=when, fast=fast)


@router.post("/api/plots/{plot_id}/journal/seen")
def journal_seen(plot_id: int, user: User = Depends(auth.current_user), db: Session = Depends(get_session)) -> dict:
    """Đánh dấu đã xem — lần mở sau nhật ký chỉ kể từ thời điểm này."""
    p = _own(db, user, plot_id)
    return {"seen_at": plot_journal.mark_seen(user.id, p.id)}


class Pt(BaseModel):
    lat: float = Field(ge=8.0, le=24.0)
    lon: float = Field(ge=102.0, le=110.5)
    name: str = Field(default="", max_length=80)


class CompareIn(BaseModel):
    points: list[Pt] = Field(min_length=2, max_length=4)

    @field_validator("points")
    @classmethod
    def _distinct(cls, v: list[Pt]) -> list[Pt]:
        if len({(round(p.lat, 5), round(p.lon, 5)) for p in v}) != len(v):
            raise ValueError("các thửa phải khác nhau")
        return v


@router.post("/api/compare")
def compare(body: CompareIn, request: Request, lang: str = "vi",
            user: User | None = Depends(auth.optional_user)) -> dict:
    """So sánh 2–4 thửa — không cần đăng nhập (người mua đang cân hai tin đăng); tính như thao tác nặng."""
    reqlang.set_lang(lang)
    from app.routes_eudr import enforce_quota
    enforce_quota("screen", request, user)
    return plot_compare.compare([p.model_dump() for p in body.points])
