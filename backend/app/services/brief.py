"""M4 — BẢN TIN SÁNG. Tin GỬI ĐI mỗi sáng, KỂ CẢ khi an toàn.

Khác thẻ tóm tắt trong app (chỉ thấy khi người ta tự mở): đây là tin CHỦ ĐỘNG
đẩy tới, để TerraTwin thành thói quen buổi sáng — "mở ra xem đất hôm nay thế
nào". Gửi cả khi an toàn có chủ đích: một sản phẩm chỉ lên tiếng khi có hoạ thì
người ta quên mất nó tồn tại, và cũng không tin nó đang thật sự canh.

Mặc định TẮT (người dùng tự bật, không spam). Gửi qua Web Push (M1). Dedup theo
NGÀY: mỗi tài khoản một tin mỗi sáng, dù cron gọi mấy lần.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Alert, Plot, User


def compose(db: Session, user: User) -> tuple[str, str] | None:
    """Soạn (tiêu đề, thân) bản tin sáng cho một người. None nếu không có thửa."""
    n_plots = db.execute(
        select(Plot.id).where(Plot.user_id == user.id)).scalars().all()
    if not n_plots:
        return None
    unread = db.execute(
        select(Alert.id).where(Alert.user_id == user.id, Alert.retro == 0,
                               Alert.acknowledged == 0)).scalars().all()
    ngay = datetime.now(timezone.utc).strftime("%d/%m")
    title = f"☀️ TerraTwin — bản tin sáng {ngay}"
    if unread:
        body = (f"Đang canh {len(n_plots)} thửa. "
                f"⚠️ {len(unread)} cảnh báo cần xem hôm nay.")
    else:
        body = (f"Đang canh {len(n_plots)} thửa. "
                f"Tất cả đang an toàn — không có gì bất thường sáng nay.")
    return title, body


def run_all(db: Session, force: bool = False) -> dict:
    """Gửi bản tin sáng cho mọi người đã BẬT + có thửa + có đăng ký push. Dedup
    theo ngày (brief_last). force=True bỏ qua dedup (dùng khi test/gửi thử)."""
    from app.services import push

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    users = db.execute(
        select(User).where(User.morning_brief == 1)).scalars().all()
    sent = skipped = 0
    for u in users:
        if not force and u.brief_last == today:
            skipped += 1
            continue
        composed = compose(db, u)
        if composed is None:
            continue
        title, body = composed
        n = push.send_to_user(db, u.id, title, body, "/")
        if n > 0 or force:
            u.brief_last = today
            sent += 1
    db.commit()
    return {"sent": sent, "skipped_already_sent": skipped,
            "opted_in": len(users), "date": today}
