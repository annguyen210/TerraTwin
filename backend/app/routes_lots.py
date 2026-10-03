"""Lô hàng — cân bằng khối lượng, chứng thư lô hàng (Merkle), tờ khai DDS nháp.

Xem services/lots.py. Tạo / sửa / phát hành cần đăng nhập (danh sách nhà cung cấp là
bí mật kinh doanh). Bằng chứng thuộc lô của MỘT vườn thì công khai theo cặp mã (lô,
hồ sơ vườn): nông hộ biết mã vườn mình + mã chứng thư là tự lấy được.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth
from app.db import Dossier, EudrSet, Lot, User, get_session
from app.services import dossier, eudr, lots, onetap, reqlang, signing

router = APIRouter(tags=["lots"])


class DeliveryIn(BaseModel):
    dossier_id: str = Field(max_length=16)
    kg: float = Field(gt=0, le=10_000_000)
    date: str | None = Field(default=None, max_length=10)
    review_ack: str | None = Field(default=None, max_length=300)


class LotIn(BaseModel):
    ref: str = Field(default="", max_length=80)
    commodity: str = Field(default="coffee", max_length=24)
    season: str = Field(default="", max_length=16)
    operator: str = Field(default="", max_length=160)
    deliveries: list[DeliveryIn] = Field(default_factory=list, max_length=5000)


def _own(db: Session, lot_id: str, user: User) -> Lot:
    lot = db.get(Lot, lot_id)
    if lot is None or lot.user_id != user.id:
        raise HTTPException(404, reqlang.tr("Không có lô hàng này.", "No such lot."))
    return lot


def _view(lot: Lot) -> dict:
    return {"id": lot.id, "ref": lot.ref, "commodity": lot.commodity, "season": lot.season,
            "operator": lot.operator, "state": lot.state, "certificate_id": lot.certificate_id,
            "certificate_url": f"{onetap.base_url()}/h/{lot.certificate_id}" if lot.certificate_id else None,
            "created_at": lot.created_at.isoformat(timespec="seconds") + "Z",
            "deliveries": json.loads(lot.deliveries_json or "[]"), "checks": json.loads(lot.checks_json or "{}")}


def _apply(db: Session, lot: Lot, body: LotIn) -> dict:
    if lot.state == "certified":
        raise HTTPException(409, reqlang.tr("Lô đã phát hành chứng thư — không sửa được; tạo lô mới.",
                                            "The lot is certified — it can't be edited; create a new lot."))
    dels, errs = lots.normalize([d.model_dump() for d in body.deliveries])
    lot.ref, lot.season, lot.operator = body.ref[:80], body.season[:16], body.operator[:160]
    lot.commodity = body.commodity if body.commodity in eudr.COMMODITIES else "other"
    lot.deliveries_json = json.dumps(dels, ensure_ascii=False)
    chk = lots.check(db, lot)
    db.commit()
    return {**_view(lot), "errors": errs, "checks": chk}


@router.post("/api/lots")
def create_lot(body: LotIn, lang: str = "vi", user: User = Depends(auth.current_user),
               db: Session = Depends(get_session)) -> dict:
    reqlang.set_lang(lang)
    lot = Lot(id=lots.new_id(), user_id=user.id)
    db.add(lot)
    return _apply(db, lot, body)


@router.put("/api/lots/{lot_id}")
def update_lot(lot_id: str, body: LotIn, lang: str = "vi", user: User = Depends(auth.current_user),
               db: Session = Depends(get_session)) -> dict:
    reqlang.set_lang(lang)
    return _apply(db, _own(db, lot_id, user), body)


@router.post("/api/lots/from-set/{set_id}")
def lot_from_set(set_id: str, lang: str = "vi", user: User = Depends(auth.current_user),
                 db: Session = Depends(get_session)) -> dict:
    """Bản nháp lô hàng từ một lô thửa đã phát hành hồ sơ: điền sẵn mã hồ sơ từng vườn,
    số kg để trống cho doanh nghiệp nhập."""
    reqlang.set_lang(lang)
    st = db.get(EudrSet, set_id)
    if st is None or st.user_id != user.id:
        raise HTTPException(404, reqlang.tr("Không có lô thửa này.", "No such set."))
    plots = {str(p["index"]): p for p in json.loads(st.plots_json)}
    rows = [{"dossier_id": r["dossier_id"], "ref": plots.get(k, {}).get("ref"), "level": r.get("level"),
             "area_ha": plots.get(k, {}).get("area_ha")}
            for k, r in json.loads(st.results_json or "{}").items() if r.get("dossier_id")]
    return {"commodity": st.commodity, "operator": st.producer, "ref": st.title, "rows": rows}


@router.get("/api/lots")
def list_lots(user: User = Depends(auth.current_user), db: Session = Depends(get_session)) -> dict:
    rows = db.execute(select(Lot).where(Lot.user_id == user.id).order_by(Lot.created_at.desc()).limit(100)).scalars().all()
    return {"lots": [{k: v for k, v in _view(r).items() if k != "deliveries"} for r in rows]}


@router.get("/api/lots/{lot_id}")
def get_lot(lot_id: str, user: User = Depends(auth.current_user), db: Session = Depends(get_session)) -> dict:
    return _view(_own(db, lot_id, user))


@router.post("/api/lots/{lot_id}/certify")
def certify_lot(lot_id: str, lang: str = "vi", user: User = Depends(auth.current_user),
                db: Session = Depends(get_session)) -> dict:
    """Kiểm lại lần cuối → phát hành CHỨNG THƯ LÔ HÀNG (một hồ sơ trong sổ móc xích)."""
    from app.routes_dossier import _payload

    reqlang.set_lang(lang)
    lot = _own(db, lot_id, user)
    if lot.state == "certified":
        raise HTTPException(409, reqlang.tr("Lô đã có chứng thư.", "The lot is already certified."))
    chk = lots.check(db, lot)
    if not chk["certifiable"]:
        db.commit()
        raise HTTPException(422, {"message": chk["headline"], "checks": chk})
    facts = lots.certificate_facts(lot, chk)
    cs = [json.loads(db.get(Dossier, d["dossier_id"]).facts_json)["plot"]["centroid"]
          for d in json.loads(lot.deliveries_json)]
    lat = sum(c["lat"] for c in cs) / len(cs)
    lon = sum(c["lon"] for c in cs) / len(cs)
    try:
        row = dossier.issue(db, facts, lat, lon, user_id=user.id)
    except signing.SigningKeyMissing as e:
        raise HTTPException(503, str(e))
    lot.state, lot.certificate_id = "certified", row.id
    db.commit()
    return {"lot": _view(lot), "certificate": _payload(db, row)}


@router.get("/api/lots/{lot_id}/dds")
def lot_dds(lot_id: str, lang: str = "vi", user: User = Depends(auth.current_user),
            db: Session = Depends(get_session)) -> dict:
    reqlang.set_lang(lang)
    return lots.dds(db, _own(db, lot_id, user))


@router.get("/api/lots/{lot_id}/geojson")
def lot_geojson(lot_id: str, user: User = Depends(auth.current_user), db: Session = Depends(get_session)) -> Response:
    d = lots.dds(db, _own(db, lot_id, user))
    return Response(json.dumps(d["geolocation"], ensure_ascii=False), media_type="application/geo+json",
                    headers={"Content-Disposition": f'attachment; filename="terratwin-lo-{lot_id}.geojson"'})


@router.get("/api/lot-proof/{certificate_id}/{dossier_id}")
def lot_proof(certificate_id: str, dossier_id: str, lang: str = "vi", db: Session = Depends(get_session)) -> dict:
    """Bằng chứng THUỘC LÔ của một vườn — công khai theo cặp mã. Kiểm được offline:
    băm lá, đi theo đường kiểm toán, so với gốc Merkle trong chứng thư ĐÃ KÝ."""
    reqlang.set_lang(lang)
    lot = db.execute(select(Lot).where(Lot.certificate_id == certificate_id)).scalars().first()
    p = lots.proof_for(lot, dossier_id.strip().lower()) if lot else None
    if p is None:
        raise HTTPException(404, reqlang.tr("Vườn này không nằm trong lô hàng đó.", "This plot is not in that lot."))
    return p


@router.delete("/api/lots/{lot_id}", status_code=204)
def delete_lot(lot_id: str, user: User = Depends(auth.current_user), db: Session = Depends(get_session)) -> Response:
    lot = _own(db, lot_id, user)
    if lot.state == "certified":
        raise HTTPException(409, reqlang.tr("Không xoá lô đã có chứng thư (chứng thư nằm trong sổ bất biến).",
                                            "A certified lot can't be deleted (its certificate is in the immutable log)."))
    db.delete(lot)
    db.commit()
    return Response(status_code=204)
