"""Kiểm độc lập lịch sử nước bằng bản đồ ngập UNOSAT (water_unosat_protocol.json): thẻ mô hình đọc thẳng tệp kết quả,
kể cả phần yếu (cảm biến khác Sentinel-1) — không được giấu."""
from __future__ import annotations

import json
import os


def test_ket_qua_va_the_mo_hinh():
    from app.services import model_cards as mc
    p = os.path.join(os.path.dirname(__file__), "..", "data", "eval", "water_unosat_result.json")
    r = json.load(open(p, encoding="utf-8"))
    assert r["passed"] is True and len(r["points"]) == 160
    assert all(isinstance(x["event"], str) for x in r["points"])                    # mã sự kiện, không bị ghi đè
    c = next(x for x in mc.cards() if x["id"] == "water_radar")
    labels = " ".join(m["label"] for m in c["metrics"])
    assert "UNOSAT" in labels and "KHÁC Sentinel-1" in labels                        # phần độc lập phải hiện riêng
    assert "6/16" in c["limits"]
