"""Lớp học sâu: canh nó KHÔNG vượt quyền khi chưa có mô hình.

Đây là lớp duy nhất trong sản phẩm mà mã đã viết xong nhưng mô hình chưa tồn
tại. Đúng tình huống dễ sinh ra bản giả lập "cho có" nhất, nên nhóm test này
canh chặt hơn canh chức năng.
"""
from __future__ import annotations

import json
import os

from app.services import landcover


def test_chua_co_mo_hinh_thi_tra_none():
    if landcover.available():
        return
    assert landcover.classify([[[0.1] * 8] * 8] * 4) is None


def test_status_noi_ro_thieu_gi_va_cach_tu_lam():
    st = landcover.status()
    if st["available"]:
        return
    assert st["missing"], "phải liệt kê thứ đang thiếu"
    assert st["how_to"], "phải chỉ các lệnh tự chạy"
    assert any("app.dl.train" in c for c in st["how_to"])


def test_mo_hinh_kem_thi_khong_duoc_bat(tmp_path, monkeypatch):
    """Có mô hình nhưng điểm dưới ngưỡng thì phải TỪ CHỐI bật.

    Lớp phủ đoán sai dẫn thẳng tới cảnh báo "xây dựng trái phép" sai, và đó là
    loại sai gây hậu quả cho người thật. Ngưỡng chốt trước khi biết kết quả.
    """
    onnx = tmp_path / "m.onnx"
    onnx.write_bytes(b"khong-phai-onnx-that")
    card = tmp_path / "m.json"
    card.write_text(json.dumps({"miou_holdout": 0.05, "classes": ["a"]}),
                    encoding="utf-8")
    monkeypatch.setattr(landcover, "MODEL_PATH", str(onnx))
    monkeypatch.setattr(landcover, "CARD_PATH", str(card))
    monkeypatch.setattr(landcover, "_tried", False)
    monkeypatch.setattr(landcover, "_sess", None)
    assert landcover.available() is False


def test_nguong_chap_nhan_duoc_chot_bang_hang_so():
    assert 0.2 <= landcover.MIN_MIOU <= 0.6


def test_khong_co_nhanh_gia_lap():
    import ast
    src = open(landcover.__file__, encoding="utf-8").read()
    cay = ast.parse(src)
    for node in ast.walk(cay):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.Module)):
            d = ast.get_docstring(node)
            if d:
                src = src.replace(d, "")
    nl = chr(10)
    low = nl.join(l.split("#")[0] for l in src.split(nl)).lower()
    for tu in ("random", "fake", "mock", "dummy", "synthetic"):
        assert tu not in low, f"landcover.py chứa '{tu}'"


def test_duong_ong_huan_luyen_co_du_ba_buoc():
    d = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(landcover.__file__))), "dl")
    for f in ("fetch.py", "train.py", "export.py", "__init__.py"):
        assert os.path.exists(os.path.join(d, f)), f"thiếu app/dl/{f}"


def test_ma_huan_luyen_khong_ro_ri_tap_kiem_tra():
    """Chia tập phải theo TỈNH, không theo ô ngẫu nhiên.

    Hai ô cách nhau 2 km gần như giống hệt nhau; chia ngẫu nhiên thì mạng đã
    thấy vùng đó lúc học và điểm kiểm tra đẹp giả tạo.
    """
    p = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(landcover.__file__))), "dl", "train.py")
    src = open(p, encoding="utf-8").read()
    assert "holdout" in src
    assert "train_test_split" not in src, "không được chia ngẫu nhiên theo ô"


def test_chấm_bằng_iou_tung_lop_khong_phai_do_chinh_xac_tong():
    """Lớp 'tán cây' chiếm phần lớn Việt Nam — đoán bừa nó vẫn cho độ chính xác
    tổng rất cao mà vô dụng. Cùng cái bẫy POD-100% đã làm hỏng backtest đầu."""
    p = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(landcover.__file__))), "dl", "train.py")
    src = open(p, encoding="utf-8").read()
    assert "iou_per_class" in src
    assert "Bề mặt xây dựng" in src, "phải theo dõi riêng lớp hiếm nhưng quan trọng"
