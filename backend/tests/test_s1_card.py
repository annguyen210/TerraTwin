"""Thẻ mô hình s1_water: chưa có kết quả → "đang huấn luyện"; có kết quả → đọc đúng từng tập, đạt vẫn CHƯA bật."""
from __future__ import annotations


def _card(monkeypatch, result):
    from app.services import model_cards
    real = model_cards._load
    monkeypatch.setattr(model_cards, "_load", lambda *p: result if p == ("ml", "s1_water_result.json") else real(*p))
    return next(c for c in model_cards.cards() if c["id"] == "s1_water_unet")


def test_chua_co_ket_qua(monkeypatch):
    c = _card(monkeypatch, None)
    assert c["status"] == "pending" and c["metrics"] == []


def test_dat_van_chua_bat_va_doc_tung_tap(monkeypatch):
    r = {"passed": True, "device": "cuda", "epochs": 40, "best_valid_iou": 0.7, "limit": None,
         "results": {"test": {"model": 0.71, "threshold_-18dB": 0.62, "otsu_per_chip": 0.55},
                     "bolivia": {"model": 0.66, "threshold_-18dB": 0.60, "otsu_per_chip": 0.5},
                     "mekong": {"model": 0.8, "threshold_-18dB": 0.7, "otsu_per_chip": 0.6}}}
    c = _card(monkeypatch, r)
    assert c["status"] == "accepted" and "CHƯA bật" in c["status_label"] and all(m["passed"] for m in c["metrics"])


def test_truot_khi_mot_tap_thua_nguong(monkeypatch):
    r = {"passed": False, "device": "cuda", "epochs": 40, "best_valid_iou": 0.7, "limit": None,
         "results": {"test": {"model": 0.71, "threshold_-18dB": 0.62}, "bolivia": {"model": 0.5, "threshold_-18dB": 0.6}}}
    c = _card(monkeypatch, r)
    assert c["status"] == "rejected" and [m["passed"] for m in c["metrics"]] == [True, False]


def test_lan_thu_may_limit_khong_bao_gio_la_ket_qua(monkeypatch):
    c = _card(monkeypatch, {"passed": False, "limit": 2, "results": {}})
    assert c["status"] == "pending"
