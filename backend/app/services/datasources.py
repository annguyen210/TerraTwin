"""Tầng nguồn dữ liệu — ưu tiên DỮ LIỆU THẬT (Open-Meteo/NASA POWER),
tự fallback sang mô hình mẫu khi offline để app luôn chạy.

Còn placeholder (cần nguồn thật khi mở rộng):
  - Độ mặn -> Ủy hội sông Mekong (MRC) / trạm thủy văn tỉnh (chưa có API mở)
  - Ảnh Sentinel quang học/radar -> Copernicus/Sentinel Hub (cần API key)
"""
from __future__ import annotations

import hashlib
import math
from datetime import date, timedelta

from app.services import realdata

# Điểm neo dọc ĐƯỜNG BỜ BIỂN Việt Nam (Móng Cái → Cà Mau → Hà Tiên) để đo
# khoảng cách tới biển gần nhất trên toàn quốc — thay cho 1 điểm cứng ở Bến Tre
# (bug cũ khiến Hạ Long bị tính "cách biển 1272 km").
_COASTLINE = [
    (21.52, 108.02), (21.00, 107.35), (20.95, 107.08), (20.75, 106.75),
    (20.28, 106.55), (20.10, 106.35), (19.75, 105.90), (18.80, 105.75),
    (18.35, 106.02), (17.48, 106.62), (16.90, 107.12), (16.55, 107.60),
    (16.05, 108.22), (15.88, 108.38), (15.12, 108.90), (14.20, 109.20),
    (13.77, 109.28), (13.10, 109.32), (12.24, 109.20), (11.90, 109.15),
    (11.56, 109.02), (10.93, 108.10), (10.55, 107.55), (10.35, 107.08),
    (10.35, 106.75), (9.95, 106.65), (9.60, 106.50), (9.30, 106.10),
    (9.28, 105.72), (8.65, 104.90), (8.60, 104.83), (9.20, 104.75),
    (10.00, 104.98), (10.38, 104.48),
]


def _seed_key(lat: float, lon: float, key: str) -> float:
    h = hashlib.md5(f"{lat:.3f},{lon:.3f},{key}".encode()).hexdigest()
    return (int(h[:8], 16) % 1000) / 1000.0


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def distance_to_coast_km(lat: float, lon: float) -> float:
    """Khoảng cách tới điểm bờ biển VN gần nhất (km) — min haversine tới đường bờ."""
    return round(min(_haversine_km(lat, lon, cla, clo) for cla, clo in _COASTLINE), 1)


def _dates(n: int = 7):
    today = date.today()
    return [(i, (today + timedelta(days=i)).isoformat()) for i in range(n)]


def series(lat: float, lon: float, key: str, base: float,
           amp: float = 0.2, trend: float = 0.03,
           ndays: int = 7, digits: int = 1):
    """Chuỗi 7 ngày MẪU (dùng khi không có dữ liệu thật)."""
    off = _seed_key(lat, lon, key)
    out = []
    for d, dt in _dates(ndays):
        wave = 1.0 + amp * math.sin((d / ndays) * 2 * math.pi + off * 6.283)
        out.append((d, dt, round(max(0.0, base * wave * (1.0 + trend * d)), digits)))
    return out


# ---------- Cao độ / bức xạ (thật + fallback) ----------

def elevation_proxy(lat: float, lon: float) -> float:
    real = realdata.elevation_m(lat, lon)
    if real is not None:
        return round(real, 1)
    return round(2.0 + distance_to_coast_km(lat, lon) * 0.12 + _seed_key(lat, lon, "elev") * 15.0, 1)


def slope_context(lat: float, lon: float):
    """(độ_dốc, is_real). Ưu tiên độ dốc THẬT từ DEM Open-Meteo (4 hướng),
    fallback mô hình mẫu khi offline."""
    real = realdata.slope_deg(lat, lon)
    if real is not None:
        return real, True
    mock = round(max(0.0, (lat - 10.5)) * 3.0 + _seed_key(lat, lon, "slope") * 20.0, 1)
    return mock, False


def slope_proxy(lat: float, lon: float) -> float:
    """Độ dốc (độ) — dùng DEM thật nếu có, fallback mẫu."""
    return slope_context(lat, lon)[0]


def solar_radiation(lat: float, lon: float):
    """(giá trị, is_real). Bức xạ kWh/m²/ngày."""
    real = realdata.solar_annual(lat, lon)
    if real is not None:
        return round(real, 2), True
    return round(4.2 + _seed_key(lat, lon, "solar") * 1.3, 2), False


# ---------- Độ mặn: ƯỚC LƯỢNG VẬT LÝ theo bờ biển + triều (chờ hiệu chỉnh MRC) ----------
# KHÔNG dùng offset ngẫu nhiên. Mặn suy giảm theo khoảng cách bờ biển gần nhất
# (hàm mũ) và dao động theo triều. Xa biển ~0 → không báo động giả nội địa.

