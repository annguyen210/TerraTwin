"""Những thứ phải đúng TRƯỚC KHI app phục vụ được request đầu tiên.

Bài học đắt: một dòng `print()` tiếng Việt trong `lifespan` làm app không khởi
động nổi trên console cp1252 (mặc định của Windows) — sập với UnicodeEncodeError
trước cả khi mở cổng. Lỗi kiểu này không bao giờ lộ ra trong pytest vì pytest
bắt stdout bằng UTF-8; nó chỉ nổ đúng lúc deploy. Nên phải test có chủ đích.
"""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path

import pytest

from app.main import log

APP = Path(__file__).resolve().parent.parent / "app"


class _Cp1252Stdout(io.TextIOWrapper):
    """Giả lập console Windows mặc định: không encode được tiếng Việt."""

    def __init__(self):
        self._raw = io.BytesIO()
        super().__init__(self._raw, encoding="cp1252", errors="strict",
                         write_through=True)


def test_log_khong_sap_khi_console_khong_ho_tro_tieng_viet(monkeypatch):
    fake = _Cp1252Stdout()
    monkeypatch.setattr(sys, "stdout", fake)
    # Không được ném — đây chính là dòng đã làm app không khởi động được.
    log("[TerraTwin] Rà soát chủ động: bộ hẹn giờ nội bộ đã bật — ✓")
    fake.flush()
    out = fake._raw.getvalue()
    assert out, "phải ghi ra được cái gì đó, dù là bản thay ký tự"
    assert b"TerraTwin" in out


def test_log_van_giu_nguyen_tieng_viet_khi_console_utf8(monkeypatch):
    raw = io.BytesIO()
    fake = io.TextIOWrapper(raw, encoding="utf-8", write_through=True)
    monkeypatch.setattr(sys, "stdout", fake)
    log("Rà soát chủ động")
    fake.flush()
    assert "Rà soát chủ động" in raw.getvalue().decode("utf-8")


def test_khong_con_print_tho_trong_main():
    """main.py phải đi qua log(), trừ chính thân hàm log().

    Chốt chặn để lần sau ai thêm một dòng print() tiếng Việt vào lifespan thì
    test đỏ ngay, thay vì phát hiện lúc container không chịu khởi động.
    """
    src = (APP / "main.py").read_text(encoding="utf-8")
    body = src[src.index("def log("):]
    body = body[:body.index("\n\n\n")]          # chỉ thân hàm log()
    rest = src.replace(body, "")
    offenders = re.findall(r"(?m)^\s*print\(", rest)
    assert not offenders, f"còn {len(offenders)} chỗ print() thô trong main.py"


def test_bo_hen_gio_tat_duoc_bang_bien_moi_truong():
    """Chạy nhiều worker thì phải tắt được, không thì mỗi worker quét một lần."""
    src = (APP / "main.py").read_text(encoding="utf-8")
    assert "TERRATWIN_RADAR_INTERVAL_H" in src
    assert "if _RADAR_INTERVAL_H > 0:" in src


def test_radar_logic_chi_ton_tai_mot_ban():
    """Route và bộ hẹn giờ phải gọi CÙNG một hàm.

    Có hai bản logic quét là chuyện sớm muộn chúng lệch nhau, và bản chạy nền
    (không ai nhìn) sẽ là bản sai.
    """
    routes = (APP / "routes_data.py").read_text(encoding="utf-8")
    assert "radar.sweep_user" in routes
    # Logic cũ đã phải biến mất khỏi route
    assert "_DEDUP_HOURS" not in routes
    assert "scan_svc.scan" not in routes


@pytest.mark.parametrize("var", [
    "TERRATWIN_SECRET", "TERRATWIN_TRUST_PROXY", "TERRATWIN_RADAR_INTERVAL_H",
    "TERRATWIN_LLM_PROVIDER", "TERRATWIN_COPERNICUS_ID",
])
def test_render_yaml_khai_bao_du_bien(var):
    """Biến nào code đọc mà render.yaml không khai thì deploy xong mới biết.

    TERRATWIN_LLM_PROVIDER là ví dụ đắt nhất: thiếu nó, người dùng cắm khóa
    Gemini vào sẽ thấy trợ lý im lặng tụt về rule-based mà không có lỗi nào.
    """
    y = (APP.parent.parent / "render.yaml").read_text(encoding="utf-8")
    assert var in y, f"render.yaml thiếu {var}"
