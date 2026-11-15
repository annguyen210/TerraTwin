"""Cổng hồ sơ công khai v2 (tin báo → radar, water_records_v2_protocol.json): kết quả tính lại được từ các điểm đã lưu, đúng
ngưỡng đã đăng ký, và thẻ mô hình hiện kết quả (kể cả TRƯỢT) trước dòng xác nhận người dùng."""
from __future__ import annotations

import json
import math
import os

E = os.path.join(os.path.dirname(__file__), "..", "data", "eval")


def _j(name):
    return json.load(open(os.path.join(E, name), encoding="utf-8"))


def test_ket_qua_tinh_lai_tu_cac_diem():
    pts, res, proto = _j("water_records_v2_points.json"), _j("water_records_v2_result.json"), _j("water_records_v2_protocol.json")
    assert res["n_events"] == proto["frame"]["n_events"] and len(pts) == res["n_points"] <= proto["frame"]["n_events"]
    assert len({p["k"] for p in pts}) == len(pts)                                     # mỗi trận nhiều nhất một điểm
    a, n1 = sum(p["reported_wet"] for p in pts), len(pts)
    ctrl = [c for p in pts for c in p["controls"]]
    c, n2 = sum(x["wet"] for x in ctrl), len(ctrl)
    assert all(1 <= len(p["controls"]) <= 2 for p in pts)
    assert (a, n1, c, n2) == (res["reported"]["wet"], res["reported"]["n"], res["control"]["wet"], res["control"]["n"])
    k = a + c
    pv = sum(math.comb(n1, x) * math.comb(n2, k - x) for x in range(a, min(n1, k) + 1)) / math.comb(n1 + n2, k)
    assert abs(pv - res["fisher_one_sided_p"]) < 1e-4
    if n1 < 15:
        assert res["passed"] is None
    else:
        ok = pv < 0.05 and a / n1 - c / n2 >= 0.20
        assert res["passed"] is ok and res["verdict"] == ("ĐẠT" if ok else "TRƯỢT")


def test_the_mo_hinh_hien_v2():
    from app.services import model_cards as mc
    res = _j("water_records_v2_result.json")
    card = next(x for x in mc.cards() if x["id"] == "water_radar")
    m = next(x for x in card["metrics"] if "hồ sơ công khai v2" in x["label"])
    assert m["passed"] is res["passed"] and res["verdict"] in m["value"]
    assert card["metrics"][-1]["label"].startswith("Kiểm thực địa")
