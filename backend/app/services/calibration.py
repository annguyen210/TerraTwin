"""Hiệu chuẩn chỉ số theo KHÍ HẬU TỪNG ĐIỂM — sửa gốc bệnh báo động giả.

VẤN ĐỀ ĐÃ ĐO ĐƯỢC (2026-08-17): thang tuyệt đối cũ bão hòa ở miền Trung.
Chạy mô hình trọn năm 2022, cửa sổ trượt 7 ngày, ngưỡng nguy hiểm 70:
    Huế       flood  164/358 ngày = 45.8%   (P90=P95=P98=100.0 → chạm trần)
    Quảng Nam flood  217/358 ngày = 60.6%
Một hệ thống hét "nguy hiểm" hơn nửa số ngày thì người dùng sẽ tắt thông báo.

CÁCH SỬA: tách hai tầng.
  1. Động lực vật lý THÔ, KHÔNG chặn trần — giữ nguyên dải biến thiên.
  2. Quy về PHÂN VI so với khí hậu 10 năm của CHÍNH điểm đó (ERA5), rồi ánh xạ
     phi tuyến về thang 0–100 quen thuộc:
         P0–P90  → 0–40   (an toàn)
         P90–P97 → 40–70  (cảnh báo)
         P97–P100→ 70–100 (nguy hiểm)
     ⇒ theo thiết kế, "nguy hiểm" chỉ nổ ~3% số ngày, "cảnh báo" ~10%.

  3. CHỐT TUYỆT ĐỐI: phân vi cao mà động lực vật lý quá nhỏ thì vẫn là an toàn —
     tránh "cực đoan so với hư không" ở vùng khô (mưa 2 mm cũng thành P99).

Đây chính là moat trong §13: ngưỡng bản địa hóa tới từng thửa, không copy được.
"""
from __future__ import annotations

import bisect
import math
import time
from datetime import date, timedelta

from app.services import datasources as ds
from app.services import realdata

_WINDOW = 7
_YEARS = 10
_LAG_DAYS = 10

# Ánh xạ phân vi → thang 0–100 (giữ nguyên ngưỡng 40/70 mà UI đang dùng)
_KNOTS = [(0.0, 0.0), (90.0, 40.0), (97.0, 70.0), (100.0, 100.0)]

# Chốt tuyệt đối: dưới mức này thì hiểm họa không thể xảy ra dù phân vi cao.
# Đơn vị theo động lực thô của từng module.
_FLOOR = {
    "flood": 25.0,      # mưa tích lũy có trọng số (mm) — dưới mức này khó ngập
    "landslide": 20.0,  # mưa tích lũy (mm) trên sườn dốc
    "drought": 30.0,    # thiếu hụt ẩm tích lũy (mm)
    "wildfire": 25.0,   # chỉ số khô-nóng thô
}

_CACHE: dict[tuple, tuple[float, list[float]]] = {}
_TTL = 24 * 3600.0        # L1 in-memory: khí hậu nền đổi chậm — giữ 1 ngày
_DB_TTL = 30 * 24 * 3600  # L2 database (kv_cache): giữ 30 ngày, sống qua restart


# ---------- Tầng 1: động lực vật lý THÔ (không chặn trần) ----------

def raw_flood(rows, elev: float) -> list[tuple[int, str, float]]:
    """Nước dồn có trọng số + phần trũng của địa hình. Không giới hạn trên."""
    terrain = max(0.0, 45.0 - elev * 2.5) / 2.2   # quy về cùng đơn vị "mm tương đương"
    carry = 0.0
    out = []
    for r in rows:
        carry = carry * 0.5 + r["precip"]
        out.append((r["day"], r["date"], round(carry + terrain, 2)))
    return out


def raw_landslide(rows, slope: float) -> list[tuple[int, str, float]]:
    """Mưa tích lũy đã nhân hệ số dốc — đồng bằng phẳng luôn ~0."""
    slope_factor = min(1.0, slope / 18.0)
    carry = 0.0
    out = []
    for r in rows:
        carry = carry * 0.6 + r["precip"]
        driver = max(carry, r["precip"] * 0.667)
        out.append((r["day"], r["date"], round(driver * slope_factor, 2)))
    return out


def raw_drought(rows, deficit0: float = 25.0) -> list[tuple[int, str, float]]:
    """Thiếu hụt ẩm tích lũy (ET₀ − mưa), không chặn trần 100."""
    deficit = deficit0
    out = []
    for r in rows:
        deficit = max(0.0, deficit + (r["et0"] - r["precip"]))
        out.append((r["day"], r["date"], round(deficit, 2)))
    return out


def raw_wildfire(rows, dry0: float = 20.0) -> list[tuple[int, str, float]]:
    dry = dry0
    out = []
    for r in rows:
        dry = max(0.0, dry + (2.0 if r["precip"] < 1.0 else -r["precip"]))
        heat = max(0.0, r["tmax"] - 30.0) * 4.0
        out.append((r["day"], r["date"], round(dry * 0.6 + heat, 2)))
    return out


_RAW = {
    "flood": lambda rows, lat, lon: raw_flood(rows, ds.elevation_proxy(lat, lon)),
    "landslide": lambda rows, lat, lon: raw_landslide(rows, ds.slope_context(lat, lon)[0]),
    "drought": lambda rows, lat, lon: raw_drought(rows),
    "wildfire": lambda rows, lat, lon: raw_wildfire(rows),
}


def raw_series(module_id: str, lat: float, lon: float, rows):
    fn = _RAW.get(module_id)
    return fn(rows, lat, lon) if fn else []


# ---------- Tầng 2: khí hậu nền của CHÍNH điểm đó ----------

