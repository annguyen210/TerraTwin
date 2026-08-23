"""Xác thực — băm mật khẩu bcrypt + JWT, và API key cho Twin API (C12).

Nguyên tắc bảo mật đã áp dụng:
  - Mật khẩu băm bcrypt (có salt), KHÔNG bao giờ lưu bản rõ.
  - API key chỉ lưu HASH; lộ database vẫn không dùng lại được khóa.
  - Đăng nhập sai không tiết lộ email có tồn tại hay không.
  - Secret lấy từ biến môi trường; nếu thiếu thì sinh ngẫu nhiên mỗi lần chạy
    (token cũ mất hiệu lực khi restart — an toàn hơn là hardcode secret).
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.services import plans
from app.db import ApiKey, User, get_session

_ALGO = "HS256"
_TOKEN_HOURS = int(os.environ.get("TERRATWIN_TOKEN_HOURS", "72"))

_SECRET = os.environ.get("TERRATWIN_SECRET") or secrets.token_urlsafe(48)
SECRET_FROM_ENV = bool(os.environ.get("TERRATWIN_SECRET"))

_BCRYPT_MAX = 72   # bcrypt bỏ qua byte thứ 73 trở đi — băm trước để không mất entropy


def _prehash(password: str) -> bytes:
    raw = password.encode("utf-8")
    if len(raw) > _BCRYPT_MAX:
        raw = hashlib.sha256(raw).hexdigest().encode("ascii")
    return raw


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prehash(password), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prehash(password), hashed.encode("ascii"))
    except (ValueError, TypeError):
        return False


def create_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": str(user_id), "iat": now, "exp": now + timedelta(hours=_TOKEN_HOURS)},
        _SECRET, algorithm=_ALGO,
    )


def decode_token(token: str) -> int | None:
    try:
        data = jwt.decode(token, _SECRET, algorithms=[_ALGO])
        return int(data["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


# ---------- API key (C12 Twin API) ----------

_KEY_PREFIX = "tt_"


def generate_api_key() -> tuple[str, str, str]:
    """Trả (khóa bản rõ, hash, prefix). Bản rõ chỉ hiện MỘT LẦN lúc tạo."""
    raw = _KEY_PREFIX + secrets.token_urlsafe(32)
    return raw, hash_api_key(raw), raw[:10]


def hash_api_key(raw: str) -> str:
    """SHA-256 là đủ và nhanh: khóa vốn đã có entropy cao, không như mật khẩu."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------- Dependency ----------

# Hạn mức lượt gọi mỗi tháng nay lấy theo GÓI của từng khóa —
# xem app/services/plans.py. Không giữ lại hằng số KEY_MONTHLY_QUOTA ở đây:
# một hằng số trông như còn điều khiển hạn mức nhưng thật ra không còn tác dụng
# là cái bẫy tệ hơn không có gì. Muốn ép một mức chung (thử nghiệm, tình huống
# khẩn) thì đặt biến môi trường TERRATWIN_KEY_MONTHLY_QUOTA — plans.quota_for()
# đọc nó và ghi đè mọi gói.

_UNAUTH = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Cần đăng nhập. Gửi header 'Authorization: Bearer <token>' "
           "hoặc 'X-API-Key: <khóa>'.",
)


def current_user(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
    db: Session = Depends(get_session),
) -> User:
    """Chấp nhận cả JWT (người dùng web) lẫn API key (tích hợp bên thứ ba)."""
    if x_api_key:
        digest = hash_api_key(x_api_key)
        row = db.execute(
            select(ApiKey).where(ApiKey.key_hash == digest, ApiKey.revoked == 0)
        ).scalar_one_or_none()
        if row is None:
            raise _UNAUTH
        now = datetime.now(timezone.utc)

        # Đếm lượt và chặn khi vượt hạn mức tháng.
        #
        # Đây là chống LẠM DỤNG, không phải tính tiền: một khóa bị lộ có thể nã
        # API không giới hạn và đốt sạch hạn mức ngày của Open-Meteo — lúc đó
        # MỌI người dùng mất dữ liệu chứ không riêng chủ khóa. Hạn mức riêng
        # từng khóa giữ cho thiệt hại nằm trong phạm vi một khóa.
        period = now.strftime("%Y-%m")
        if row.period != period:
            row.period, row.calls_period = period, 0
        row.calls_period = (row.calls_period or 0) + 1
        row.calls_total = (row.calls_total or 0) + 1
        row.last_used_at = now
        db.commit()

        limit = plans.quota_for(getattr(row, "plan", None))
        if limit > 0 and row.calls_period > limit:
            tier = plans.PLANS.get(getattr(row, "plan", None) or "free",
                                   plans.PLANS["free"])
            raise HTTPException(
                status_code=429,
                detail=(f"Khóa này đã dùng {row.calls_period} lượt trong tháng "
                        f"{period}, vượt hạn mức {limit} của gói "
                        f"{tier['name']}. Hạn mức đặt lại vào đầu tháng sau. "
                        "Xem GET /api/plans để biết các mức cao hơn."))

        user = db.get(User, row.user_id)
        if user is None:
            raise _UNAUTH
        return user

    if not authorization or not authorization.lower().startswith("bearer "):
        raise _UNAUTH
    uid = decode_token(authorization.split(" ", 1)[1].strip())
    if uid is None:
        raise _UNAUTH
    user = db.get(User, uid)
    if user is None:
        raise _UNAUTH
    return user


def optional_user(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
    db: Session = Depends(get_session),
) -> User | None:
    """Cho các endpoint chạy được cả khi chưa đăng nhập (demo công khai)."""
    try:
        return current_user(authorization, x_api_key, db)
    except HTTPException:
        return None


def constant_time_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)
