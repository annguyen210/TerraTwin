"""Suy luận lớp phủ bằng mô hình học sâu — chạy trên máy chủ, KHÔNG cần torch.

Đọc data/landcover.onnx qua onnxruntime. Thiếu tệp hoặc thiếu thư viện thì trả
None — cùng kỷ luật với lớp vệ tinh và lớp học máy: thiếu thì nói thiếu.

VÌ SAO LỚP NÀY TỒN TẠI, nói cho gọn: chỉ số phổ xét TỪNG ĐIỂM ẢNH một, nên NDBI
lẫn lộn mái tôn với đất khô — hai thứ phản xạ gần giống nhau. Mạng tích chập
nhìn cả vùng lân cận nên thấy được hình chữ nhật, đường thẳng, kết cấu đều đặn
của mái nhà. Đó là năng lực mà công thức không có, không phải nhãn dán.

TRẠNG THÁI THẬT: đường ống huấn luyện ĐÃ ĐƯỢC CHẠY THẬT ĐẦU-CUỐI trên máy có
torch — fetch --smoke lấy ảnh Sentinel-2 qua Planetary Computer, train --smoke
dựng UNet 1,9 triệu tham số đúng kích thước, export ra một tệp ONNX 7,7 MB, và
onnxruntime chạy suy luận (n,4,256,256 → n,11,256,256). Nhưng mô hình THẬT thì
chưa huấn luyện: việc đó cần 4–8 giờ trên GPU.

Cho tới khi có tệp .onnx, mọi hàm ở đây trả None và các mô-đun tiếp tục dùng chỉ
số phổ như cũ. Không có bản giả lập nào để "trông cho có".

HAI CÁI BẪY ĐẮT TIỀN đã được chặn ở đây, cả hai đều làm mất công huấn luyện:
  · Thiếu onnxruntime trên máy chủ → lớp này im lặng trả None, nhìn từ ngoài y
    hệt "chưa huấn luyện". status() nay phân biệt rõ hai trường hợp đó.
  · torch ≥2.x mặc định tách trọng số ra tệp .onnx.data riêng, nên chép mỗi
    landcover.onnx lên máy chủ sẽ được một khung rỗng. export.py ép dynamo=False
    để gói tất cả vào một tệp.
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


RUNS_PATH = os.path.join(os.path.dirname(MODEL_PATH), "landcover_runs.json")


def training_runs() -> list:
    """Các lần huấn luyện THẬT đã chạy, kể cả lần KHÔNG ĐẠT — công khai để thấy
    ngưỡng được giữ thật, không chỉ nói. (data/landcover_runs.json)"""
    try:
        with open(RUNS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def status() -> dict:
    """Trạng thái để hiển thị — nói rõ đang thiếu gì và ai làm được việc đó."""
    runs = training_runs()
    if _load() is None:
        out = _status_missing()
        if runs:
            last = runs[-1]
            out.update({
                "message": (f"Đã huấn luyện thật ngày {last.get('date')}: mIoU trên tỉnh mô "
                            f"hình chưa từng thấy = {last.get('miou_test')} — dưới ngưỡng "
                            f"{MIN_MIOU} đặt trước, nên KHÔNG bật vào sản phẩm. "
                            + (last.get("diagnosis") or "")),
                "last_run": last, "runs": len(runs), "min_miou_required": MIN_MIOU,
            })
        return out
    return _status_ready()


def _status_missing() -> dict:
    thieu = []
    if not os.path.exists(MODEL_PATH):
        thieu.append("chưa có data/landcover.onnx")
    try:
        import onnxruntime  # noqa: F401
    except ImportError:
        thieu.append("chưa cài onnxruntime")
    # Nói rõ CÓ TỆP MÔ HÌNH nhưng THIẾU THƯ VIỆN — đây là cái bẫy đắt nhất:
    # người dùng huấn luyện 4-8 tiếng, chép tệp lên máy chủ, rồi lớp này im
    # lặng trả None vì onnxruntime chưa cài. Nhìn từ ngoài y hệt như "chưa
    # huấn luyện", nên rất dễ đi huấn luyện lại lần nữa.
    co_tep = os.path.exists(MODEL_PATH)
    return {
        "available": False,
        "missing": thieu,
        "model_file_present": co_tep,
        "message": (
            "ĐÃ CÓ tệp mô hình nhưng máy chủ thiếu onnxruntime — chạy "
            "`pip install onnxruntime` rồi khởi động lại. Không cần huấn "
            "luyện lại." if co_tep and "chưa cài onnxruntime" in thieu else
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


def _status_ready() -> dict:
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


def classify_window(patch, center_px: int = 12) -> dict | None:
    """Như classify(), nhưng chỉ ĐẾM ở ô giữa center_px × center_px (mặc định
    12 × 10 m = 120 m — cùng cỡ ô của services/landuse.py), trong khi mạng vẫn
    NHÌN cả ô 2,56 km. Ngữ cảnh xung quanh là thứ giúp mạng phân biệt mái tôn
    với đất khô; còn kết luận thì phải nói về đúng chỗ thửa đất.

    Trả {"groups_pct": {nhóm: %}, "classes_pct": {tên lớp: %}} hoặc None."""
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
    try:
        logits = sess.run(None, {sess.get_inputs()[0].name: x})[0]
    except Exception:
        return None
    pred = logits.argmax(axis=1)[0]
    h, w = pred.shape
    c0, c1 = (h - center_px) // 2, (w - center_px) // 2
    win = pred[c0:c0 + center_px, c1:c1 + center_px]

    from app.services.landuse import CLASSES
    codes = (_card or {}).get("codes") or [10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100]
    names = (_card or {}).get("classes") or []
    classes_pct, groups_pct = {}, {}
    for i, code in enumerate(codes):
        n = int((win == i).sum())
        if not n:
            continue
        pct = round(100.0 * n / win.size, 1)
        classes_pct[names[i] if i < len(names) else str(code)] = pct
        g = CLASSES.get(int(code), ("", "", "open"))[2]
        groups_pct[g] = round(groups_pct.get(g, 0.0) + pct, 1)
    return {"groups_pct": groups_pct, "classes_pct": classes_pct}
