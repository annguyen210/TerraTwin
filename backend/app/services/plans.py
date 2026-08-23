"""Gói cước và bảng kê sử dụng — phần thương mại hoá LÀM ĐƯỢC bằng mã.

RANH GIỚI RÕ RÀNG, và đây là chỗ dễ làm màu nhất trong cả sản phẩm:

  LÀM ĐƯỢC bằng mã, và đã làm ở đây:
    · Gói cước với hạn mức riêng, thi hành thật ở tầng xác thực.
    · Đo lượt dùng theo khoá, theo tháng, đủ chi tiết để xuất hoá đơn.
    · Bảng kê sử dụng: dùng bao nhiêu, còn bao nhiêu, vượt bao nhiêu.
    · GIÁ VỐN theo lượt gọi ra ngoài — thứ quyết định một gói có lãi hay không.

  KHÔNG LÀM, và cố ý không làm:
    · Cổng thanh toán. VNPay, MoMo, ZaloPay đều đòi giấy phép kinh doanh và
      hợp đồng thương nhân. Viết một "adapter thanh toán" rỗng để trông cho
      đủ bộ là tự lừa mình: nó không nhận được một đồng nào, mà lại làm người
      đọc mã tưởng phần thanh toán đã xong.
    · Vì vậy chỗ này dừng đúng ở ranh giới kỹ thuật. Bước sau là đăng ký doanh
      nghiệp và ký hợp đồng — việc của người chủ, không phải việc của mã.

GIÁ TRONG BẢNG LÀ GIÁ ĐỀ XUẤT, CHƯA CÓ AI TRẢ. Đánh dấu rõ ở mọi nơi trả ra,
để không ai đọc nhầm thành doanh thu đã có.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

# Giá vốn thật cho mỗi lượt quét: mỗi lần quét toàn cảnh gọi ra ngoài khoảng
# ngần này lượt (đo được, xem tests/test_parallel_sectors.py). Nguồn hiện tại
# miễn phí nên giá vốn tiền mặt bằng 0 — nhưng HẠN MỨC thì không vô hạn, và đó
# mới là thứ khan hiếm cần phân bổ giữa các gói.
UPSTREAM_CALLS_PER_SCAN = 6

PLANS: dict[str, dict] = {
    "free": {
        "name": "Miễn phí",
        "quota": 500,
        "price_vnd": 0,
        "for": "Hộ gia đình, một vài thửa đất",
        "features": ["Toàn bộ 13 mũi nhọn chạy ngay", "Cảnh báo trên web",
                     "Xem lại 4 thiên tai lịch sử"],
    },
    "pro": {
        "name": "Chuyên nghiệp",
        "quota": 5000,
        "price_vnd": 299_000,
        "for": "Hợp tác xã, trang trại nhiều thửa",
        "features": ["Mọi thứ của gói Miễn phí", "Danh mục nhiều thửa",
                     "Rà soát tự động 6 giờ một lần", "Xuất báo cáo",
                     "Khoá API"],
    },
    "enterprise": {
        "name": "Doanh nghiệp",
        "quota": 50000,
        "price_vnd": 2_990_000,
        "for": "Doanh nghiệp thu mua, bảo hiểm, ngân hàng",
        "features": ["Mọi thứ của gói Chuyên nghiệp", "Hồ sơ MRV carbon/ESG",
                     "Rủi ro vùng nguyên liệu", "Dấu niêm phong truy xuất",
                     "Hạn mức API cao"],
    },
}

DEFAULT_PLAN = "free"


def quota_for(plan: str | None) -> int:
    """Hạn mức tháng của một gói. Biến môi trường ghi đè được để thử nghiệm."""
    override = os.environ.get("TERRATWIN_KEY_MONTHLY_QUOTA")
    if override is not None and override.strip():
        try:
            return int(override)
        except ValueError:
            pass
    return PLANS.get(plan or DEFAULT_PLAN, PLANS[DEFAULT_PLAN])["quota"]


def catalogue() -> dict:
    """Bảng giá. Luôn kèm cảnh báo là chưa ai trả tiền."""
    return {
        "plans": [{"id": k, **v} for k, v in PLANS.items()],
        "currency": "VND",
        "billing_period": "tháng",
        "status": "đề xuất",
        "disclaimer": (
            "Giá đề xuất, CHƯA có cổng thanh toán và chưa có khách hàng trả "
            "tiền. Phần thu tiền cần giấy phép kinh doanh và hợp đồng thương "
            "nhân với VNPay/MoMo — là bước pháp lý, không phải bước lập trình."),
    }


def statement(key_row, plan: str | None = None) -> dict:
    """Bảng kê sử dụng của một khoá — đủ chi tiết để xuất hoá đơn khi cần.

    Không làm tròn cho đẹp: hiện đúng số lượt đã dùng, số còn lại, và phần
    vượt. Nếu đã vượt thì nói vượt bao nhiêu, không giấu sau chữ "gần hết".
    """
    plan = plan or getattr(key_row, "plan", None) or DEFAULT_PLAN
    limit = quota_for(plan)
    now = datetime.now(timezone.utc)
    period = now.strftime("%Y-%m")

    used = key_row.calls_period or 0
    if key_row.period != period:
        used = 0                      # tháng mới, bộ đếm chưa kịp đặt lại

    remaining = max(limit - used, 0) if limit > 0 else None
    over = max(used - limit, 0) if limit > 0 else 0

    return {
        "period": period,
        "plan": plan,
        "plan_name": PLANS.get(plan, PLANS[DEFAULT_PLAN])["name"],
        "quota": limit if limit > 0 else None,
        "used": used,
        "remaining": remaining,
        "over_quota": over,
        "calls_total_all_time": key_row.calls_total or 0,
        "prefix": key_row.prefix,
        "created_at": key_row.created_at.isoformat() if key_row.created_at else None,
        "last_used_at": (key_row.last_used_at.isoformat()
                         if key_row.last_used_at else None),
        "upstream_calls_estimate": used * UPSTREAM_CALLS_PER_SCAN,
        "cash_cost_vnd": 0,
        "cost_note": (
            "Giá vốn tiền mặt bằng 0 vì mọi nguồn dữ liệu chính đều miễn phí. "
            "Thứ khan hiếm là HẠN MỨC của nguồn, nên hạn mức mới là cái được "
            "phân bổ giữa các gói — không phải tiền."),
        "billing_status": "chưa thu tiền — chưa có cổng thanh toán",
    }
