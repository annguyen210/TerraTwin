"""Tổ hợp dự báo mưa best_match + ECMWF AIFS (cổng đăng ký trước đạt 18/10/2026): chỉ trộn MƯA, đúng cách đã chấm."""
from __future__ import annotations


def test_ket_qua_cong_dat_va_bat():
    from app.services import realdata
    assert realdata.blend_on() is True
    assert realdata._models_q() == "&models=best_match,ecmwf_aifs025_single"


def test_tron_mua_trung_binh_aifs_thieu_giu_best_best_thieu_thi_thieu():
    from app.services import realdata
    dd = {"time": ["d1", "d2", "d3", "d4"],
          "precipitation_sum_best_match": [10.0, 4.0, None, 0.0],
          "precipitation_sum_ecmwf_aifs025_single": [30.0, None, 8.0, 0.0],
          "et0_fao_evapotranspiration_best_match": [3.0, 3.1, 3.2, 3.3],
          "et0_fao_evapotranspiration_ecmwf_aifs025_single": [9, 9, 9, 9],
          "temperature_2m_max_best_match": [30.0, 31.0, 32.0, 33.0],
          "temperature_2m_max_ecmwf_aifs025_single": [1, 1, 1, 1]}
    times, precip, et0, tmax = realdata._daily_cols(dd)
    assert precip == [20.0, 4.0, None, 0.0]
    assert et0 == [3.0, 3.1, 3.2, 3.3] and tmax == [30.0, 31.0, 32.0, 33.0]     # chỉ mưa được trộn


def test_mot_mo_hinh_ten_tran_van_doc_duoc():
    from app.services import realdata
    times, precip, et0, tmax = realdata._daily_cols({"time": ["a"], "precipitation_sum": [5.0],
                                                     "et0_fao_evapotranspiration": [2.0], "temperature_2m_max": [29.0]})
    assert precip == [5.0] and et0 == [2.0] and tmax == [29.0]


def test_du_bao_7_ngay_goi_hai_mo_hinh_trong_mot_luot(monkeypatch):
    from app.services import realdata
    seen = []

    def fake_get(url, timeout=8.0, headers=None):
        seen.append(url)
        return {"daily": {"time": [f"2026-10-{18 + i}" for i in range(7)],
                          "precipitation_sum_best_match": [0, 10, 20, 0, 0, 0, 0],
                          "precipitation_sum_ecmwf_aifs025_single": [0, 30, 40, 0, 0, 0, 0],
                          "et0_fao_evapotranspiration_best_match": [3] * 7, "temperature_2m_max_best_match": [31] * 7}}
    monkeypatch.setattr(realdata, "_get", fake_get)
    rows = realdata.weather_7d(16.52, 107.59)
    assert len(seen) == 1 and "models=best_match,ecmwf_aifs025_single" in seen[0]
    assert [r["precip"] for r in rows[:3]] == [0.0, 20.0, 30.0] and rows[0]["et0"] == 3
    assert rows[0]["source"] == "open-meteo-blend"
    from app.services import hazard
    assert "ECMWF AIFS" in hazard.source_label("open-meteo-blend", "lượng mưa", "rain")
    assert hazard.source_label("open-meteo", "lượng mưa", "rain").startswith("Open-Meteo: lượng mưa (thật)")


def test_the_mo_hinh_ghi_gioi_han_dot_rieng_biet():
    from app.services import model_cards
    c = next(x for x in model_cards.cards() if x["id"] == "aifs_blend")
    assert c["status"] == "accepted" and "50" in c["limits"] and "17" in c["limits"] and "22" in c["limits"]
