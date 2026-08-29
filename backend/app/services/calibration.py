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

# Địa hình của một toạ độ KHÔNG đổi giữa các cửa sổ thời gian. Tra nó bên trong
# vòng lặp là hỏi cùng một câu 3.646 lần.
_TERRAIN = {
    "flood": lambda lat, lon: ds.elevation_proxy(lat, lon),
    "landslide": lambda lat, lon: ds.slope_context(lat, lon)[0],
}
_RAW_FIXED = {
    "flood": raw_flood,
    "landslide": raw_landslide,
    "drought": lambda rows, _: raw_drought(rows),
    "wildfire": lambda rows, _: raw_wildfire(rows),
}


def _rolling_peaks(module_id: str, lat: float, lon: float, rows) -> list[float]:
    """Đỉnh động lực thô của mọi cửa sổ 7 ngày trong chuỗi lịch sử.

    ĐỊA HÌNH ĐƯỢC TRA MỘT LẦN, ngoài vòng lặp. Bản trước gọi raw_series() cho
    từng cửa sổ, mà với lũ và sạt lở thì raw_series lại tra cao độ/độ dốc — tức
    là hỏi cùng một câu 3.646 lần cho một toạ độ không hề di chuyển. Kết quả tuy
    lấy từ cache nhưng riêng chi phí gọi hàm đã chiếm gần hết thời gian: đo được
    lũ 1,04s và sạt lở 0,91s, trong khi hạn và cháy — hai module không cần địa
    hình — chỉ mất 0,04s.
    """
    fn = _RAW_FIXED.get(module_id)
    if fn is None:
        return []
    dh = _TERRAIN.get(module_id)
    terrain = dh(lat, lon) if dh else None
    if dh is not None and terrain is None:
        return []

    out = []
    n = len(rows)
    for i in range(n - _WINDOW):
        w = [{**r, "day": j} for j, r in enumerate(rows[i:i + _WINDOW])]
        s = fn(w, terrain)
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


# ────────────────────── ĐỐI CHỨNG: ngưỡng chung cả nước ──────────────────────
#
# VÌ SAO CẦN CON SỐ NÀY. Điểm mạnh nhất của TerraTwin là thứ VÔ HÌNH theo đúng
# nghĩa đen: báo động giả 3% nghĩa là những lần kêu oan ĐÃ KHÔNG XẢY RA, mà
# không ai nhìn thấy được thứ không xảy ra. Người dùng mở app lên chỉ thấy "hôm
# nay an toàn" — giống hệt mọi phần mềm khác. Cách duy nhất làm cái vô hình đó
# hiện lên là cho xem ĐỐI CHỨNG: ở chính thửa này, một hệ thống dùng ngưỡng
# chung sẽ báo động bao nhiêu ngày.
#
# ĐỊNH NGHĨA CHẶT, không phải con số bịa cho dễ thắng: lấy giá trị động lực thô
# ở phân vị 97 khi GỘP CẢ NƯỚC, rồi áp đúng con số đó ở mọi nơi. Đó chính xác là
# ý nghĩa của "một ngưỡng chung cho toàn quốc", và nó được chọn ở P97 để CÙNG
# mục tiêu thiết kế với bản hiệu chuẩn — tức là đối thủ mạnh, không phải hình nộm.
#
# Đo từ 58.336 cửa sổ 7 ngày thật: 16 điểm phủ hết các kiểu khí hậu Việt Nam
# (Hà Giang → Cà Mau), 10 năm ERA5, kèm cao độ và độ dốc thật của từng điểm.
# Cách tính lại: xem app/ml/dataset.py SITES và hàm raw_* ngay phía trên.
# LƯU Ý PHƯƠNG PHÁP — đây là chỗ tôi đã tính SAI một lần và phải làm lại.
# climatology() trả về ĐỈNH CỦA TỪNG CỬA SỔ 7 NGÀY, và bộ tích luỹ được đặt lại
# ở mỗi cửa sổ. Lần đầu tôi tính hằng số này trên một chuỗi liền 10 năm, nơi
# thiếu hụt ẩm của raw_drought cộng dồn không giới hạn tới hàng nghìn. Hai phân
# bố khác hẳn nhau, nên ngưỡng hạn ra 3.623 và không nơi nào trên cả nước chạm
# tới — đối chứng hiện "0 ngày/năm" ở cả Phan Rang, chỗ khô hạn nhất Việt Nam.
# Con số vô lý đó là thứ duy nhất làm lộ ra lỗi. Nay tính bằng ĐÚNG quy trình
# _rolling_peaks, gộp 58.336 cửa sổ.
NATIONAL_P97 = {
    "flood": 95.23,
    "landslide": 28.07,
    "drought": 64.48,
    "wildfire": 45.28,
}


def contrast(module_id: str, lat: float, lon: float,
             threshold: float = 70.0, today: date | None = None) -> dict | None:
    """So số ngày báo động: ngưỡng chung cả nước vs hiệu chuẩn theo nơi này.

    Không tốn thêm lượt gọi mạng nào — dùng lại đúng phân bố 10 năm mà
    climatology() đã tải và cache cho việc hiệu chuẩn.
    """
    fixed = NATIONAL_P97.get(module_id)
    if fixed is None:
        return None
    dist = climatology(module_id, lat, lon, today=today)
    if not dist:
        return None

    floor = _FLOOR.get(module_id, 0.0)
    n = len(dist)
    n_fixed = sum(1 for raw in dist if raw >= fixed)
    n_cal = sum(
        1 for raw in dist
        if raw >= floor and map_percentile(percentile_of(raw, dist)) >= threshold
    )

    # Quy ra ngày/năm — đơn vị người đọc hình dung được ngay, khác với "%" là
    # thứ phải nhân chia trong đầu mới thấy được mức độ phiền.
    per_year = 365.0 / n if n else 0.0
    fixed_yr = round(n_fixed * per_year * (n / 365.0) / max(n / 365.0, 1e-9))
    cal_yr = round(n_cal * per_year * (n / 365.0) / max(n / 365.0, 1e-9))
    years = max(n / 365.0, 1e-9)

    return {
        "module_id": module_id,
        "windows": n,
        "years": round(years, 1),
        "fixed_threshold": fixed,
        "fixed_alarms": n_fixed,
        "fixed_days_per_year": round(n_fixed / years, 1),
        "calibrated_alarms": n_cal,
        "calibrated_days_per_year": round(n_cal / years, 1),
        "method": (
            "Ngưỡng chung = giá trị thô ở phân vị 97 khi gộp 16 điểm phủ cả "
            "nước, 58.336 cửa sổ 7 ngày ERA5. Hiệu chuẩn = phân vị 97 của riêng "
            "toạ độ này. Cả hai cùng mục tiêu thiết kế, chỉ khác chỗ lấy nền so."),
    }


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
