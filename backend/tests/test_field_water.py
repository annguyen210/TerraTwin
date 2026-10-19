"""Nước trong ảnh thực địa (SegFormer, đã qua cổng): thiếu mô hình → None (không bịa); có mô hình → tỉ lệ đúng từ logits;
chỉ là tham khảo — không đổi kết luận kiểm ảnh, không vào public() (thứ đóng băng vào hồ sơ ký)."""
from __future__ import annotations

import io


def _jpeg() -> bytes:
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (64, 48), (90, 120, 160)).save(b, "JPEG")
    return b.getvalue()


def test_thieu_mo_hinh_thi_none(monkeypatch, tmp_path):
    from app.services import field_water
    monkeypatch.setattr(field_water, "MODEL_PATH", str(tmp_path / "khong_co.onnx"))
    from PIL import Image
    assert field_water.available() is False and field_water.water_ratio(Image.new("RGB", (8, 8))) is None


def test_ti_le_tu_logits(monkeypatch, tmp_path):
    import numpy as np
    from PIL import Image
    from app.services import field_water
    p = tmp_path / "m.onnx"; p.write_bytes(b"x")
    monkeypatch.setattr(field_water, "MODEL_PATH", str(p))
    monkeypatch.setattr(field_water, "available", lambda: True)

    class Fake:
        def run(self, _out, feeds):
            x = feeds["image"]
            assert x.shape == (1, 3, 512, 512) and x.dtype == np.float32
            lg = np.zeros((1, 2, 128, 128), dtype=np.float32)
            lg[0, 1, :32, :] = 5.0                       # 1/4 ảnh là nước
            return [lg]
    monkeypatch.setattr(field_water, "_session", lambda: Fake())
    assert field_water.water_ratio(Image.new("RGB", (300, 200))) == 0.25


def test_khong_doi_ket_luan_va_khong_vao_ho_so(monkeypatch):
    from app.db import SessionLocal, init_db
    from app.services import evidence, field_water
    init_db()
    monkeypatch.setattr(field_water, "water_ratio", lambda img: 0.4)
    db = SessionLocal()
    try:
        r = evidence.analyze(db, _jpeg(), 16.46, 107.59)
        assert r["water_ratio"] == 0.4 and r["verdict"] in ("review", "mismatch", "match")
        monkeypatch.setattr(field_water, "water_ratio", lambda img: None)
        assert evidence.analyze(db, _jpeg(), 16.46, 107.59)["verdict"] == r["verdict"]   # không đổi kết luận
        row = evidence.store(db, r, 16.46, 107.59)
        assert row.water_ratio == 0.4 and "water_ratio" not in evidence.public(row)
    finally:
        db.close()


def test_co_tep_mo_hinh_nhung_truot_doi_chung_thi_khong_chay(monkeypatch, tmp_path):
    """19/10/2026: đối chứng ảnh đồng ruộng khô trượt → chép tệp .onnx vào máy chủ cũng KHÔNG bật được."""
    import json
    from app.services import field_water
    (tmp_path / "m.onnx").write_bytes(b"x")
    monkeypatch.setattr(field_water, "MODEL_PATH", str(tmp_path / "m.onnx"))
    (tmp_path / "field_water_negctrl_result.json").write_text(json.dumps({"passed": True}))
    (tmp_path / "field_water_negctrl_1b_result.json").write_text(json.dumps({"passed": False}))
    assert field_water.controls_passed() is False and field_water.available() is False
    (tmp_path / "field_water_negctrl_1b_result.json").write_text(json.dumps({"passed": True}))
    assert field_water.controls_passed() is True


def test_ban_2_quyet_dinh_khi_co_ket_qua(monkeypatch, tmp_path):
    """Có field_water_v2_result.json thì chỉ bản 2 quyết định — phải đạt CẢ ảnh lũ lẫn đối chứng khô."""
    import json
    from app.services import field_water
    (tmp_path / "m.onnx").write_bytes(b"x")
    monkeypatch.setattr(field_water, "MODEL_PATH", str(tmp_path / "m.onnx"))
    (tmp_path / "field_water_negctrl_result.json").write_text(json.dumps({"passed": True}))
    (tmp_path / "field_water_negctrl_1b_result.json").write_text(json.dumps({"passed": False}))
    v2 = tmp_path / "field_water_v2_result.json"
    v2.write_text(json.dumps({"passed": False, "passed_flood": True, "passed_dry": False}))
    assert field_water.controls_passed() is False
    v2.write_text(json.dumps({"passed": True, "passed_flood": True, "passed_dry": True}))
    assert field_water.controls_passed() is True
