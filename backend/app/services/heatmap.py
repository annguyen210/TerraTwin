"""C06 — Bản đồ nhiệt rủi ro quanh thửa đất.

Lấy mẫu lưới N×N quanh điểm người dùng chọn, chạy ĐÚNG mô hình cảnh báo trên
từng ô, trả GeoJSON để bản đồ tô màu. Nhờ Open-Meteo nhận nhiều toạ độ trong
một lần gọi, cả lưới 49 ô chỉ tốn 2 lượt gọi (~0,5 s) chứ không phải 49 lượt.

HAI ĐIỀU TRUNG THỰC ĐÃ GHI RÕ TRONG KẾT QUẢ:
1. Khí hậu nền để hiệu chuẩn lấy ở TÂM lưới rồi dùng chung cho cả lưới. Trên
   phạm vi ~10 km khí hậu gần như đồng nhất, nên chấp nhận được — nhưng phải
   nói ra, vì đó là xấp xỉ chứ không phải hiệu chuẩn riêng từng ô.
2. Độ phân giải thật của dữ liệu nền (~11 km với ECMWF, ~90 m với DEM) THÔ HƠN
   ô lưới. Bản đồ mượt không có nghĩa là biết chi tiết tới từng mét.
"""
from __future__ import annotations

import math

from app.services import cache_store, calibration, hazard
from app.services import datasources as ds
from app.services import realdata

_TTL = 3600            # dự báo đổi theo giờ
_MAX_SIDE = 11         # trần 121 ô — đủ mượt mà vẫn 1 lượt gọi
_NATIVE_RES_KM = 11.0  # độ phân giải thật của mô hình thời tiết nền


def _grid(lat: float, lon: float, radius_km: float, side: int):
    """Lưới side×side phủ ô vuông bán kính radius_km quanh tâm."""
    dlat = radius_km / 111.0
    dlon = radius_km / (111.0 * max(0.15, math.cos(math.radians(lat))))
    pts = []
    for r in range(side):
        fy = (r / (side - 1)) * 2 - 1 if side > 1 else 0.0
        for c in range(side):
            fx = (c / (side - 1)) * 2 - 1 if side > 1 else 0.0
            pts.append((round(lat + fy * dlat, 5), round(lon + fx * dlon, 5)))
    return pts, dlat * 2 / max(1, side - 1), dlon * 2 / max(1, side - 1)


def build(module_id: str, lat: float, lon: float,
          radius_km: float = 8.0, side: int = 7) -> dict | None:
    if not hazard.supports(module_id):
        return None
    name, unit = hazard.name_unit(module_id)
    side = max(3, min(int(side), _MAX_SIDE))
    radius_km = max(1.0, min(float(radius_km), 40.0))

    ckey = cache_store.make_key("heatmap", module_id, round(lat, 3), round(lon, 3),
                                radius_km, side)
    cached = cache_store.get(ckey)
    if cached:
        cached["cached"] = True
        return cached

    pts, cell_dlat, cell_dlon = _grid(lat, lon, radius_km, side)

    # 1 lượt gọi cho toàn bộ lưới
    weather = realdata.weather_multi(pts)
    elevs = (realdata.elevation_multi(pts)
             if module_id in ("flood", "landslide") else [None] * len(pts))

    # Khí hậu nền lấy ở TÂM, dùng chung cả lưới (xấp xỉ đã ghi rõ ở trên).
    dist = calibration.climatology(module_id, lat, lon)

    cells = []
    values = []
    for i, (la, lo) in enumerate(pts):
        rows = weather[i] if i < len(weather) else None
        if not rows:
            cells.append({"lat": la, "lon": lo, "value": None, "risk": "unknown"})
            continue

        if dist:
            if module_id == "flood" and elevs[i] is not None:
                series, _ = calibration.calibrated_with_terrain(
                    module_id, lat, lon, rows, terrain=elevs[i], dist=dist)
            elif module_id == "landslide":
                slope, _ = ds.slope_context(la, lo)
                series, _ = calibration.calibrated_with_terrain(
                    module_id, lat, lon, rows, terrain=slope, dist=dist)
            else:
                series, _ = calibration.calibrated_series(
                    module_id, la, lo, rows, dist=dist)
        else:
            series = hazard.index_series_absolute(module_id, la, lo, rows)

        peak = hazard.peak_of(series or [])
        risk = ("danger" if peak >= hazard.WARNING
                else "warning" if peak >= hazard.SAFE else "safe")
        cells.append({"lat": la, "lon": lo, "value": round(peak, 1), "risk": risk})
        values.append(peak)

    n_danger = sum(1 for c in cells if c["risk"] == "danger")
    n_warning = sum(1 for c in cells if c["risk"] == "warning")
    hottest = max((c for c in cells if c["value"] is not None),
                  key=lambda c: c["value"], default=None)

    if not values:
        headline = "Chưa lấy được dữ liệu thời tiết cho vùng này."
    elif n_danger:
        headline = (f"{n_danger}/{len(cells)} ô ở mức nguy hiểm — "
                    f"cao nhất {hottest['value']} {unit}.")
    elif n_warning:
        headline = f"{n_warning}/{len(cells)} ô ở mức cảnh báo, chưa ô nào nguy hiểm."
    else:
        headline = f"Toàn vùng an toàn — cao nhất {max(values):.1f} {unit}."

    result = {
        "module_id": module_id, "module_name": name, "unit": unit,
        "center": {"lat": lat, "lon": lon},
        "radius_km": radius_km, "side": side, "cells": cells,
        "cell_dlat": round(cell_dlat, 6), "cell_dlon": round(cell_dlon, 6),
        "calibrated": bool(dist),
        "safe": hazard.SAFE, "warning": hazard.WARNING,
        "n_danger": n_danger, "n_warning": n_warning,
        "hottest": hottest,
        "headline": headline,
        "cached": False,
        "caveat": (
            f"Lưới {side}×{side} phủ bán kính {radius_km:g} km. Khí hậu nền để "
            "hiệu chuẩn lấy ở TÂM lưới và dùng chung — xấp xỉ hợp lý ở quy mô này. "
            f"Độ phân giải THẬT của mô hình thời tiết nền là ~{_NATIVE_RES_KM:g} km, "
            "thô hơn ô lưới: bản đồ mượt không có nghĩa là biết chi tiết tới từng mét."
            if dist else
            "Chưa lấy được khí hậu nền — đang dùng thang tuyệt đối CHƯA hiệu chuẩn, "
            "tỉ lệ báo động có thể cao."
        ),
        "method": ("Chạy đúng mô hình cảnh báo trên từng ô lưới; toàn bộ lưới lấy "
                   "trong 1–2 lượt gọi Open-Meteo nhờ truy vấn đa toạ độ."),
    }
    cache_store.put(ckey, result, _TTL)
    return result
