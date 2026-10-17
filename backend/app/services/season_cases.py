"""TẬP CA THẬT TỪ NGƯỜI DÙNG cho lớp mùa lũ v4 (17/10/2026, việc 5 của yêu cầu v3).

Mỗi lần người dùng nói "ruộng có ngập thật" (trả lời một chạm, hoặc tự ghi quan sát lũ) mà ngày đó rơi vào một ĐỢT NƯỚC
bị lớp mùa lũ v1 xếp "ngoài mùa" → lưu thành một ca kiểm dương tính cho phiên bản sau. Đó chính là loại ca mà v2/v3 thiếu:
lũ sớm/muộn CÓ NGƯỜI XÁC NHẬN, thay cho danh sách bão tự chọn.

Không chạy radar ở đây (vài phút) — chỉ đọc lịch sử nước đã có trong cache. Chưa đọc thì không có ca; không đoán.
Toạ độ thô giữ trong CSDL như quan sát gốc (không công khai); xuất ra để đăng ký cổng phải làm tròn.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

NEAR_DAYS = 6          # quan sát cách ngày bắt đầu đợt ≤ 6 ngày (chu kỳ chụp) thì coi là cùng đợt
CELL = 0.001           # ~100 m: cùng người, cùng đợt, trong ô này = cùng một ca


def capture(db: Session, obs) -> object | None:
    """Ghi một ca nếu quan sát `obs` (Observation) là lũ có xảy ra và rơi vào đợt v1 'ngoài mùa'. Trả bản ghi hoặc None."""
    from app.db import SeasonCase
    if obs.module_id != "flood" or obs.outcome != "occurred":
        return None
    if obs.id is not None and db.execute(select(SeasonCase.id).where(SeasonCase.observation_id == obs.id)).first():
        return None
    return capture_at(db, obs.lat, obs.lon, obs.observed_on, obs.user_id, obs.source or "user", obs.id)


def capture_at(db: Session, lat: float, lon: float, observed_on: str, user_id: int | None, source: str,
               observation_id: int | None = None) -> object | None:
    """Lõi chung: ngày `observed_on` (ruộng có ngập) rơi vào một đợt radar v1 'ngoài mùa' ở (lat, lon) → ghi SeasonCase.
    source "event" = người dùng bấm "Có ngập" ngay trên đợt đó (routes_water /api/water/confirm)."""
    from app.db import SeasonCase
    from app.services import cache_store, flood_season as fs, water_history as wh
    try:
        d = date.fromisoformat(observed_on)
    except (TypeError, ValueError):
        return None
    h = cache_store.get(wh.cache_key(lat, lon))
    if not h or not h.get("available") or not h.get("events"):
        return None
    s = fs.season(lat, lon)
    if not s:
        return None
    near = [e for e in h["events"] if abs((date.fromisoformat(e["start"]) - d).days) <= NEAR_DAYS
            or e["start"] <= d.isoformat() <= e["end"]]
    if not near:
        return None
    e = min(near, key=lambda e: abs((date.fromisoformat(e["start"]) - d).days))
    if fs.label(e["start"], s) != "out":
        return None
    if user_id is not None and db.execute(select(SeasonCase.id).where(
            SeasonCase.user_id == user_id, SeasonCase.event_start == e["start"],
            SeasonCase.lat.between(lat - CELL, lat + CELL), SeasonCase.lon.between(lon - CELL, lon + CELL))).first():
        return None                                     # cùng người đã có ca cho đợt này ở thửa này — một người, một ca
    row = SeasonCase(observation_id=observation_id, user_id=user_id, lat=lat, lon=lon, observed_on=observed_on,
                     event_start=e["start"], event_end=e["end"], v1_label="out", source=source,
                     season_months=",".join(str(m) for m in s["months"]))
    db.add(row)
    return row

