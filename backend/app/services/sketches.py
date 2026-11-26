"""THỐNG KÊ ẨN DANH BẰNG CẤU TRÚC DỮ LIỆU XÁC SUẤT (26/11/2026).

  · HyperLogLog (Flajolet et al. 2007, p = 12 → 4 096 thanh ghi, sai số chuẩn ≈ 1,04/√4096 = 1,6%): đếm số NGƯỜI KHÁC
    NHAU mở app mỗi ngày mà không lưu IP. Mỗi lượt chỉ cập nhật thanh ghi từ blake2b(muối-của-ngày ‖ IP ‖ trình duyệt);
    muối đổi mỗi ngày và bắt nguồn từ khoá bí mật của máy chủ → không dò ngược ra IP, không nối được người qua các ngày.
    Gộp nhiều ngày = lấy max từng thanh ghi (đếm 7/30 ngày không phải cộng dồn).
  · Count-Min Sketch (Cormode & Muthukrishnan 2005, 4 × 2048) + Top-K: nơi được TÌM nhiều nhất theo tháng — chỉ đếm tên
    địa danh đã chuẩn hoá có kết quả, không lưu ai tìm, không lưu từng lượt. Ước lượng không bao giờ thấp hơn thật.
Lưu trong cache_store (bảng kv_cache) — vài KB mỗi ngày/tháng.
"""
from __future__ import annotations

import base64
import hashlib
import math
import os
import threading
from datetime import date, timedelta

P = 12
M = 1 << P
CMS_W, CMS_D, TOPK = 2048, 4, 30
_lock = threading.Lock()
_TTL = 400 * 86400


# ---------------------------------------------------------------- HyperLogLog

def _alpha(m: int) -> float:
    return 0.7213 / (1 + 1.079 / m)


def hll_new() -> bytearray:
    return bytearray(M)


def hll_add(reg: bytearray, item: bytes) -> None:
    h = int.from_bytes(hashlib.blake2b(item, digest_size=8).digest(), "big")
    idx = h >> (64 - P)
    w = (h << P) & ((1 << 64) - 1)
    rank = (64 - P) + 1 if w == 0 else (64 - w.bit_length()) + 1
    if rank > reg[idx]:
        reg[idx] = rank


def hll_count(reg: bytearray) -> int:
    z = sum(2.0 ** -r for r in reg)
    e = _alpha(M) * M * M / z
    zeros = reg.count(0)
    if e <= 2.5 * M and zeros:
        e = M * math.log(M / zeros)          # hiệu chỉnh vùng nhỏ (linear counting)
    return int(round(e))


def hll_merge(regs: list[bytearray]) -> bytearray:
    out = hll_new()
    for r in regs:
        for i, v in enumerate(r):
            if v > out[i]:
                out[i] = v
    return out


def _salt(day: date) -> bytes:
    secret = os.environ.get("TERRATWIN_SECRET", "terratwin-dev")
    return hashlib.blake2b(f"{secret}|hll|{day.isoformat()}".encode(), digest_size=16).digest()


def _load(key: str) -> bytearray | None:
    from app.services import cache_store
    v = cache_store.get(key)
    return bytearray(base64.b64decode(v)) if isinstance(v, str) else None


def _save(key: str, reg: bytearray) -> None:
    from app.services import cache_store
    cache_store.put(key, base64.b64encode(bytes(reg)).decode(), ttl_seconds=_TTL)


def visit(ip: str, ua: str, day: date | None = None) -> None:
    day = day or date.today()
    key = f"hll:visit:{day.isoformat()}"
    with _lock:
        reg = _load(key) or hll_new()
        hll_add(reg, _salt(day) + (ip or "").encode() + b"|" + (ua or "")[:200].encode())
        _save(key, reg)


def visitors(days: int = 30, today: date | None = None) -> dict:
    today = today or date.today()
    regs, daily = [], []
    for i in range(days):
        d = today - timedelta(days=i)
        r = _load(f"hll:visit:{d.isoformat()}")
        if r is not None:
            regs.append(r)
            daily.append({"date": d.isoformat(), "unique": hll_count(r)})
    return {"daily": daily[:7], f"unique_{days}d": hll_count(hll_merge(regs)) if regs else 0,
            "unique_7d": hll_count(hll_merge(regs[:7])) if regs else 0, "std_error_pct": round(104 / math.sqrt(M), 1)}


# ---------------------------------------------------------------- Count-Min Sketch + Top-K

def _cms_idx(item: str) -> list[int]:
    d = hashlib.blake2b(item.encode(), digest_size=16).digest()
    h1, h2 = int.from_bytes(d[:8], "little"), int.from_bytes(d[8:], "little") | 1
    return [(h1 + i * h2) % CMS_W for i in range(CMS_D)]


def cms_add(state: dict, item: str, n: int = 1) -> int:
    rows = state.setdefault("rows", [[0] * CMS_W for _ in range(CMS_D)])
    est = None
    for r, j in enumerate(_cms_idx(item)):
        rows[r][j] += n
        est = rows[r][j] if est is None else min(est, rows[r][j])
    top = state.setdefault("top", {})
    top[item] = est
    if len(top) > TOPK:
        del top[min(top, key=top.get)]
    return est


def cms_estimate(state: dict, item: str) -> int:
    rows = state.get("rows")
    return 0 if not rows else min(rows[r][j] for r, j in enumerate(_cms_idx(item)))


def search_hit(place_key: str, day: date | None = None) -> None:
    from app.services import cache_store
    if not place_key:
        return
    key = f"cms:place:{(day or date.today()).strftime('%Y-%m')}"
    with _lock:
        st = cache_store.get(key) or {}
        cms_add(st, place_key[:80])
        cache_store.put(key, st, ttl_seconds=_TTL)


def top_places(day: date | None = None, k: int = 10) -> list[dict]:
    from app.services import cache_store
    st = cache_store.get(f"cms:place:{(day or date.today()).strftime('%Y-%m')}") or {}
    top = st.get("top") or {}
    return [{"place": p, "searches": n} for p, n in sorted(top.items(), key=lambda x: -x[1])[:k]]
