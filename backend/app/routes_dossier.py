"""Hồ sơ đất số — phát hành, xem công khai, kiểm tệp, sổ đăng ký công khai.

Xem services/dossier.py cho lý do và ba lớp kiểm chứng.
"""
from __future__ import annotations

import base64
import binascii

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import Field
from sqlalchemy.orm import Session

from app import auth
from app.db import Dossier, FieldPhoto, User, get_session
from app.schemas import Location
from app.services import dossier, evidence, onetap, region, reqlang, signing

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


class DossierIn(Location):
    # Ảnh thực địa ĐÃ KIỂM (POST /api/evidence) muốn đóng băng vào hồ sơ.
    evidence_ids: list[str] = Field(default_factory=list, max_length=6)


@router.post("/api/dossier")
def issue_dossier(body: DossierIn, lang: str = "vi",
                  user: User | None = Depends(auth.optional_user),
                  db: Session = Depends(get_session)) -> dict:
    """Phát hành Hồ sơ đất số cho một thửa. Không cần đăng nhập (người mua đất
    thường chưa có tài khoản); đăng nhập thì hồ sơ gắn với tài khoản."""
    reqlang.set_lang(lang)
    reg = region.classify(body.lat, body.lon)
    if not reg.get("serviceable", True):
        raise HTTPException(422, reg.get("note") or reqlang.tr(
            "Ngoài phạm vi phục vụ.", "Out of service area."))

    photos = []
    for pid in dict.fromkeys(body.evidence_ids):          # bỏ trùng, giữ thứ tự
        ph = db.get(FieldPhoto, pid)
        if ph is None:
            raise HTTPException(422, reqlang.tr(f"Không có ảnh mã {pid}.", f"No photo with ID {pid}."))
        # Ảnh kiểm cho thửa KHÁC không được gắn vào hồ sơ này.
        if evidence.haversine_m(ph.plot_lat, ph.plot_lon, body.lat, body.lon) > evidence.SAME_PLOT_M:
            raise HTTPException(422, reqlang.tr(f"Ảnh {pid} được kiểm cho một thửa khác.",
                                                f"Photo {pid} was checked for a different plot."))
        photos.append(ph)

    facts = dossier.build_facts(body.lat, body.lon, body.area_ha, db)
    if photos:
        # Đóng băng vào nội dung đã ký: SHA-256 bản gốc + mã băm ảnh thu nhỏ —
        # thay ảnh trong CSDL là lệch mã băm (phép kiểm "evidence").
        facts["field_evidence"] = [evidence.public(p) for p in photos]
    try:
        row = dossier.issue(db, facts, body.lat, body.lon, user_id=user.id if user else None)
    except signing.SigningKeyMissing as e:
        raise HTTPException(503, str(e))
    for p in photos:
        p.dossier_id = p.dossier_id or row.id
    db.commit()
    return _payload(db, row)


class PhotoIn(Location):
    name: str = Field(default="", max_length=200)
    # Ảnh GỐC (còn EXIF), base64. Không nén/thu nhỏ ở trình duyệt: canvas xoá EXIF.
    data_b64: str = Field(min_length=16, max_length=12_000_000)


@router.post("/api/evidence")
def upload_evidence(body: PhotoIn, lang: str = "vi",
                    user: User = Depends(auth.current_user),
                    db: Session = Depends(get_session)) -> dict:
    """Kiểm MỘT ảnh thực địa cho một thửa (GPS, khoảng cách, thời điểm, dấu chỉnh
    sửa, dùng lại) và lưu ảnh thu nhỏ đã xoá EXIF. Trả mã để gắn vào hồ sơ.

    CẦN ĐĂNG NHẬP: ảnh nằm trong CSDL có trần dung lượng (Neon miễn phí 0,5 GB),
    nên phải có trần mỗi tài khoản — ẩn danh thì không đặt trần được. Hồ sơ đất
    số KHÔNG kèm ảnh vẫn phát hành được khi chưa đăng nhập."""
    reqlang.set_lang(lang)
    why = evidence.check_quota(db, user.id)
    if why:
        raise HTTPException(429, why)
    try:
        data = base64.b64decode(body.data_b64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, reqlang.tr("Dữ liệu ảnh không phải base64 hợp lệ.",
                                            "Photo data is not valid base64."))
    try:
        res = evidence.analyze(db, data, body.lat, body.lon, body.area_ha)
    except evidence.PhotoError as e:
        raise HTTPException(422, str(e))
    row = evidence.store(db, res, body.lat, body.lon, user_id=user.id)
    return {**evidence.public(row), "name": body.name}


@router.get("/api/evidence/{photo_id}/thumb")
def evidence_thumb(photo_id: str, db: Session = Depends(get_session)) -> Response:
    """Ảnh thu nhỏ đã xoá EXIF — công khai theo mã (mã ngẫu nhiên 12 ký tự)."""
    row = db.get(FieldPhoto, photo_id)
    if row is None:
        raise HTTPException(404, "Không có ảnh này.")
    return Response(row.thumb, media_type="image/jpeg",
                    headers={"Cache-Control": "public, max-age=31536000, immutable"})


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
