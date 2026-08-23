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


_SLOPE_STEP_M = 500.0     # cùng bước với realdata.slope_deg, để hai bên khớp nhau


def _grid_slopes(pts):
    """Độ dốc cho MỌI ô của lưới trong một lượt gọi, thay vì mỗi ô một lượt.

    Với mỗi ô cần cao độ ở 4 hướng lân cận (Bắc/Nam/Đông/Tây cách ~500 m) — y
    hệt realdata.slope_deg, chỉ khác là gom hết điểm của cả lưới lại rồi hỏi
    một lần. elevation_multi tự chia lô 100 điểm và chạy các lô song song.

    Lưới 7×7 nghĩa là 49×4 = 196 điểm, gọn trong hai lô. So với 49 lượt gọi
    riêng của bản cũ.

    Trả list cùng thứ tự với `pts`, phần tử None khi thiếu dữ liệu — người gọi
    tự lùi về cách cũ cho riêng ô đó.
    """
    need = []
    for la, lo in pts:
        dlat = _SLOPE_STEP_M / 111_320.0
        dlon = _SLOPE_STEP_M / (111_320.0 * max(0.1, math.cos(math.radians(la))))
        need += [(round(la + dlat, 5), round(lo, 5)),
                 (round(la - dlat, 5), round(lo, 5)),
                 (round(la, 5), round(lo + dlon, 5)),
                 (round(la, 5), round(lo - dlon, 5))]

    got = realdata.elevation_multi(need) or []
    if len(got) < len(need):
        return None

    out = []
    for i in range(len(pts)):
        n, s_, e_, w = got[i * 4:i * 4 + 4]
        if None in (n, s_, e_, w):
            out.append(None)
            continue
        dz_ns = (n - s_) / (2 * _SLOPE_STEP_M)
        dz_ew = (e_ - w) / (2 * _SLOPE_STEP_M)
        out.append(round(math.degrees(math.atan(math.hypot(dz_ns, dz_ew))), 1))
    return out


def _prepare(module_id: str, lat: float, lon: float,
             radius_km: float, side: int, rows_override=None) -> dict:
    """Lấy toàn bộ dữ liệu nền cho một lưới. Dùng chung cho bản đồ nhiệt và
    dòng thời gian — hai bên PHẢI đọc cùng một nguồn.

    Nhân đôi logic ở đây là cách chắc chắn nhất để hai màn hình nói hai chuyện
    khác nhau về cùng một chỗ. Dự án này đã mất một đợt để dẹp đúng loại lệch
    đó giữa thẻ mô-đun và bản đồ nhiệt.
    """
    pts, cell_dlat, cell_dlon = _grid(lat, lon, radius_km, side)

    weather = realdata.weather_multi(pts)
    elevs = (realdata.elevation_multi(pts)
             if module_id in ("flood", "landslide") else [None] * len(pts))

    # Độ dốc cho CẢ lưới trong một lượt, thay vì hỏi từng ô.
    #
    # Trước đây vòng lặp gọi ds.slope_context(la, lo) cho từng ô — mỗi lượt là
    # một truy vấn cao độ 5 điểm. ĐO ĐƯỢC ở tầng mạng: lưới 7×7 tốn 52 lượt gọi
    # và 41 giây, so với 4 lượt / 6 giây của module Lũ cùng kích thước lưới.
    slopes = _grid_slopes(pts) if module_id == "landslide" else None

    # Khí hậu nền lấy ở TÂM, dùng chung cả lưới (xấp xỉ đã ghi rõ ở đầu file).
    dist = calibration.climatology(module_id, lat, lon)

    return {"module_id": module_id, "lat": lat, "lon": lon, "pts": pts,
            "weather": weather, "elevs": elevs, "slopes": slopes, "dist": dist,
            "cell_dlat": cell_dlat, "cell_dlon": cell_dlon,
            "rows_override": rows_override}


def _cell_series(grid: dict, i: int, rows=None):
    """Chuỗi chỉ số 7 ngày cho ô thứ i. None nếu ô đó không có dữ liệu."""
    module_id, lat, lon = grid["module_id"], grid["lat"], grid["lon"]
    la, lo = grid["pts"][i]
    if rows is None:
        w = grid["weather"]
        rows = w[i] if i < len(w) else None
    if not rows:
        return None

    dist = grid["dist"]
    if not dist:
        return hazard.index_series_absolute(module_id, la, lo, rows)

    if module_id == "flood" and grid["elevs"][i] is not None:
        series, _ = calibration.calibrated_with_terrain(
            module_id, lat, lon, rows, terrain=grid["elevs"][i], dist=dist)
        return series
    if module_id == "landslide":
        sl = grid["slopes"]
        slope = (sl[i] if sl and sl[i] is not None else ds.slope_context(la, lo)[0])
        series, _ = calibration.calibrated_with_terrain(
            module_id, lat, lon, rows, terrain=slope, dist=dist)
        return series
    series, _ = calibration.calibrated_series(module_id, la, lo, rows, dist=dist)
    return series


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

    grid = _prepare(module_id, lat, lon, radius_km, side)
    pts, cell_dlat, cell_dlon = grid["pts"], grid["cell_dlat"], grid["cell_dlon"]
    dist = grid["dist"]

    cells = []
    values = []
    for i, (la, lo) in enumerate(pts):
        series = _cell_series(grid, i)
        if series is None:
            cells.append({"lat": la, "lon": lo, "value": None, "risk": "unknown"})
            continue

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


