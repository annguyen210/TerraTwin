"""Quét TOÀN CẢNH một thửa đất — chạy cả 14 module trong 1 lần gọi.

Trả lưới rủi ro đầy đủ + danh sách CẢNH BÁO ưu tiên (nguy hiểm trước). Nhờ tầng
cache thời tiết (realdata), 14 module dùng chung ~vài lần gọi Open-Meteo nên nhanh.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.schemas import Location, ScanModule, ScanResult
from app.services import terrascore

_RISK_ORDER = {"danger": 0, "warning": 1, "safe": 2, "unknown": 3, "not_implemented": 4}


def scan(loc: Location, include_heavy: bool = False) -> ScanResult:
    """Chạy toàn bộ mô-đun ĐỒNG THỜI.

    Trước đây chạy nối tiếp: mỗi mô-đun chờ mạng xong mới tới lượt mô-đun sau,
    nên endpoint được dùng nhiều nhất cũng là endpoint chậm nhất. Chúng độc lập
    với nhau (chỉ dùng chung tầng cache) nên chạy song song được.

    Mô-đun nào hỏng trả None và bị bỏ qua — một nguồn dữ liệu chết không được
    làm trắng cả bảng toàn cảnh.
    """
    from app.modules.registry import get_module, list_modules
    from app.services import jobs

    # Mô-đun NẶNG quét cả một vùng chứ không riêng thửa này, mất ~10 giây mỗi
    # cái. Người dùng bấm bản đồ thì không được bắt chờ ngần ấy, nên mặc định bỏ
    # qua và KHAI BÁO ra. Nhưng rà soát nền (C05) thì chạy đủ — ở đó không ai
    # ngồi chờ, mà đó lại đúng là lúc cảnh báo có giá trị nhất: lũ từ thượng
    # nguồn ập tới lúc ba giờ sáng, không phải lúc người ta đang mở app.
    all_infos = [i for i in list_modules() if get_module(i.id) is not None]
    infos = all_infos if include_heavy else [i for i in all_infos if not i.heavy]
    skipped = [] if include_heavy else [i.id for i in all_infos if i.heavy]

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
        fc = a.forecast or []
        spark = [round(p.value, 1) for p in fc]
        mods.append(ScanModule(
            id=info.id, name=info.name, icon=info.icon, group=info.group,
            risk_level=a.risk_level, headline=a.headline,
            recommendation=a.recommendation, is_real=a.is_real, score=a.score,
            threat=info.threat, status=a.status,
            confidence=getattr(a, "confidence", None),
            spark=spark,
            unit=fc[0].unit if fc else None,
            peak=(max(p.value for p in fc) if fc else None),
        ))
        real_total += 1
        if a.is_real:
            real_count += 1

    # MỤC NẶNG VẪN CÓ MẶT TRONG DANH SÁCH, chỉ là chưa có kết quả.
    #
    # Bỏ hẳn chúng đi thì màn hình đầu từ 16 mục còn 11 — trông TRỐNG HƠN, đúng
    # cái phải tránh. Nhưng chạy chúng ngay thì lượt quét từ 2,5 giây thành hơn
    # một phút, và người dùng đóng app trước khi thấy gì.
    #
    # Lối ra là trạng thái thứ năm: "đang kiểm tra". Người dùng thấy đủ 16 mục
    # ngay, biết 5 mục còn lại đang chạy chứ không phải không có, và giao diện
    # điền dần khi kết quả về. "Chưa xong" và "không có" là hai chuyện khác hẳn
    # nhau — gộp lại là tự bôi xấu chính mình.
    for info in all_infos:
        if info.id in assessments or not info.heavy:
            continue
        mods.append(ScanModule(
            id=info.id, name=info.name, icon=info.icon, group=info.group,
            risk_level="unknown", status="pending", is_real=False,
            headline="Đang kiểm tra — mục này cần ảnh vệ tinh nên lâu hơn",
            recommendation="", threat=info.threat,
        ))

    # Cảnh báo hành động: chỉ lấy mô-đun (a) dùng DỮ LIỆU THẬT và (b) thật sự
    # mô tả một MỐI ĐE DOẠ.
    #
    # Điều kiện (b) là một lỗi đã sửa, không phải cẩn thận thừa: điện mặt trời
    # trả "danger" khi bức xạ chỉ ở mức trung bình, và bảo hiểm tham số trả
    # "danger" khi ĐÃ KÍCH HOẠT CHI TRẢ — tin tốt. Không lọc thì rà soát nền
    # gửi email lúc ba giờ sáng báo "điện mặt trời: nguy hiểm". Vài lần như thế
    # là người dùng tắt thông báo, và lần lũ thật họ không còn nhận được nữa.
    alerts = sorted(
        [m for m in mods
         if m.is_real and m.threat and m.risk_level in ("danger", "warning")],
        key=lambda m: _RISK_ORDER.get(m.risk_level, 9),
    )
    ts = terrascore.compute(loc, assessments=assessments)   # tái dùng, không assess lại
    ratio = round(real_count / real_total, 2) if real_total else 0.0
    return ScanResult(
        location=loc, terrascore=ts, modules=mods, alerts=alerts,
        real_data_ratio=ratio, skipped_heavy=skipped,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
