"""Sinh cặp khoá VAPID cho Web Push (M1) — GHI RA FILE CỤC BỘ, không in ra màn
hình, để khoá riêng KHÔNG lọt qua chat/log.

CÁCH DÙNG (chạy trong terminal RIÊNG của bạn, KHÔNG qua ô chat `!`):
    cd backend && .venv/Scripts/python.exe ../ops/gen_vapid.py
Xong sẽ có file  backend/.vapid-keys.txt  (đã .gitignore) chứa 2 dòng env.
Mở file, dán 2 biến vào terratwin-api → Environment trên Render, rồi XOÁ file.

Vì sao ghi file thay vì in: khoá riêng in ra là lọt vào khung chat/nhật ký — đúng
lỗi ta đang sửa. File cục bộ chỉ bạn đọc, dán thẳng lên Render, rồi xoá.
"""
import base64
import os

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid01

v = Vapid01()
v.generate_keys()
b64 = lambda b: base64.urlsafe_b64encode(b).decode().rstrip("=")
pub = b64(v.public_key.public_bytes(
    serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
priv = b64(v.private_key.private_numbers().private_value.to_bytes(32, "big"))

out = os.path.join(os.path.dirname(__file__), "..", "backend", ".vapid-keys.txt")
out = os.path.abspath(out)
with open(out, "w", encoding="utf-8") as f:
    f.write(f"TERRATWIN_VAPID_PUBLIC_KEY={pub}\n")
    f.write(f"TERRATWIN_VAPID_PRIVATE_KEY={priv}\n")

print("Wrote keys to:", out)
print("-> Open the file, paste both vars into terratwin-api -> Environment (Render), then DELETE the file.")
print("-> Do NOT commit, do NOT paste the private key into chat.")
