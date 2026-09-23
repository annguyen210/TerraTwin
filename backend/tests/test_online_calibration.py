"""A13 — hiệu chỉnh trực tuyến: mặc định TẮT (không vùng nào đủ 30 quan sát,
và cờ TERRATWIN_ONLINE_CALIBRATION mặc định tắt luôn cả khi đủ dữ liệu).
Test bằng dữ liệu giả lập — không chạm DB thật, không chạm mạng.
"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from app.services import online_calibration as calibration


def _obs(lat, lon, module_id, model_index, outcome):
    return SimpleNamespace(lat=lat, lon=lon, module_id=module_id,
                           model_index=model_index, outcome=outcome)


def test_pava_lam_don_dieu_dung():
    # 3, 1, 4 → không đơn điệu ở (3,1). Gộp hai điểm đầu thành 2,2 → [2,2,4].
    y = np.array([3.0, 1.0, 4.0])
    out = calibration._pava(y)
    np.testing.assert_array_almost_equal(out, [2.0, 2.0, 4.0])
    assert np.all(np.diff(out) >= -1e-9), "Kết quả PAVA phải không giảm"


def test_pava_da_don_dieu_thi_giu_nguyen():
    y = np.array([1.0, 2.0, 3.0, 5.0])
    out = calibration._pava(y)
    np.testing.assert_array_almost_equal(out, y)


def test_mac_dinh_tat_khong_doi_gia_tri():
    """Cờ ENABLED mặc định đọc từ môi trường — session test không đặt
    TERRATWIN_ONLINE_CALIBRATION nên phải là tắt."""
    assert calibration.ENABLED is False, (
        "A13 phải mặc định TẮT — không được tự bật khi chưa ai gạt cờ")


def test_calibrate_tra_ve_nguyen_khi_tat(monkeypatch):
    monkeypatch.setattr(calibration, "ENABLED", False)
    obs = [_obs(10.0, 106.0, "flood", 70.0, "occurred") for _ in range(50)]
    r = calibration.calibrate(obs, "10.0,106.0", "flood", raw_index=55.0)
    assert r["calibrated_index"] == 55.0
    assert r["used_calibration"] is False
    assert r["reason"] == "off_by_flag"


def test_calibrate_tra_ve_nguyen_khi_thieu_du_lieu(monkeypatch):
    monkeypatch.setattr(calibration, "ENABLED", True)
    # Chỉ 5 quan sát — dưới MIN_OBS_CALIBRATION (30).
    obs = [_obs(10.0, 106.0, "flood", 70.0, "occurred") for _ in range(5)]
    r = calibration.calibrate(obs, "10.0,106.0", "flood", raw_index=55.0)
    assert r["calibrated_index"] == 55.0
    assert r["used_calibration"] is False
    assert r["reason"] == "not_enough_observations"
    assert r["observations"] == 5


def test_calibrate_chi_tinh_quan_sat_dung_vung_dung_module(monkeypatch):
    monkeypatch.setattr(calibration, "ENABLED", True)
    same = [_obs(10.0, 106.0, "flood", float(i), "none") for i in range(20)]
    other_cell = [_obs(20.0, 116.0, "flood", 90.0, "occurred") for _ in range(20)]
    other_module = [_obs(10.0, 106.0, "drought", 90.0, "occurred") for _ in range(20)]
    r = calibration.calibrate(same + other_cell + other_module,
                              "10.0,106.0", "flood", raw_index=50.0)
    # Chỉ 20 quan sát "same" hợp lệ — vẫn dưới 30 dù tổng truyền vào là 60.
    assert r["observations"] == 20
    assert r["used_calibration"] is False


def test_calibrate_hieu_chinh_khi_du_du_lieu_va_bat_co(monkeypatch):
    monkeypatch.setattr(calibration, "ENABLED", True)
    # Model báo cao (70-100) nhưng THỰC TẾ hiếm khi xảy ra ("none") → model
    # đang lạc quan quá — hiệu chỉnh phải kéo calibrated_index XUỐNG so với raw.
    obs = []
    for i in range(40):
        idx = 60.0 + i  # 60..99
        outcome = "occurred" if i < 3 else "none"   # hầu hết KHÔNG xảy ra dù model báo cao
        obs.append(_obs(10.0, 106.0, "flood", idx, outcome))

    r = calibration.calibrate(obs, "10.0,106.0", "flood", raw_index=90.0)
    assert r["used_calibration"] is True
    assert r["observations"] == 40
    assert r["calibrated_index"] < 90.0, (
        f"Model lạc quan quá mà quan sát cho thấy hiếm khi xảy ra thật — "
        f"hiệu chỉnh phải kéo XUỐNG, kết quả: {r}")


def test_do_dich_chuyen_bi_chan_tran():
    monkeypatch_target = calibration
    monkeypatch_target.ENABLED = True
    try:
        # Cực đoan: model báo 100 nhưng CHƯA BAO GIỜ xảy ra — không hiệu chỉnh
        # nào được đẩy calibrated_index xuống quá MAX_DISPLACEMENT so với raw.
        obs = [_obs(10.0, 106.0, "flood", 100.0, "none") for _ in range(40)]
        r = calibration.calibrate(obs, "10.0,106.0", "flood", raw_index=100.0)
        assert r["used_calibration"] is True
        assert abs(r["displacement"]) <= calibration.MAX_DISPLACEMENT + 1e-6
        assert r["raw_index"] + r["displacement"] == pytest.approx(r["calibrated_index"])
    finally:
        monkeypatch_target.ENABLED = False
