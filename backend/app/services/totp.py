"""GĐ7 — XÁC THỰC HAI LỚP (TOTP, RFC 6238) cho tài khoản quản trị và doanh nghiệp.

Mật khẩu lộ (dùng lại ở trang khác, bị lừa nhập) là đường tấn công phổ biến nhất. Với tài khoản quản trị
— xem được góp ý thí điểm, nhãn kiểm định, sổ vận hành — mật khẩu một mình là không đủ. TOTP: ứng dụng
Authenticator trên điện thoại sinh mã 6 số đổi mỗi 30 giây từ một bí mật chung; máy chủ tính lại và so.

  · Thuần thư viện chuẩn (hmac/hashlib/base32) — kiểm được với vector thử của RFC 6238.
  · Bí mật mã hoá khi lưu (AES-GCM, khoá dẫn xuất HKDF từ TERRATWIN_SECRET): đọc trộm bảng users không đủ
    để sinh mã. Không có TERRATWIN_SECRET cố định thì TỪ CHỐI bật — khởi động lại sẽ khoá chủ tài khoản ra.
  · Chống dùng lại: mỗi bước thời gian (30 giây) chỉ chấp nhận một lần.
  · 8 mã khôi phục dùng một lần, chỉ lưu SHA-256.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import struct
import time
import urllib.parse

STEP = 30
DIGITS = 6
WINDOW = 1                 # chấp nhận lệch ±1 bước (đồng hồ điện thoại lệch vài giây)
ISSUER = "TerraTwin"


class NoStableSecret(RuntimeError):
    pass


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _key(secret_b32: str) -> bytes:
    s = secret_b32.upper()
    return base64.b32decode(s + "=" * (-len(s) % 8))


def code_at(secret_b32: str, step: int, digits: int = DIGITS, algo=hashlib.sha1) -> str:
    mac = hmac.new(_key(secret_b32), struct.pack(">Q", step), algo).digest()
    off = mac[-1] & 0x0F
    v = (struct.unpack(">I", mac[off:off + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(v).zfill(digits)


def now_step(t: float | None = None) -> int:
    return int((time.time() if t is None else t) // STEP)


def verify(secret_b32: str, code: str, last_step: int | None, t: float | None = None) -> int | None:
    """Trả bước thời gian khớp (để lưu chống dùng lại), hoặc None."""
    code = "".join(ch for ch in str(code) if ch.isdigit())
    if len(code) != DIGITS:
        return None
    s = now_step(t)
    for st in range(s - WINDOW, s + WINDOW + 1):
        if last_step is not None and st <= last_step:
            continue
        if hmac.compare_digest(code_at(secret_b32, st), code):
            return st
    return None


def uri(secret_b32: str, account: str) -> str:
    label = urllib.parse.quote(f"{ISSUER}:{account}")
    return (f"otpauth://totp/{label}?secret={secret_b32}&issuer={ISSUER}"
            f"&algorithm=SHA1&digits={DIGITS}&period={STEP}")


# ------------------------------------------------------------------ lưu trữ

def _aead():
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    base = os.environ.get("TERRATWIN_SECRET")
    if not base:
        raise NoStableSecret("Chưa đặt TERRATWIN_SECRET cố định — không bật được xác thực hai lớp "
                             "(khởi động lại sẽ không giải mã được bí mật, khoá chủ tài khoản ra ngoài).")
    k = HKDF(algorithm=hashes.SHA256(), length=32, salt=b"terratwin-totp/1", info=b"totp-secret").derive(base.encode())
    return AESGCM(k)


def seal(secret_b32: str) -> str:
    n = secrets.token_bytes(12)
    return base64.b64encode(n + _aead().encrypt(n, secret_b32.encode("ascii"), b"totp")).decode("ascii")


def unseal(blob: str) -> str:
    raw = base64.b64decode(blob)
    return _aead().decrypt(raw[:12], raw[12:], b"totp").decode("ascii")


def new_recovery_codes(n: int = 8) -> tuple[list[str], str]:
    """(mã cho người dùng xem MỘT lần, JSON mã băm để lưu)."""
    codes = ["-".join(secrets.token_hex(2) for _ in range(3)) for _ in range(n)]
    return codes, json.dumps([hashlib.sha256(c.encode()).hexdigest() for c in codes])


def use_recovery(stored_json: str | None, code: str) -> str | None:
    """Mã khôi phục đúng → trả JSON mới (đã gạch mã vừa dùng); sai → None."""
    try:
        hashes_ = json.loads(stored_json or "[]")
    except ValueError:
        return None
    h = hashlib.sha256(code.strip().lower().encode()).hexdigest()
    if h not in hashes_:
        return None
    hashes_.remove(h)
    return json.dumps(hashes_)
