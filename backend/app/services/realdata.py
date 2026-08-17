"""Nguồn dữ liệu THẬT, miễn phí, không cần API key.

- Open-Meteo (nền ECMWF): dự báo mưa, bốc thoát hơi (ET₀), nhiệt độ, cao độ.
- NASA POWER: bức xạ mặt trời (climatology).

Có cache 30 phút + tự fallback (trả None) khi offline/timeout để app luôn chạy.
Ảnh vệ tinh Sentinel (quang học/radar) cần API key → thêm ở đây khi triển khai.
"""
from __future__ import annotations

import json
import math
import time
import urllib.request

_CACHE: dict[str, tuple[float, object]] = {}
_TTL = 1800  # giây


def _get(url: str, timeout: float = 8.0):
    now = time.time()
    hit = _CACHE.get(url)
    if hit and now - hit[0] < _TTL:
        return hit[1]
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "TerraTwin/0.2"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        _CACHE[url] = (now, data)
        return data
    except Exception:
        return None


def _bust(url: str) -> None:
    """Xóa cache một URL để lần gọi sau fetch lại (tự lành khi response hỏng)."""
    _CACHE.pop(url, None)


def _num(x):
    """Trả float nếu là số thật; None nếu thiếu dữ liệu (KHÔNG nhầm null thành 0)."""
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def weather_7d(lat: float, lon: float):
    """Dự báo 7 ngày THẬT. Trả list dict {day,date,precip,et0,tmax} hoặc None.

    Phân biệt null (thiếu dữ liệu) vs 0.0 (thật sự không mưa). Nếu Open-Meteo trả
    mảng mưa toàn null (dữ liệu chưa sẵn), coi như KHÔNG hợp lệ → None + xóa cache
    để lần sau fetch lại (tránh 'khô giả' bị kẹt 30 phút).
    """
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&daily=precipitation_sum,et0_fao_evapotranspiration,temperature_2m_max"
        "&forecast_days=7&timezone=auto"
    )
    d = _get(url)
    if not d or "daily" not in d:
        return None
    dd = d["daily"]
    try:
        times = dd["time"]
        precip = [_num(v) for v in dd.get("precipitation_sum", [])]
        et0 = [_num(v) for v in dd.get("et0_fao_evapotranspiration", [])]
        tmax = [_num(v) for v in dd.get("temperature_2m_max", [])]
    except (KeyError, TypeError):
        _bust(url)
        return None

    # Bắt buộc có ≥ nửa số ngày với lượng mưa thật; nếu không → dữ liệu chưa sẵn.
    valid_precip = [p for p in precip if p is not None]
    if not times or len(valid_precip) < max(1, len(times) // 2):
        _bust(url)
        return None

    rows = []
    for i in range(len(times)):
        rows.append({
            "day": i, "date": times[i],
            "precip": precip[i] if i < len(precip) and precip[i] is not None else 0.0,
            "et0": et0[i] if i < len(et0) and et0[i] is not None else 0.0,
            "tmax": tmax[i] if i < len(tmax) and tmax[i] is not None else 0.0,
        })
    return rows


def elevation_m(lat: float, lon: float):
    d = _get(f"https://api.open-meteo.com/v1/elevation?latitude={lat}&longitude={lon}")
    try:
        return float(d["elevation"][0])
    except (KeyError, IndexError, TypeError):
        return None


def slope_deg(lat: float, lon: float, step_m: float = 500.0):
    """Độ dốc THẬT (độ) từ chênh cao độ 4 hướng lân cận (Open-Meteo DEM).

    Lấy cao độ tại tâm + Bắc/Nam/Đông/Tây cách ~step_m, tính gradient địa hình
    rồi quy ra góc dốc. Trả None nếu không lấy được dữ liệu.
    """
    dlat = step_m / 111_320.0
    dlon = step_m / (111_320.0 * max(0.1, math.cos(math.radians(lat))))
    # thứ tự: tâm, Bắc, Nam, Đông, Tây
    lats = [lat, lat + dlat, lat - dlat, lat, lat]
    lons = [lon, lon, lon, lon + dlon, lon - dlon]
    lat_q = ",".join(f"{v:.5f}" for v in lats)
    lon_q = ",".join(f"{v:.5f}" for v in lons)
    d = _get(f"https://api.open-meteo.com/v1/elevation?latitude={lat_q}&longitude={lon_q}")
    try:
        e = [float(x) for x in d["elevation"]]
        _c, n, s, ea, w = e[0], e[1], e[2], e[3], e[4]
        dz_ns = (n - s) / (2 * step_m)
        dz_ew = (ea - w) / (2 * step_m)
        grad = math.hypot(dz_ns, dz_ew)
        return round(math.degrees(math.atan(grad)), 1)
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def historical_weather(lat: float, lon: float, start: str, end: str):
    """Thời tiết THẬT trong quá khứ (Open-Meteo Archive, nền ERA5, không cần key).

    Dùng cho backtest kiểm chứng: model có báo trước sự kiện thật hay không.
    Trả list dict {day,date,precip,et0,tmax} hoặc None.
    """
    url = (
        "https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={lat}&longitude={lon}"
        f"&start_date={start}&end_date={end}"
        "&daily=precipitation_sum,et0_fao_evapotranspiration,temperature_2m_max"
        "&timezone=auto"
    )
    d = _get(url, timeout=15.0)
    if not d or "daily" not in d:
        return None
    dd = d["daily"]
    try:
        return [
            {
                "day": i,
                "date": dd["time"][i],
                "precip": float(dd["precipitation_sum"][i] or 0.0),
                "et0": float((dd.get("et0_fao_evapotranspiration") or [])[i] or 0.0),
                "tmax": float((dd.get("temperature_2m_max") or [])[i] or 0.0),
            }
            for i in range(len(dd["time"]))
        ]
    except (KeyError, IndexError, TypeError):
        return None


def solar_annual(lat: float, lon: float):
    """Bức xạ mặt trời trung bình năm (kWh/m²/ngày) từ NASA POWER."""
    url = (
        "https://power.larc.nasa.gov/api/temporal/climatology/point"
        "?parameters=ALLSKY_SFC_SW_DWN&community=RE"
        f"&longitude={lon}&latitude={lat}&format=JSON"
    )
    d = _get(url, timeout=12.0)
    try:
        return float(d["properties"]["parameter"]["ALLSKY_SFC_SW_DWN"]["ANN"])
    except (KeyError, TypeError):
        return None
