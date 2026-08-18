"""S09 — AI Data & Model Engine: đo mô hình bằng quan sát thực địa.

Huấn luyện model cần dataset gán nhãn và GPU. Nhưng LÕI của một "model engine"
không phải huấn luyện — mà là biết mô hình đang tốt hay tệ, ở đâu, và có đang
khá lên không. Không có phần đo, huấn luyện chỉ là tiêu tiền trong bóng tối.

Module này làm phần đó, trên dữ liệu đã có thật:
  - Kho quan sát thực địa (bảng observations) là dataset.
  - Chấm mô hình bằng bộ chỉ số khí tượng chuẩn: POD, FAR, CSI, bias.
  - Chỉ ra vùng nào mô hình đang lệch, và lệch theo hướng nào.

BỘ CHỈ SỐ (bảng dự phòng 2×2 — chuẩn dùng trong dự báo thời tiết):
                      thực tế XẢY RA   thực tế KHÔNG
  model BÁO              hit (a)        false alarm (b)
  model IM LẶNG          miss (c)       correct negative (d)

  POD = a/(a+c)      bắt được bao nhiêu phần sự việc thật  (càng cao càng tốt)
  FAR = b/(a+b)      trong số lần báo, bao nhiêu là báo hụt (càng thấp càng tốt)
  CSI = a/(a+b+c)    chỉ số tổng hợp, bỏ qua ô correct negative
  bias= (a+b)/(a+c)  >1 là báo quá nhiều, <1 là báo quá ít

CSI là chỉ số nên đọc trước. POD một mình vô nghĩa: một model luôn hét "nguy
hiểm" có POD = 100% và hoàn toàn vô dụng — chính cái bẫy đã làm hỏng bản
backtest đầu tiên của dự án này.
"""
from __future__ import annotations

from collections import defaultdict

from app.services import federated, hazard

WARN = hazard.SAFE      # ngưỡng coi là "model đã báo"


def _metrics(a: int, b: int, c: int, d: int) -> dict:
    """a=hit, b=false alarm, c=miss, d=correct negative."""
    pod = a / (a + c) if (a + c) else None
    far = b / (a + b) if (a + b) else None
    csi = a / (a + b + c) if (a + b + c) else None
    bias = (a + b) / (a + c) if (a + c) else None
    return {
        "hit": a, "false_alarm": b, "miss": c, "correct_negative": d,
        "samples": a + b + c + d,
        "pod": round(pod, 3) if pod is not None else None,
        "far": round(far, 3) if far is not None else None,
        "csi": round(csi, 3) if csi is not None else None,
        "bias": round(bias, 2) if bias is not None else None,
    }


def _verdict(m: dict) -> str:
    if m["samples"] < federated.MIN_OBS:
        return "chưa đủ quan sát để kết luận"
    csi, bias = m["csi"], m["bias"]
    if csi is None:
        return "chưa có sự việc nào để đối chiếu"
    if csi >= 0.6:
        return "khớp thực địa tốt"
    if bias is not None and bias > 1.5:
        return "báo quá nhiều — nên nâng ngưỡng ở vùng này"
    if bias is not None and bias < 0.6:
        return "bỏ sót nhiều — nên hạ ngưỡng ở vùng này"
    return "còn lệch, cần thêm quan sát để biết lệch theo hướng nào"


def _tally(observations: list) -> tuple[int, int, int, int]:
    a = b = c = d = 0
    for o in observations:
        if o.model_index is None:
            continue
        warned = o.model_index >= WARN
        if o.outcome == "occurred":
            a += warned
            c += not warned
        elif o.outcome == "none":
            b += warned
            d += not warned
    return a, b, c, d


def evaluate(observations: list) -> dict:
    """Chấm điểm mô hình trên toàn bộ quan sát. Không lộ dữ liệu cá nhân."""
    overall = _metrics(*_tally(observations))

    by_module = {}
    per_module: dict[str, list] = defaultdict(list)
    for o in observations:
        per_module[o.module_id].append(o)
    for mid, obs in sorted(per_module.items()):
        m = _metrics(*_tally(obs))
        m["verdict"] = _verdict(m)
        by_module[mid] = m

    # Vùng lệch nhiều nhất — nơi đáng đi hiệu chỉnh trước.
    per_cell: dict[tuple[str, str], list] = defaultdict(list)
    for o in observations:
        per_cell[(federated.cell_of(o.lat, o.lon), o.module_id)].append(o)
    worst = []
    for (cell, mid), obs in per_cell.items():
        m = _metrics(*_tally(obs))
        if m["samples"] < federated.MIN_OBS or m["csi"] is None:
            continue
        worst.append({"cell": cell, "module_id": mid, "csi": m["csi"],
                      "bias": m["bias"], "samples": m["samples"],
                      "verdict": _verdict(m)})
    worst.sort(key=lambda w: w["csi"])

    n = overall["samples"]
    if n < federated.MIN_OBS:
        headline = (f"Mới có {n} quan sát thực địa — cần ít nhất "
                    f"{federated.MIN_OBS} để chấm điểm mô hình.")
    elif overall["csi"] is None:
        headline = f"{n} quan sát, nhưng chưa có sự việc nào để đối chiếu."
    else:
        headline = (f"CSI {overall['csi']} trên {n} quan sát thực địa "
                    f"(POD {overall['pod']} · FAR {overall['far']}).")

    return {
        "dataset": {
            "observations": n,
            "modules_covered": len(by_module),
            "cells_covered": len(per_cell),
            "warn_threshold": WARN,
        },
        "overall": overall,
        "overall_verdict": _verdict(overall),
        "by_module": by_module,
        "weakest_cells": worst[:10],
        "headline": headline,
        "metric_guide": {
            "pod": "Bắt được bao nhiêu phần sự việc thật (cao là tốt).",
            "far": "Trong số lần báo, bao nhiêu phần là báo hụt (thấp là tốt).",
            "csi": "Chỉ số tổng hợp — đọc cái này trước.",
            "bias": ">1 báo quá nhiều · <1 báo quá ít · ~1 vừa đúng.",
        },
        "why_csi_first": (
            "POD một mình vô nghĩa: model luôn hét 'nguy hiểm' có POD 100% mà "
            "hoàn toàn vô dụng. Đúng cái bẫy đã làm hỏng bản backtest đầu tiên "
            "của dự án này, nên ở đây CSI và FAR luôn đứng cạnh POD."),
        "honesty_note": (
            "Đây là phần ĐO của model engine, chạy trên quan sát thật. Phần "
            "HUẤN LUYỆN lại (S09 đầy đủ) cần dataset gán nhãn lớn và GPU — chưa "
            "có. Nhưng không đo được thì huấn luyện cũng chỉ là tiêu tiền trong "
            "bóng tối, nên phần này làm trước là đúng thứ tự."),
    }
