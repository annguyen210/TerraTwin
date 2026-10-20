"""S10 ① — làm sắc B11 20 m → 10 m (s2_sharpen_protocol.json): toạ độ UTM, toán tử ×2, chiếu ngược giữ đúng ảnh đo,
hồi quy phục hồi được chi tiết khi quan hệ giữa các băng là thật; điểm cuối không bịa khi chưa bật."""
from __future__ import annotations

import json

import numpy as np


def test_utm_moc_chuan():
    from app.services import s2_sharpen as S
    e, n = S.to_utm(0.0, 105.0, 32648)                       # kinh tuyến trục múi 48
    assert abs(e - 500000.0) < 1e-6 and abs(n) < 1e-6
    e, n = S.to_utm(0.0, 108.0, 32648)                       # mép múi ở xích đạo: 833 978,556 m (giá trị chuẩn)
    assert abs(e - 833978.556) < 0.01 and abs(n) < 1e-6
    e1, _ = S.to_utm(16.0, 104.0, 32648)
    e2, _ = S.to_utm(16.0, 106.0, 32648)
    assert abs((e1 - 500000) + (e2 - 500000)) < 1e-6         # đối xứng qua kinh tuyến trục


def test_khung_bam_dung_luoi_20m():
    from app.services import s2_sharpen as S
    it = {"properties": {"proj:epsg": 32648}, "assets": {"B11": {"proj:transform": [20, 0, 499980, 0, -20, 1200000]}}}
    epsg, b = S.grid_box(it, 10.45, 105.25, 32)
    assert epsg == 32648 and b[2] - b[0] == 640 and b[3] - b[1] == 640
    assert (b[0] - 499980) % 20 == 0 and (1200000 - b[3]) % 20 == 0
    e, n = S.to_utm(10.45, 105.25, 32648)
    assert b[0] <= e <= b[2] and b[1] <= n <= b[3]


def test_toan_tu_va_chieu_nguoc():
    from app.services import s2_sharpen as S
    assert np.allclose(S.up(np.full((8, 8), 0.3)), 0.3)
    c = np.random.default_rng(1).random((16, 16))
    p = S.back_project(S.up(c), c)
    assert p.shape == (32, 32) and np.abs(S.down(p) - c).max() < 1e-4   # thu nhỏ lại RA ĐÚNG ảnh đo


def test_hoi_quy_phuc_hoi_chi_tiet_that():
    """B11 thật là tổ hợp tuyến tính của băng 10 m → rg gần như phục hồi đúng, bậc ba thì mờ."""
    from app.services import s2_sharpen as S
    rng = np.random.default_rng(7)
    fine = np.clip(0.1 + 0.05 * rng.standard_normal((4, 64, 64)).cumsum(1).cumsum(2) / 20, 0.01, 0.6)
    t = 0.02 + 0.3 * fine[3] + 0.4 * fine[2]                 # "B11 thật" ở thang mịn
    c = S.down(t)
    e_bc = np.sqrt(np.mean((S.bicubic(fine, c) - t) ** 2))
    e_rg = np.sqrt(np.mean((S.sharpen_rg(fine, c) - t) ** 2))
    assert e_rg < 0.2 * e_bc
    assert np.abs(S.down(S.sharpen_rg(fine, c)) - c).max() < 1e-4


def test_chua_dat_thi_tat(monkeypatch, tmp_path):
    from app.services import s2_sharpen as S
    monkeypatch.setattr(S, "RESULT_PATH", str(tmp_path / "kq.json"))
    assert S.available() is False
    (tmp_path / "kq.json").write_text(json.dumps({"passed": False}))
    assert S.available() is False
    (tmp_path / "kq.json").write_text(json.dumps({"passed": True, "selected": "ml", "ml_weights": [0.1] * 8}))
    assert S.available() is True and S.method()[0] == "ml" and len(S.method()[1]) == 8


def test_diem_cuoi(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services import s2_sharpen as S
    with TestClient(app) as c:
        monkeypatch.setattr(S, "available", lambda: False)
        j = c.get("/api/optical/ndmi10", params={"lat": 10.45, "lon": 105.25}).json()
        assert j["available"] is False
        assert c.get("/api/optical/ndmi10", params={"lat": 1, "lon": 2}).status_code == 422
        monkeypatch.setattr(S, "available", lambda: True)
        monkeypatch.setattr(S, "ndmi_map", lambda la, lo: {"available": True, "found": True, "center_ndmi_10m": 0.31})
        j = c.get("/api/optical/ndmi10", params={"lat": 10.45, "lon": 105.25}).json()
        assert j["found"] is True and j["center_ndmi_10m"] == 0.31


def test_lo_trinh_s10_doc_ket_qua_khong_ghi_cung(monkeypatch):
    """S10 'done' CHỈ khi phép kiểm đạt; tắt đi thì bảng tự quay về 'partial' và 25/26."""
    from app.services import roadmap, s2_sharpen as S
    monkeypatch.setattr(S, "available", lambda: False)
    d = roadmap.status()
    s10 = next(f for f in d["flows"] if f["id"] == "S10")
    assert s10["status"] == "partial" and "25/26" in d["honesty_note"]
    monkeypatch.setattr(S, "available", lambda: True)
    monkeypatch.setattr(S, "_result", lambda: {"checks": {"g1_median_rel_gain": [0.36, True], "g3_median_ndmi_rel_gain": [0.35, True]},
                                               "n": {"train": 25, "test": 16}, "ml_train_pixels": 89886})
    d = roadmap.status()
    s10 = next(f for f in d["flows"] if f["id"] == "S10")
    assert s10["status"] == "done" and "36%" in s10["note"] and "TỪ CHỐI" in s10["note"]
    assert d["done"] == d["total"] == 26 and "26/26" in d["honesty_note"]
