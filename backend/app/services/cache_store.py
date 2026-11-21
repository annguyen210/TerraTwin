"""Cache BỀN trong database — dùng chung cho lấy mẫu lưới.

Cache in-memory ở realdata.py vỡ khi chạy nhiều worker uvicorn và mất sạch mỗi
lần restart. Với Heatmap (C06) và Twin Genome (S04) — vốn lấy mẫu hàng chục đến
hàng trăm điểm — điều đó sẽ đốt hết hạn mức Open-Meteo. Bảng kv_cache giải
quyết cả hai vấn đề.

Thiết kế: hỏng cache KHÔNG được làm hỏng request. Mọi lỗi đều nuốt và coi như
cache miss, vì cache chỉ là tối ưu tốc độ chứ không phải nguồn sự thật.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import threading
import zlib
from collections import OrderedDict
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete as _sa_delete, select

# Tham chiếu MODULE chứ không import trực tiếp `SessionLocal`: import trực tiếp
# sẽ khóa cứng vào engine tại thời điểm nạp module, nên đổi engine lúc chạy
# (test, hoặc chuyển sang Postgres sau khi app đã khởi động) sẽ không có tác dụng.
from app import db as _db
from app.db import KVCache


def _session():
    return _db.SessionLocal()


# GIẢM LƯU LƯỢNG RA KHỎI NEON (17/11/2026). Gói Neon miễn phí cho 5 GB truyền dữ liệu/tháng/dự án; tháng 11 dùng hết
# 5,62 GB vào ngày 16 nên API không nối được CSDL tới 1/12. Thủ phạm: mỗi lần mở thửa, get() kéo NGUYÊN khối JSON
# (thời tiết, OSM… tới 0,5–2 MB) từ Neon, lần sau lại kéo y như vậy; sao lưu hằng ngày cũng kéo cả bảng. Hai cách giảm:
#   1. Nhớ đệm trong tiến trình (_MEMO): đọc lại cùng khoá không hỏi CSDL. Giữ CHUỖI JSON chứ không giữ đối tượng —
#      nơi gọi hay sửa thẳng dict trả về (vd water_history._annotate), giữ đối tượng thì lần sau nhận bản đã bị sửa.
#   2. Nén zlib khi ghi khối > _ZMIN ký tự (đo trên CSDL thử: 84 MB → 29 MB). Đọc vẫn hiểu giá trị cũ chưa nén.
_ZTAG = "z1:"
_ZMIN = 1024
_MEMO_MAX = int(float(os.environ.get("TERRATWIN_CACHE_MEMO_MB", "12")) * 1_000_000)
_MEMO: "OrderedDict[str, tuple[str, datetime]]" = OrderedDict()
_memo_size = 0
_memo_owner = None
_lock = threading.Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _encode(payload: str) -> str:
    if len(payload) <= _ZMIN:
        return payload
    z = _ZTAG + base64.b64encode(zlib.compress(payload.encode("utf-8"), 9)).decode("ascii")
    return z if len(z) < len(payload) else payload


def _decode(stored: str) -> str:
    if stored.startswith(_ZTAG):
        return zlib.decompress(base64.b64decode(stored[len(_ZTAG):])).decode("utf-8")
    return stored


def _memo_check_owner() -> None:
    """Đổi SessionLocal (test, hoặc đổi CSDL lúc chạy) thì bỏ hết nhớ đệm — đó là dữ liệu của CSDL khác. Gọi khi giữ _lock."""
    global _memo_owner, _memo_size
    if _memo_owner is not _db.SessionLocal:
        _MEMO.clear()
        _memo_size = 0
        _memo_owner = _db.SessionLocal


def _memo_drop(key: str) -> None:
    global _memo_size
    old = _MEMO.pop(key, None)
    if old is not None:
        _memo_size -= len(old[0])


def _memo_put(key: str, payload: str, expires: datetime) -> None:
    global _memo_size
    with _lock:
        _memo_check_owner()
        _memo_drop(key)
        if len(payload) > _MEMO_MAX // 4:
            return                    # một khối quá to thì không chiếm chỗ của cả trăm khối nhỏ
        _MEMO[key] = (payload, expires)
        _memo_size += len(payload)
        while _memo_size > _MEMO_MAX and _MEMO:
            _, (old, _) = _MEMO.popitem(last=False)
            _memo_size -= len(old)


def memo_clear() -> None:
    global _memo_size
    with _lock:
        _MEMO.clear()
        _memo_size = 0


def make_key(*parts) -> str:
    """Khóa = '<nhóm>:<hash>'. Phần đầu (nhóm, vd 'passport') giữ ĐỌC ĐƯỢC để
    còn xoá theo nhóm khi đổi công thức; phần sau băm để không lộ toạ độ trong
    log. Đổi format này cũng tự vô hiệu mọi cache cũ MỘT LẦN — đúng thứ ta cần
    khi công thức đổi mà cache thì giữ 30 ngày."""
    prefix = str(parts[0]) if parts else "k"
    raw = "|".join(str(p) for p in parts)
    return f"{prefix}:{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:40]}"


def clear_prefix(prefix: str) -> int:
    """Xoá mọi cache thuộc một nhóm (vd 'passport'). Dùng khi đổi công thức mà
    không muốn đợi TTL. Trả số dòng đã xoá."""
    with _lock:
        for k in [k for k in _MEMO if k.startswith(f"{prefix}:")]:
            _memo_drop(k)
    try:
        with _session() as s:
            n = s.execute(
                _sa_delete(KVCache).where(KVCache.key.like(f"{prefix}:%"))).rowcount
            s.commit()
            return n or 0
    except Exception:
        return 0


def delete(key: str) -> None:
    """Xoá đúng MỘT khoá. Khác clear_prefix (xoá cả nhóm) — dùng khi một entry
    cụ thể đã biết là hỏng (vd realdata._bust khi response thiếu trường)."""
    with _lock:
        _memo_drop(key)
    try:
        with _session() as s:
            s.execute(_sa_delete(KVCache).where(KVCache.key == key))
            s.commit()
    except Exception:
        pass


def get(key: str):
    try:
        with _lock:
            _memo_check_owner()
            hit = _MEMO.get(key)
            if hit is not None:
                if hit[1] > _now():
                    _MEMO.move_to_end(key)
                    return json.loads(hit[0])
                _memo_drop(key)
        with _session() as s:
            row = s.get(KVCache, key)
            if row is None:
                return None
            if row.expires_at <= _now():
                s.delete(row)
                s.commit()
                return None
            payload, expires = _decode(row.value), row.expires_at
        _memo_put(key, payload, expires)
        return json.loads(payload)
    except Exception:
        return None      # cache hỏng không được làm hỏng request


def put(key: str, value, ttl_seconds: int) -> None:
    try:
        payload = json.dumps(value, ensure_ascii=False)
        expires = _now() + timedelta(seconds=ttl_seconds)
        stored = _encode(payload)
        with _session() as s:
            row = s.get(KVCache, key)
            if row is None:
                s.add(KVCache(key=key, value=stored, expires_at=expires))
            else:
                row.value = stored
                row.expires_at = expires
            s.commit()
        _memo_put(key, payload, expires)
    except Exception:
        pass


def purge_expired() -> int:
    """Dọn bản ghi hết hạn. Trả số dòng đã xóa."""
    try:
        now = _now()
        with _lock:
            for k in [k for k, (_, exp) in _MEMO.items() if exp <= now]:
                _memo_drop(k)
        with _session() as s:
            n = s.execute(_sa_delete(KVCache).where(KVCache.expires_at <= now)).rowcount
            s.commit()
            return n or 0
    except Exception:
        return 0


def size() -> int:
    try:
        with _session() as s:
            return len(s.execute(select(KVCache.key)).scalars().all())
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# TRẢ BẢN CŨ NGAY, TÍNH LẠI Ở NỀN (kiểm A–Z 21/11/2026, P1-5): /api/scorecard?days=90 mất 40 s, /api/heatmap/flood 37 s ở
# lần gọi đầu — cache RAM mất sau mỗi lần Render khởi động lại/ngủ dậy, cache bền thì hết hạn rồi bắt người kế tiếp chờ tính
# lại. Nay: còn mới → trả; cũ nhưng còn trong hạn `stale_s` → trả NGAY bản cũ và tính lại ở MỘT luồng nền; chưa từng có →
# tính tại chỗ (lần duy nhất). Bản lưu bền nên sống qua khởi động lại.
# ---------------------------------------------------------------------------
import threading as _threading
import time as _time

_swr_running: set[str] = set()
_swr_lock = _threading.Lock()


def swr(key: str, compute, fresh_s: float, stale_s: float):
    """(dữ liệu, trạng thái) — trạng thái: "fresh" | "stale" (đang tính lại ở nền) | "computed"."""
    row = get(key)
    now = _time.time()
    if isinstance(row, dict) and "at" in row and "data" in row:
        age = now - float(row["at"])
        if age < fresh_s:
            return row["data"], "fresh"
        if age < stale_s:
            _swr_refresh(key, compute, stale_s)
            return row["data"], "stale"
    data = compute()
    if data is not None:
        put(key, {"at": now, "data": data}, int(stale_s))
    return data, "computed"


def _swr_refresh(key: str, compute, stale_s: float) -> None:
    with _swr_lock:
        if key in _swr_running:            # đã có luồng đang tính lại khoá này
            return
        _swr_running.add(key)

    def _run():
        try:
            d = compute()
            if d is not None:
                put(key, {"at": _time.time(), "data": d}, int(stale_s))
        except Exception:                  # tính lại hỏng thì giữ bản cũ, lần sau thử lại
            pass
        finally:
            with _swr_lock:
                _swr_running.discard(key)

    _threading.Thread(target=_run, name=f"swr:{key[:24]}", daemon=True).start()
