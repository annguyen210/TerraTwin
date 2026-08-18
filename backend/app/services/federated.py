"""S05 — Federated Twin Learning: học từ quan sát thực địa của người dùng.

VÌ SAO ĐÂY LÀ MOAT: mô hình chạy trên Open-Meteo và ERA5 — dữ liệu mở, ai cũng
tải được. Thứ không ai copy được là "hôm 12/10 ruộng tôi ngập thật, nước tới
đầu gối". Càng nhiều nông dân gửi quan sát, ngưỡng càng khớp với thực địa Việt
Nam, và khoảng cách đó không mua được bằng tiền hay tính được bằng GPU.

"FEDERATED" Ở ĐÂY CÓ NGHĨA CỤ THỂ, KHÔNG PHẢI NHÃN DÁN:
  - Quan sát THÔ (toạ độ chính xác, ghi chú, ai gửi) không bao giờ rời khỏi tài
    khoản người gửi. Không endpoint nào trả về chúng cho người khác.
  - Thứ được chia sẻ giữa mọi người chỉ là MỘT con số cho mỗi vùng×module:
    độ dịch ngưỡng, kèm số quan sát đã góp vào.
  - Vùng gộp ở lưới 0,5° và chỉ công bố khi đủ số quan sát tối thiểu, nên không
    truy ngược được về một thửa hay một người cụ thể.

CÁCH HIỆU CHỈNH: nếu ở một vùng model thường xuyên BÁO mà thực tế KHÔNG xảy ra
(báo động giả), nâng ngưỡng lên. Ngược lại, nếu sự việc xảy ra mà model IM
LẶNG (bỏ sót), hạ ngưỡng xuống. Dịch chuyển bị chặn trong ±15 điểm để một
nhóm nhỏ quan sát sai không thể phá mô hình.
"""
from __future__ import annotations

import math
from collections import defaultdict

GRID = 0.5              # độ — vùng gộp ~55 km
MIN_OBS = 3             # dưới ngưỡng này không công bố, tránh truy ngược cá nhân
MAX_SHIFT = 15.0        # trần dịch ngưỡng (điểm), chống nhiễm độc dữ liệu
_STEP = 4.0             # mỗi quan sát lệch góp tối đa bằng này


def cell_of(lat: float, lon: float) -> str:
    """Mã vùng gộp. Làm tròn xuống lưới 0,5° nên không lộ toạ độ chính xác."""
    return f"{math.floor(lat / GRID) * GRID:.1f},{math.floor(lon / GRID) * GRID:.1f}"


def _shift_from(observations: list) -> tuple[float, dict]:
    """Tính độ dịch ngưỡng từ một nhóm quan sát cùng vùng, cùng module.

    Quy ước `outcome`:
      occurred — sự việc CÓ xảy ra thật
      none     — KHÔNG xảy ra
    Kết hợp với `model_index` (chỉ số model tính cho đúng ngày đó) để biết
    model đã đúng hay sai:
      model báo (≥40) mà none      → báo động giả  → cần NÂNG ngưỡng
      model im (<40) mà occurred   → bỏ sót        → cần HẠ ngưỡng
    """
    false_alarm = missed = hit = correct_quiet = 0
    for o in observations:
        idx = o.model_index
        if idx is None:
            continue
        warned = idx >= 40.0
        if o.outcome == "occurred":
            hit += warned
            missed += not warned
        elif o.outcome == "none":
            false_alarm += warned
            correct_quiet += not warned

    total = hit + missed + false_alarm + correct_quiet
    if total < MIN_OBS:
        return 0.0, {"total": total, "enough": False}

    # Báo động giả đẩy ngưỡng lên, bỏ sót kéo ngưỡng xuống.
    shift = (false_alarm - missed) * _STEP
    shift = max(-MAX_SHIFT, min(MAX_SHIFT, shift))
    return round(shift, 1), {
        "total": total, "enough": True,
        "hit": hit, "missed": missed,
        "false_alarm": false_alarm, "correct_quiet": correct_quiet,
    }


def aggregate(observations: list) -> dict:
    """Gộp mọi quan sát thành bảng hiệu chỉnh theo vùng×module.

    Nhận list Observation (ORM hoặc bất cứ object nào có lat/lon/module_id/
    outcome/model_index). KHÔNG trả về bất kỳ trường nhận dạng cá nhân nào.
    """
    groups: dict[tuple[str, str], list] = defaultdict(list)
    for o in observations:
        groups[(cell_of(o.lat, o.lon), o.module_id)].append(o)

    adjustments, contributors = [], set()
    for (cell, module_id), obs in sorted(groups.items()):
        shift, stats = _shift_from(obs)
        contributors.update(getattr(o, "user_id", None) for o in obs)
        if not stats["enough"]:
            continue
        adjustments.append({
            "cell": cell, "module_id": module_id,
            "threshold_shift": shift,
            "observations": stats["total"],
            "hit": stats["hit"], "missed": stats["missed"],
            "false_alarm": stats["false_alarm"],
            "correct_quiet": stats["correct_quiet"],
            "direction": ("nâng ngưỡng — vùng này hay báo động giả" if shift > 0
                          else "hạ ngưỡng — vùng này hay bị bỏ sót" if shift < 0
                          else "giữ nguyên — model đang khớp thực địa"),
        })

    pending = sum(1 for g in groups.values() if len(g) < MIN_OBS)
    return {
        "grid_deg": GRID, "min_observations": MIN_OBS, "max_shift": MAX_SHIFT,
        "total_observations": len(observations),
        "contributors": len([c for c in contributors if c is not None]),
        "cells_published": len(adjustments),
        "cells_pending": pending,
        "adjustments": adjustments,
        "privacy": (
            "Quan sát thô không bao giờ rời khỏi tài khoản người gửi. Bảng này "
            f"chỉ chứa một con số cho mỗi vùng ~{GRID}° và chỉ công bố khi đã có "
            f"ít nhất {MIN_OBS} quan sát, nên không truy ngược được về một thửa "
            "hay một người cụ thể."),
        "method": (
            "Model báo mà thực tế không xảy ra → nâng ngưỡng. Sự việc xảy ra mà "
            f"model im lặng → hạ ngưỡng. Mỗi quan sát lệch góp {_STEP} điểm, "
            f"tổng dịch chuyển chặn trong ±{MAX_SHIFT} điểm để một nhóm nhỏ quan "
            "sát sai không phá được mô hình."),
    }


def shift_for(adjustments: list[dict], lat: float, lon: float,
              module_id: str) -> float:
    """Độ dịch ngưỡng áp cho một vị trí cụ thể. 0.0 nếu vùng chưa đủ dữ liệu."""
    cell = cell_of(lat, lon)
    for a in adjustments:
        if a["cell"] == cell and a["module_id"] == module_id:
            return a["threshold_shift"]
    return 0.0
