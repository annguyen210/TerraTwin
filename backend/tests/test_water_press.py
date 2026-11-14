"""Đối chiếu PHỤ lịch sử nước với báo chí (water_press_protocol.json): số trên thẻ mô hình đọc thẳng tệp kết quả,
mỗi dòng 'khớp' có nguồn trong cửa sổ ngày, và KHÔNG lẫn vào cổng kiểm thực địa bằng xác nhận người dùng."""
from __future__ import annotations

import inspect
import json
import os
from collections import Counter
from datetime import date, timedelta

P = os.path.join(os.path.dirname(__file__), "..", "data", "eval", "water_press_result.json")


def _r():
    return json.load(open(P, encoding="utf-8"))


def test_so_dem_tinh_tu_cac_dong():
    r = _r()
    assert r["n_events"] == len(r["rows"]) == 24
    assert r["counts"] == {k: Counter(x["level"] for x in r["rows"]).get(k, 0)
                           for k in ("commune", "district", "province", "not_found", "contradicts")}
    assert r["matched_commune_or_district"] == r["counts"]["commune"] + r["counts"]["district"]
    for p, v in r["per_plot"].items():
        rows = [x for x in r["rows"] if x["plot"] == p]
        assert v == {"events": len(rows), "matched": sum(x["level"] in ("commune", "district") for x in rows)}


def test_dong_khop_co_nguon_trong_cua_so():
    for x in _r()["rows"]:
        if x["level"] not in ("commune", "district", "province"):
            continue
        start = date.fromisoformat(x["event_start"])
        lo, hi = start - timedelta(days=12), start + timedelta(days=3)
        ok = [s for s in x["sources"] if s["counted"] and lo <= date.fromisoformat(s.get("described_from") or s["date"]) <= hi]
        assert ok, (x["plot"], x["event_start"])
        assert all(s["url"].startswith("https://") and len(s["note"]) < 200 for s in x["sources"])   # chỉ tóm tắt, không chép bài


def test_khong_lan_vao_cong_thuc_dia():
    from app.services import field_truth, model_cards as mc
    r = _r()
    assert r["counts_toward_field_gate"] is False and r["entered_as_field_confirmations"] is False
    assert "water_press" not in inspect.getsource(field_truth)
    c = next(x for x in mc.cards() if x["id"] == "water_radar")
    labels = [m["label"] for m in c["metrics"]]
    i = next(k for k, s in enumerate(labels) if "báo chí" in s)
    assert "KHÔNG phải xác nhận thực địa" in labels[i] and c["metrics"][i]["passed"] is None
    assert c["metrics"][i]["value"].startswith(f"{r['matched_commune_or_district']}/24")
    assert c["metrics"][-1]["label"].startswith("Kiểm thực địa") and i < len(labels) - 1   # cổng người dùng vẫn đứng riêng, cuối
