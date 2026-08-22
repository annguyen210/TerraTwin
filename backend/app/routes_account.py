"""Tài khoản, danh mục thửa đất, và khóa Twin API.

Thay hoàn toàn localStorage: thửa đất nay lưu trong database nên đồng bộ đa
thiết bị và bán được cho doanh nghiệp (nhiều người dùng, phân quyền theo user).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import auth
from app.db import ApiKey, Plot, User, get_session
from app.schemas import Location

router = APIRouter(tags=["account"])

_MIN_PW = 8


# ---------- Kiểu dữ liệu ----------

class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=_MIN_PW, max_length=256)
    name: str = Field(default="", max_length=120)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=256)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class UserOut(BaseModel):
    id: int
    email: str
    name: str


class PlotIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    location: Location
    score: int | None = Field(default=None, ge=0, le=100)
    grade: str | None = Field(default=None, max_length=4)


class PlotOut(BaseModel):
    id: int
    name: str
    lat: float
    lon: float
    area_ha: float | None
    score: int | None
    grade: str | None
    created_at: datetime


class ApiKeyOut(BaseModel):
    id: int
    label: str
    prefix: str
    created_at: datetime
    last_used_at: datetime | None
    revoked: bool
    calls_total: int = 0
    calls_period: int = 0
    period: str = ""
    monthly_quota: int = 0


class ApiKeyCreated(ApiKeyOut):
    key: str      # bản rõ — chỉ trả về DUY NHẤT một lần


TokenOut.model_rebuild()


def _out(u: User) -> UserOut:
    return UserOut(id=u.id, email=u.email, name=u.name)


def _plot_out(p: Plot) -> PlotOut:
    return PlotOut(id=p.id, name=p.name, lat=p.lat, lon=p.lon, area_ha=p.area_ha,
                   score=p.score, grade=p.grade, created_at=p.created_at)


def _check_password_strength(pw: str) -> None:
    if len(pw) < _MIN_PW:
        raise HTTPException(422, f"Mật khẩu cần tối thiểu {_MIN_PW} ký tự.")
    if not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
        raise HTTPException(422, "Mật khẩu cần có cả chữ và số.")


# ---------- Tài khoản ----------

@router.post("/api/auth/register", response_model=TokenOut, status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_session)) -> TokenOut:
    _check_password_strength(body.password)
    email = body.email.strip().lower()
    user = User(email=email, password_hash=auth.hash_password(body.password),
                name=body.name.strip())
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Email này đã được đăng ký.")
    db.refresh(user)
    return TokenOut(access_token=auth.create_token(user.id), user=_out(user))


@router.post("/api/auth/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_session)) -> TokenOut:
    email = body.email.strip().lower()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    # Cùng một thông báo cho email sai và mật khẩu sai — không tiết lộ email nào tồn tại.
    if user is None or not auth.verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email hoặc mật khẩu không đúng.")
    return TokenOut(access_token=auth.create_token(user.id), user=_out(user))


@router.get("/api/auth/me", response_model=UserOut)
def me(user: User = Depends(auth.current_user)) -> UserOut:
    return _out(user)


# ---------- Danh mục thửa đất (thay localStorage) ----------

@router.get("/api/plots", response_model=list[PlotOut])
def list_plots(user: User = Depends(auth.current_user),
               db: Session = Depends(get_session)) -> list[PlotOut]:
    rows = db.execute(
        select(Plot).where(Plot.user_id == user.id)
        .order_by(Plot.score.desc().nullslast(), Plot.created_at.desc())
    ).scalars().all()
    return [_plot_out(p) for p in rows]


@router.get("/api/plots/overview")
def plots_overview(heavy: bool = False,
                   user: User = Depends(auth.current_user),
                   db: Session = Depends(get_session)) -> dict:
    """C08 — nhìn cả danh mục như một VÙNG, không phải một danh sách.

    Hợp tác xã 200 thửa không hỏi "thửa số 137 thế nào" mà hỏi "chỗ nào của tôi
    sắp gãy". Gộp theo ô ~11 km và xếp vùng nặng nhất lên đầu.
    """
    from app.services import portfolio

    rows = db.execute(
        select(Plot).where(Plot.user_id == user.id)
        .order_by(Plot.created_at.desc())).scalars().all()
    return portfolio.overview(rows, include_heavy=heavy)


@router.post("/api/plots", response_model=PlotOut, status_code=201)
def create_plot(body: PlotIn, user: User = Depends(auth.current_user),
                db: Session = Depends(get_session)) -> PlotOut:
    loc = body.location
    existing = db.execute(
        select(Plot).where(Plot.user_id == user.id,
                           Plot.lat == loc.lat, Plot.lon == loc.lon)
    ).scalar_one_or_none()
    if existing:                       # lưu lại cùng toạ độ = cập nhật
        existing.name = body.name
        existing.area_ha = loc.area_ha
        existing.score = body.score
        existing.grade = body.grade
        db.commit()
        return _plot_out(existing)

    p = Plot(user_id=user.id, name=body.name, lat=loc.lat, lon=loc.lon,
             area_ha=loc.area_ha, score=body.score, grade=body.grade)
    db.add(p)
    db.commit()
    db.refresh(p)
    return _plot_out(p)


@router.delete("/api/plots/{plot_id}", status_code=204,
               response_class=Response, response_model=None)
def delete_plot(plot_id: int, user: User = Depends(auth.current_user),
                db: Session = Depends(get_session)):
    p = db.get(Plot, plot_id)
    # Không phân biệt "không tồn tại" với "của người khác" — tránh dò ID.
    if p is None or p.user_id != user.id:
        raise HTTPException(404, "Không tìm thấy thửa đất.")
    db.delete(p)
    db.commit()


# ---------- Khóa Twin API (C12) ----------

@router.get("/api/keys", response_model=list[ApiKeyOut])
def list_keys(user: User = Depends(auth.current_user),
              db: Session = Depends(get_session)) -> list[ApiKeyOut]:
    rows = db.execute(
        select(ApiKey).where(ApiKey.user_id == user.id).order_by(ApiKey.created_at.desc())
    ).scalars().all()
    return [ApiKeyOut(id=k.id, label=k.label, prefix=k.prefix,
                      created_at=k.created_at, last_used_at=k.last_used_at,
                      revoked=bool(k.revoked),
                      calls_total=k.calls_total or 0,
                      calls_period=k.calls_period or 0,
                      period=k.period or "",
                      monthly_quota=auth.KEY_MONTHLY_QUOTA) for k in rows]


@router.post("/api/keys", response_model=ApiKeyCreated, status_code=201)
def create_key(label: str = "", user: User = Depends(auth.current_user),
               db: Session = Depends(get_session)) -> ApiKeyCreated:
    raw, digest, prefix = auth.generate_api_key()
    k = ApiKey(user_id=user.id, label=label[:120], key_hash=digest, prefix=prefix)
    db.add(k)
    db.commit()
    db.refresh(k)
    return ApiKeyCreated(id=k.id, label=k.label, prefix=k.prefix,
                         created_at=k.created_at, last_used_at=None,
                         revoked=False, monthly_quota=auth.KEY_MONTHLY_QUOTA,
                         key=raw)


@router.delete("/api/keys/{key_id}", status_code=204,
               response_class=Response, response_model=None)
def revoke_key(key_id: int, user: User = Depends(auth.current_user),
               db: Session = Depends(get_session)):
    k = db.get(ApiKey, key_id)
    if k is None or k.user_id != user.id:
        raise HTTPException(404, "Không tìm thấy khóa.")
    k.revoked = 1
    db.commit()
