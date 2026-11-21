"""Kiểm 21/11/2026: khung trả lời trợ lý in nguyên văn nên "**5 đợt**" của LLM lộ dấu ** ra màn hình."""
from app.services import copilot


def test_bo_markdown_thua():
    s = "## Kết luận\nThửa này đã có **5 đợt** nước phủ và __15 đợt__ điều kiện thời tiết ERA5. Còn ** lẻ."
    out = copilot._plain(s)
    assert "**" not in out and "__" not in out and not out.startswith("#")
    assert "5 đợt nước phủ" in out and "15 đợt điều kiện" in out


def test_loi_dan_cam_markdown():
    assert "markdown" in copilot._system().lower()
