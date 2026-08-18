"""S04 — Twin Genome: tìm những thửa đất "song sinh" với thửa của bạn.

Ý tưởng: mỗi vị trí có một "bộ gen" gồm các đặc trưng đo được — địa hình, vị trí
so với biển, và khí hậu. Hai nơi có bộ gen gần nhau thì thường gặp cùng loại
vấn đề và hợp cùng loại giải pháp. Nông dân Bến Tre học được từ Trà Vinh nhanh
hơn từ Sơn La, và bộ gen nói rõ vì sao.

Cách làm: dựng một lưới tham chiếu phủ Việt Nam, tính bộ gen cho từng ô, chuẩn
hoá z-score rồi tìm láng giềng gần nhất theo khoảng cách Euclid có trọng số.

BA GIỚI HẠN ĐÃ GHI RÕ TRONG KẾT QUẢ — bản đồ đẹp dễ khiến người ta tin quá mức:
  1. Lưới ~0,75° (~80 km): tìm được VÙNG tương đồng, không phải thửa giống hệt.
  2. Khí hậu lấy từ MỘT năm tham chiếu, không phải chuẩn khí hậu 30 năm.
  3. Lọc đất liền bằng cao độ > 0 nên bỏ sót một phần đất ven biển cao 0 m.
"""
from __future__ import annotations

import math
from datetime import date

from app.services import cache_store
from app.services import datasources as ds
from app.services import realdata
from app.schemas import VN_LAT_MAX, VN_LAT_MIN, VN_LON_MAX, VN_LON_MIN

STEP = 0.75              # độ — ~80 km
BATCH = 40               # số điểm mỗi lần gọi Archive API
REF_YEAR = 2023          # năm tham chiếu cho khí hậu
_TTL = 30 * 24 * 3600    # khí hậu nền đổi rất chậm — cache 30 ngày

# Trọng số từng đặc trưng. Địa hình và khí hậu quyết định "chất đất" nhiều hơn
# khoảng cách biển, nên nặng hơn.
_WEIGHTS = {
    "elev": 1.0,
    "slope": 1.0,
    "coast_km": 0.7,
    "rain_annual": 1.2,
    "dry_share": 1.2,     # tỉ lệ mưa rơi vào mùa khô — phân biệt Bắc/Trung/Nam
    "tmax_mean": 0.8,
    "tmax_range": 0.8,    # biên độ nhiệt mùa — miền Bắc cao, miền Nam thấp
}
_FEATURES = tuple(_WEIGHTS)

_LABELS = {
    "elev": ("Cao độ", "m"),
    "slope": ("Độ dốc", "°"),
    "coast_km": ("Cách biển", "km"),
    "rain_annual": ("Mưa cả năm", "mm"),
    "dry_share": ("Tỉ lệ mưa mùa khô", "%"),
    "tmax_mean": ("Nhiệt tối đa TB", "°C"),
    "tmax_range": ("Biên độ nhiệt mùa", "°C"),
}

_DRY_MONTHS = {12, 1, 2, 3, 4}   # mùa khô ở phần lớn Việt Nam

# Các đặc trưng LỆCH MẠNH được log-hoá trước khi z-score.
# Lý do: cao độ Việt Nam trải 0–3000 m, nên nếu z-score thẳng thì chênh lệch
# 6 m với 52 m ở đồng bằng bị coi như không đáng kể — trong khi với nông dân
# ĐBSCL đó là khác biệt sống còn về ngập. Log nén dải núi lại và trả đúng trọng
# lượng cho khác biệt ở vùng thấp.
_LOG_FEATURES = {"elev", "coast_km", "slope"}


def _scale(feature: str, value: float) -> float:
    return math.log1p(max(0.0, value)) if feature in _LOG_FEATURES else value


def _grid() -> list[tuple[float, float]]:
    pts = []
    lat = VN_LAT_MIN + STEP / 2
    while lat <= VN_LAT_MAX:
        lon = VN_LON_MIN + STEP / 2
        while lon <= VN_LON_MAX:
            pts.append((round(lat, 3), round(lon, 3)))
            lon += STEP
        lat += STEP
    return pts


