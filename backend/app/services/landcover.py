"""Suy luận lớp phủ bằng mô hình học sâu — chạy trên máy chủ, KHÔNG cần torch.

Đọc data/landcover.onnx qua onnxruntime. Thiếu tệp hoặc thiếu thư viện thì trả
None — cùng kỷ luật với lớp vệ tinh và lớp học máy: thiếu thì nói thiếu.

VÌ SAO LỚP NÀY TỒN TẠI, nói cho gọn: chỉ số phổ xét TỪNG ĐIỂM ẢNH một, nên NDBI
lẫn lộn mái tôn với đất khô — hai thứ phản xạ gần giống nhau. Mạng tích chập
nhìn cả vùng lân cận nên thấy được hình chữ nhật, đường thẳng, kết cấu đều đặn
của mái nhà. Đó là năng lực mà công thức không có, không phải nhãn dán.

TRẠNG THÁI THẬT: mã đã viết xong và có test, nhưng mô hình CHƯA ĐƯỢC HUẤN LUYỆN
— máy phát triển không có GPU và không cài được torch. Cho tới khi có tệp
.onnx, mọi hàm ở đây trả None và các mô-đun tiếp tục dùng chỉ số phổ như cũ.
Không có bản giả lập nào để "trông cho có".
"""
from __future__ import annotations

import json
import os

MODEL_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "data", "landcover.onnx")
CARD_PATH = MODEL_PATH.replace(".onnx", ".json")

# Ngưỡng chấp nhận, chốt TRƯỚC khi có kết quả huấn luyện. Mô hình dưới mức này
# không được đưa vào phục vụ, kể cả khi nó là thứ mới nhất và tốn công nhất.
MIN_MIOU = 0.35

_sess = None
_card: dict | None = None
_tried = False


def _load():
    global _sess, _card, _tried
    if _tried:
        return _sess
    _tried = True
    if not (os.path.exists(MODEL_PATH) and os.path.exists(CARD_PATH)):
        return None
    try:
        import onnxruntime as ort
    except ImportError:
        return None
    try:
        with open(CARD_PATH, encoding="utf-8") as f:
            card = json.load(f)
    except (OSError, ValueError):
        return None
    if float(card.get("miou_holdout") or 0.0) < MIN_MIOU:
        # Có mô hình nhưng nó chưa đủ tốt. Không bật — một lớp phủ đoán sai
        # dẫn thẳng tới cảnh báo "xây dựng trái phép" sai, và đó là loại sai
        # gây hậu quả cho người thật.
        return None
    try:
        _sess = ort.InferenceSession(MODEL_PATH, providers=["CPUExecutionProvider"])
        _card = card
    except Exception:
        _sess = None
    return _sess


def available() -> bool:
    return _load() is not None


def status() -> dict:
    """Trạng thái để hiển thị — nói rõ đang thiếu gì và ai làm được việc đó."""
    if _load() is None:
        thieu = []
        if not os.path.exists(MODEL_PATH):
            thieu.append("chưa có data/landcover.onnx")
        try:
            import onnxruntime  # noqa: F401
        except ImportError:
            thieu.append("chưa cài onnxruntime")
        return {
            "available": False,
            "missing": thieu,
            "message": (
                "Mô hình học sâu chưa sẵn sàng. Mã huấn luyện đã có sẵn trong "
                "app/dl/ và chạy được trên máy có GPU: fetch → train → export. "
                "Trong lúc chờ, các mô-đun vẫn dùng chỉ số phổ cổ điển — kém "
                "hơn ở chỗ không thấy được ngữ cảnh không gian, nhưng đúng và "
                "kiểm chứng được."),
            "how_to": ["python -m app.dl.fetch --smoke",
                       "python -m app.dl.fetch",
                       "python -m app.dl.train --smoke",
                       "python -m app.dl.train",
                       "python -m app.dl.export"],
        }
    c = _card or {}
    return {
        "available": True,
        "task": c.get("task"),
        "classes": c.get("classes"),
        "miou_holdout": c.get("miou_holdout"),
        "iou_per_class": c.get("iou_per_class"),
        "holdout_provinces": c.get("holdout_provinces"),
        "labels": c.get("labels"),
        "note": c.get("note"),
        "min_miou_required": MIN_MIOU,
    }


def classify(patch) -> dict | None:
    """Phân loại một ô ảnh 4×H×W (phản xạ 0–1) → tỉ lệ từng lớp phủ.

    `patch` là mảng dạng numpy. Trả None nếu mô hình chưa sẵn sàng — người gọi
    PHẢI xử lý None chứ không được coi nó là "không có lớp phủ nào".
    """
    sess = _load()
    if sess is None:
        return None
    try:
        import numpy as np
    except ImportError:
        return None

    x = np.asarray(patch, dtype=np.float32)
    if x.ndim == 3:
        x = x[None, ...]
    if x.ndim != 4:
        return None
    try:
        logits = sess.run(None, {sess.get_inputs()[0].name: x})[0]
    except Exception:
        return None

    pred = logits.argmax(axis=1)
    names = (_card or {}).get("classes") or []
    total = pred.size
    out = {}
    for i, ten in enumerate(names):
        n = int((pred == i).sum())
        if n:
            out[ten] = round(100.0 * n / total, 2)
    return {
        "fractions_pct": dict(sorted(out.items(), key=lambda kv: -kv[1])),
        "dominant": max(out, key=out.get) if out else None,
        "miou_holdout": (_card or {}).get("miou_holdout"),
        "caveat": (
            "Tỉ lệ theo diện tích trong ô, do mạng phân đoạn dự đoán. Độ tin "
            "cậy khác nhau theo lớp — xem iou_per_class trong /api/landcover; "
            "lớp hiếm như bề mặt xây dựng thường kém chính xác hơn lớp phổ biến."),
    }
