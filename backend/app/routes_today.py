"""BẢNG TIN "HÔM NAY" — lý do để mở TerraTwin mỗi ngày.

Không phải trang phân tích: là DANH SÁCH VIỆC của chính người dùng, xếp theo độ gấp —
đợt giao hàng chờ xác nhận, vườn bị giám sát đánh dấu (kể cả tín hiệu radar xuyên mây),
lô hàng bị chặn, vườn cần người xem, cảnh báo chưa đọc — cộng đồng hồ đếm ngược tới hạn
EUDR và một điều khoản EUDR mỗi ngày (có nguồn). Chưa đăng nhập vẫn thấy phần chung.
"""
from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import auth
from app.db import Alert, Dossier, DossierMonitor, EudrSet, Lot, Plot, User, get_session
from app.services import reqlang, translog
from app.services.reqlang import tr

router = APIRouter(tags=["today"])

DEADLINES = [("2026-12-30", "Doanh nghiệp lớn và vừa", "Large and medium operators"),
             ("2027-06-30", "Doanh nghiệp nhỏ và siêu nhỏ", "Micro and small operators")]
_RANK = {"urgent": 0, "action": 1, "info": 2}


def _tip(today: date) -> dict | None:
    from app.services import eudr_assistant
    docs = eudr_assistant._index()[0]
    if not docs:
        return None
    d = docs[today.toordinal() % len(docs)]
    return {"id": d["id"], "title": d["title"], "text": d["text"], "source": d["source"], "url": d["url"]}


@router.get("/api/today")
def today(lang: str = "vi", user: User | None = Depends(auth.optional_user), db: Session = Depends(get_session)) -> dict:
    reqlang.set_lang(lang)
    now = date.today()
    out = {
        "date": now.isoformat(),
        "deadlines": [{"date": d, "days": (date.fromisoformat(d) - now).days, "who": tr(vi, en)} for d, vi, en in DEADLINES],
        "tip": _tip(now),
        "log_size": translog.size(db),
        "items": [], "signed_in": user is not None,
    }
    if user is None:
        return out
    items = out["items"]

    # 1) Đợt giao hàng khai cho các vườn MÌNH phát hành, chưa xác nhận.
    my_dossiers = {r.id: r for r in db.execute(select(Dossier).where(Dossier.user_id == user.id)).scalars().all()}
    eudr_ids = {k for k, r in my_dossiers.items() if '"kind":"eudr_plot"' in r.facts_json}
    if eudr_ids:
        for lot in db.execute(select(Lot)).scalars().all():
            for d in json.loads(lot.deliveries_json or "[]"):
                if d.get("dossier_id") in eudr_ids and not d.get("producer_confirmation"):
                    items.append({"kind": "delivery", "priority": "action", "link": f"/h/{d['dossier_id']}",
                                  "title": tr(f"{lot.operator or 'Một doanh nghiệp'} khai {d['kg']:,.0f} kg từ vườn của bạn",
                                              f"{lot.operator or 'A company'} declared {d['kg']:,.0f} kg from your plot"),
                                  "body": tr("Mở đường link đầy đủ của hồ sơ để xác nhận hoặc từ chối.",
                                             "Open the dossier's full link to confirm or reject.")})

    # 2) Giám sát sau phát hành đánh dấu thay đổi (cả radar xuyên mây).
    if eudr_ids:
        for m in db.execute(select(DossierMonitor).where(DossierMonitor.dossier_id.in_(eudr_ids),
                                                         DossierMonitor.changed == 1)
                            .order_by(DossierMonitor.checked_at.desc()).limit(10)).scalars().all():
            summ = json.loads(m.summary_json or "{}")
            ref = json.loads(my_dossiers[m.dossier_id].facts_json).get("plot", {}).get("ref")
            radar = "radar_drop" in (summ.get("why") or [])
            items.append({"kind": "monitor", "priority": "urgent", "link": f"/h/{m.dossier_id}",
                          "title": tr(f"Vườn “{ref}” xấu đi sau khi phát hành" + (" — radar xuyên mây thấy tụt tán cây" if radar else ""),
                                      f"Plot “{ref}” worsened after issuance" + (" — cloud-piercing radar saw canopy loss" if radar else "")),
                          "body": tr(f"Lúc phát hành: {m.issued_level} → nay: {m.level}. Lô hàng chứa vườn này đang bị chặn.",
                                     f"At issuance: {m.issued_level} → now: {m.level}. Lots containing this plot are blocked.")})

    # 3) Lô hàng của mình: bị chặn / chờ nông hộ xác nhận.
    for lot in db.execute(select(Lot).where(Lot.user_id == user.id, Lot.state == "draft")).scalars().all():
        chk = json.loads(lot.checks_json or "{}")
        pend = sum(1 for d in json.loads(lot.deliveries_json or "[]") if not d.get("producer_confirmation"))
        if chk.get("n_blocked"):
            items.append({"kind": "lot", "priority": "action", "link": "/lo",
                          "title": tr(f"Lô {lot.ref or lot.id}: {chk['n_blocked']} đợt nhập bị chặn", f"Lot {lot.ref or lot.id}: {chk['n_blocked']} deliveries blocked"),
                          "body": chk.get("headline") or ""})
        elif pend:
            items.append({"kind": "lot", "priority": "info", "link": "/lo",
                          "title": tr(f"Lô {lot.ref or lot.id}: {pend} đợt giao chờ nông hộ xác nhận", f"Lot {lot.ref or lot.id}: {pend} deliveries await farmer confirmation"),
                          "body": tr("Gửi nông hộ đường link hồ sơ của họ để xác nhận.", "Send farmers their dossier link to confirm.")})

    # 4) Vườn cần người xem (sàng lọc "cần xem lại" / "rủi ro").
    n_review = 0
    for st in db.execute(select(EudrSet).where(EudrSet.user_id == user.id)).scalars().all():
        n_review += sum(1 for r in json.loads(st.results_json or "{}").values() if r.get("level") in ("review", "high"))
    if n_review:
        items.append({"kind": "review", "priority": "action", "link": "/eudr?tab=tong-quan",
                      "title": tr(f"{n_review} vườn cần người xem (sàng lọc “cần xem lại” / “rủi ro”)",
                                  f"{n_review} plots need a human look (screening “review” / “risk”)"),
                      "body": tr("Xem ảnh vệ tinh trước/sau, giấy tờ, ảnh thực địa rồi ghi lý do.",
                                 "Check before/after imagery, documents and field photos, then record why.")})

    # 5) Cảnh báo chưa đọc trên thửa đã lưu (tham khảo — nguồn chính thức nchmf.gov.vn).
    for a in db.execute(select(Alert).where(Alert.user_id == user.id, Alert.acknowledged == 0, Alert.retro == 0)
                        .order_by(Alert.created_at.desc()).limit(5)).scalars().all():
        items.append({"kind": "alert", "priority": "urgent" if a.risk_level == "danger" else "info", "link": "/",
                      "title": a.headline, "body": tr("Cảnh báo tham khảo — bản tin chính thức: nchmf.gov.vn.",
                                                      "Reference alert — official bulletins: nchmf.gov.vn.")})
    items.sort(key=lambda x: _RANK.get(x["priority"], 9))
    out["counts"] = {"plots_saved": int(db.scalar(select(func.count()).select_from(Plot).where(Plot.user_id == user.id)) or 0),
                     "dossiers": len(my_dossiers), "eudr_dossiers": len(eudr_ids)}
    return out