def _climate_batch(points: list[tuple[float, float]]) -> list[dict | None]:
    """Khí hậu năm tham chiếu cho nhiều điểm trong MỘT lần gọi."""
    rows = realdata.historical_weather_multi(
        points, f"{REF_YEAR}-01-01", f"{REF_YEAR}-12-31")
    out: list[dict | None] = []
    for r in rows:
        if not r:
            out.append(None)
            continue
        rain_all = rain_dry = 0.0
        tmaxs, monthly_max = [], {}
        for d in r:
            try:
                m = int(d["date"][5:7])
            except (KeyError, ValueError):
                continue
            p = d.get("precip") or 0.0
            rain_all += p
            if m in _DRY_MONTHS:
                rain_dry += p
            t = d.get("tmax")
            if t is not None:
                tmaxs.append(t)
                monthly_max[m] = max(monthly_max.get(m, -99.0), t)
        if not tmaxs:
            out.append(None)
            continue
        monthly = list(monthly_max.values())
        out.append({
            "rain_annual": round(rain_all, 1),
            "dry_share": round(100.0 * rain_dry / rain_all, 1) if rain_all > 0 else 0.0,
            "tmax_mean": round(sum(tmaxs) / len(tmaxs), 1),
            "tmax_range": round(max(monthly) - min(monthly), 1) if len(monthly) > 1 else 0.0,
        })
    return out


def build_reference(force: bool = False) -> dict:
    """Dựng lưới tham chiếu (chậm lần đầu, sau đó lấy từ cache 30 ngày)."""
    key = cache_store.make_key("genome-ref", STEP, REF_YEAR, "v2-log")
    if not force:
        hit = cache_store.get(key)
        if hit:
            hit["cached"] = True
            return hit

    pts = _grid()
    elevs = realdata.elevation_multi(pts)

    # Chỉ giữ điểm trên đất liền. Open-Meteo trả 0.0 cho điểm biển.
    land = [(p, e) for p, e in zip(pts, elevs) if e is not None and e > 0.0]

    cells = []
    for i in range(0, len(land), BATCH):
        chunk = land[i:i + BATCH]
        climate = _climate_batch([p for p, _ in chunk])
        for (p, e), c in zip(chunk, climate):
            if c is None:
                continue
            lat, lon = p
            slope, _ = ds.slope_context(lat, lon)
            cells.append({
                "lat": lat, "lon": lon,
                "elev": round(e, 1), "slope": slope,
                "coast_km": ds.distance_to_coast_km(lat, lon),
                **c,
            })

    stats = {}
    for f in _FEATURES:
        vals = [_scale(f, c[f]) for c in cells]
        if not vals:
            stats[f] = {"mean": 0.0, "std": 1.0}
            continue
        m = sum(vals) / len(vals)
        var = sum((v - m) ** 2 for v in vals) / max(1, len(vals) - 1)
        stats[f] = {"mean": m, "std": max(math.sqrt(var), 1e-6)}

    result = {
        "grid_step_deg": STEP, "reference_year": REF_YEAR,
        "candidates_scanned": len(pts), "land_cells": len(cells),
        "cells": cells, "stats": stats, "cached": False,
        "built_at": date.today().isoformat(),
    }
    if cells:
        cache_store.put(key, result, _TTL)
    return result


def genome_of(lat: float, lon: float) -> dict | None:
    """Bộ gen của MỘT vị trí bất kỳ (không cần nằm trên lưới)."""
    elev = ds.elevation_proxy(lat, lon)
    slope, _ = ds.slope_context(lat, lon)
    c = _climate_batch([(lat, lon)])[0]
    if c is None:
        return None
    return {"lat": lat, "lon": lon, "elev": elev, "slope": slope,
            "coast_km": ds.distance_to_coast_km(lat, lon), **c}


