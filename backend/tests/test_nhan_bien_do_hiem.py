"""Kiểm A–Z 24/11/2026: ô "Độ hiếm tổ hợp thời tiết" in thô "drange, rain_3d, wb_60d" — bảng nhãn ở giao diện
(PlotPlan.tsx DRIVER_L) thiếu 7/10 biến của mô hình. Mọi biến trong FEATURES phải có nhãn."""
from __future__ import annotations

import re
from pathlib import Path


def test_moi_bien_mo_hinh_do_hiem_co_nhan_giao_dien():
    from app.ml.dataset import FEATURES
    src = (Path(__file__).resolve().parents[2] / "frontend" / "components" / "PlotPlan.tsx").read_text(encoding="utf-8")
    block = src.split("const DRIVER_L", 1)[1].split("};", 1)[0]
    keys = set(re.findall(r"^\s*([a-z0-9_]+):\s*\[", block, flags=re.M))
    assert set(FEATURES) <= keys, f"thiếu nhãn: {sorted(set(FEATURES) - keys)}"
