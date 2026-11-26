"""Nâng cấp 26/11/2026 — mật khẩu băm Argon2id; hash bcrypt cũ vẫn đăng nhập được rồi tự chuyển."""
from __future__ import annotations

import bcrypt

from app import auth


def test_argon2id_moi_va_kiem():
    h = auth.hash_password("mat-khau-dai-123")
    assert h.startswith("$argon2id$") and "m=19456,t=2,p=1" in h
    assert auth.verify_password("mat-khau-dai-123", h) and not auth.verify_password("sai", h)
    assert not auth.needs_rehash(h)


def test_bcrypt_cu_van_kiem_duoc_va_can_bam_lai():
    old = bcrypt.hashpw(b"mat-khau-cu", bcrypt.gensalt()).decode()
    assert auth.verify_password("mat-khau-cu", old) and not auth.verify_password("x", old)
    assert auth.needs_rehash(old)
    assert not auth.verify_password("a", "rac") and not auth.verify_password("a", "$argon2id$rac")
