"""CÂY MERKLE theo RFC 6962 / RFC 9162 (Certificate Transparency) — thuần Python.

Dùng ở hai chỗ:
  · CHỨNG THƯ LÔ HÀNG: gốc Merkle của mọi hồ sơ vườn trong một lô được ký. Mỗi vườn
    có BẰNG CHỨNG THUỘC LÔ dài ⌈log₂ n⌉ mã băm — nhà nhập khẩu kiểm một vườn mà
    không cần xem danh sách nhà cung cấp còn lại (lô 10.000 vườn: 14 mã băm).
  · SỔ MINH BẠCH: mọi hồ sơ đã phát hành là lá của một cây chỉ-được-thêm. BẰNG
    CHỨNG NHẤT QUÁN giữa hai kích thước cây chứng minh cây mới chứa NGUYÊN VẸN cây
    cũ — tức là không ai lặng lẽ sửa hay xoá một hồ sơ đã phát hành. Bên thứ ba
    (một tác vụ GitHub Actions) giữ các "đầu cây" đã ký và kiểm điều này mỗi ngày.

Tiền tố 0x00 cho lá, 0x01 cho nút trong (RFC 6962 §2.1) chặn tấn công "nút giả làm
lá" (second-preimage). Thuật toán kiểm đúng theo RFC 9162 §2.1.3.2 và §2.1.4.2.
"""
from __future__ import annotations

import hashlib


def _h(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()


def leaf_hash(data: bytes) -> bytes:
    return _h(b"\x00" + data)


def node_hash(left: bytes, right: bytes) -> bytes:
    return _h(b"\x01" + left + right)


EMPTY_ROOT = _h(b"")


def _split(n: int) -> int:
    """Luỹ thừa của 2 lớn nhất NHỎ HƠN n (n ≥ 2)."""
    k = 1
    while k * 2 < n:
        k *= 2
    return k


def root(leaves: list[bytes]) -> bytes:
    """MTH(D[n]) — `leaves` là mã băm lá (đã qua leaf_hash)."""
    n = len(leaves)
    if n == 0:
        return EMPTY_ROOT
    if n == 1:
        return leaves[0]
    k = _split(n)
    return node_hash(root(leaves[:k]), root(leaves[k:]))


def inclusion_proof(index: int, leaves: list[bytes]) -> list[bytes]:
    """PATH(m, D[n]) — đường kiểm toán cho lá thứ `index` (đếm từ 0)."""
    n = len(leaves)
    if not 0 <= index < n:
        raise ValueError("chỉ số lá ngoài cây")
    if n == 1:
        return []
    k = _split(n)
    if index < k:
        return inclusion_proof(index, leaves[:k]) + [root(leaves[k:])]
    return inclusion_proof(index - k, leaves[k:]) + [root(leaves[:k])]


def verify_inclusion(leaf: bytes, index: int, size: int, proof: list[bytes], expected_root: bytes) -> bool:
    """RFC 9162 §2.1.3.2."""
    if not 0 <= index < size:
        return False
    fn, sn = index, size - 1
    r = leaf
    for p in proof:
        if sn == 0:
            return False
        if fn & 1 or fn == sn:
            r = node_hash(p, r)
            if not fn & 1:
                while True:
                    fn >>= 1
                    sn >>= 1
                    if fn & 1 or fn == 0:
                        break
        else:
            r = node_hash(r, p)
        fn >>= 1
        sn >>= 1
    return sn == 0 and r == expected_root


def consistency_proof(m: int, leaves: list[bytes]) -> list[bytes]:
    """PROOF(m, D[n]) — cây kích thước m là tiền tố của cây kích thước n."""
    n = len(leaves)
    if not 0 < m <= n:
        raise ValueError("kích thước cây cũ không hợp lệ")
    return _subproof(m, leaves, True)


def _subproof(m: int, leaves: list[bytes], b: bool) -> list[bytes]:
    n = len(leaves)
    if m == n:
        return [] if b else [root(leaves)]
    k = _split(n)
    if m <= k:
        return _subproof(m, leaves[:k], b) + [root(leaves[k:])]
    return _subproof(m - k, leaves[k:], False) + [root(leaves[:k])]


def verify_consistency(m: int, n: int, old_root: bytes, new_root: bytes, proof: list[bytes]) -> bool:
    """RFC 9162 §2.1.4.2."""
    if not 0 < m <= n:
        return False
    if m == n:
        return not proof and old_root == new_root
    if not proof:
        return False
    if m & (m - 1) == 0:                     # m là luỹ thừa của 2: thêm old_root vào đầu
        proof = [old_root] + proof
    fn, sn = m - 1, n - 1
    while fn & 1:
        fn >>= 1
        sn >>= 1
    fr = sr = proof[0]
    for c in proof[1:]:
        if sn == 0:
            return False
        if fn & 1 or fn == sn:
            fr = node_hash(c, fr)
            sr = node_hash(c, sr)
            if not fn & 1:
                while True:
                    fn >>= 1
                    sn >>= 1
                    if fn & 1 or fn == 0:
                        break
        else:
            sr = node_hash(sr, c)
        fn >>= 1
        sn >>= 1
    return fr == old_root and sr == new_root and sn == 0


def hexes(xs: list[bytes]) -> list[str]:
    return [x.hex() for x in xs]


def unhex(xs: list[str]) -> list[bytes]:
    return [bytes.fromhex(x) for x in xs]
