"""C01 Twin Builder — dựng bản sao số đầy đủ của một thửa đất.

Trước đây file này chỉ sinh một uuid rồi nhét vào dict trong bộ nhớ; không ai
dùng, và mất sạch khi restart. Nay Twin là thứ có thật: gom TẤT CẢ các lớp dữ
liệu tại một thời điểm — địa hình, khí hậu, 14 module hiểm họa, TerraScore —
rồi lưu vào database.

Vì sao đáng lưu thay vì gọi lại API mỗi lần: một Twin là ẢNH CHỤP tại thời
điểm dựng. Xem lại hồ sơ thửa đất tháng trước phải ra đúng con số tháng trước,
không phải dự báo hôm nay.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from app.schemas import Location


def build_layers(loc: Location) -> dict:
    """Gom mọi lớp dữ liệu của một vị trí thành một Twin."""
    from app.modules.registry import get_module, list_modules
    from app.services import datasources as ds
    from app.services import genome, terrascore

    elev = ds.elevation_proxy(loc.lat, loc.lon)
    slope, slope_real = ds.slope_context(loc.lat, loc.lon)
    coast = ds.distance_to_coast_km(loc.lat, loc.lon)

    modules, assessments = [], {}
    for info in list_modules():
        m = get_module(info.id)
        if m is None:
            continue
        try:
            a = m.assess(loc)
        except Exception:
            continue
        assessments[info.id] = a
        modules.append({
            "id": info.id, "name": info.name, "icon": info.icon,
            "group": info.group, "risk_level": a.risk_level,
            "headline": a.headline, "recommendation": a.recommendation,
            "is_real": a.is_real, "status": a.status,
            "confidence": a.confidence, "metrics": a.metrics,
        })

    ts = terrascore.compute(loc, assessments)

    # Bộ gen khí hậu là tuỳ chọn: cần gọi mạng và có thể hỏng — Twin vẫn dựng được.
    try:
        gen = genome.genome_of(loc.lat, loc.lon)
    except Exception:
        gen = None

    n_real = sum(1 for m in modules if m["is_real"])
    return {
        "terrain": {
            "elevation_m": elev, "slope_deg": slope, "slope_is_real": slope_real,
            "coast_distance_km": coast,
            "salinity_zone": ds.salinity_zone(loc.lat, loc.lon),
        },
        "climate_genome": gen,
        "modules": modules,
        "terrascore": {"score": ts.score, "grade": ts.grade,
                       "summary": ts.summary,
                       "real_data_ratio": ts.real_data_ratio},
        "data_quality": {
            "modules_total": len(modules),
            "modules_real_data": n_real,
            "real_ratio": round(n_real / len(modules), 2) if modules else 0.0,
            "climate_genome_available": gen is not None,
        },
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def build(loc: Location) -> dict:
    """Dựng Twin nhưng KHÔNG lưu — dùng cho khách chưa đăng nhập."""
    layers = build_layers(loc)
    return {
        "persisted": False,
        "location": loc.model_dump(),
        "layers": layers,
        "note": ("Đăng nhập để lưu Twin này lại — bản lưu giữ nguyên số liệu tại "
                 "thời điểm dựng, xem lại sau vẫn đúng con số cũ."),
    }


def to_json(layers: dict) -> str:
    return json.dumps(layers, ensure_ascii=False)


def from_json(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}