def get_salinity_context(lat: float, lon: float) -> dict:
    dist = distance_to_coast_km(lat, lon)
    elev = elevation_proxy(lat, lon)   # cao độ THẬT (Open-Meteo)
    # Xâm nhập mặn = hiện tượng vùng THẤP ven biển. Hai yếu tố vật lý:
    #  - khoảng cách bờ biển (suy giảm mũ, e-fold ~30 km)
    #  - cao độ: nước mặn không leo cao; >25 m coi như không ảnh hưởng.
    dist_factor = math.exp(-dist / 30.0)
    elev_factor = max(0.0, min(1.0, (25.0 - elev) / 25.0))
    base = 8.0 * dist_factor * elev_factor
    out = []
    for d, dt in _dates(7):
        tide = 1.0 + 0.35 * math.sin((d / 7.0) * 2 * math.pi)
        out.append((d, dt, round(base * tide * (1.0 + 0.04 * d), 2)))
    return {"distance_to_coast_km": dist, "elevation_m": elev, "series": out}


# ---------- Chỉ số THUẦN từ chuỗi thời tiết (dùng chung: dự báo + backtest) ----------
# Nhận list dict {day,date,precip,et0,tmax}; trả list (day,date,value).
# Nhờ tách thuần nên chạy y hệt nhau cho dữ liệu tương lai (forecast) lẫn quá khứ (archive).

def drought_index(rows, deficit0: float = 25.0):
    deficit = deficit0
    out = []
    for r in rows:
        deficit = min(100.0, max(0.0, deficit + (r["et0"] - r["precip"])))
        out.append((r["day"], r["date"], round(deficit, 1)))
    return out


def flood_index(rows, elev: float):
    low = max(0.0, 45.0 - elev * 2.5)
    carry = 0.0
    out = []
    for r in rows:
        carry = carry * 0.5 + r["precip"]
        out.append((r["day"], r["date"], round(min(100.0, low + carry * 2.2), 1)))
    return out


def wildfire_index(rows, dry0: float = 20.0):
    dry = dry0
    out = []
    for r in rows:
        dry = min(100.0, max(0.0, dry + (2.0 if r["precip"] < 1.0 else -r["precip"])))
        heat = max(0.0, (r["tmax"] - 30.0)) * 4.0
        out.append((r["day"], r["date"], round(min(100.0, dry * 0.6 + heat), 1)))
    return out


# Ngưỡng độ dốc "nhạy cao": DEM công khai ~90m làm mượt sườn dốc nên đo nhẹ hơn
# thực tế → dùng 18° (không phải 30°) làm mốc nhạy cao cho dữ liệu DEM thô.
_SLOPE_HIGH = 18.0


def landslide_index(rows, slope: float):
    """Sạt lở = ĐỘ DỐC × MƯA. Kích hoạt bởi mưa tích lũy nhiều ngày HOẶC
    mưa cực đoan 1 ngày (đều đã được 'khóa' bởi độ dốc → đồng bằng luôn ~0)."""
    slope_factor = min(1.0, slope / _SLOPE_HIGH)
    carry = 0.0
    out = []
    for r in rows:
        carry = carry * 0.6 + r["precip"]
        rain_factor = min(1.0, max(carry / 80.0, r["precip"] / 120.0))
        out.append((r["day"], r["date"], round(min(95.0, 100.0 * slope_factor * (0.2 + 0.8 * rain_factor)), 1)))
    return out


# ---------- Chuỗi chỉ số cho DỰ BÁO 7 ngày (thật + fallback mẫu). Trả (series, is_real). ----------

def drought_series(lat: float, lon: float):
    w = realdata.weather_7d(lat, lon)
    if w:
        return drought_index(w), True
    base = 35 + _seed_key(lat, lon, "drought") * 45
    return series(lat, lon, "drought", base, amp=0.18, trend=0.04), False


def flood_series(lat: float, lon: float):
    w = realdata.weather_7d(lat, lon)
    elev = elevation_proxy(lat, lon)
    if w:
        return flood_index(w, elev), True
    base = max(8.0, 80.0 - elev * 4.0)
    return series(lat, lon, "flood", base, amp=0.28, trend=0.02), False


def wildfire_series(lat: float, lon: float):
    w = realdata.weather_7d(lat, lon)
    if w:
        return wildfire_index(w), True
    base = 25 + _seed_key(lat, lon, "fire") * 55
    return series(lat, lon, "fire", base, amp=0.15), False


def landslide_series(lat: float, lon: float):
    """Sạt lở = ĐỘ DỐC × MƯA TÍCH LŨY. Đất phẳng (đồng bằng) ~0 dù mưa lớn."""
    w = realdata.weather_7d(lat, lon)
    slope, slope_real = slope_context(lat, lon)
    if w:
        return landslide_index(w, slope), (slope_real and True)
    slope_factor = min(1.0, slope / _SLOPE_HIGH)
    base = 100.0 * slope_factor * (0.25 + 0.6 * _seed_key(lat, lon, "slide"))
    return series(lat, lon, "slide", max(2.0, base), amp=0.3, trend=0.02), False


def recent_precip_total(lat: float, lon: float):
    w = realdata.weather_7d(lat, lon)
    if w:
        return round(sum(r["precip"] for r in w), 1), True
    return None, False
