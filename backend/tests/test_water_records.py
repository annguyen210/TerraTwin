"""Cổng hồ sơ công khai v1 (water_records_protocol.json): kết quả tính lại được từ nhãn đã khoá + khoá phân loại, khớp mã
băm đã commit trước khi tra, và thẻ mô hình hiện đúng kết quả (kể cả TRƯỢT) ngay trước dòng xác nhận người dùng."""
from __future__ import annotations

import hashlib
import json
import math
import os

E = os.path.join(os.path.dirname(__file__), "..", "data", "eval")


def _j(name):
    return json.load(open(os.path.join(E, name), encoding="utf-8"))


def test_ket_qua_tinh_lai_tu_nhan_va_khoa():
    lab, res, items = _j("water_records_labels.json"), _j("water_records_result.json"), _j("water_records_items.json")
    key = res["key"]
    raw = open(os.path.join(E, "water_records_key.json"), "rb").read()                # tệp khoá gốc, giữ nguyên byte (-text)
    assert hashlib.sha256(raw).hexdigest() == lab["sha256_key_expected"] == items["sha256_key"]   # = mã băm commit trước khi tra
    assert json.loads(raw) == key
    assert set(key) == {x["id"] for x in items["items"]} == set(lab["labels"])
    pos = lambda i: lab["labels"][i]["level"] in ("commune", "district")                  # noqa: E731
    rad = [i for i in key if key[i] == "radar"]
    pla = [i for i in key if key[i] == "placebo"]
    assert len(rad) == res["n_radar"] == 20 and len(pla) == res["n_placebo"] == 20
    a, c = sum(map(pos, rad)), sum(map(pos, pla))
    assert (a, c) == (res["radar"]["positive"], res["placebo"]["positive"])
    p = sum(math.comb(20, x) * math.comb(20, a + c - x) for x in range(a, a + c + 1)) / math.comb(40, a + c)
    assert abs(p - res["fisher_one_sided_p"]) < 1e-4
    ok = p < 0.05 and a / 20 - c / 20 >= 0.20
    assert res["passed"] is ok and res["verdict"] == ("ĐẠT" if ok else "TRƯỢT")


def test_the_mo_hinh_hien_ket_qua_cong():
    from app.services import model_cards as mc
    res = _j("water_records_result.json")
    c = next(x for x in mc.cards() if x["id"] == "water_radar")
    i = next(k for k, m in enumerate(c["metrics"]) if "hồ sơ công khai có đối chứng" in m["label"])
    m = c["metrics"][i]
    assert m["passed"] is res["passed"] and res["verdict"] in m["value"]
    assert m["value"].startswith(f"{res['radar']['positive']}/20 ngày radar")
    assert c["metrics"][-1]["label"].startswith("Kiểm thực địa") and i == len(c["metrics"]) - 2
    assert "TRƯỢT" in c["limits"] or res["passed"]