def _distance(a: dict, b: dict, stats: dict) -> float:
    """Khoảng cách Euclid có trọng số; đặc trưng lệch mạnh đã log-hoá trước."""
    total = 0.0
    for f, w in _WEIGHTS.items():
        d = (_scale(f, a[f]) - _scale(f, b[f])) / stats[f]["std"]
        total += w * d * d
    return math.sqrt(total / sum(_WEIGHTS.values()))


def _compare(a: dict, b: dict) -> list[dict]:
    out = []
    for f in _FEATURES:
        label, unit = _LABELS[f]
        out.append({"feature": f, "label": label, "unit": unit,
                    "yours": a[f], "theirs": b[f],
                    "diff": round(b[f] - a[f], 1)})
    return out


def find_twins(lat: float, lon: float, k: int = 5) -> dict:
    """Tìm k vùng có bộ gen gần nhất."""
    k = max(1, min(int(k), 20))
    mine = genome_of(lat, lon)
    if mine is None:
        return {"available": False,
                "message": "Chưa lấy được dữ liệu khí hậu cho vị trí này "
                           "(kiểm tra kết nối mạng)."}

    ref = build_reference()
    if not ref["cells"]:
        return {"available": False,
                "message": "Chưa dựng được lưới tham chiếu (kiểm tra kết nối mạng)."}

    scored = []
    for c in ref["cells"]:
        # Bỏ chính ô chứa mình — "song sinh" với chính mình thì vô nghĩa.
        if ds._haversine_km(lat, lon, c["lat"], c["lon"]) < STEP * 55:
            continue
        scored.append((_distance(mine, c, ref["stats"]), c))
    scored.sort(key=lambda t: t[0])

    twins = []
    for dist, c in scored[:k]:
        # 0 → 100%. Khoảng cách 1.0 độ lệch chuẩn ≈ 50% tương đồng.
        similarity = round(100.0 / (1.0 + dist), 1)
        twins.append({
            "lat": c["lat"], "lon": c["lon"],
            "similarity_pct": similarity,
            "distance_km": round(ds._haversine_km(lat, lon, c["lat"], c["lon"]), 0),
            "genome": {f: c[f] for f in _FEATURES},
            "comparison": _compare(mine, c),
        })

    best = twins[0] if twins else None
    headline = (
        f"Vùng giống nhất cách {best['distance_km']:.0f} km "
        f"({best['similarity_pct']}% tương đồng) — cùng nhóm cao độ, khí hậu và "
        "vị trí so với biển."
        if best else "Không tìm được vùng tương đồng."
    )

    return {
        "available": True,
        "location": {"lat": lat, "lon": lon},
        "your_genome": {f: mine[f] for f in _FEATURES},
        "feature_labels": {f: {"label": _LABELS[f][0], "unit": _LABELS[f][1]}
                           for f in _FEATURES},
        "twins": twins,
        "reference": {
            "land_cells": ref["land_cells"],
            "grid_step_deg": ref["grid_step_deg"],
            "reference_year": ref["reference_year"],
            "cached": ref["cached"],
        },
        "headline": headline,
        "why_useful": ("Vùng cùng bộ gen thường gặp cùng loại vấn đề và hợp cùng "
                       "loại giải pháp — giống cây, lịch mùa vụ, cách phòng hạn/mặn "
                       "đã hiệu quả ở đó là nơi đáng học hỏi trước tiên."),
        "caveat": (
            f"Lưới ~{STEP}° (≈80 km) nên tìm được VÙNG tương đồng, không phải thửa "
            f"giống hệt. Khí hậu lấy từ MỘT năm tham chiếu ({REF_YEAR}), không phải "
            "chuẩn khí hậu 30 năm. Điểm trên đất liền lọc bằng cao độ > 0 m nên bỏ "
            "sót một phần đất ven biển thấp ngang mực nước."
        ),
        "method": ("7 đặc trưng (cao độ, độ dốc, cách biển, mưa năm, tỉ lệ mưa mùa "
                   "khô, nhiệt tối đa, biên độ nhiệt) chuẩn hoá z-score rồi tính "
                   "khoảng cách Euclid có trọng số."),
    }
