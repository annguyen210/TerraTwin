"""Chữ ký số Ed25519 cho Hồ sơ đất số.

VÌ SAO CẦN CHỮ KÝ, KHÔNG CHỈ MÃ BĂM. Báo cáo cũ (services/report.py) tự mang mã
băm SHA-256 của chính nó. Mã băm chứng minh "nội dung khớp mã băm đi kèm" —
nhưng kẻ sửa nội dung chỉ việc băm lại và thay mã mới, bên nhận không phân biệt
được. Chữ ký Ed25519 dùng khoá BÍ MẬT chỉ máy chủ giữ: ai cũng kiểm được bằng
khoá công khai, nhưng không ai ngoài máy chủ tạo được chữ ký hợp lệ cho nội
dung đã sửa.

KHOÁ. Ưu tiên TERRATWIN_SIGNING_KEY (base64 của 32 byte hạt giống Ed25519 — sinh
bằng ops/gen_signing_key.py, ghi ra tệp cục bộ, không in ra màn hình). Chưa đặt
thì tự sinh MỘT lần và lưu vào bảng signing_keys để khởi động lại vẫn dùng đúng
khoá đó — chạy được ngay, nhưng khoá bí mật nằm trong CSDL: ai đọc được CSDL thì
giả được chữ ký. /api/dossiers/keys ghi rõ nguồn khoá (env / auto) để người kiểm
biết mức tin cậy.

Mọi khoá công khai từng dùng được giữ lại (bảng signing_keys): đổi khoá thì hồ
sơ cũ vẫn kiểm được bằng khoá cũ.
"""
from __future__ import annotations

import base64
import hashlib
import os
import threading

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db import SigningKey

ALGORITHM = "Ed25519"
_lock = threading.Lock()


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _pub_bytes(priv: Ed25519PrivateKey) -> bytes:
    return priv.public_key().public_bytes(serialization.Encoding.Raw,
                                          serialization.PublicFormat.Raw)


def key_id_for(public_raw: bytes) -> str:
    """16 ký tự hex đầu của SHA-256 khoá công khai — ngắn để in lên hồ sơ."""
    return hashlib.sha256(public_raw).hexdigest()[:16]


def _from_env() -> Ed25519PrivateKey | None:
    raw = os.environ.get("TERRATWIN_SIGNING_KEY", "").strip()
    if not raw:
        return None
    try:
        seed = base64.b64decode(raw, validate=True)
    except ValueError as e:
        raise RuntimeError("TERRATWIN_SIGNING_KEY không phải base64 hợp lệ") from e
    if len(seed) != 32:
        raise RuntimeError("TERRATWIN_SIGNING_KEY phải là base64 của đúng 32 byte")
    return Ed25519PrivateKey.from_private_bytes(seed)


def current_key(db: Session) -> tuple[Ed25519PrivateKey, str, str]:
    """(khoá bí mật, key_id, nguồn) đang dùng để ký. Tự đăng ký khoá công khai
    vào bảng signing_keys lần đầu gặp."""
    with _lock:
        priv = _from_env()
        if priv is not None:
            pub = _pub_bytes(priv)
            kid = key_id_for(pub)
            if db.get(SigningKey, kid) is None:
                db.add(SigningKey(key_id=kid, public_b64=_b64(pub), private_b64=None,
                                  source="env"))
            # Đã có khoá từ biến môi trường → XOÁ phần bí mật của mọi khoá tự sinh
            # cũ. Khoá ký nằm cùng chỗ với dữ liệu nó bảo vệ thì người sửa được
            # CSDL cũng ký lại được — lời hứa chống sửa mất nghĩa. Giữ public_b64:
            # hồ sơ đã ký bằng khoá cũ vẫn KIỂM được, chỉ không ai KÝ thêm được.
            db.execute(update(SigningKey).where(SigningKey.private_b64.is_not(None))
                       .values(private_b64=None))
            db.commit()
            return priv, kid, "env"

        if _strict():
            raise SigningKeyMissing(
                "TERRATWIN_STRICT=1: chưa đặt TERRATWIN_SIGNING_KEY — không tự sinh "
                "khoá lưu trong CSDL. Sinh khoá bằng ops/gen_signing_key.py.")

        row = db.execute(select(SigningKey).where(SigningKey.source == "auto",
                                                  SigningKey.private_b64.is_not(None))
                         .order_by(SigningKey.created_at.desc())).scalars().first()
        if row is not None:
            priv = Ed25519PrivateKey.from_private_bytes(base64.b64decode(row.private_b64))
            return priv, row.key_id, "auto"

        priv = Ed25519PrivateKey.generate()
        seed = priv.private_bytes(serialization.Encoding.Raw,
                                  serialization.PrivateFormat.Raw,
                                  serialization.NoEncryption())
        pub = _pub_bytes(priv)
        kid = key_id_for(pub)
        db.add(SigningKey(key_id=kid, public_b64=_b64(pub), private_b64=_b64(seed),
                          source="auto"))
        db.commit()
        return priv, kid, "auto"


class SigningKeyMissing(RuntimeError):
    """Chế độ nghiêm (TERRATWIN_STRICT=1) mà chưa đặt TERRATWIN_SIGNING_KEY."""


def _strict() -> bool:
    return os.environ.get("TERRATWIN_STRICT", "").strip().lower() in ("1", "true", "yes")


def source_info(db: Session) -> dict:
    """Khoá đang ký lấy từ đâu — cho /api/health, /status. KHÔNG sinh khoá mới."""
    if os.environ.get("TERRATWIN_SIGNING_KEY", "").strip():
        return {"source": "env", "message": None}
    auto = db.execute(select(SigningKey).where(SigningKey.source == "auto",
                                               SigningKey.private_b64.is_not(None))).scalars().first()
    if auto is not None:
        return {"source": "auto-db", "key_id": auto.key_id, "message": (
            "CẢNH BÁO: khoá ký Hồ sơ đất số đang TỰ SINH và lưu trong CSDL — ai sửa được "
            "CSDL cũng ký lại được hồ sơ đã sửa. Đặt TERRATWIN_SIGNING_KEY (ops/gen_signing_key.py).")}
    return {"source": "none", "message": (
        "Chưa có khoá ký: hồ sơ đầu tiên sẽ tự sinh khoá lưu trong CSDL. Nên đặt "
        "TERRATWIN_SIGNING_KEY trước (ops/gen_signing_key.py).")}


def key_source(db: Session, key_id: str) -> str | None:
    row = db.get(SigningKey, key_id)
    return row.source if row else None


def sign(db: Session, message: bytes) -> tuple[str, str]:
    """Ký → (chữ ký base64, key_id)."""
    priv, kid, _ = current_key(db)
    return _b64(priv.sign(message)), kid


def verify(db: Session, message: bytes, signature_b64: str, key_id: str) -> bool:
    row = db.get(SigningKey, key_id)
    if row is None:
        return False
    try:
        pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(row.public_b64))
        pub.verify(base64.b64decode(signature_b64), message)
        return True
    except (InvalidSignature, ValueError):
        return False


def public_keys(db: Session) -> list[dict]:
    """Mọi khoá công khai từng dùng — KHÔNG bao giờ kèm phần bí mật."""
    rows = db.execute(select(SigningKey).order_by(SigningKey.created_at)).scalars().all()
    return [{"key_id": r.key_id, "algorithm": ALGORITHM, "public_key_b64": r.public_b64,
             "source": r.source, "created_at": r.created_at.isoformat() + "Z"}
            for r in rows]

