"""Mục 6 (25/11/2026) — xếp hạng khả năng ngập theo địa hình chỉ hiện khi có tệp mô hình đã qua cổng."""
from __future__ import annotations

import json

from app.schemas import Assessment, Location
from app.services import flood_susceptibility as fs, reqlang

M = {"w": [0.0, -1.0, 0.0, 0.0, 0.0, 0.0], "mu": [2.0, 0, 0, 0, 0], "sd": [1.0, 1, 1, 1, 1],
     "ref_scores": [0.1, 0.2, 0.3, 0.5, 0.7, 0.9], "auc_test": 0.78}


def test_khong_co_mo_hinh_thi_khong_hien(monkeypatch, tmp_path):
    monkeypatch.setattr(fs, "MODEL", tmp_path / "khong.json")
    fs._model.cache_clear()
    assert fs.assess(10.0, 106.0) is None
    fs._model.cache_clear()


def test_xep_hang_va_gan_vao_module(monkeypatch, tmp_path):
    f = tmp_path / "m.json"
    f.write_text(json.dumps(M), encoding="utf-8")
    monkeypatch.setattr(fs, "MODEL", f)
    fs._model.cache_clear()
    monkeypatch.setattr(fs, "features", lambda lat, lon: [0.0, 1, 0, 0, 0])     # thấp → z = +2 → p ≈ 0.88
    r = fs.assess(10.0, 106.0)
    assert r["score"] == 0.881 and r["top_pct"] == 17 and r["n_ref"] == 6
    reqlang.set_lang("vi")
    from app.modules.group_b import _with_terrain
    loc = Location(lat=10.0, lon=106.0)
    a = _with_terrain(Assessment(module_id="flood", module_name="Lũ", location=loc, status="ok", risk_level="safe",
                                 headline="h", detail="d.", recommendation="r"), loc)
    assert a.metrics["kha_nang_ngap_dia_hinh_top_pct"] == 17 and "17%" in a.detail and "AUC 0.78" in a.detail
    fs._model.cache_clear()
