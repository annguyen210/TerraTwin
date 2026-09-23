"""A13 — hiệu chỉnh trực tuyến (isotonic regression) theo vùng×module.

VÌ SAO VIẾT SẴN NHƯNG ĐỂ TẮT. federated.py đã có một cơ chế hiệu chỉnh —
dịch NGƯỠNG BÁO ĐỘNG cộng/trừ một số điểm cố định, đủ tin cậy với CHỈ 3 quan
sát (MIN_OBS) vì phép tính thô, dễ giải thích, khó overfit. Ở đây làm việc
KHÁC và TINH hơn: hiệu chỉnh cả ĐƯỜNG CONG xác suất (model báo X điểm thì THỰC
TẾ xảy ra bao nhiêu % trong quá khứ, tại ĐÚNG vùng này) bằng isotonic
regression — không giả định tuyến tính, khớp sát dữ liệu hơn khi đủ, nhưng
cần NHIỀU quan sát hơn hẳn mới đáng tin (30, không phải 3) vì một đường cong
linh hoạt dễ overfit với ít điểm.

Hiện CHƯA vùng×module nào có đủ 30 quan sát (đo lúc viết module này — xem
GET /api/learn/loop hoặc bảng observations). Vì vậy còn thêm MỘT lớp tắt nữa
ngoài ngưỡng dữ liệu: cờ môi trường TERRATWIN_ONLINE_CALIBRATION. Lý do có cả
hai lớp — không chỉ dựa ngưỡng 30: nếu dữ liệu đột ngột đủ (vd một đợt gửi
quan sát hàng loạt), cơ chế này KHÔNG được tự bật sống trên production mà
chưa ai xem qua kết quả hiệu chỉnh trước; phải gạt cờ tay.

fallback_line (raw_index không đổi) là đường ĐƠN nhất quán ở MỌI nhánh tắt:
cờ tắt, thiếu dữ liệu, hay module lỗi — không bao giờ để một hiệu chỉnh hỏng
âm thầm đổi kết quả cảnh báo.
"""
from __future__ import annotations

import os

import numpy as np

MIN_OBS_CALIBRATION = 30
# Trần dịch chuyển (điểm, thang model_index 0-100) — cùng tinh thần MAX_SHIFT
# của federated.py: một đường cong hiệu chỉnh fit lệch (ít dữ liệu ngoại lai,
# hoặc vùng đang chuyển mùa) không được phép đảo ngược kết luận của model.
MAX_DISPLACEMENT = 20.0

ENABLED = os.environ.get("TERRATWIN_ONLINE_CALIBRATION", "0").strip() == "1"


def _pava(y_sorted_by_x: np.ndarray) -> np.ndarray:
    """Pool Adjacent Violators — isotonic regression thuần numpy (không
    sklearn/scipy). Đầu vào: y đã sắp theo x tăng dần. Trả y đơn điệu KHÔNG
    GIẢM, cùng độ dài, trung bình trọng số trong mỗi khối gộp."""
    blocks: list[list[float]] = []   # mỗi phần tử: [giá trị trung bình, trọng số, số điểm gốc]
    for yi in y_sorted_by_x:
        blocks.append([float(yi), 1.0, 1])
        while len(blocks) > 1 and blocks[-2][0] > blocks[-1][0]:
            v2, w2, c2 = blocks.pop()
            v1, w1, c1 = blocks.pop()
            new_w = w1 + w2
            blocks.append([(v1 * w1 + v2 * w2) / new_w, new_w, c1 + c2])

    out = np.empty(len(y_sorted_by_x))
    i = 0
    for v, _w, c in blocks:
        out[i:i + c] = v
        i += c
    return out


def fit_isotonic(model_index: np.ndarray, occurred: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Khớp đường cong model_index → xác suất xảy ra thật, đơn điệu không
    giảm. Trả (x_sorted, y_calibrated) để nội suy cho điểm mới bằng np.interp."""
    order = np.argsort(model_index, kind="stable")
    x_sorted = model_index[order]
    y_sorted = occurred[order].astype(float)
    return x_sorted, _pava(y_sorted)


def calibrate(observations: list, cell: str, module_id: str, raw_index: float) -> dict:
    """Hiệu chỉnh MỘT điểm model_index thô, dùng lịch sử quan sát của đúng
    vùng×module đó. `observations` là list đối tượng có .lat/.lon/.module_id/
    .model_index/.outcome (cùng interface federated._shift_from() dùng) —
    KHÔNG tự truy vấn DB, để test được bằng dữ liệu giả lập, người gọi tự lọc/
    truyền vào (xem services/radar.py hoặc onetap.py cho ví dụ truy vấn thật).
    """
    if not ENABLED:
        return {"calibrated_index": raw_index, "used_calibration": False,
                "reason": "off_by_flag",
                "message": "Hiệu chỉnh trực tuyến đang TẮT (TERRATWIN_ONLINE_CALIBRATION)."}

    from app.services import federated
    relevant = [o for o in observations
               if federated.cell_of(o.lat, o.lon) == cell
               and o.module_id == module_id and o.model_index is not None]

    if len(relevant) < MIN_OBS_CALIBRATION:
        return {"calibrated_index": raw_index, "used_calibration": False,
                "reason": "not_enough_observations",
                "observations": len(relevant), "min_needed": MIN_OBS_CALIBRATION,
                "message": (f"Vùng×module này mới có {len(relevant)} quan sát, "
                           f"cần {MIN_OBS_CALIBRATION} mới đủ tin để hiệu chỉnh.")}

    x = np.array([o.model_index for o in relevant], dtype=float)
    y = np.array([1.0 if o.outcome == "occurred" else 0.0 for o in relevant])
    x_sorted, y_iso = fit_isotonic(x, y)

    calibrated_prob = float(np.interp(raw_index, x_sorted, y_iso))
    calibrated_index = calibrated_prob * 100.0
    displacement = calibrated_index - raw_index
    capped = max(-MAX_DISPLACEMENT, min(MAX_DISPLACEMENT, displacement))

    return {
        "calibrated_index": round(raw_index + capped, 2),
        "used_calibration": True,
        "raw_index": raw_index,
        "displacement": round(capped, 2),
        "displacement_uncapped": round(displacement, 2),
        "observations": len(relevant),
        "message": f"Đã hiệu chỉnh dựa trên {len(relevant)} quan sát cùng vùng×module.",
    }
