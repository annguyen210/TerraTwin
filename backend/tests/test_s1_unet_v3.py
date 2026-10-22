"""U-Net radar bản 3 (s1_unet_v3_protocol.json): xác nhận theo MỨC VƯỢT nền mùa khô của chính thửa — hồ thường trực
không còn bị đếm là đợt ngập. Kết quả thật 22/10/2026: ĐẠT."""
from __future__ import annotations

import json


def _hist():
    days = [f"2021-{m:02d}-{d:02d}" for m in range(1, 13) for d in (3, 15, 27)]
    return {"available": True, "flood_season": {"months": [9, 10, 11]}, "series": [[d, -10.0, -12.0] for d in days]}


def test_ho_thuong_truc_khong_bi_xac_nhan(monkeypatch):
    from app.services import s1_unet as U
    monkeypatch.setattr(U, "share_on_day", lambda la, lo, d: (0.25, "S1X"))   # khung luôn có ~25% là hồ
    r = U.v3_judge(16.43, 107.56, "2021-10-15", _hist())
    assert r["baseline"] == 0.25 and r["excess"] == 0.0 and r["confirmed"] is False


def test_dot_ngap_vuot_nen_thi_xac_nhan(monkeypatch):
    from app.services import s1_unet as U
    monkeypatch.setattr(U, "share_on_day", lambda la, lo, d: ((1.0 if d == "2021-10-15" else 0.0), "S1X"))
    r = U.v3_judge(16.57, 107.49, "2021-10-15", _hist())
    assert r["confirmed"] is True and r["excess"] == 1.0 and "vượt nền" in r["rule"]


def test_nen_chi_lay_mua_kho_va_cach_xa_ngay_dot(monkeypatch):
    from app.services import s1_unet as U
    seen = []
    monkeypatch.setattr(U, "share_on_day", lambda la, lo, d: (seen.append(d), (0.0, "S1X"))[1])
    U.v3_judge(16.57, 107.49, "2021-08-15", _hist())
    base = seen[1:]
    assert len(base) == U.V3_K
    assert all(int(d[5:7]) not in (9, 10, 11) for d in base)                    # ngoài mùa lũ
    assert all(not d.startswith("2021-08") and not d.startswith("2021-07-27") for d in base)  # cách > 30 ngày


def test_luot_1_ghi_ro_lech_giao_thuc():
    import os
    from app.services import s1_unet as U
    r = json.load(open(os.path.join(os.path.dirname(U.V3_RESULT_PATH), "s1_unet_v3_result_run1.json"), encoding="utf-8"))
    assert r["superseded"] is True and "passed" not in r and "Open-Meteo" in r["protocol_deviation"]["what"]


def test_thieu_mua_lu_thi_khong_doan(monkeypatch):
    """Lượt 1 bị Open-Meteo chặn đã lấy nền cả mùa lũ — nay thiếu mùa lũ thì không trả ý kiến."""
    from app.services import flood_season as fs, s1_unet as U
    monkeypatch.setattr(fs, "season", lambda la, lo: None)
    monkeypatch.setattr(U, "share_on_day", lambda la, lo, d: (0.5, "S1X"))
    h = _hist()
    h["flood_season"] = None
    assert U.v3_judge(16.57, 107.49, "2021-10-15", h) is None


def test_chua_co_ket_qua_chay_lai_thi_tat():
    """Lượt 1 lệch giao thức (s1_unet_v3_result_run1.json) KHÔNG được bật bản 3."""
    import os
    from app.services import s1_unet as U
    if not os.path.exists(U.V3_RESULT_PATH):
        assert U.v3_gate_passed() is False and U.v3_available() is False
