"""A7 — kiểm chứng thuật toán BFAST/CUSUM rút gọn bằng chuỗi GIẢ LẬP có kiểm
soát, đúng hai tiêu chí "done when" của yêu cầu gốc:

  1. Lúa ba vụ (dao động mùa vụ đều đặn) KHÔNG được báo là mất tán cây.
  2. Một đợt phá rừng biết trước THÁNG xảy ra PHẢI được báo đúng khoảng đó.

Không chạm mạng — dùng detect_from_series() trực tiếp, không qua mpc.index_series()
(cái đó cần ảnh Sentinel-2 thật, xem app/services/change_detect.detect()).
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from app.services import change_detect

RNG = np.random.default_rng(42)


def _dates(n_days: int, step_days: int = 8, start: str = "2024-01-01") -> list[str]:
    d0 = date.fromisoformat(start)
    return [(d0 + timedelta(days=i)).isoformat() for i in range(0, n_days, step_days)]


def _rice_series(dates: list[str], noise: float = 0.02) -> list[float]:
    """Lúa ba vụ/năm: NDVI lên ~0,7 giữa vụ, xuống ~0,15 lúc gặt — chu kỳ
    ~121,75 ngày, LẶP LẠI ĐỀU trong suốt 24 tháng, không có xu hướng giảm."""
    d0 = date.fromisoformat(dates[0])
    out = []
    for d in dates:
        t = (date.fromisoformat(d) - d0).days
        phase = 2 * np.pi * t / (365.25 / 3.0)
        # Nửa sin dương (lên rồi xuống trong mỗi vụ), không âm.
        v = 0.15 + 0.55 * max(0.0, np.sin(phase)) ** 1.5
        out.append(float(v + RNG.normal(0, noise)))
    return out


def _forest_then_cleared_series(dates: list[str], clear_at_day: int,
                                noise: float = 0.03) -> list[float]:
    """Rừng ổn định NDVI ~0,75 (dao động mùa nhẹ), rồi mất tán ĐỘT NGỘT tại
    clear_at_day và KHÔNG hồi phục — đúng dạng ảnh vệ tinh của một đợt phá
    rừng thật (khác lúa: không có chu kỳ lặp, chỉ MỘT lần đổi rồi giữ nguyên)."""
    d0 = date.fromisoformat(dates[0])
    out = []
    for d in dates:
        t = (date.fromisoformat(d) - d0).days
        seasonal_wobble = 0.03 * np.sin(2 * np.pi * t / 365.25)   # rừng cũng nhích nhẹ theo mùa
        base = 0.75 if t < clear_at_day else 0.20
        out.append(float(base + seasonal_wobble + RNG.normal(0, noise)))
    return out


def test_lua_ba_vu_khong_bi_bao_mat_tan_cay():
    """Tiêu chí 1: dao động mùa vụ đều đặn KHÔNG được xem là mất tán cây."""
    dates = _dates(730)
    values = _rice_series(dates)
    r = change_detect.detect_from_series(dates, values)
    assert r["available"] is True
    assert r["change_detected"] is False, (
        f"Lúa ba vụ bị báo nhầm là mất tán cây: {r}")


def test_pha_rung_duoc_bao_dung_khoang_thang():
    """Tiêu chí 2: phá rừng ở một mốc BIẾT TRƯỚC phải được phát hiện, và mốc
    báo ra phải nằm trong vòng ~1 tháng quanh mốc thật."""
    dates = _dates(730)
    clear_day = 400   # khoảng tháng thứ 13 trong chuỗi 24 tháng
    values = _forest_then_cleared_series(dates, clear_at_day=clear_day)
    r = change_detect.detect_from_series(dates, values)
    assert r["available"] is True
    assert r["change_detected"] is True, f"Không phát hiện được đợt phá rừng rõ ràng: {r}"

    d0 = date.fromisoformat(dates[0])
    reported_day = (date.fromisoformat(r["change_date"]) - d0).days
    assert abs(reported_day - clear_day) <= 31, (
        f"Mốc báo ra ({r['change_date']}, ngày {reported_day}) lệch quá xa "
        f"mốc thật (ngày {clear_day})")
    assert r["level_shift_ndvi"] < 0, "Mất tán cây phải là mức GIẢM, không phải tăng"


def test_tang_che_phu_khong_bi_bao_la_mat_tan_cay():
    """Một khúc gãy đi LÊN (vd trồng lại, phục hồi) không phải 'mất tán cây' —
    dù cùng độ mạnh thống kê với một đợt phá rừng, dấu phải đúng."""
    dates = _dates(730)
    d0 = date.fromisoformat(dates[0])
    values = []
    for d in dates:
        t = (date.fromisoformat(d) - d0).days
        base = 0.20 if t < 400 else 0.75   # NGƯỢC lại: thấp rồi tăng vọt
        values.append(float(base + RNG.normal(0, 0.03)))
    r = change_detect.detect_from_series(dates, values)
    assert r["available"] is True
    assert r["change_detected"] is False, (
        "Tăng che phủ (đi lên) không được gắn nhãn 'mất tán cây'")


def test_qua_it_diem_thi_bao_khong_du_du_lieu():
    dates = _dates(60, step_days=20)   # 3 điểm — dưới MIN_POINTS
    values = [0.5, 0.51, 0.49]
    r = change_detect.detect_from_series(dates, values)
    assert r["available"] is False
    assert r["reason"] == "not_enough_points"


def test_nhieu_ngau_nhien_thuan_khong_bao_doi():
    """Nhiễu trắng quanh một mức ổn định — không có mùa vụ, không có đổi
    thật — không được báo dương tính giả."""
    dates = _dates(730)
    values = [float(0.5 + RNG.normal(0, 0.03)) for _ in dates]
    r = change_detect.detect_from_series(dates, values)
    assert r["available"] is True
    assert r["change_detected"] is False
