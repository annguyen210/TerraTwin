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


# ---- v2 (đăng ký trước: data/eval/flood_season_v2_protocol.json) — số giả lập, không mạng

def test_v2_tong_mua_3_ngay_va_cua_so_toi_da_12_ngay():
    rows = [{"date": f"2024-09-{d:02d}", "precip": p} for d, p in zip(range(1, 21), [0] * 14 + [40, 90, 70, 5, 0, 0])]
    s = fs.three_day_sums(rows)
    assert s["2024-09-17"] == 200.0 and "2024-09-02" not in s           # cần đủ 3 ngày liên tiếp
    assert fs.window("2024-09-19", "2024-09-07") == ("2024-09-08", "2024-09-19")
    assert fs.window("2024-09-19", "2024-08-01") == ("2024-09-08", "2024-09-19")   # cảnh khô quá xa → tối đa 12 ngày
    assert fs.window("2024-09-19", "2024-09-13") == ("2024-09-14", "2024-09-19")
    assert fs.max3_in_window(s, "2024-09-08", "2024-09-19") == (200.0, "2024-09-17")


def test_v2_phan_vi_noi_suy_tuyen_tinh_nhu_numpy():
    assert fs.percentile([1, 2, 3, 4, 5], 97) == 4.88 and fs.percentile([10], 97) == 10


def test_v2_chi_xet_lai_dot_ngoai_mua_v1(monkeypatch):
    s = {"months": [10, 11, 12, 1]}
    rows = [{"date": f"2024-09-{d:02d}", "precip": p} for d, p in zip(range(1, 21), [0] * 14 + [40, 90, 70, 5, 0, 0])]
    rows += [{"date": f"2024-05-{d:02d}", "precip": 3} for d in range(1, 31)]
    monkeypatch.setattr(fs, "threshold_p97", lambda la, lo: 120.0)
    monkeypatch.setattr(fs, "_rain_rows", lambda la, lo: rows)
    ev = [{"start": "2024-05-20"}, {"start": "2024-09-19"}, {"start": "2024-10-13"}]
    got = {e["start"]: e for e in fs.label_v2(ev, ["2024-05-08", "2024-05-20", "2024-09-07", "2024-09-19", "2024-10-13"], s, 0, 0)}
    assert got["2024-05-20"]["season"] == "out" and got["2024-05-20"]["rain3d_mm"] == 9.0
    assert got["2024-09-19"]["season"] == "extreme" and got["2024-09-19"]["rain3d_mm"] == 200.0 and got["2024-09-19"]["p97_mm"] == 120.0
    assert got["2024-10-13"]["season"] == "in" and "rain3d_mm" not in got["2024-10-13"]   # đợt trong mùa v1 giữ nguyên
