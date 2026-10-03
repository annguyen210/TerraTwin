"""TIẾT LỘ CHỌN LỌC — giấu họ tên (hay trường nhạy cảm khác) khỏi trang công khai
mà chữ ký vẫn kiểm được, và chủ hồ sơ chứng minh được khi CẦN.

Cùng ý tưởng với SD-JWT (IETF): nội dung được ký chỉ chứa CAM KẾT
    sha256("terratwin.sd/1|<trường>|<muối>|<giá trị>")
với muối ngẫu nhiên 128 bit. Không có muối thì không dò ngược được tên (kể cả thử
hết danh sách họ tên Việt Nam). Chủ hồ sơ giữ (trường, muối, giá trị); đưa cho ai
thì người đó băm lại, so với cam kết trong nội dung ĐÃ KÝ → chứng minh đúng tên đó
nằm trong hồ sơ từ lúc phát hành, không ai thêm sau.

Vì sao cần: họ tên nông hộ gắn toạ độ vườn là dữ liệu cá nhân (Luật Bảo vệ dữ liệu
cá nhân 2025). Mặc định ẨN trên trang công khai; nông hộ tự quyết đưa cho ai.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets

PREFIX = "terratwin.sd/1"


def commitment(field: str, salt: str, value: str) -> str:
    return hashlib.sha256(f"{PREFIX}|{field}|{salt}|{value}".encode("utf-8")).hexdigest()


def commit(field: str, value: str) -> tuple[str, dict]:
    """→ (cam kết hex, phần riêng {salt, value})."""
    salt = secrets.token_hex(16)
    return commitment(field, salt, value), {"salt": salt, "value": value}


def verify(field: str, salt: str, value: str, digest: str) -> bool:
    return secrets.compare_digest(commitment(field, salt, value), digest)


def encode_token(private: dict) -> str:
    """Phần riêng → chuỗi gọn cho đường link (base64url, không đệm)."""
    raw = json.dumps({k: [v["salt"], v["value"]] for k, v in private.items()},
                     ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_token(token: str) -> dict:
    pad = "=" * (-len(token) % 4)
    d = json.loads(base64.urlsafe_b64decode(token + pad).decode("utf-8"))
    return {k: {"salt": str(v[0]), "value": str(v[1])} for k, v in d.items()}


def reveal(commitments: dict, private: dict) -> dict:
    """{trường: {value, ok}} cho các trường có cả cam kết lẫn phần riêng."""
    out = {}
    for field, digest in (commitments or {}).items():
        p = private.get(field)
        if p:
            out[field] = {"value": p["value"], "ok": verify(field, p["salt"], p["value"], digest)}
    return out
