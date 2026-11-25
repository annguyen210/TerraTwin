"""Mục 7 (25/11/2026) — xác suất cảnh báo ĐÃ HIỆU CHUẨN chỉ hiện cho module có trong bảng (đã qua cổng)."""
from __future__ import annotations

import json

from app.schemas import Assessment, Location
from app.services import alert_prob, reqlang

TABLE = {"modules": {"flood": {"steps": [[20.0, 0.05], [55.0, 0.3], [100.0, 0.8]], "bins": [0, 20, 40, 55, 70, 101],
                               "halfwidth_by_bin": {"0": 8.0, "1": 15.0, "2": 20.0, "3": 25.0, "4": 30.0},
                               "hit_threshold": 40.0, "n_test": 1900, "brier_skill": 0.21, "coverage": 0.9}}}


def _use(monkeypatch, tmp_path, table):
    f = tmp_path / "t.json"
    f.write_text(json.dumps(table), encoding="utf-8")
    monkeypatch.setattr(alert_prob, "TABLE", f)
    alert_prob._table.cache_clear()


def test_tra_bang_va_dai(monkeypatch, tmp_path):
    _use(monkeypatch, tmp_path, TABLE)
    c = alert_prob.calibrated("flood", 72.0)
    assert c["p_hit"] == 0.8 and (c["lo"], c["hi"]) == (42.0, 100.0)
    assert alert_prob.calibrated("flood", 10.0)["p_hit"] == 0.05
    assert alert_prob.calibrated("landslide", 72.0) is None          # module không có trong bảng (trượt cổng) → không số
    reqlang.set_lang("vi")
    assert "80%" in alert_prob.sentence(c) and "1900" in alert_prob.sentence(c)
    alert_prob._table.cache_clear()


def test_khong_co_bang_thi_khong_hien_gi(monkeypatch, tmp_path):
    monkeypatch.setattr(alert_prob, "TABLE", tmp_path / "khong-co.json")
    alert_prob._table.cache_clear()
    assert alert_prob.calibrated("flood", 72.0) is None
    alert_prob._table.cache_clear()


def test_module_gan_xac_suat_chi_khi_du_lieu_that(monkeypatch, tmp_path):
    from app.modules.group_b import _with_prob
    _use(monkeypatch, tmp_path, TABLE)
    loc = Location(lat=16.46, lon=107.59)
    mk = lambda: Assessment(module_id="flood", module_name="Lũ", location=loc, status="ok", risk_level="warning",  # noqa: E731
                            headline="h", detail="d.", recommendation="r")
    s = [("d1", 0, 30.0), ("d2", 1, 72.0)]
    a = _with_prob(mk(), s, True)
    assert a.metrics["xac_suat_hieu_chuan_pct"] == 80 and "hiệu chuẩn" in a.detail
    b = _with_prob(mk(), s, False)                                    # ước lượng (không thật) → không gắn
    assert "xac_suat_hieu_chuan_pct" not in (b.metrics or {}) and b.detail == "d."
    alert_prob._table.cache_clear()


def test_hai_dau_khong_noi_0_hay_100():
    reqlang.set_lang("vi")
    base = {"lo": 0.0, "hi": 19.0, "hit_threshold": 40.0, "n_test": 1998}
    assert "dưới 1%" in alert_prob.sentence({**base, "p_hit": 0.0}) and " 0% " not in alert_prob.sentence({**base, "p_hit": 0.0})
    assert "trên 99%" in alert_prob.sentence({**base, "p_hit": 1.0})
    assert "78%" in alert_prob.sentence({**base, "p_hit": 0.784})
