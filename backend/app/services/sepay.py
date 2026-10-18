"""TỰ XÁC NHẬN CHUYỂN KHOẢN QUA SEPAY (18/10/2026) — nối tiếp VietQR (services/vietqr.py).

SePay (sepay.vn) theo dõi biến động số dư của tài khoản ngân hàng chủ dự án tự liên kết, rồi gọi webhook về TerraTwin cho
từng giao dịch. TerraTwin đọc NỘI DUNG chuyển khoản tìm mã yêu cầu "TT<số>" (đúng mã VietQR đã in), so số tiền với giá
gói, rồi tự kích hoạt gói 1 tháng — không cần quản trị đối chiếu sao kê bằng tay.

An toàn:
- Chỉ nhận khi header `Authorization: Apikey <TERRATWIN_SEPAY_API_KEY>` khớp (so sánh hằng thời gian). Chưa đặt khoá →
  webhook tắt hẳn (503), không bao giờ "mở cửa".
- Mỗi mã giao dịch SePay chỉ xử lý MỘT lần (cột duy nhất) — SePay gửi lại khi mạng chập chờn sẽ không cấp gói hai lần.
- Thiếu tiền, sai mã, yêu cầu đã xử lý, tiền ra → ghi lại "chưa khớp" cho quản trị xem, KHÔNG cấp gói.
- Không lưu số tài khoản người chuyển; nội dung chuyển khoản cắt còn 200 ký tự.

Cấu hình (chủ dự án tự đặt trên Render, KHÔNG để trong mã): TERRATWIN_SEPAY_API_KEY — khoá tự đặt ở my.sepay.vn → Tích hợp
WebHooks (kiểu chứng thực "API Key"), URL webhook: https://<api>/api/payments/sepay.
"""
from __future__ import annotations

import hmac
import os
import re

_REQ = re.compile(r"TT\s*0*(\d{1,9})", re.I)


def configured() -> bool:
    return bool(os.environ.get("TERRATWIN_SEPAY_API_KEY", "").strip())


def authorized(header: str | None) -> bool:
    key = os.environ.get("TERRATWIN_SEPAY_API_KEY", "").strip()
    if not key or not header:
        return False
    m = re.fullmatch(r"\s*Apikey\s+(\S+)\s*", header, re.I)
    return bool(m) and hmac.compare_digest(m.group(1).encode(), key.encode())


def request_id(content: str | None) -> int | None:
    """Mã yêu cầu trong nội dung chuyển khoản. Ngân hàng hay dính chữ ("TT12PRO") hoặc thêm tiền tố ("MBVCB.123.TT12 PRO")."""
    m = _REQ.search(content or "")
    return int(m.group(1)) if m else None


def decide(txn: dict, req, price_vnd: int) -> tuple[str, str]:
    """(trạng thái, lý do) cho một giao dịch — hàm thuần để test được. req là UpgradeRequest hoặc None."""
    if str(txn.get("transferType", "")).lower() != "in":
        return "ignored", "tiền ra khỏi tài khoản"
    amount = int(txn.get("transferAmount") or 0)
    if req is None:
        return "unmatched", "không thấy mã yêu cầu TT<số> hợp lệ trong nội dung"
    if req.status != "pending":
        return "unmatched", f"yêu cầu #{req.id} đã {req.status} — cần hoàn tiền hoặc cấp tay"
    if price_vnd <= 0:
        return "unmatched", "gói không có giá"
    if amount < price_vnd:
        return "underpaid", f"chuyển {amount:,} < giá {price_vnd:,} đ".replace(",", ".")
    return "matched", f"đủ {amount:,} đ".replace(",", ".")
