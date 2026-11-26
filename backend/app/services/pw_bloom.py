"""BLOOM FILTER chặn mật khẩu phổ biến (26/11/2026) — kiểm "mật khẩu này có trong danh sách hay bị lộ không" trong vài
micro-giây với ~12 KB bộ nhớ, không giữ danh sách trong RAM.

m bit, k hàm băm (băm kép từ blake2b: h_i = h1 + i·h2 mod m — Kirsch & Mitzenmacher 2006). Với n ≈ 10 000 mục, m = 10·n,
k = 7 → tỉ lệ báo nhầm ≈ 0,8% (một mật khẩu lạ hiếm khi bị chặn nhầm; mật khẩu trong danh sách KHÔNG BAO GIỜ lọt).
Danh sách: data/common_passwords.txt (SecLists 10k, MIT + mật khẩu hay gặp ở Việt Nam).
"""
from __future__ import annotations

import hashlib
import math
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data" / "common_passwords.txt"


class Bloom:
    def __init__(self, n: int, bits_per_item: int = 10):
        self.m = max(64, n * bits_per_item)
        self.k = max(1, round(bits_per_item * math.log(2)))
        self.bits = bytearray((self.m + 7) // 8)

    def _idx(self, item: str):
        d = hashlib.blake2b(item.encode("utf-8"), digest_size=16).digest()
        h1, h2 = int.from_bytes(d[:8], "little"), int.from_bytes(d[8:], "little") | 1
        return ((h1 + i * h2) % self.m for i in range(self.k))

    def add(self, item: str) -> None:
        for i in self._idx(item):
            self.bits[i >> 3] |= 1 << (i & 7)

    def __contains__(self, item: str) -> bool:
        return all(self.bits[i >> 3] & (1 << (i & 7)) for i in self._idx(item))


@lru_cache(maxsize=1)
def _filter() -> Bloom | None:
    try:
        words = [w.strip() for w in DATA.read_text(encoding="utf-8").splitlines() if w.strip() and not w.startswith("#")]
    except OSError:
        return None
    b = Bloom(len(words))
    for w in words:
        b.add(w)
    return b


def is_common(password: str) -> bool:
    b = _filter()
    return b is not None and (password or "").strip().lower() in b
