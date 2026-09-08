"""Tài khoản, danh mục thửa đất, và khóa Twin API.

Thay hoàn toàn localStorage: thửa đất nay lưu trong database nên đồng bộ đa
thiết bị và bán được cho doanh nghiệp (nhiều người dùng, phân quyền theo user).
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import auth
from app.services import plans
from app.db import (
    ActionLog, Alert, ApiKey, Dataset, KnowledgeNote, NotifyChannel,
    Observation, Plot, Twin, User, get_session,
)
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
    plan: str = "free"


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
                      plan=getattr(k, "plan", None) or plans.DEFAULT_PLAN,
                      monthly_quota=plans.quota_for(getattr(k, "plan", None)))
            for k in rows]


@router.post("/api/keys", response_model=ApiKeyCreated, status_code=201)
def create_key(label: str = "", plan: str = plans.DEFAULT_PLAN,
               user: User = Depends(auth.current_user),
               db: Session = Depends(get_session)) -> ApiKeyCreated:
    if plan not in plans.PLANS:
        raise HTTPException(
            status_code=400,
            detail=f"Gói không hợp lệ. Chọn một trong: {', '.join(plans.PLANS)}")
    raw, digest, prefix = auth.generate_api_key()
    k = ApiKey(user_id=user.id, label=label[:120], key_hash=digest,
               prefix=prefix, plan=plan)
    db.add(k)
    db.commit()
    db.refresh(k)
    return ApiKeyCreated(id=k.id, label=k.label, prefix=k.prefix,
                         created_at=k.created_at, last_used_at=None,
                         revoked=False, plan=plan,
                         monthly_quota=plans.quota_for(plan), key=raw)


@router.get("/api/plans")
def plan_catalogue() -> dict:
    """Bảng giá đề xuất. Luôn kèm ghi chú là CHƯA có ai trả tiền."""
    return plans.catalogue()


@router.get("/api/usage")
def usage(user: User = Depends(auth.current_user),
          db: Session = Depends(get_session)) -> dict:
    """Bảng kê sử dụng từng khoá — đủ chi tiết để xuất hoá đơn khi có cổng thu.

    Hiện đúng số đã dùng và phần VƯỢT nếu có, không giấu sau chữ "gần hết".
    """
    rows = db.execute(
        select(ApiKey).where(ApiKey.user_id == user.id, ApiKey.revoked == 0)
    ).scalars().all()
    kê = [plans.statement(k) for k in rows]
    return {
        "keys": kê,
        "total_calls_this_period": sum(k["used"] for k in kê),
        "billing_status": "chưa thu tiền — chưa có cổng thanh toán",
        "next_step": ("Thu tiền cần giấy phép kinh doanh và hợp đồng thương "
                      "nhân với VNPay/MoMo. Đó là bước pháp lý, không phải "
                      "bước lập trình."),
    }


@router.delete("/api/keys/{key_id}", status_code=204,
               response_class=Response, response_model=None)
def revoke_key(key_id: int, user: User = Depends(auth.current_user),
               db: Session = Depends(get_session)):
    k = db.get(ApiKey, key_id)
    if k is None or k.user_id != user.id:
        raise HTTPException(404, "Không tìm thấy khóa.")
    k.revoked = 1
    db.commit()


# ---------------------------------------------------------------------------
# QUYỀN RIÊNG TƯ — xuất toàn bộ dữ liệu & xoá tài khoản (khớp chính sách công bố)
# ---------------------------------------------------------------------------

# Các bảng thuộc về người dùng. Giữ ở một chỗ để export và delete KHÔNG bao giờ
# lệch nhau: quên một bảng ở delete là để lại dữ liệu cá nhân sau khi "đã xoá".
_OWNED = [
    ("plots", Plot), ("twins", Twin), ("channels", NotifyChannel),
    ("observations", Observation), ("actions", ActionLog),
    ("knowledge_notes", KnowledgeNote), ("api_keys", ApiKey),
    ("datasets", Dataset), ("alerts", Alert),
]


def _row_to_dict(row) -> dict:
    out = {}
    for c in row.__table__.columns:
        v = getattr(row, c.name)
        if isinstance(v, datetime):
            v = v.isoformat()
        # Không bao giờ xuất bí mật ra ngoài, kể cả cho chính chủ: hash mật khẩu
        # và hash khoá API là thứ không được rời database.
        if c.name in ("password_hash", "key_hash", "prefix_hash"):
            continue
        out[c.name] = v
    return out


@router.get("/api/account/export")
def export_my_data(user: User = Depends(auth.current_user),
                   db: Session = Depends(get_session)) -> dict:
    """Xuất TOÀN BỘ dữ liệu của tài khoản dưới dạng JSON — quyền của người dùng.

    Không kèm hash mật khẩu/khoá (bí mật không rời database). Đây là bản sao đầy
    đủ để người dùng tự giữ hoặc chuyển đi.
    """
    data: dict = {
        "account": {"id": user.id, "email": user.email, "name": user.name,
                    "created_at": user.created_at.isoformat() if user.created_at else None},
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    for label, model in _OWNED:
        rows = db.execute(
            select(model).where(model.user_id == user.id)).scalars().all()
        data[label] = [_row_to_dict(r) for r in rows]
    return data


@router.delete("/api/account", status_code=204, response_class=Response,
               response_model=None)
def delete_my_account(user: User = Depends(auth.current_user),
                      db: Session = Depends(get_session)):
    """Xoá vĩnh viễn tài khoản và MỌI dữ liệu thuộc về nó.

    Xoá tường minh từng bảng thay vì dựa vào cascade của cơ sở dữ liệu: SQLite
    mặc định KHÔNG bật khoá ngoại, nên 'ON DELETE CASCADE' có thể im lặng không
    chạy và để lại dữ liệu mồ côi sau khi người dùng tưởng đã xoá sạch.
    """
    for _, model in _OWNED:
        for r in db.execute(
                select(model).where(model.user_id == user.id)).scalars().all():
            db.delete(r)
    db.delete(user)
    db.commit()


# ---------------------------------------------------------------------------
# N1 — QUÊN / ĐẶT LẠI / ĐỔI MẬT KHẨU
# ---------------------------------------------------------------------------
#
# Trước đây chỉ có register/login/me: quên mật khẩu là mất VĨNH VIỄN mọi thửa,
# cảnh báo, quan sát — và người vận hành cũng không giúp được. Chuyện này xảy ra
# với người dùng thứ mười, không phải thứ nghìn.
#
# Token đặt lại dùng lại đúng cơ chế JWT ký số của onetap: chứa id người dùng,
# loại "reset", hết hạn 1 giờ. KHÔNG phải phiên đăng nhập — chỉ đổi được đúng
# mật khẩu của đúng tài khoản đó.

import jwt as _jwt                                            # noqa: E402
from app.auth import _ALGO as _AUTH_ALGO, _SECRET as _AUTH_SECRET   # noqa: E402

_RESET_TTL_MIN = 60


def _make_reset_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    return _jwt.encode(
        {"u": int(user_id), "k": "reset", "iat": now,
         "exp": now + timedelta(minutes=_RESET_TTL_MIN)},
        _AUTH_SECRET, algorithm=_AUTH_ALGO)


def _read_reset_token(token: str) -> int | None:
    try:
        d = _jwt.decode(token, _AUTH_SECRET, algorithms=[_AUTH_ALGO])
    except _jwt.PyJWTError:
        return None
    if d.get("k") != "reset":
        return None
    try:
        return int(d["u"])
    except (KeyError, TypeError, ValueError):
        return None


class ForgotIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str
    password: str = Field(min_length=_MIN_PW, max_length=256)


class ChangePwIn(BaseModel):
    old_password: str = Field(max_length=256)
    new_password: str = Field(min_length=_MIN_PW, max_length=256)


@router.post("/api/auth/forgot")
def forgot_password(body: ForgotIn, db: Session = Depends(get_session)) -> dict:
    """Gửi liên kết đặt lại mật khẩu. LUÔN trả 200 dù email không tồn tại —
    trả 404 là để lộ email nào đã đăng ký."""
    email = body.email.strip().lower()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    out: dict = {"message": ("Nếu email có trong hệ thống, chúng tôi đã gửi liên "
                             "kết đặt lại (hết hạn sau 1 giờ).")}
    if user is not None:
        from app.services import notify, onetap
        token = _make_reset_token(user.id)
        link = f"{onetap.base_url()}/reset/{token}"
        if notify.smtp_configured():
            notify.send_email(
                email, "TerraTwin — đặt lại mật khẩu",
                f"Bấm vào liên kết để đặt lại mật khẩu (hết hạn sau 1 giờ):\n\n{link}\n\n"
                f"Nếu không phải bạn yêu cầu, bỏ qua email này.")
        elif os.environ.get("TERRATWIN_ENV", "prod").strip().lower() == "dev":
            # Chưa cấu hình SMTP + đang chạy dev → trả link ra để thử được ngay.
            out["dev_link"] = link
    return out


@router.post("/api/auth/reset")
def reset_password(body: ResetIn, db: Session = Depends(get_session)) -> dict:
    _check_password_strength(body.password)
    uid = _read_reset_token(body.token)
    if uid is None:
        raise HTTPException(400, "Liên kết đặt lại không hợp lệ hoặc đã hết hạn (1 giờ).")
    user = db.get(User, uid)
    if user is None:
        raise HTTPException(400, "Tài khoản không còn tồn tại.")
    user.password_hash = auth.hash_password(body.password)
    db.commit()
    return {"message": "Đã đặt lại mật khẩu. Hãy đăng nhập lại."}


@router.post("/api/auth/change-password")
def change_password(body: ChangePwIn, user: User = Depends(auth.current_user),
                    db: Session = Depends(get_session)) -> dict:
    if not auth.verify_password(body.old_password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Mật khẩu cũ không đúng.")
    _check_password_strength(body.new_password)
    user.password_hash = auth.hash_password(body.new_password)
    db.commit()
    return {"message": "Đã đổi mật khẩu."}
