"""Quy tắc mùa lũ v1 (lớp diễn giải, đăng ký trước — data/eval/flood_season_protocol.json). Số giả lập, không mạng."""
from app.services import flood_season as fs


def test_loi_la_cac_thang_mua_nhieu_nhat_toi_50_phan_tram_cong_thang_lien_sau():
    # khí hậu kiểu miền Trung: mưa dồn tháng 9–12
    mm = [60, 30, 30, 50, 90, 80, 70, 120, 400, 800, 600, 250]
    s = fs.season_from_monthly(mm)
    assert s["core"] == [10, 11] and s["months"] == [10, 11, 12]   # 800+600 = 1400 ≥ 50% của 2580
    assert s["annual_mm"] == 2580


def test_mua_vong_qua_cuoi_nam_va_chu_thich_thang():
    mm = [300, 50, 40, 30, 30, 30, 30, 30, 40, 60, 100, 280]
    s = fs.season_from_monthly(mm)
    assert s["core"] == [1, 12] and s["months"] == [1, 2, 12]
    assert fs.months_text(s["months"]) == "12–2"
    assert fs.months_text([7, 8, 9, 10]) == "7–10" and fs.months_text([3, 7, 8]) == "3, 7–8"


def test_gan_nhan_theo_thang_bat_dau_cua_dot():
    s = {"months": [9, 10, 11, 12]}
    assert fs.label("2020-10-10", s) == "in" and fs.label("2026-01-30", s) == "out"


def test_mua_trung_binh_tung_thang_qua_cac_nam():
    rows = [{"date": "2016-01-01", "precip": 10}, {"date": "2016-01-02", "precip": 5}, {"date": "2017-01-05", "precip": 25},
            {"date": "2016-02-01", "precip": 4}]
    mm = fs.monthly_mm(rows)
    assert mm[0] == 20.0 and mm[1] == 4.0 and mm[2] == 0.0
