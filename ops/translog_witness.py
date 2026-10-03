#!/usr/bin/env python3
"""NHÂN CHỨNG SỔ MINH BẠCH — chạy bởi .github/workflows/transparency.yml, mỗi ngày.

Việc của một nhân chứng (witness) trong Certificate Transparency, viết gọn:
  1. Lấy đầu cây đã ký mới nhất của TerraTwin (GET /api/log/sth).
  2. Kiểm chữ ký Ed25519 bằng khoá công khai (GET /api/dossiers/keys).
  3. So với đầu cây đã lưu lần trước (heads.jsonl trên nhánh transparency-log):
       · cây nhỏ đi             → SỔ BỊ XOÁ  → thất bại
       · cùng kích thước, khác gốc → SỔ BỊ SỬA → thất bại
       · lớn hơn → đòi bằng chứng nhất quán, TỰ KIỂM (RFC 9162 §2.1.4.2) → sai là thất bại
  4. Ghi thêm đầu cây mới vào heads.jsonl (workflow commit lên nhánh).

Độc lập với mã nguồn máy chủ: thuật toán kiểm được chép lại ở đây (không import app/),
để một máy chủ bị chiếm không thể sửa luôn cả người kiểm nó.

    python3 ops/translog_witness.py <đường/dẫn/heads.jsonl> [URL api]
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone


def get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "terratwin-witness/1"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def node(l: bytes, r: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + l + r).digest()


def verify_consistency(m: int, n: int, old: bytes, new: bytes, proof: list[bytes]) -> bool:
    if not 0 < m <= n:
        return False
    if m == n:
        return not proof and old == new
    if not proof:
        return False
    if m & (m - 1) == 0:
        proof = [old] + proof
    fn, sn = m - 1, n - 1
    while fn & 1:
        fn >>= 1
        sn >>= 1
    fr = sr = proof[0]
    for c in proof[1:]:
        if sn == 0:
            return False
        if fn & 1 or fn == sn:
            fr, sr = node(c, fr), node(c, sr)
            if not fn & 1:
                while True:
                    fn >>= 1
                    sn >>= 1
                    if fn & 1 or fn == 0:
                        break
        else:
            sr = node(sr, c)
        fn >>= 1
        sn >>= 1
    return fr == old and sr == new and sn == 0


def verify_sig(head: dict, keys: dict) -> bool:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    k = keys.get(head["key_id"])
    if not k:
        return False
    msg = f"{head['schema']}|{head['tree_size']}|{head['root_hash']}|{head['timestamp']}".encode("ascii")
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(k)).verify(base64.b64decode(head["signature"]), msg)
        return True
    except (InvalidSignature, ValueError):
        return False


def fail(msg: str) -> None:
    print(f"::error::{msg}")
    sys.exit(1)


def main() -> None:
    path = sys.argv[1]
    api = (sys.argv[2] if len(sys.argv) > 2 else os.environ.get("TERRATWIN_API", "https://terratwin-api.onrender.com")).rstrip("/")
    head = get(f"{api}/api/log/sth")
    keys = {k["key_id"]: k["public_key_b64"] for k in get(f"{api}/api/dossiers/keys")["keys"]}
    if not verify_sig(head, keys):
        fail(f"Chữ ký đầu cây KHÔNG hợp lệ (cây {head.get('tree_size')}, khoá {head.get('key_id')}).")
    last = None
    if os.path.exists(path):
        lines = [ln for ln in open(path, encoding="utf-8").read().splitlines() if ln.strip()]
        last = json.loads(lines[-1]) if lines else None
    n = int(head["tree_size"])
    if last:
        m = int(last["tree_size"])
        if n < m:
            fail(f"SỔ BỊ XOÁ: cây từ {m} xuống {n} hồ sơ.")
        if n == m:
            if head["root_hash"] != last["root_hash"]:
                fail(f"SỔ BỊ SỬA: cùng {n} hồ sơ nhưng gốc Merkle khác ({last['root_hash'][:12]}… → {head['root_hash'][:12]}…).")
            print(f"Không có hồ sơ mới (cây {n}). Gốc khớp.")
            return
        if m > 0:
            c = get(f"{api}/api/log/consistency?first={m}&second={n}")
            ok = (c["first_root"] == last["root_hash"] and c["second_root"] == head["root_hash"] and
                  verify_consistency(m, n, bytes.fromhex(last["root_hash"]), bytes.fromhex(head["root_hash"]),
                                     [bytes.fromhex(x) for x in c["proof"]]))
            if not ok:
                fail(f"Bằng chứng nhất quán {m}→{n} SAI — lịch sử sổ đã bị viết lại.")
            print(f"Nhất quán {m}→{n}: đã kiểm ({len(c['proof'])} mã băm).")
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({**head, "witnessed_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                           ensure_ascii=False) + "\n")
    print(f"Đã ghi đầu cây {n}, gốc {head['root_hash'][:16]}…")


if __name__ == "__main__":
    main()
