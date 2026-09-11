"""A3 — dự báo xác suất từ tổ hợp: phân vị + % vượt ngưỡng."""
from app.services import probabilistic
from app.services import hazard


def test_not_enough_members():
    r = probabilistic.summarize([50.0, 60.0])
    assert r["available"] is False


def test_all_safe_gives_zero_probability():
    r = probabilistic.summarize([10, 20, 30, 35, 38, 15])
    assert r["available"] is True
    assert r["prob_exceed_warning"] == 0
    assert r["prob_exceed_watch"] == 0
    assert "an toàn" in r["sentence"]


def test_all_danger_gives_full_probability():
    r = probabilistic.summarize([80, 85, 90, 75, 72, 95])
    assert r["prob_exceed_warning"] == 100
    assert "NGUY HIỂM" in r["sentence"]


def test_percentiles_and_mixed_probability():
    peaks = [30, 40, 45, 50, 60, 75, 80]     # 2/7 ≥ 70 → ~29%; 6/7 ≥ 40 → ~86%
    r = probabilistic.summarize(peaks)
    assert r["p10"] <= r["p50"] <= r["p90"]
    assert r["prob_exceed_warning"] == 29
    assert r["prob_exceed_watch"] == 86


def test_thresholds_match_hazard():
    # Ngưỡng dùng đúng của hazard, không bịa hằng số riêng.
    assert hazard.WARNING == 70.0 and hazard.SAFE == 40.0
