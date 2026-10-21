"""U-Net radar bản 2 (s1_unet_vn_protocol.json): khung bám lưới gốc cảnh S1, mặt nạ dốc > 5°, chỉ bật khi phép kiểm
đạt — kết quả thật 21/10/2026 là TRƯỢT nên thẻ phải ghi trượt và không bật."""
from __future__ import annotations

import json

import numpy as np


def test_khung_bam_luoi_canh_s1():
    from app.services import s1_unet as U
    it = {"properties": {"proj:epsg": 32648, "proj:transform": [10.0, 0.0, 387610.0, 0.0, -10.0, 1339730.0]}}
    epsg, b = U.s1_grid_box(it, 10.40, 105.35)
    assert epsg == 32648 and b[2] - b[0] == 1280 and b[3] - b[1] == 1280
    assert (b[0] - 387610) % 10 == 0 and (1339730 - b[3]) % 10 == 0


def test_mat_na_doc():
    from app.services import s1_unet as U
    logit, slope = np.ones((4, 4)), np.zeros((4, 4))
    slope[0] = 12.0                                         # sườn dốc: nước không đọng
    m = U.predict_mask(logit, slope)
    assert not m[0].any() and m[1:].all()
    assert U.predict_mask(-np.ones((2, 2)), None).sum() == 0


def test_chi_bat_khi_dat(monkeypatch, tmp_path):
    from app.services import s1_unet as U
    (tmp_path / "m.onnx").write_bytes(b"x")
    monkeypatch.setattr(U, "V2_MODEL_PATH", str(tmp_path / "m.onnx"))
    monkeypatch.setattr(U, "V2_RESULT_PATH", str(tmp_path / "kq.json"))
    assert U.v2_available() is False
    (tmp_path / "kq.json").write_text(json.dumps({"passed": False}))
    assert U.v2_available() is False
    (tmp_path / "kq.json").write_text(json.dumps({"passed": True}))
    assert U.v2_gate_passed() is True


def test_the_mo_hinh_ghi_dung_ket_qua_that():
    from app.services import model_cards as mc, s1_unet as U
    r = json.load(open(U.V2_RESULT_PATH, encoding="utf-8"))
    assert r["passed"] is False and U.v2_available() is False             # trượt thật → không bật
    c = next(x for x in mc.cards() if x["id"] == "s1_water_unet_vn")
    assert c["status"] == "rejected" and "TRƯỢT" in c["status_label"]
    assert "0.4329" in c["metrics"][0]["value"] and c["metrics"][0]["passed"] is False
