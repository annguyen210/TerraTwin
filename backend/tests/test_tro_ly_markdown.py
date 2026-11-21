"""Kiểm 21/11/2026: khung trả lời trợ lý in nguyên văn nên "**5 đợt**" của LLM lộ dấu ** ra màn hình."""
from app.services import copilot


def test_bo_markdown_thua():
    s = "## Kết luận\nThửa này đã có **5 đợt** nước phủ và __15 đợt__ điều kiện thời tiết ERA5. Còn ** lẻ."
    out = copilot._plain(s)
    assert "**" not in out and "__" not in out and not out.startswith("#")
    assert "5 đợt nước phủ" in out and "15 đợt điều kiện" in out


def test_loi_dan_cam_markdown():
    assert "markdown" in copilot._system().lower()


def test_loi_dan_khong_bao_viet_thuong():
    """21/11/2026: "Viết chữ thường" trong tiếng Việt nghĩa là KHÔNG VIẾT HOA — LLM trả "radar sentinel‑1", "era5"."""
    s = copilot._system()
    assert "chữ thường" not in s and "viết hoa đúng chính tả" in s


def test_che_do_tieng_viet_khong_chen_tieng_anh():
    """21/11/2026: chế độ VI trả "…Sentinel‑1; additionally, ERA5 ghi nhận…" — mỗi chế độ ra đúng một ngôn ngữ."""
    out = copilot._viet_hoa("Thửa này đã từng ngập; additionally, ERA5 ghi nhận 15 đợt. However radar Sentinel-1 thấy 5 đợt.")
    assert "additionally" not in out.lower() and "however" not in out.lower()
    assert "ngoài ra, ERA5" in out and "Tuy nhiên radar Sentinel-1" in out


def test_loi_dan_moi_che_do_mot_ngon_ngu():
    from app.services import reqlang
    reqlang.set_lang("vi")
    assert "CHỈ dùng tiếng Việt" in copilot._system()
    reqlang.set_lang("en")
    try:
        assert "ONLY in English" in copilot._system()
    finally:
        reqlang.set_lang("vi")