def _rolling_peaks(module_id: str, lat: float, lon: float, rows) -> list[float]:
    """Đỉnh động lực thô của mọi cửa sổ 7 ngày trong chuỗi lịch sử."""
    out = []
    for i in range(len(rows) - _WINDOW):
        w = [{**r, "day": j} for j, r in enumerate(rows[i:i + _WINDOW])]
        s = raw_series(module_id, lat, lon, w)
        if s:
            out.append(max(v for _, _, v in s))
    return sorted(out)


def climatology(module_id: str, lat: float, lon: float,
                years: int = _YEARS, today: date | None = None) -> list[float] | None:
    """Phân bố đỉnh động lực thô 10 năm tại điểm này. None nếu không tải được.

    Cache hai tầng để không nã lại 10 năm ERA5 cho mỗi toạ độ sau mỗi restart:
      L1 in-memory  — nhanh nhất, mất khi restart.
      L2 kv_cache DB — sống qua restart & dùng chung giữa nhiều worker uvicorn.
    `last` (năm cuối cửa sổ) nằm trong khóa nên sang năm mới tự lấy lại số liệu.
    """
    today = today or date.today()
    last = (today - timedelta(days=_LAG_DAYS)).year - 1
    key = (module_id, round(lat, 2), round(lon, 2), years, last)
    now = time.time()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < _TTL:
        return hit[1]

    # L2: cache bền trong database (bảng kv_cache).
    from app.services import cache_store   # lazy: tránh phụ thuộc DB khi test thuần
    db_key = cache_store.make_key("clim", module_id, round(lat, 2), round(lon, 2), years, last)
    cached = cache_store.get(db_key)
    if isinstance(cached, list) and cached:
        _CACHE[key] = (now, cached)
        return cached

    rows = realdata.historical_weather(
        lat, lon, date(last - years + 1, 1, 1).isoformat(), date(last, 12, 31).isoformat())
    if not rows:
        return None
    dist = _rolling_peaks(module_id, lat, lon, rows)
    if not dist:
        return None
    _CACHE[key] = (now, dist)
    cache_store.put(db_key, dist, ttl_seconds=_DB_TTL)   # sống qua restart
    return dist


def percentile_of(value: float, dist: list[float]) -> float:
    """Phân vi của `value` trong phân bố đã sắp xếp (0–100)."""
    if not dist:
        return 0.0
    i = bisect.bisect_left(dist, value)
    return 100.0 * i / len(dist)


def map_percentile(p: float) -> float:
    """Phân vi → thang 0–100 theo các mốc _KNOTS (tuyến tính từng khúc)."""
    for (p0, v0), (p1, v1) in zip(_KNOTS, _KNOTS[1:]):
        if p <= p1:
            if p1 == p0:
                return v1
            return v0 + (v1 - v0) * (p - p0) / (p1 - p0)
    return 100.0


# ---------- Kết hợp: chuỗi chỉ số ĐÃ HIỆU CHUẨN ----------

def calibrated_series(module_id: str, lat: float, lon: float, rows,
                      dist: list[float] | None = None,
                      today: date | None = None):
    """Trả (series 0–100 đã hiệu chuẩn, is_calibrated).

    Khi không lấy được khí hậu nền (offline) → trả None để bên gọi tự lùi về
    thang tuyệt đối cũ, và PHẢI gắn cờ chưa hiệu chuẩn cho người dùng biết.
    """
    if dist is None:
        dist = climatology(module_id, lat, lon, today=today)
    if not dist:
        return None, False

    floor = _FLOOR.get(module_id, 0.0)
    out = []
    for d, dt, raw in raw_series(module_id, lat, lon, rows):
        v = map_percentile(percentile_of(raw, dist))
        if raw < floor:
            v = min(v, 39.0)      # chốt tuyệt đối: không đủ động lực vật lý
        out.append((d, dt, round(v, 1)))
    return out, True


def calibrated_with_terrain(module_id: str, lat: float, lon: float, rows,
                            terrain: float, dist: list[float] | None = None,
                            today: date | None = None):
    """Như `calibrated_series` nhưng ÉP giá trị địa hình (cao độ / độ dốc).

    Dùng cho S07 Explain (tắt yếu tố địa hình) và S03 Goal-Seek (tôn nền).
    Phân bố khí hậu nền vẫn là của điểm gốc — đúng ý nghĩa "so với nơi này".
    """
    if module_id not in ("flood", "landslide"):
        return calibrated_series(module_id, lat, lon, rows, dist=dist, today=today)
    if dist is None:
        dist = climatology(module_id, lat, lon, today=today)
    if not dist:
        return None, False

    base = (raw_flood(rows, terrain) if module_id == "flood"
            else raw_landslide(rows, terrain))
    floor = _FLOOR.get(module_id, 0.0)
    out = []
    for d, dt, raw in base:
        v = map_percentile(percentile_of(raw, dist))
        if raw < floor:
            v = min(v, 39.0)
        out.append((d, dt, round(v, 1)))
    return out, True


def alarm_rate(module_id: str, lat: float, lon: float, threshold: float = 70.0,
               years: int = _YEARS, today: date | None = None) -> dict | None:
    """FAR thiết kế: bao nhiêu % cửa sổ trong lịch sử vượt ngưỡng sau hiệu chuẩn."""
    dist = climatology(module_id, lat, lon, years=years, today=today)
    if not dist:
        return None
    floor = _FLOOR.get(module_id, 0.0)
    n_alarm = sum(
        1 for raw in dist
        if raw >= floor and map_percentile(percentile_of(raw, dist)) >= threshold
    )
    return {
        "windows": len(dist),
        "alarms": n_alarm,
        "alarm_rate_pct": round(100.0 * n_alarm / len(dist), 1),
        "threshold": threshold,
    }
