"""Kiểm A–Z 24/11/2026: cùng thửa Tuệ Tĩnh, Sổ tay thửa "15 đợt mưa lớn", So sánh "16" — khung 10 năm trượt theo ngày,
hai trang nhớ đệm ở hai ngày khác nhau. Khung neo theo THÁNG TRỌN và vào khoá nhớ đệm của cả hai trang."""
from __future__ import annotations

from datetime import date

from app.services import passport


def test_khung_neo_theo_thang_tron():
    assert passport.window_end(date(2026, 11, 24)) == date(2026, 10, 31)
    assert passport.window_end(date(2026, 11, 30)) == date(2026, 10, 31)     # cả tháng 11 cùng một khung
    assert passport.window_end(date(2026, 12, 10)) == date(2026, 10, 31)     # độ trễ ERA5 10 ngày
    assert passport.window_end(date(2026, 12, 11)) == date(2026, 11, 30)


def test_hai_trang_cung_khoa_thang():
    """Khoá nhớ đệm của Sổ tay thửa (passport.build) và So sánh (plot_compare) đều có tháng cuối của khung."""
    import inspect
    from app.services import plot_compare
    assert "window_tag()" in inspect.getsource(passport.build)
    assert "passport.window_tag()" in inspect.getsource(plot_compare)
    assert passport.window_tag() == passport.window_end().isoformat()[:7]


def test_nhan_ban_kinh_dung_voi_so_do():
    """So sánh từng ghi "Thấp hơn % đất trong 5 km" trong khi số đo lấy 3 vòng 1–3 km (như Sổ tay thửa, Kiểm tin rao)."""
    from app.services import plot_compare
    row = next(r for r in plot_compare.ROWS if r[0] == "lower_than_pct") if hasattr(plot_compare, "ROWS") else None
    src = __import__("inspect").getsource(plot_compare)
    assert f"trong {int(max(passport.RINGS_KM))} km" in src and "Thấp hơn % đất trong 5 km" not in src
    assert row is None or "3 km" in row[1]


def test_vung_nhiem_man_co_tran_khoang_cach_bien():
    """Ruộng Tuệ Tĩnh (cách biển 54 km) và Hà Nội từng thành "vùng nhiễm mặn ĐBSH"; Châu Đốc thượng nguồn thành "vùng mặn ĐBSCL"."""
    from app.services import datasources as ds, reqlang
    reqlang.set_lang("vi")
    assert ds.salinity_zone(20.9716, 106.2834) is None and ds.salinity_zone(21.03, 105.85) is None
    assert ds.salinity_zone(20.45, 106.55) == "Đồng bằng sông Hồng"            # Thái Bình ven biển
    assert ds.salinity_zone(10.70, 105.117) is None                          # Châu Đốc
    assert ds.salinity_zone(10.04427, 106.5902) == "Đồng bằng sông Cửu Long"  # Ba Tri
