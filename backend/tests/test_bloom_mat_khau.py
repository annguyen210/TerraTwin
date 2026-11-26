"""26/11/2026 — Bloom filter chặn mật khẩu phổ biến."""
from __future__ import annotations

import random
import string

from app.services import pw_bloom


def test_trong_danh_sach_khong_bao_gio_lot():
    words = [w.strip() for w in pw_bloom.DATA.read_text(encoding="utf-8").splitlines() if w.strip() and not w.startswith("#")]
    assert len(words) > 9000 and all(pw_bloom.is_common(w) for w in words)
    assert pw_bloom.is_common("Password1") and pw_bloom.is_common("matkhau123")


def test_bao_nham_hiem():
    rnd = random.Random(7)
    fake = ["".join(rnd.choices(string.ascii_letters + string.digits, k=14)) for _ in range(5000)]
    fp = sum(pw_bloom.is_common(x) for x in fake) / len(fake)
    assert fp < 0.02 and pw_bloom._filter().k == 7
