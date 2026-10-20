"""Thẻ mô hình s1_water: chưa có kết quả → "đang huấn luyện"; có kết quả → đọc đúng từng tập, đạt vẫn CHƯA bật."""
from __future__ import annotations


def _card(monkeypatch, result, confirm=None):
    from app.services import model_cards
    real = model_cards._load
    files = {("ml", "s1_water_result.json"): result, ("ml", "s1_unet_confirm_result.json"): confirm}
    monkeypatch.setattr(model_cards, "_load", lambda *p: files[p] if p in files else real(*p))
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


def test_dat_cong_mo_hinh_nhung_truot_phep_kiem_thua_gd2(monkeypatch):
    r = {"passed": True, "device": "cuda", "epochs": 40, "best_valid_iou": 0.6457, "limit": None,
         "results": {"test": {"model": 0.668, "threshold_-18dB": 0.443}}}
    conf = {"passed": False, "positive": [{"label": "lũ Huế 10/2020", "events": [{"flag_date": "2020-10-10", "unet_share": 0.0}], "pass": False}],
            "negative": [{"case": "Đồi thông", "n": 24, "n_confirmed_wrongly_or_unread": 14, "pass": False}]}
    c = _card(monkeypatch, r, conf)
    assert c["status"] == "rejected" and "TRƯỢT phép kiểm" in c["status_label"]
    assert [m["passed"] for m in c["metrics"]] == [True, False, False]
