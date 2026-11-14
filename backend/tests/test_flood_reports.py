"""Sổ lũ công khai (flood_reports.json + ranh huyện cũ 2020): định vị đúng huyện, cửa sổ ngày −12/+3, mức huyện > tỉnh,
và chỉ là lớp diễn giải — không đổi số đợt, không lẫn vào xác nhận thực địa."""
from __future__ import annotations

import inspect
import json
import os

from app.services import flood_reports as fr

DATA = os.path.join(os.path.dirname(__file__), "..", "data")


def test_so_lu_hop_le_va_moi_huyen_co_ranh():
    reps = json.load(open(os.path.join(DATA, "flood_reports.json"), encoding="utf-8"))["reports"]
    assert len(reps) >= 15 and len({r["id"] for r in reps}) == len(reps)
    units = {(fr.fold(u["province"]), fr.fold(u["name"]))
             for u in json.load(open(os.path.join(DATA, "admin", "vnm_adm2_2020.json"), encoding="utf-8"))["units"]}
    for r in reps:
        assert r["url"].startswith("https://") and r["flood_from"] <= r["flood_to"] <= r["published"], r["id"]
        assert r["summary"]["vi"] and r["summary"]["en"] and len(r["summary"]["vi"]) < 300      # tóm tắt, không chép bài
        for a in r["areas"]:
            assert a["level"] == "district" and (fr.fold(a["province"]), fr.fold(a["name"])) in units, (r["id"], a)
            assert fr.fold(a["province"]) in {fr.fold(p) for p in r["provinces"]}


def test_dinh_vi_huyen_cu():
    want = {(20.9716, 106.2834): ("camgiang", "Hải Dương"), (17.6118, 106.5026): ("botrach", "Quảng Bình"),
            (16.5751, 107.4952): ("quangdien", "Thừa Thiên Huế"), (16.52, 107.59): ("phuvang", "Thừa Thiên Huế")}
    for (la, lo), (d, p) in want.items():
        loc = fr.locate(la, lo)
        assert loc["district_key"] == d and loc["province"] == p
    assert fr.locate(13.75, 100.5) is None                                             # Bangkok: ngoài sổ
    assert fr.locate(20.77592, 105.97731)["province"] == "Hưng Yên"                    # Khoái Châu (lớp tỉnh 2008 gán nhầm Hà Nội)


def test_moi_huyen_thuoc_dung_mot_trong_63_tinh():
    u = json.load(open(os.path.join(DATA, "admin", "vnm_adm2_2020.json"), encoding="utf-8"))["units"]
    assert len(u) == 708 and len({x["province"] for x in u}) == 63
    got = {(x["name"], x["province"]) for x in u}
    assert {("Kim Bang", "Hà Nam"), ("Pho Yen", "Thái Nguyên"), ("Cho Gao", "Tiền Giang"), ("Binh Giang", "Hải Dương")} <= got


def test_duong_no_khop_huyen_va_cua_so_ngay():
    ev = [{"start": "2017-07-27"}, {"start": "2025-10-26"}, {"start": "2026-10-28"}]
    out = fr.annotate({"events": ev}, 16.52, 107.59)
    a, b, c = out["events"]
    assert b["press"]["level"] == "district" and any(x["id"] == "vtcnews-ar984376" for x in b["press"]["reports"])
    assert "Dương Nỗ" in (b["press"]["reports"][-1]["via"] or "") or any("Dương Nỗ" in (x["via"] or "") for x in b["press"]["reports"])
    assert a["press"] is None and c["press"] is None
    assert out["press"]["n_district"] == 1 and len(out["events"]) == len(ev)            # không thêm/bớt đợt
    loc = fr.locate(16.52, 107.59)
    rep = next(r for r in fr.registry() if r["id"] == "vtcnews-ar984830")            # ngập 2–3/11/2025
    assert fr._overlaps(rep, "2025-11-06") and not fr._overlaps(rep, "2025-11-16")   # S−12 ≤ hết ngập
    assert fr._overlaps(rep, "2025-10-30") and not fr._overlaps(rep, "2025-10-29")   # bắt đầu ngập ≤ S+3
    assert fr.match_event("2025-11-16", loc) is None


def test_muc_tinh_khi_bai_khong_neu_huyen():
    out = fr.annotate({"events": [{"start": "2024-09-19"}]}, 17.6118, 106.5026)       # Soulik: bài chỉ nêu Minh Hóa
    m = out["events"][0]["press"]
    assert m["level"] == "province" and out["press"]["n_district"] == 0 and out["press"]["n_province"] == 1


def test_khong_co_dot_hoac_ngoai_vn_thi_im_lang():
    assert fr.annotate({"events": []}, 16.52, 107.59) == {}
    assert fr.annotate({"events": [{"start": "2025-10-26"}]}, 13.75, 100.5) == {}


def test_kiem_tin_rao_them_cau_bao_chi():
    from app.services import listing_check as lc
    w = {"n_events": 1, "first": "2017-01-01", "n_scenes": 300,
         "events": fr.annotate({"events": [{"start": "2025-10-26"}]}, 16.52, 107.59)["events"]}
    v, msg, src = lc.judge("no_flood", {"water": w})
    assert v == "contradicted" and "Báo chí cũng ghi ngập" in msg and "báo chí" in src
    w2 = {"n_events": 1, "first": "2017-01-01", "n_scenes": 300, "events": [{"start": "2017-07-27", "press": None}]}
    assert "Báo chí" not in lc.judge("no_flood", {"water": w2})[1]


def test_khong_lan_vao_xac_nhan_thuc_dia():
    from app.services import field_truth
    assert "flood_reports" not in inspect.getsource(field_truth)
