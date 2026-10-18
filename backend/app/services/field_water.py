"""Tỉ lệ NƯỚC trong ảnh thực địa — SegFormer-b0 đã qua cổng đăng ký trước (IoU test 0,816 so với màu 0,4285,
backend/data/ml/field_water_result.json · REPRODUCE.md §12).

Đúng giao thức `field_water_protocol.json`: chỉ là tín hiệu THAM KHẢO trong nhật ký thửa / đối chiếu ba chiều —
KHÔNG vào nội dung ký của hồ sơ, KHÔNG đổi kết luận kiểm ảnh (GPS / thời điểm / ảnh dùng lại), KHÔNG thay câu trả lời
"có nước / không" của người dùng.

Đọc data/ml/field_water_segformer.onnx (+ .onnx.data: trọng số tách riêng, PHẢI chép cả hai) qua onnxruntime.
Thiếu tệp hoặc thiếu thư viện → available() False, mọi hàm trả None (không bịa số). TERRATWIN_FIELD_WATER=0 tắt hẳn.
"""
from __future__ import annotations

import os
import threading

MODEL_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                          "data", "ml", "field_water_segformer.onnx")
SIZE = 512
_MEAN = (0.485, 0.456, 0.406)
_STD = (0.229, 0.224, 0.225)
_lock = threading.Lock()
_sess = None


def available() -> bool:
    if os.environ.get("TERRATWIN_FIELD_WATER", "1") == "0" or not os.path.exists(MODEL_PATH):
        return False
    try:
        import onnxruntime  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


def _session():
    global _sess
    if _sess is None:
        import onnxruntime as ort
        o = ort.SessionOptions()
        o.intra_op_num_threads = 1          # máy chủ miễn phí 0,1 CPU / 512 MB: một luồng, một ảnh mỗi lúc
        o.inter_op_num_threads = 1
        _sess = ort.InferenceSession(MODEL_PATH, sess_options=o, providers=["CPUExecutionProvider"])
    return _sess


def _tensor(img):
    import numpy as np
    from PIL import Image
    x = np.asarray(img.convert("RGB").resize((SIZE, SIZE), Image.BILINEAR), dtype=np.float32) / 255.0
    x = (x - np.array(_MEAN, dtype=np.float32)) / np.array(_STD, dtype=np.float32)
    return x.transpose(2, 0, 1)[None].astype(np.float32)


def water_ratio(img) -> float | None:
    """Tỉ lệ điểm ảnh mô hình xếp là nước (0–1, 3 chữ số), hoặc None khi mô hình không có / lỗi."""
    if not available():
        return None
    try:
        import numpy as np
        with _lock:
            logits = _session().run(None, {"image": _tensor(img)})[0]     # (1, 2, 128, 128)
        return round(float((np.argmax(logits[0], axis=0) == 1).mean()), 3)
    except Exception:  # noqa: BLE001 — tín hiệu tham khảo: hỏng thì im lặng, không chặn việc nhận ảnh
        return None
