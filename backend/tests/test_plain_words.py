"""Câu lời thường của lịch sử nước và kiểm tin đăng (việc b, 2/11/2026) — chỉ diễn đạt lại, không đổi phán quyết."""
from __future__ import annotations

from app.services import listing_check as lc, water_history as wh

BASE = {"available": True, "n_scenes": 330, "first": "2017-01-11", "last": "2026-10-28"}
SEASON = {"months": [1, 10, 11, 12], "core": [10, 11, 12], "text": "10–1", "window": "2016–2025"}


def test_sia_hue_mot_anh_le_ngoai_mua_khong_tinh_va_noi_vi_sao():
    """Ca thật 2/11/2026, đầu tây đường Trần Bá Song (Sịa): 0 đợt trong mùa, 1 ảnh lẻ 31/5/2026 (8 ngày mưa ~10 mm)."""
    r = {**BASE, "n_events": 1, "n_in": 0, "n_out": 1, "flood_season": SEASON, "out_kind": "weather",
         "events": [{"start": "2026-05-31", "end": "2026-05-31", "n_scenes": 1, "season": "out"}]}
    p = wh.plain(r)
    assert p["level"] == "dry" and p["count"] == 0
    assert p["short"] == "Từ 2017 đến nay, vệ tinh chưa thấy nước phủ thửa này trong mùa mưa lũ (330 lần chụp)."
    assert "Không tính 1 lần nước ngoài mùa mưa (chỉ thấy trên ảnh lẻ — có thể là nhiễu hoặc mưa trái mùa)" in p["text"]


def test_khu_nha_cua_0_dot_thi_noi_khong_ket_luan_duoc_khong_noi_chua_tung_ngap():
    r = {**BASE, "n_events": 0, "events": [], "urban": {"built_pct": 44.7, "note": "…"}}
    p = wh.plain(r)
    assert p["level"] == "blind" and "KHÔNG kết luận được" in p["text"] and "chưa lần nào" not in p["text"]
    assert "nhà cửa chiếm 44.7% khung đo" in p["text"] and "phần lớn" not in p["text"]   # 44,7% không phải "phần lớn"


def test_khong_co_lop_mua_lu_dem_moi_dot_va_nhac_nuoc_tuoi_neu_la_ruong():
    r = {**BASE, "n_events": 2, "cropland": {"note": "…"},
         "events": [{"start": "2020-10-28", "end": "2020-10-30", "n_scenes": 2}, {"start": "2024-09-12", "end": "2024-09-12", "n_scenes": 1}]}
    p = wh.plain(r)
    assert p["short"] == "Từ 2017 đến nay, vệ tinh thấy nước phủ thửa này 2 lần, lần gần nhất 12/9/2024."
    assert "nước tưới" in p["text"]


def test_chua_tung_thay_nuoc_noi_ro_anh_cach_6_12_ngay():
    p = wh.plain({**BASE, "n_events": 0, "events": []})
    assert p["level"] == "dry" and "chưa lần nào" in p["text"] and "6–12 ngày" in p["text"]


def test_mat_nuoc_thuong_xuyen_va_chua_doc_duoc():
    assert wh.plain({**BASE, "n_events": 0, "events": [], "water_surface": {"pct": 40}})["level"] == "water_body"
    assert wh.plain({"available": False}) is None


def test_cau_dau_kiem_tin_khu_nha_cua_noi_khong_kiem_duoc():
    rows = [{"type": "no_flood", "sentence": "không bao giờ ngập lụt", "verdict": "insufficient", "evidence": "…"},
            {"type": "high_ground", "sentence": "cao ráo", "verdict": "consistent", "evidence": "…"}]
    h = lc.headline(rows, {"urban": {"built_pct": 44.7}}, needs_water=False)
    assert h["level"] == "na" and h["text"].startswith("Tin viết “không bao giờ ngập lụt” — vệ tinh KHÔNG kiểm được")


def test_cau_dau_kiem_tin_khong_co_mau_thuan_van_nhac_khong_phai_bao_dam():
    rows = [{"type": "flat", "sentence": "bằng phẳng", "verdict": "consistent", "evidence": "Độ dốc 1°."}]
    h = lc.headline(rows, {}, needs_water=False)
    assert h["level"] == "ok" and "chưa phải bảo đảm" in h["text"]
    assert lc.headline([], {}, needs_water=False) is None


def test_cau_dau_kiem_tin_mau_thuan_khong_phai_ngap_dung_bang_chung_cua_cau_do():
    rows = [{"type": "near_sea", "sentence": "gần biển", "verdict": "contradicted", "evidence": "Cách bờ biển khoảng 48 km."},
            {"type": "flat", "sentence": "bằng phẳng", "verdict": "contradicted", "evidence": "Độ dốc 18° — không phải đất bằng."}]
    h = lc.headline(rows, {}, needs_water=False)
    assert h["text"] == "Tin viết “bằng phẳng” — nhưng độ dốc 18° — không phải đất bằng. Thêm 1 câu khác cũng trái với dữ liệu đo."


def test_cao_rao_noi_theo_dem_duoc_va_noi_ro_mau_thuan_do_nuoc():
    """Kiểm 7/11/2026 mục 5: "Thửa thấp hơn 38% đất trong bán kính" đọc như đất cao. Ca thửa demo Tuệ Tĩnh: 38% điểm quanh
    cao hơn (mức giữa) + 5 đợt nước trong mùa lũ → mâu thuẫn CHỦ YẾU do nước, địa hình nói theo kiểu đếm được."""
    terr = {"lower_than_pct": 38, "radius_km": 5.0, "elevation_m": 3.1}
    w = {"n_in": 5, "n_out": 0, "n_events": 5, "events": [], "flood_season": {"text": "7–10", "window": "2016–2025"}}
    v, msg, _ = lc.judge("high_ground", {"terrain": terr, "water": w})
    assert v == "contradicted" and msg.startswith("Mâu thuẫn chủ yếu vì radar thấy nước phủ thửa 5 đợt trong mùa lũ.")
    assert "cứ 100 điểm đo quanh thửa (bán kính 5 km) thì 38 điểm cao hơn thửa" in msg and "không phải chỗ cao" in msg
    assert "thấp hơn 38%" not in msg

    v, msg, _ = lc.judge("high_ground", {"terrain": {**terr, "lower_than_pct": 85}, "water": None})
    assert v == "contradicted" and "trũng hơn hầu hết đất xung quanh" in msg and "85 điểm cao hơn thửa" in msg

    v, msg, _ = lc.judge("high_ground", {"terrain": {**terr, "lower_than_pct": 12}, "water": None})
    assert v == "consistent" and "cao hơn phần lớn đất xung quanh" in msg and "12 điểm cao hơn thửa" in msg

    v, msg, _ = lc.judge("high_ground", {"terrain": terr, "water": {**w, "n_in": 1}})
    assert v == "insufficient" and "mức giữa" in msg and "Radar thấy nước phủ 1 đợt trong mùa lũ." in msg