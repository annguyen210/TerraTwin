"""VietQR (EMVCo/NAPAS): mã kiểm CRC đúng chuẩn, cấu trúc trường đúng, chưa cấu hình thì KHÔNG bịa tài khoản."""
from __future__ import annotations


def test_crc_dung_gia_tri_kiem_chuan():
    from app.services import vietqr
    assert vietqr.crc16_ccitt("123456789") == "29B1"          # giá trị kiểm chuẩn của CRC-16/CCITT-FALSE


def test_chuoi_qr_dung_cau_truc_va_tu_kiem_duoc():
    from app.services import vietqr
    s = vietqr.payload("970436", "0123456789", 299000, "TT12 pro")
    assert s.startswith("000201010212") and "0010A000000727" in s and "0208QRIBFTTA" in s
    assert "5303704" in s and "5406299000" in s and "5802VN" in s and "0808TT12 PRO" in s
    assert s[-8:-4] == "6304" and vietqr.crc16_ccitt(s[:-4]) == s[-4:]
    # trường 38: 00 GUID + 01 (00 BIN + 01 số TK) + 02 dịch vụ
    assert "38540010A00000072701240006970436011001234567890208QRIBFTTA" in s


def test_noi_dung_khong_dau_va_gioi_han():
    from app.services import vietqr
    assert vietqr.ascii_memo("Nâng cấp gói Mở rộng — TT12!") == "NANG CAP GOI MO RONG TT12"
    assert len(vietqr.ascii_memo("x" * 80)) == 25


def test_chua_cau_hinh_khong_bia_tai_khoan(monkeypatch):
    from app.services import vietqr
    monkeypatch.delenv("TERRATWIN_VIETQR_BIN", raising=False)
    monkeypatch.delenv("TERRATWIN_VIETQR_ACCOUNT", raising=False)
    r = vietqr.for_request(7, "pro", 299000)
    assert r["available"] is False and "qr_payload" not in r and r["memo"] == "TT7 PRO"


def test_da_cau_hinh_tra_qr_va_chi_4_so_cuoi(monkeypatch):
    from app.services import vietqr
    monkeypatch.setenv("TERRATWIN_VIETQR_BIN", "970436")
    monkeypatch.setenv("TERRATWIN_VIETQR_ACCOUNT", "0123456789")
    r = vietqr.for_request(7, "pro", 299000)
    assert r["available"] and r["account_tail"] == "6789" and r["qr_svg"].startswith("data:image/svg+xml")
    assert "0123456789" not in str({k: v for k, v in r.items() if k != "qr_payload"})
