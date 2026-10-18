"""Thẻ mô hình field_water: chưa có kết quả → "đang huấn luyện"; có kết quả → đúng cổng đăng ký trước (≥ 0,70 và hơn màu)."""
from __future__ import annotations


def _card(monkeypatch, result):
    from app.services import model_cards
    real = model_cards._load
    monkeypatch.setattr(model_cards, "_load", lambda *p: result if p == ("ml", "field_water_result.json") else real(*p))
    return next(c for c in model_cards.cards() if c["id"] == "field_water_segformer")


def _res(model, base, passed):
    return {"passed": passed, "device": "cuda", "epochs": 40, "best_valid_iou": 0.8,
            "n": {"train": 204, "valid": 43, "test": 43}, "test": {"model_iou": model, "color_baseline_iou": base}}


def test_chua_co_ket_qua(monkeypatch):
    c = _card(monkeypatch, None)
    assert c["status"] == "pending" and c["metrics"] == []


def test_dat_van_chua_bat(monkeypatch):
    c = _card(monkeypatch, _res(0.78, 0.31, True))
    assert c["status"] == "accepted" and "CHƯA bật" in c["status_label"] and all(m["passed"] for m in c["metrics"])


def test_truot_khi_duoi_070(monkeypatch):
    c = _card(monkeypatch, _res(0.65, 0.31, False))
    assert c["status"] == "rejected" and [m["passed"] for m in c["metrics"]] == [False, True]
