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


# ---- v3 (đăng ký trước: data/eval/flood_season_v3_protocol.json) — số giả lập, không mạng

def test_v3_o_glofas_trong_5_km_tam_o_x25_x75():
    cells = fs.cells_within(16.52, 107.59)
    assert cells and all(fs._km(16.52, 107.59, *c) <= 5.0 for c in cells)
    assert all(round(c[0] / 0.025) % 2 == 1 and round(c[1] / 0.025) % 2 == 1 for c in cells)   # tâm ô ở x,x25 / x,x75


def _v3_setup(monkeypatch, in_scope=True):
    cell = {"lat": 16.525, "lon": 107.625, "km": 3.9, "mean_m3s": 85.0 if in_scope else 3.0,
            "p97_m3s": 900.0, "p90_m3s": 400.0, "in_scope": in_scope}
    monkeypatch.setattr(fs, "river_cell", lambda la, lo: cell)
    q = {"2024-09-08": 50.0, "2024-09-18": 950.0, "2024-09-19": 700.0, "2024-05-15": 450.0, "2024-05-20": 300.0}
    monkeypatch.setattr(fs, "discharge", lambda c, frm, to: {d: v for d, v in q.items() if frm <= d <= to})
    rows = [{"date": f"2024-09-{d:02d}", "precip": p} for d, p in zip(range(1, 21), [0] * 14 + [40, 90, 70, 5, 0, 0])]
    rows += [{"date": f"2024-05-{d:02d}", "precip": 3} for d in range(1, 31)]
    monkeypatch.setattr(fs, "threshold_p97", lambda la, lo: 120.0)
    monkeypatch.setattr(fs, "_rain_rows", lambda la, lo: rows)


def test_v3_R_a_va_R_b_chi_xet_lai_dot_ngoai_mua(monkeypatch):
    _v3_setup(monkeypatch)
    s = {"months": [10, 11, 12, 1]}
    ev = [{"start": "2024-05-20"}, {"start": "2024-09-19"}, {"start": "2024-10-13"}]
    scenes = ["2024-05-08", "2024-05-20", "2024-09-07", "2024-09-19", "2024-10-13"]
    a = {e["start"]: e for e in fs.label_v3(ev, scenes, s, 16.52, 107.59, "a")}
    assert a["2024-09-19"]["season"] == "river" and a["2024-09-19"]["q_max_m3s"] == 950.0 and a["2024-09-19"]["q_date"] == "2024-09-18"
    assert a["2024-05-20"]["season"] == "out" and a["2024-05-20"]["q_max_m3s"] == 450.0      # 450 < P97 900
    assert a["2024-10-13"]["season"] == "in" and "q_max_m3s" not in a["2024-10-13"]
    b = {e["start"]: e for e in fs.label_v3(ev, scenes, s, 16.52, 107.59, "b")}
    assert b["2024-09-19"]["season"] == "river" and b["2024-09-19"]["rain3d_mm"] == 200.0     # q ≥ P90 VÀ mưa ≥ P97
    assert b["2024-05-20"]["season"] == "out"                                                  # q 450 ≥ P90 nhưng mưa 9 mm


def test_v3_ngoai_pham_vi_giu_nhan_v1(monkeypatch):
    _v3_setup(monkeypatch, in_scope=False)
    out = fs.label_v3([{"start": "2024-09-19"}], ["2024-09-07", "2024-09-19"], {"months": [10, 11, 12, 1]}, 16.52, 107.59, "a")
    assert out[0]["season"] == "out" and out[0]["v3_scope"] is False and "q_max_m3s" not in out[0]
