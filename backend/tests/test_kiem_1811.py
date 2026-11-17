"""Kiểm 18/11/2026 trên production: chữ tiếng Anh lọt ra giao diện tiếng Việt ("Chấm cảnh báo drought…", "chúng tôi báo
urban thửa…") và dòng nhật ký hiện hai lần (một trong câu tóm tắt, một trong danh sách ngay dưới)."""
from __future__ import annotations

from datetime import datetime

from app.modules.registry import module_label
from app.services import plot_journal, reqlang


def test_ten_mo_dun_theo_ngon_ngu():
    reqlang.set_lang("vi")
    assert module_label("urban") == "Ngập úng & mảng xanh đô thị"
    assert "drought" not in module_label("drought")
    assert module_label("khong-co") == "khong-co"
    reqlang.set_lang("en")
    try:
        assert module_label("urban") == "Urban flooding & green space"
    finally:
        reqlang.set_lang("vi")


def test_tom_tat_ngan_khong_lap_lai_su_kien():
    reqlang.set_lang("vi")
    sig = [{"kind": "graded", "text": "Chấm cảnh báo «Hạn» ngày 2026-11-09: BỎ SÓT", "significant": True}]
    since = datetime(2026, 11, 17, 6, 0)
    full = plot_journal.summary(since, sig, {})
    short = plot_journal.summary(since, sig, {}, with_events=False)
    assert "BỎ SÓT" in full                       # bản đầy đủ (MyLand chỉ hiện tóm tắt) vẫn nêu sự kiện
    assert "BỎ SÓT" not in short and "1 thay đổi" in short
