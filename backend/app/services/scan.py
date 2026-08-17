"""Quét TOÀN CẢNH một thửa đất — chạy cả 14 module trong 1 lần gọi.

Trả lưới rủi ro đầy đủ + danh sách CẢNH BÁO ưu tiên (nguy hiểm trước). Nhờ tầng
cache thời tiết (realdata), 14 module dùng chung ~vài lần gọi Open-Meteo nên nhanh.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.schemas import Location, ScanModule, ScanResult
from app.services import terrascore

_RISK_ORDER = {"danger": 0, "warning": 1, "safe": 2, "unknown": 3, "not_implemented": 4}


def scan(loc: Location) -> ScanResult:
    from app.modules.registry import list_modules, get_module

    mods: list[ScanModule] = []
    assessments = {}          # id → Assessment (tái dùng cho TerraScore, khỏi assess lại)
    real_count = 0
    real_total = 0
    for info in list_modules():
        module = get_module(info.id)
        if module is None:
            continue
        a = module.assess(loc)
        assessments[info.id] = a
        mods.append(ScanModule(
            id=info.id, name=info.name, icon=info.icon, group=info.group,
            risk_level=a.risk_level, headline=a.headline,
            recommendation=a.recommendation, is_real=a.is_real, score=a.score,
        ))
        real_total += 1
        if a.is_real:
            real_count += 1

    # Cảnh báo hành động: CHỈ lấy module dùng DỮ LIỆU THẬT (tránh báo động giả từ
    # module mẫu), xếp nguy hiểm trước. Module mẫu vẫn hiện trong lưới, gắn cờ 🧪.
    alerts = sorted(
        [m for m in mods if m.is_real and m.risk_level in ("danger", "warning")],
        key=lambda m: _RISK_ORDER.get(m.risk_level, 9),
    )
    ts = terrascore.compute(loc, assessments=assessments)   # tái dùng, không assess lại
    ratio = round(real_count / real_total, 2) if real_total else 0.0
    return ScanResult(
        location=loc, terrascore=ts, modules=mods, alerts=alerts,
        real_data_ratio=ratio,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
