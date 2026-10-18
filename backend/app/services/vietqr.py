"""THANH TOÁN MIỄN PHÍ BẰNG VIETQR (18/10/2026) — thay cho cổng thanh toán (cần pháp nhân, hợp đồng, phí giao dịch).

VietQR là chuẩn QR chuyển khoản liên ngân hàng của NAPAS (dựa trên EMVCo Merchant-Presented QR): mọi app ngân hàng Việt
Nam quét được, tiền vào THẲNG tài khoản người nhận, không qua trung gian, không phí cổng. Mã chứa: mã ngân hàng (BIN),
số tài khoản, số tiền, nội dung chuyển khoản. TerraTwin chỉ DỰNG chuỗi QR — không giữ tiền, không thấy số thẻ.

Giới hạn trung thực: không có webhook ngân hàng → quản trị đối chiếu sao kê theo NỘI DUNG chuyển khoản (mã yêu cầu) rồi
duyệt gói thủ công trong /admin. Bán dịch vụ có thu tiền vẫn cần hỏi thủ tục kinh doanh/thuế — phần mã đã sẵn sàng.

Cấu hình (chủ dự án tự đặt trên Render, KHÔNG để trong mã):
  TERRATWIN_VIETQR_BIN      mã BIN ngân hàng 6 số (vd 970436 Vietcombank, 970415 VietinBank, 970418 BIDV)
  TERRATWIN_VIETQR_ACCOUNT  số tài khoản nhận
  TERRATWIN_VIETQR_NAME     tên chủ tài khoản (KHÔNG DẤU, để hiện cho người chuyển kiểm)
"""
from __future__ import annotations

import os
import re
import unicodedata

GUID = "A000000727"            # định danh NAPAS trong trường 38
SERVICE = "QRIBFTTA"           # chuyển nhanh 24/7 tới TÀI KHOẢN


def _tlv(tag: str, value: str) -> str:
    if len(value) > 99:
        raise ValueError(f"trường {tag} quá dài")
    return f"{tag}{len(value):02d}{value}"


def crc16_ccitt(data: str) -> str:
    """CRC-16/CCITT-FALSE (đa thức 0x1021, khởi tạo 0xFFFF) — đúng thuật toán EMVCo yêu cầu cho trường 63."""
    crc = 0xFFFF
    for b in data.encode("utf-8"):
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return f"{crc:04X}"


def ascii_memo(text: str, limit: int = 25) -> str:
    """Nội dung chuyển khoản: không dấu, chỉ chữ/số/khoảng trắng (nhiều ngân hàng cắt hoặc đổi ký tự lạ)."""
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    t = re.sub(r"[^A-Za-z0-9 ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip().upper()[:limit]


def payload(bin_code: str, account: str, amount_vnd: int | None, memo: str) -> str:
    if not re.fullmatch(r"\d{6}", bin_code or ""):
        raise ValueError("BIN ngân hàng phải gồm 6 chữ số")
    if not re.fullmatch(r"[0-9A-Za-z]{4,19}", account or ""):
        raise ValueError("số tài khoản không hợp lệ")
    beneficiary = _tlv("00", bin_code) + _tlv("01", account)
    s = (_tlv("00", "01")
         + _tlv("01", "12" if amount_vnd else "11")                     # 12 = mã dùng một lần (có số tiền)
         + _tlv("38", _tlv("00", GUID) + _tlv("01", beneficiary) + _tlv("02", SERVICE))
         + _tlv("53", "704")                                              # VND
         + (_tlv("54", str(int(amount_vnd))) if amount_vnd else "")
         + _tlv("58", "VN")
         + (_tlv("62", _tlv("08", ascii_memo(memo))) if memo else "")
         + "6304")
    return s + crc16_ccitt(s)


def configured() -> bool:
    return bool(os.environ.get("TERRATWIN_VIETQR_BIN") and os.environ.get("TERRATWIN_VIETQR_ACCOUNT"))


def for_request(req_id: int, plan_id: str, amount_vnd: int) -> dict:
    """Thông tin chuyển khoản cho một yêu cầu nâng cấp. Chưa cấu hình → available False (không bịa tài khoản)."""
    memo = ascii_memo(f"TT{req_id} {plan_id}")
    if not configured() or amount_vnd <= 0:
        return {"available": False, "amount_vnd": amount_vnd, "memo": memo,
                "note": "Chưa bật thanh toán chuyển khoản (máy chủ chưa đặt TERRATWIN_VIETQR_*). Quản trị liên hệ trực tiếp."}
    bin_code, acct = os.environ["TERRATWIN_VIETQR_BIN"].strip(), os.environ["TERRATWIN_VIETQR_ACCOUNT"].strip()
    data = payload(bin_code, acct, amount_vnd, memo)
    svg = None
    try:
        import segno
        svg = segno.make(data, error="m").svg_data_uri(scale=5, border=2, dark="#0b1218", light="#ffffff")
    except Exception:
        pass
    return {"available": True, "amount_vnd": amount_vnd, "memo": memo, "qr_payload": data, "qr_svg": svg,
            "bank_bin": bin_code, "account_tail": acct[-4:], "account_name": os.environ.get("TERRATWIN_VIETQR_NAME", ""),
            "note": "Quét bằng app ngân hàng bất kỳ. Giữ ĐÚNG nội dung chuyển khoản — quản trị đối chiếu theo nội dung rồi kích hoạt gói."}