# ---------------------------------------------------------------- dòng thời gian

# Trần lưới cho dòng thời gian, thấp hơn bản đồ nhiệt tĩnh.
# Lý do là kích thước phản hồi: 4 kịch bản × 7 ngày × N ô. Lưới 9×9 cho ~2.300
# con số (~40 KB); 11×11 cho ~3.400 (~100 KB) mà không thêm thông tin nào, vì
# mô hình thời tiết nền vốn thô hơn ô lưới rất nhiều.
_MAX_SIDE_TIMELINE = 9

# Độ phân giải HIỆU DỤNG của từng mô-đun, km.
#
# Đây là con số trung thực nhất trong cả file. Mô hình thời tiết nền có ô lưới
# ~11 km. Với hạn và cháy — hai thứ chỉ phụ thuộc thời tiết — đó CHÍNH LÀ độ
# phân giải thật, dù bản đồ có vẽ mịn tới đâu. Với lũ và sạt lở, địa hình (DEM
# ~90 m) tham gia trực tiếp vào chỉ số nên mức độ khác nhau giữa hai thửa cạnh
# nhau là thật; chỉ có THỜI ĐIỂM là vẫn bị khoá theo lưới thời tiết.
_EFFECTIVE_RES_KM = {
    "drought": 11.0, "wildfire": 11.0,
    "flood": 3.0, "landslide": 1.0,
}


def _timing(series, warn: float):
    """(ngày đến, số ngày vượt ngưỡng) — thứ bản đồ đỉnh đang vứt đi.

    Bản đồ nhiệt hiện tại chỉ giữ ĐỈNH của 7 ngày. Nhưng với người ra quyết
    định, "ngập ngày mai" và "ngập thứ Bảy" là hai việc hoàn toàn khác nhau, và
    "ngập một ngày" khác hẳn "ngập bốn ngày" — lúa chết vì cái sau, không phải
    cái trước. Hai con số này tính được miễn phí từ dữ liệu đã tải.
    """
    if not series:
        return None, 0
    arrival = None
    over = 0
    for idx, (_d, _dt, v) in enumerate(series):
        if v >= warn:
            over += 1
            if arrival is None:
                arrival = idx
    return arrival, over


