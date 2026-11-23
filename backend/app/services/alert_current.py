"""Cảnh báo CÒN HIỆU LỰC của thửa — quét toàn bộ 23/11/2026, P1.

Danh sách thửa từng lấy MỌI cảnh báo chưa đọc (/api/alerts limit 50) làm "7 ngày tới": Trà Leng "có mối NGUY HIỂM —
thượng nguồn 225.3 mm" là bản ghi 11/11 trong khi lượt chấm 21/11 chỉ còn CẢNH BÁO; Lai Châu "Quan sát:" lặp 5 lần; tài
khoản 10 thửa chạm đúng trần 50 bản ghi chưa đọc.

Quy tắc (không xoá lịch sử — bản ghi cũ vẫn còn, chỉ được đánh dấu hết hiệu lực):
  · mỗi (thửa, mô-đun) chỉ xét bản ghi MỚI NHẤT;
  · thửa đã có lượt rà soát SAU (hoặc cùng lúc) bản ghi đó → còn hiệu lực khi lượt ấy vẫn báo mô-đun này; mức + tiêu đề
    lấy theo LƯỢT ẤY (lượt rà soát chống báo trùng 72 giờ nên mức hạ xuống không sinh bản ghi mới — chỉ trạng thái lượt
    rà soát biết mức hiện tại). Lượt rà soát quá STALE_HOURS thì coi như không còn biết → hết hiệu lực;
  · chưa có lượt rà soát nào sau bản ghi → còn hiệu lực trong STALE_HOURS kể từ lúc ghi.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

STALE_HOURS = 48
_SAME_SWEEP = timedelta(minutes=5)      # bản ghi tạo trong cùng lượt rà soát ghi trạng thái


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def sweep_state(p) -> dict | None:
    """{at: datetime, modules: {module_id: {level, headline}}} của lượt rà soát gần nhất (None = chưa có)."""
    raw = getattr(p, "alert_state", "") or ""
    if not raw:
        return None
    try:
        st = json.loads(raw)
        return {"at": datetime.fromisoformat(st["at"]), "modules": st.get("modules") or {}}
    except (ValueError, KeyError, TypeError):
        return None


def record_sweep(p, alerts, when: datetime | None = None) -> None:
    """Ghi trạng thái lượt rà soát lên thửa — gọi TRƯỚC khi tạo bản ghi cảnh báo của lượt đó."""
    p.alert_state = json.dumps({
        "at": (when or _now()).isoformat(),
        "modules": {m.id: {"level": m.risk_level, "headline": f"{p.name}: {m.headline}"} for m in alerts},
    }, ensure_ascii=False)


def evaluate(a, p, now: datetime | None = None) -> dict | None:
    """{level, headline} nếu bản ghi `a` (đã là bản mới nhất của cặp thửa–mô-đun) còn hiệu lực, None nếu hết."""
    now = now or _now()
    st = sweep_state(p) if p is not None else None
    if st and st["at"] >= a.created_at - _SAME_SWEEP:
        if now - st["at"] > timedelta(hours=STALE_HOURS):
            return None
        cur = st["modules"].get(a.module_id)
        return {"level": cur["level"], "headline": cur["headline"]} if cur else None
    if now - a.created_at > timedelta(hours=STALE_HOURS):
        return None
    return {"level": a.risk_level, "headline": a.headline}


def current_map(db: Session, user_id: int, now: datetime | None = None) -> dict[int, dict]:
    """alert_id → {level, headline} cho MỌI bản ghi còn hiệu lực của người dùng (mỗi cặp thửa–mô-đun tối đa một)."""
    from app.db import Alert, Plot
    plots = {p.id: p for p in db.execute(select(Plot).where(Plot.user_id == user_id)).scalars().all()}
    rows = db.execute(select(Alert).where(Alert.user_id == user_id, Alert.retro == 0)
                      .order_by(Alert.created_at.desc(), Alert.id.desc())).scalars().all()
    seen: set = set()
    out: dict[int, dict] = {}
    for a in rows:
        k = (a.plot_id, a.module_id)
        if k in seen:
            continue
        seen.add(k)
        info = evaluate(a, plots.get(a.plot_id), now)
        if info:
            out[a.id] = info
    return out
