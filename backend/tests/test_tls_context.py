"""Một SSLContext dùng chung cho mọi lượt gọi HTTPS ra ngoài (8/11/2026).

Tạo context mới mỗi lượt gọi = nạp lại kho chứng chỉ CA, GIL bị giữ suốt; trên Render 0,1 CPU đủ để /api/health quá 5 s
và Render khởi động lại instance khi mở một thửa mới.
"""
import ssl
import urllib.request

import app
from app.services import mpc


def _https_handler(opener: urllib.request.OpenerDirector) -> urllib.request.HTTPSHandler:
    return next(h for h in opener.handlers if isinstance(h, urllib.request.HTTPSHandler))


def test_urlopen_dung_context_chung():
    assert isinstance(app.TLS_CONTEXT, ssl.SSLContext)
    assert app.TLS_CONTEXT.verify_mode == ssl.CERT_REQUIRED and app.TLS_CONTEXT.check_hostname
    assert _https_handler(urllib.request._opener)._context is app.TLS_CONTEXT


def test_ket_noi_planetary_computer_dung_context_chung():
    mpc._tls.conn = None
    try:
        assert mpc._pc_conn(5.0)._context is app.TLS_CONTEXT
    finally:
        mpc._tls.conn = None