def timeline(module_id: str, lat: float, lon: float,
             radius_km: float = 8.0, side: int = 7) -> dict | None:
    """Diễn tiến rủi ro theo NGÀY trên lưới, cho cả 4 kịch bản song song.

    Chi phí mạng bằng ĐÚNG một lượt bản đồ nhiệt: `weather_multi` vốn đã tải cả
    7 ngày cho mọi ô, và bản cũ tính ra chuỗi 7 ngày rồi vứt đi chỉ giữ đỉnh.
    Bốn kịch bản chỉ là phép nhân trên cùng bộ dữ liệu đó, không tải lại gì.

    Trả về đủ để giao diện phát lại tại chỗ, không gọi mạng khi kéo trượt.
    """
    from app.services.whatif import SCENARIOS

    if not hazard.supports(module_id):
        return None
    name, unit = hazard.name_unit(module_id)
    side = max(3, min(int(side), _MAX_SIDE_TIMELINE))
    radius_km = max(1.0, min(float(radius_km), 40.0))

    ckey = cache_store.make_key("timeline", module_id, round(lat, 3),
                                round(lon, 3), radius_km, side)
    cached = cache_store.get(ckey)
    if cached:
        cached["cached"] = True
        return cached

    grid = _prepare(module_id, lat, lon, radius_km, side)
    pts, dist = grid["pts"], grid["dist"]
    warn = hazard.SAFE      # ngưỡng "đáng chú ý" — cùng mốc với bản đồ nhiệt

    dates = []
    scen_out = []
    for label, rain, temp in SCENARIOS:
        cells = []
        n_over_by_day = None
        for i, (la, lo) in enumerate(pts):
            w = grid["weather"]
            rows = w[i] if i < len(w) else None
            rows = hazard.transform(rows, rain, temp) if rows else None
            series = _cell_series(grid, i, rows=rows)
            if series is None:
                cells.append({"lat": la, "lon": lo, "values": None,
                              "arrival_day": None, "days_over": 0})
                continue
            if not dates:
                dates = [dt for (_d, dt, _v) in series]
            if n_over_by_day is None:
                n_over_by_day = [0] * len(series)
            vals = [round(v, 1) for (_d, _dt, v) in series]
            for k, v in enumerate(vals):
                if v >= warn and k < len(n_over_by_day):
                    n_over_by_day[k] += 1
            arrival, over = _timing(series, warn)
            cells.append({"lat": la, "lon": lo, "values": vals,
                          "arrival_day": arrival, "days_over": over})

        arrivals = [c["arrival_day"] for c in cells if c["arrival_day"] is not None]
        scen_out.append({
            "label": label, "rain_mult": rain, "temp_delta": temp,
            "cells": cells,
            "n_over_by_day": n_over_by_day or [],
            "first_arrival_day": min(arrivals) if arrivals else None,
            "cells_affected": len(arrivals),
            "max_days_over": max((c["days_over"] for c in cells), default=0),
        })

    # --- Trung thực về độ phân giải: ô lưới có mịn hơn dữ liệu không? ---
    eff_km = _EFFECTIVE_RES_KM.get(module_id, _NATIVE_RES_KM)
    cell_km = (2.0 * radius_km) / max(1, side - 1)
    oversampled = cell_km < eff_km
    ratio = round(eff_km / cell_km, 1) if cell_km > 0 else None

    base = scen_out[0] if scen_out else None
    head = "Chưa lấy được dữ liệu thời tiết cho vùng này."
    if base and base["cells_affected"]:
        d = base["first_arrival_day"]
        head = (f"{base['cells_affected']}/{len(pts)} ô chạm ngưỡng, sớm nhất "
                f"{'hôm nay' if d == 0 else f'sau {d} ngày'} "
                f"({dates[d] if dates and d is not None and d < len(dates) else '—'}); "
                f"kéo dài tối đa {base['max_days_over']} ngày.")
    elif base:
        head = f"Cả {len(pts)} ô đều dưới ngưỡng suốt 7 ngày tới."

    result = {
        "module_id": module_id, "module_name": name, "unit": unit,
        "center": {"lat": lat, "lon": lon},
        "radius_km": radius_km, "side": side,
        "cell_dlat": round(grid["cell_dlat"], 6),
        "cell_dlon": round(grid["cell_dlon"], 6),
        "dates": dates, "scenarios": scen_out,
        "safe": hazard.SAFE, "warning": hazard.WARNING,
        "calibrated": bool(dist),
        "headline": head,
        "cached": False,
        "resolution": {
            "cell_km": round(cell_km, 2),
            "effective_km": eff_km,
            "native_weather_km": _NATIVE_RES_KM,
            "oversampled": oversampled,
            "cells_per_data_pixel": ratio,
            "note": (
                f"Mỗi ô hiển thị rộng ~{cell_km:.1f} km, nhưng dữ liệu thật chỉ "
                f"phân biệt được tới ~{eff_km:.0f} km — một ô dữ liệu phủ khoảng "
                f"{ratio} ô hiển thị. Bản đồ mượt KHÔNG có nghĩa là biết chi tiết "
                "tới từng ô."
                if oversampled else
                f"Ô hiển thị (~{cell_km:.1f} km) không mịn hơn dữ liệu "
                f"(~{eff_km:.0f} km), nên không có chi tiết nào bị bịa ra."),
            "why": (
                "Hạn và cháy chỉ phụ thuộc thời tiết, nên độ phân giải thật đúng "
                "bằng lưới mô hình khí tượng (~11 km) dù vẽ mịn tới đâu. Lũ và "
                "sạt lở có địa hình (DEM ~90 m) tham gia trực tiếp nên khác biệt "
                "giữa hai thửa cạnh nhau là THẬT — nhưng THỜI ĐIỂM thì vẫn bị "
                "khoá theo lưới thời tiết."),
        },
        "caveat": (
            "Bốn kịch bản đều chạy trên CÙNG một bộ dữ liệu thời tiết thật, chỉ "
            "khác hệ số mưa/nhiệt — nên chênh lệch giữa chúng là do giả định, "
            "không phải do dữ liệu. 'Ngày đến' và 'số ngày kéo dài' tính từ chính "
            "chuỗi 7 ngày mà bản đồ nhiệt vốn đã tải rồi bỏ đi."),
    }
    cache_store.put(ckey, result, _TTL)
    return result
