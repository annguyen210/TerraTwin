"""M1 — WEB PUSH: gửi cảnh báo tới trình duyệt/PWA kể cả khi app đã đóng.

Đây là kênh cảnh báo DUY NHẤT sống được ngay lúc này: Zalo chờ duyệt, Telegram
cần cài app, còn Web Push chạy thẳng trên PWA đã có — không xin phép nhà cung cấp
nào. VAPID là cặp khoá ECDSA P-256 TỰ SINH (một lệnh), không ai cấp.

Cấu hình bằng biến môi trường (không hardcode khoá riêng vào mã):
  TERRATWIN_VAPID_PUBLIC_KEY   — khoá công khai (cũng đưa ra frontend)
  TERRATWIN_VAPID_PRIVATE_KEY  — khoá riêng, CHỈ ở máy chủ
  TERRATWIN_VAPID_SUBJECT      — mailto: hoặc URL liên hệ (mặc định mailto).
Thiếu khoá → push coi như CHƯA cấu hình: không gửi, không lỗi; frontend ẩn nút.
"""
from __future__ import annotations

import json
import os

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import PushSub
from app.safelog import log


def public_key() -> str | None:
    return os.environ.get("TERRATWIN_VAPID_PUBLIC_KEY") or None


def _private_key() -> str | None:
    return os.environ.get("TERRATWIN_VAPID_PRIVATE_KEY") or None


def _subject() -> str:
    return os.environ.get("TERRATWIN_VAPID_SUBJECT", "mailto:alerts@terratwin.app")


def configured() -> bool:
    return bool(public_key() and _private_key())


def save_subscription(db: Session, user_id: int, sub: dict) -> bool:
    """Lưu (hoặc cập nhật) một đăng ký. Trả True nếu hợp lệ."""
    endpoint = (sub or {}).get("endpoint")
    keys = (sub or {}).get("keys") or {}
    p256dh, auth = keys.get("p256dh"), keys.get("auth")
    if not (endpoint and p256dh and auth):
        return False
    row = db.execute(
        select(PushSub).where(PushSub.endpoint == endpoint)).scalar_one_or_none()
    if row is None:
        db.add(PushSub(user_id=user_id, endpoint=endpoint, p256dh=p256dh, auth=auth))
    else:
        row.user_id, row.p256dh, row.auth = user_id, p256dh, auth
    db.commit()
    return True


def _send_one(sub: PushSub, payload: dict) -> bool:
    """Gửi một push. Trả False nếu endpoint chết (để gọi ngoài xoá)."""
    from pywebpush import WebPushException, webpush
    try:
        webpush(
            subscription_info={
                "endpoint": sub.endpoint,
                "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
            },
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=_private_key(),
            vapid_claims={"sub": _subject()},
            timeout=10,
        )
        return True
    except WebPushException as e:
        code = getattr(getattr(e, "response", None), "status_code", None)
        if code in (404, 410):
            return False      # endpoint chết → báo xoá
        log(f"[push] gửi lỗi ({code}): {type(e).__name__}")
        return True           # lỗi tạm — giữ đăng ký, thử lần sau
    except Exception as e:    # noqa: BLE001 — push hỏng không kéo sập việc gọi
        log(f"[push] lỗi: {type(e).__name__}")
        return True


def send_to_user(db: Session, user_id: int, title: str, body: str,
                 url: str = "/") -> int:
    """Gửi tới mọi thiết bị của một người. Trả số thiết bị gửi được. Best-effort:
    chưa cấu hình VAPID hoặc không có đăng ký thì trả 0, không ném lỗi."""
    if not configured():
        return 0
    subs = db.execute(
        select(PushSub).where(PushSub.user_id == user_id)).scalars().all()
    sent, dead = 0, []
    payload = {"title": title, "body": body, "url": url}
    for s in subs:
        if _send_one(s, payload):
            sent += 1
        else:
            dead.append(s.endpoint)
    if dead:
        db.execute(delete(PushSub).where(PushSub.endpoint.in_(dead)))
        db.commit()
    return sent
