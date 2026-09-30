"""Hồ sơ đất số — phát hành, xem công khai, kiểm tệp, sổ đăng ký công khai.

Xem services/dossier.py cho lý do và ba lớp kiểm chứng.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import auth
from app.db import Dossier, User, get_session
from app.schemas import Location
from app.services import dossier, onetap, region, reqlang, signing

router = APIRouter(tags=["dossier"])


def _qr_data_uri(url: str) -> str | None:
    """QR trỏ tới trang kiểm chứng công khai — quét bằng điện thoại là thấy bản gốc."""
    try:
        import segno
        return segno.make(url, error="m").svg_data_uri(scale=4, border=2,
                                                      dark="#0b1218", light="#ffffff")
    except Exception:
        return None


def _payload(db: Session, row: Dossier) -> dict:
    url = f"{onetap.base_url()}/h/{row.id}"
    return {**dossier.document(row), "url": url, "qr": _qr_data_uri(url),
            "verification": dossier.verify_row(db, row)}


@router.post("/api/dossier")
def issue_dossier(location: Location, lang: str = "vi",
                  user: User | None = Depends(auth.optional_user),
                  db: Session = Depends(get_session)) -> dict:
    """Phát hành Hồ sơ đất số cho một thửa. Không cần đăng nhập (người mua đất
    thường chưa có tài khoản); đăng nhập thì hồ sơ gắn với tài khoản."""
    reqlang.set_lang(lang)
    reg = region.classify(location.lat, location.lon)
    if not reg.get("serviceable", True):
        raise HTTPException(422, reg.get("note") or reqlang.tr(
            "Ngoài phạm vi phục vụ.", "Out of service area."))
    facts = dossier.build_facts(location.lat, location.lon, location.area_ha, db)
    row = dossier.issue(db, facts, location.lat, location.lon,
                        user_id=user.id if user else None)
    return _payload(db, row)


@router.get("/api/dossier/{dossier_id}")
def get_dossier(dossier_id: str, lang: str = "vi",
                db: Session = Depends(get_session)) -> dict:
    """Công khai theo mã — chia sẻ mã (hoặc QR) là chia sẻ quyền xem. Mã 12 ký
    tự ngẫu nhiên (~60 bit) nên không dò ra được hồ sơ của người khác."""
    reqlang.set_lang(lang)
    row = db.get(Dossier, dossier_id)
    if row is None:
        raise HTTPException(404, reqlang.tr("Không có hồ sơ nào mang mã này.",
                                            "No dossier with this ID."))
    return _payload(db, row)


@router.post("/api/dossier/verify")
def verify_dossier_file(doc: dict, lang: str = "vi",
                        db: Session = Depends(get_session)) -> dict:
    """Kiểm một TỆP hồ sơ (bản JSON đã tải về) với sổ đăng ký."""
    reqlang.set_lang(lang)
    return dossier.verify_document(db, doc)


@router.get("/api/dossiers/log")
def dossier_log(limit: int = 100, db: Session = Depends(get_session)) -> dict:
    """Sổ đăng ký công khai: mã băm + chữ ký + thời điểm, KHÔNG nội dung/toạ độ."""
    return dossier.public_log(db, limit=max(1, min(limit, 1000)))


@router.get("/api/dossiers/keys")
def dossier_keys(db: Session = Depends(get_session)) -> dict:
    """Khoá công khai để tự kiểm chữ ký — không bao giờ kèm phần bí mật."""
    signing.current_key(db)          # bảo đảm khoá hiện hành đã được đăng ký
    return {"algorithm": signing.ALGORITHM, "keys": signing.public_keys(db),
            "how_to_verify": reqlang.tr(
                "Chữ ký Ed25519 ký lên chuỗi ASCII entry_hash (64 ký tự hex). Kiểm "
                "bằng khoá công khai (32 byte, base64) có key_id tương ứng.",
                "The Ed25519 signature covers the ASCII entry_hash (64 hex chars). "
                "Verify it with the public key (32 bytes, base64) of the matching key_id.")}
