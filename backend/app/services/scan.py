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
    """Chạy toàn bộ mô-đun ĐỒNG THỜI.

    Trước đây chạy nối tiếp: mỗi mô-đun chờ mạng xong mới tới lượt mô-đun sau,
    nên endpoint được dùng nhiều nhất cũng là endpoint chậm nhất. Chúng độc lập
    với nhau (chỉ dùng chung tầng cache) nên chạy song song được.

    Mô-đun nào hỏng trả None và bị bỏ qua — một nguồn dữ liệu chết không được
    làm trắng cả bảng toàn cảnh.
    """
    from app.modules.registry import get_module, list_modules
    from app.services import jobs

    # Bỏ qua mô-đun nặng: chúng quét cả một vùng chứ không riêng thửa này, và
    # để chúng trong lượt toàn cảnh thì mười sáu mô-đun nhanh phải chờ một mô-đun
    # chậm. Người dùng mở riêng từng cái khi cần.
    all_infos = [i for i in list_modules() if get_module(i.id) is not None]
    infos = [i for i in all_infos if not i.heavy]
    skipped = [i.id for i in all_infos if i.heavy]

    def _task(mid: str):
        return lambda: get_module(mid).assess(loc)

    results = jobs.gather([_task(i.id) for i in infos])

    mods: list[ScanModule] = []
    assessments = {}          # id → Assessment (tái dùng cho TerraScore, khỏi assess lại)
    real_count = 0
    real_total = 0
    for info, a in zip(infos, results):
        if a is None:
            continue
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
        real_data_ratio=ratio, skipped_heavy=skipped,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
