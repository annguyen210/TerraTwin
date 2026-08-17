"""Cache BỀN trong database — dùng chung cho lấy mẫu lưới.

Cache in-memory ở realdata.py vỡ khi chạy nhiều worker uvicorn và mất sạch mỗi
lần restart. Với Heatmap (C06) và Twin Genome (S04) — vốn lấy mẫu hàng chục đến
hàng trăm điểm — điều đó sẽ đốt hết hạn mức Open-Meteo. Bảng kv_cache giải
quyết cả hai vấn đề.

Thiết kế: hỏng cache KHÔNG được làm hỏng request. Mọi lỗi đều nuốt và coi như
cache miss, vì cache chỉ là tối ưu tốc độ chứ không phải nguồn sự thật.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

# Tham chiếu MODULE chứ không import trực tiếp `SessionLocal`: import trực tiếp
# sẽ khóa cứng vào engine tại thời điểm nạp module, nên đổi engine lúc chạy
# (test, hoặc chuyển sang Postgres sau khi app đã khởi động) sẽ không có tác dụng.
from app import db as _db
from app.db import KVCache


def _session():
    return _db.SessionLocal()


def make_key(*parts) -> str:
    """Khóa ngắn, ổn định, không lộ toạ độ chính xác trong log."""
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:48]


def get(key: str):
    try:
        with _session() as s:
            row = s.get(KVCache, key)
            if row is None:
                return None
            if row.expires_at <= datetime.now(timezone.utc).replace(tzinfo=None):
                s.delete(row)
                s.commit()
                return None
            return json.loads(row.value)
    except Exception:
        return None      # cache hỏng không được làm hỏng request


def put(key: str, value, ttl_seconds: int) -> None:
    try:
        payload = json.dumps(value, ensure_ascii=False)
        expires = (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
                   ).replace(tzinfo=None)
        with _session() as s:
            row = s.get(KVCache, key)
            if row is None:
                s.add(KVCache(key=key, value=payload, expires_at=expires))
            else:
                row.value = payload
                row.expires_at = expires
            s.commit()
    except Exception:
        pass


def purge_expired() -> int:
    """Dọn bản ghi hết hạn. Trả số dòng đã xóa."""
    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with _session() as s:
            n = s.execute(delete(KVCache).where(KVCache.expires_at <= now)).rowcount
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
