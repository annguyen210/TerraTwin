"""Sinh khoá ký Ed25519 cho Hồ sơ đất số — GHI RA FILE CỤC BỘ, không in khoá ra
màn hình, để khoá bí mật KHÔNG lọt qua chat/log (cùng cách với gen_vapid.py).

CÁCH DÙNG (chạy trong terminal RIÊNG của bạn, KHÔNG qua ô chat `!`):
    cd backend && .venv/Scripts/python.exe ../ops/gen_signing_key.py
Xong sẽ có file  backend/.signing-key.txt  (đã .gitignore) chứa 1 dòng env.
Mở file, dán TERRATWIN_SIGNING_KEY vào terratwin-api → Environment trên Render,
cất một bản ở nơi an toàn (mất khoá = không ký tiếp bằng khoá cũ được, nhưng hồ
sơ cũ vẫn kiểm được vì khoá CÔNG KHAI đã lưu trong CSDL), rồi XOÁ file.
"""
import base64
import hashlib
import os

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

k = Ed25519PrivateKey.generate()
seed = k.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                       serialization.NoEncryption())
pub = k.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
key_id = hashlib.sha256(pub).hexdigest()[:16]          # = signing.key_id_for

out = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend", ".signing-key.txt"))
with open(out, "w", encoding="utf-8") as f:
    f.write(f"TERRATWIN_SIGNING_KEY={base64.b64encode(seed).decode('ascii')}\n")

print("Wrote key to:", out)
print("Public key id (safe to share):", key_id)
print("-> Paste TERRATWIN_SIGNING_KEY into terratwin-api -> Environment (Render), keep a safe copy, then DELETE the file.")
print("-> Do NOT commit, do NOT paste the key into chat.")
