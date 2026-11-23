"""Quét toàn bộ 23/11/2026, P1 — "Đo & bán tín chỉ carbon rừng" ghi "PHÙ HỢP" trên ruộng lúa demo (20.9716,106.2834):
"Che phủ tán 5.7% trên 144.0 ha (≈8.15 ha có rừng). Trữ lượng ước tính 3134.88 tCO₂". FAO: rừng = tán ≥ 10% (≥ 0,5 ha)."""
from app.modules.registry import get_module
from app.schemas import Location
from app.services import mrv, reqlang, sentinel


def _fake(monkeypatch, frac):
    monkeypatch.setattr(sentinel, "index_distribution", lambda *a, **k: {"area_ha": 144.0, "mean": 0.4, "std": 0.1, "coverage_pct": 98.0, "observed_window": "2026-10-01/2026-11-20", "pixel_m": 10})
    monkeypatch.setattr(sentinel, "fraction_above", lambda d, thr: frac)


def test_tan_duoi_10_phan_tram_khong_phai_rung(monkeypatch):
    reqlang.set_lang("vi")
    _fake(monkeypatch, 0.057)
    r = mrv.build(20.9716, 106.2834)
    assert r["is_forest"] is False
    assert r["headline"].startswith("Không áp dụng — không phải rừng theo định nghĩa FAO (tán ≥ 10%)")
    assert "tCO" not in r["headline"] and "không phải diện tích thửa" in r["headline"]
    a = get_module("carbon").assess(Location(lat=20.9716, lon=106.2834))
    assert a.status == "out_of_scope" and a.risk_level == "unknown"      # không còn "phù hợp"
    assert "tCO" not in a.headline


def test_rung_that_van_bao_tru_luong(monkeypatch):
    reqlang.set_lang("vi")
    _fake(monkeypatch, 0.62)
    r = mrv.build(11.5, 107.4)
    assert r["is_forest"] is True and "tCO₂" in r["headline"] and "không phải diện tích thửa" in r["headline"]
    a = get_module("carbon").assess(Location(lat=11.5, lon=107.4))
    assert a.status == "ok" and a.risk_level == "safe"
