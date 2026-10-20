"""U-Net radar làm ý kiến thứ hai (s1_unet_confirm_protocol.json): chưa đạt phép kiểm thì TẮT; khung thửa ở giữa đúng
20 × 20; dB + chuẩn hoá đúng như huấn luyện; điểm cuối /api/water/unet không bịa khi chưa bật."""
from __future__ import annotations

import json


def test_chua_dat_phep_kiem_thi_tat(monkeypatch, tmp_path):
    from app.services import s1_unet
    (tmp_path / "m.onnx").write_bytes(b"x")
    monkeypatch.setattr(s1_unet, "MODEL_PATH", str(tmp_path / "m.onnx"))
    monkeypatch.setattr(s1_unet, "RESULT_PATH", str(tmp_path / "kq.json"))
    assert s1_unet.available() is False                                     # chưa có kết quả
    (tmp_path / "kq.json").write_text(json.dumps({"passed": False}))
    assert s1_unet.available() is False                                     # có nhưng trượt
    (tmp_path / "kq.json").write_text(json.dumps({"passed": True}))
    assert s1_unet.gate_passed() is True


def test_khung_thua_o_giua_va_chuan_hoa():
    import numpy as np
    from app.services import s1_unet
    assert s1_unet.center_px() == 10                                        # bán kính 100 m → 20 × 20
    mask = np.zeros((128, 128), bool)
    mask[54:74, 54:74] = True                                               # đúng khung thửa
    assert s1_unet.plot_share(mask) == 1.0
    mask[:] = False
    mask[54:64, 54:74] = True                                               # nửa khung
    assert s1_unet.plot_share(mask) == 0.5
    m, s = s1_unet._load_norm()
    arr = np.full((2, 4, 4), 10 ** (m[0] / 10), np.float32)
    arr[1] = 10 ** (m[1] / 10)
    arr[0, 0, 0] = 0.0                                                      # ngoài dải quét → thay bằng trung bình
    x = s1_unet.prepare(arr)
    assert x.shape == (1, 2, 4, 4) and abs(float(x.max())) < 1e-3


def test_diem_cuoi_khi_chua_bat(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services import s1_unet
    monkeypatch.setattr(s1_unet, "available", lambda: False)
    with TestClient(app) as c:
        r = c.get("/api/water/unet", params={"lat": 16.575, "lon": 107.495, "date": "2020-10-10"})
        assert r.status_code == 200 and r.json()["available"] is False
        assert c.get("/api/water/unet", params={"lat": 1, "lon": 2, "date": "x"}).status_code == 422


def test_diem_cuoi_khi_bat(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services import s1_unet
    monkeypatch.setattr(s1_unet, "available", lambda: True)
    monkeypatch.setattr(s1_unet, "water_share", lambda la, lo, d, **k: {"date": d, "item": "S1X", "share": 0.42, "confirmed": True,
                                                                         "model": "m", "rule": "r"})
    with TestClient(app) as c:
        j = c.get("/api/water/unet", params={"lat": 16.575, "lon": 107.495, "date": "2020-10-10"}).json()
        assert j["available"] is True and j["share"] == 0.42 and j["confirmed"] is True
