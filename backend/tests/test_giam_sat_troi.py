"""Nâng cấp 25/11/2026 — giám sát trôi xác suất đã hiệu chuẩn: lệch quá 2 độ lệch chuẩn (≥ 30 cảnh báo) → tự tắt."""
from __future__ import annotations

import random

from app.services import alert_prob, calibration_drift as cd


def test_dung_hua_thi_khong_troi():
    rnd = random.Random(1)
    rows = [(0.7, 1 if rnd.random() < 0.7 else 0) for _ in range(400)]
    r = cd.evaluate(rows)
    assert r["enough"] and not r["drift"] and abs(r["observed"] - 0.7) < 0.08


def test_lech_xa_thi_troi():
    r = cd.evaluate([(0.8, 1)] * 10 + [(0.8, 0)] * 30)     # hứa 80%, trúng 25%
    assert r["drift"] and r["z"] < -2


def test_it_mau_chua_ket_luan():
    r = cd.evaluate([(0.8, 0)] * 10)
    assert not r["enough"] and not r["drift"]
    assert cd.evaluate([])["n"] == 0


def test_troi_thi_alert_prob_tu_tat(monkeypatch):
    monkeypatch.setattr(cd, "drifted", lambda: True)
    alert_prob._table.cache_clear()
    assert alert_prob.calibrated("flood", 72.0) is None
    monkeypatch.setattr(cd, "drifted", lambda: False)
    assert alert_prob.calibrated("flood", 72.0) is not None       # bảng thật data/alert_calibration.json
    alert_prob._table.cache_clear()


def test_xac_suat_di_tu_danh_gia_toi_canh_bao():
    from types import SimpleNamespace as NS
    from app.services import radar
    assert radar._p_cal(NS(p_calibrated=0.78)) == 0.78
    assert radar._p_cal(NS(metrics={"xac_suat_hieu_chuan_pct": 86.0})) == 0.86
    assert radar._p_cal(NS()) is None
