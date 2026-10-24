"""U-Net radar bản 3 (s1_unet_v3_protocol.json): xác nhận theo MỨC VƯỢT nền mùa khô của chính thửa — hồ thường trực
không còn bị đếm là đợt ngập. Lượt 1 (22/10/2026) LỆCH giao thức; chấm lại đúng giao thức 23/10/2026: ĐẠT."""
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


def test_ket_qua_cham_lai_dung_giao_thuc():
    """Kết quả dùng để BẬT là lượt chấm lại 23/10/2026: đọc được mọi điểm (thiếu mùa lũ thì 'không đọc', không đoán)."""
    import os
    from app.services import s1_unet as U
    if not os.path.exists(U.V3_RESULT_PATH):
        return
    r = json.load(open(U.V3_RESULT_PATH, encoding="utf-8"))
    sm = r["U1"]["summary"]
    assert r["passed"] is True and r["protocol"] == "terratwin.s1_unet_vn/3"
    assert sm["pos"]["rate"] >= 0.60 and sm["neg"]["rate"] <= 0.10 and sm["pos"]["read"] / sm["pos"]["n"] >= 0.80
    assert all(len(p["baseline_scenes"]) == U.V3_K for p in r["U1"]["points"] if p["read"])
    log = json.load(open(os.path.join(os.path.dirname(U.V3_RESULT_PATH), "s1_unet_v3_protocol.json"), encoding="utf-8"))["run_log"]
    assert any("đúng giao thức" in e["what"] for e in log)


def test_chay_nen_tra_pending_roi_ket_qua(monkeypatch):
    """Máy chủ 0,1 CPU: không giữ yêu cầu chờ hàng chục giây — chạy nền, không chạy trùng, rồi trả từ bộ nhớ."""
    import time
    from app.services import cache_store, s1_unet as U
    out = {"date": "2021-10-15", "share": 0.9, "baseline": 0.0, "excess": 0.9, "confirmed": True}
    calls = []

    def fake(la, lo, d, r=100.0):
        calls.append(d)
        time.sleep(0.2)
        cache_store.put(U._v3_key(la, lo, d), out, 60)
        return out
    monkeypatch.setattr(U, "water_share", fake)
    lat, lon, d = 16.1111, 107.2222, "2021-10-15"
    assert U.water_share_bg(lat, lon, d) == "pending"
    assert U.water_share_bg(lat, lon, d) == "pending"          # đang chạy → không chạy trùng
    for _ in range(100):
        if U.water_share_bg(lat, lon, d) != "pending":
            break
        time.sleep(0.05)
    assert U.water_share_bg(lat, lon, d)["confirmed"] is True and calls == [d]


def test_doc_hong_thi_bao_khong_doc_duoc_va_khong_chay_lai_ngay(monkeypatch):
    import time
    from app.services import s1_unet as U
    calls = []
    monkeypatch.setattr(U, "water_share", lambda la, lo, d, r=100.0: calls.append(d))
    lat, lon, d = 16.3333, 107.4444, "2021-10-16"
    assert U.water_share_bg(lat, lon, d) == "pending"
    for _ in range(100):
        if U.water_share_bg(lat, lon, d) != "pending":
            break
        time.sleep(0.05)
    assert U.water_share_bg(lat, lon, d) is None and calls == [d]


def test_diem_cuoi_ban_3_tra_pending(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services import s1_unet as U
    monkeypatch.setattr(U, "v3_available", lambda: True)
    monkeypatch.setattr(U, "water_share_bg", lambda la, lo, d: "pending")
    with TestClient(app) as c:
        j = c.get("/api/water/unet", params={"lat": 16.575, "lon": 107.495, "date": "2020-10-10"}).json()
    assert j == {"available": True, "pending": True, "retry_after_s": 10}
