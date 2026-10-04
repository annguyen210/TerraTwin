"""GIÁM SÁT SAU PHÁT HÀNH — hồ sơ vườn không phải ảnh chụp một lần rồi thôi.

EUDR đòi thẩm định cho TỪNG lô hàng, nên một hồ sơ "đạt" từ năm ngoái không nói được
vườn năm nay còn nguyên. Tác vụ này sàng lọc lại các hồ sơ vườn đã phát hành bằng dữ
liệu mới nhất (cùng quy tắc, cùng nguồn), và ghi KẾT QUẢ SỐNG vào bảng dossier_monitors
— hồ sơ đã ký thì bất biến, không sửa. Trang kiểm /h hiện kèm, ghi rõ là kết quả sống.
Mức xấu đi (đạt → cần xem lại / rủi ro) hoặc xuất hiện dấu hiệu mất cây mới thì đánh
dấu `changed` — lô hàng chứa vườn đó bị chặn cho tới khi sàng lọc lại (services/lots.py).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import Dossier, DossierMonitor
from app.services import eudr_forest

RANK = {"low": 0, "review": 1, "high": 2}


def _plot_from_facts(f: dict) -> dict:
    p = f["plot"]
    return {"kind": p.get("kind"), "geometry": p.get("geometry"), "area_ha": p.get("area_ha"),
            "centroid": p.get("centroid"), "valid": True, "ref": p.get("ref")}


def compare(issued: dict, now: dict) -> tuple[bool, list[str]]:
    """Có xấu đi so với lúc phát hành không? (mức, hoặc dấu hiệu mất cây MỚI)."""
    why = []
    a, b = RANK.get(issued.get("level")), RANK.get(now.get("level"))
    if a is not None and b is not None and b > a:
        why.append(f"{issued.get('level')}→{now.get('level')}")
    was = bool((issued.get("signals") or {}).get("loss"))
    is_ = bool((now.get("signals") or {}).get("loss"))
    if is_ and not was:
        why.append("new_tree_loss")
    return bool(why), why


def run(db: Session, limit: int = 20, recheck_days: int = 30, screen=None, radar=None) -> dict:
    """Sàng lọc lại tối đa `limit` hồ sơ vườn lâu chưa kiểm nhất."""
    screen = screen or eudr_forest.screen
    if radar is None:
        from app.services import radar_s1
        radar = radar_s1.change
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=recheck_days)
    last = (select(DossierMonitor.dossier_id, func.max(DossierMonitor.checked_at).label("last"))
            .group_by(DossierMonitor.dossier_id).subquery())
    rows = db.execute(select(Dossier, last.c.last).outerjoin(last, last.c.dossier_id == Dossier.id)
                      .where(Dossier.facts_json.like('%"kind":"eudr_plot"%'))
                      .where((last.c.last.is_(None)) | (last.c.last < cutoff))
                      .order_by(last.c.last.is_not(None), last.c.last, Dossier.seq).limit(limit)).all()
    done, changed = 0, 0
    for row, _ in rows:
        f = json.loads(row.facts_json)
        issued = f.get("screening") or {}
        try:
            now = screen(_plot_from_facts(f))
        except Exception:
            continue
        ch, why = compare(issued, now)
        # Radar Sentinel-1 xuyên mây: thấy được mất tán cây CẢ mùa mưa, khi ảnh quang học mù.
        try:
            rd = radar(_plot_from_facts(f))
        except Exception:
            rd = None
        if rd and rd.get("signal") == "strong":
            ch, why = True, why + ["radar_drop"]
        was_changed = bool(db.scalar(select(DossierMonitor.changed)
                                     .where(DossierMonitor.dossier_id == row.id)
                                     .order_by(DossierMonitor.checked_at.desc()).limit(1)))
        db.add(DossierMonitor(dossier_id=row.id, level=now.get("level") or "unknown",
                              issued_level=issued.get("level") or "unknown", changed=int(ch),
                              summary_json=json.dumps({"why": why, "reasons": now.get("reasons"),
                                                       "signals": now.get("signals"),
                                                       "s2_after": ((now.get("s2") or {}).get("after") or {}).get("date"),
                                                       "radar": rd},
                                                      ensure_ascii=False)))
        db.commit()
        if ch and not was_changed:          # chỉ lần ĐẦU chuyển sang "thay đổi" — không báo lặp mỗi tuần
            _notify_change(db, row, f, why)
        done += 1
        changed += int(ch)
    return {"checked": done, "changed": changed, "candidates": len(rows)}


def _notify_change(db: Session, row: Dossier, facts: dict, why: list[str]) -> int:
    """Báo ĐẨY tới chủ hồ sơ và mọi doanh nghiệp có lô hàng chứa vườn này. Best-effort:
    chưa cấu hình VAPID / chưa đăng ký thiết bị thì thôi, không làm hỏng lượt giám sát."""
    from app.db import Lot
    from app.services import push
    ref = (facts.get("plot") or {}).get("ref") or row.id
    radar = "radar_drop" in why
    title = f"Vườn “{ref}” thay đổi sau khi phát hành"
    body = ("Radar xuyên mây thấy tán cây giảm mạnh. " if radar else "Sàng lọc lại cho kết quả xấu hơn lúc phát hành. ") +         "Lô hàng chứa vườn này tạm bị chặn — mở để xem ảnh trước/sau."
    users = {row.user_id} if row.user_id else set()
    for lot in db.execute(select(Lot)).scalars().all():
        if any(d.get("dossier_id") == row.id for d in json.loads(lot.deliveries_json or "[]")):
            users.add(lot.user_id)
    sent = 0
    for uid in users:
        try:
            sent += push.send_to_user(db, uid, title, body, url=f"/h/{row.id}")
        except Exception:
            continue
    return sent
