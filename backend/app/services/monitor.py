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


def run(db: Session, limit: int = 20, recheck_days: int = 30, screen=None) -> dict:
    """Sàng lọc lại tối đa `limit` hồ sơ vườn lâu chưa kiểm nhất."""
    screen = screen or eudr_forest.screen
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
        db.add(DossierMonitor(dossier_id=row.id, level=now.get("level") or "unknown",
                              issued_level=issued.get("level") or "unknown", changed=int(ch),
                              summary_json=json.dumps({"why": why, "reasons": now.get("reasons"),
                                                       "signals": now.get("signals"),
                                                       "s2_after": ((now.get("s2") or {}).get("after") or {}).get("date")},
                                                      ensure_ascii=False)))
        db.commit()
        done += 1
        changed += int(ch)
    return {"checked": done, "changed": changed, "candidates": len(rows)}
