"""Kiểm 20/11/2026 trên fd89ebd: /plot/20.97160,106.28340 dòng đầu ghi "15 lần ngập lụt chạm ngưỡng nguy hiểm trong 10 năm"
ngay trên "vệ tinh thấy nước phủ thửa này 5 lần"; trợ lý "Thửa này từng ngập chưa?" trả "15 đợt lũ/ngập". Con số 15 là đợt
CHỈ SỐ MƯA ERA5 vượt ngưỡng — không phải lần ngập. Ngập quan sát được lấy từ radar Sentinel-1."""
from __future__ import annotations

import pytest

HIST = {"flood": {"name": None, "events": 15, "peak_month": 8, "peak_month_events": 6, "latest": "2026-08-23",
                  "worst_value": 80.0, "worst_date": "2020-10-10", "national_threshold": 40.0}}
WATER = {"cached": True, "available": True, "n_events": 5, "first": "2017-01-01", "last": "2026-11-01",
         "last_event": "2025-10-01"}


@pytest.fixture()
def gia(monkeypatch):
    from app.services import cache_store, passport, reqlang, water_history
    reqlang.set_lang("vi")
    h = {k: {**v, "name": passport._ten(k)} for k, v in HIST.items()}
    monkeypatch.setattr(passport, "history", lambda lat, lon, years=10: h)
    monkeypatch.setattr(passport, "terrain", lambda lat, lon: None)
    monkeypatch.setattr(water_history, "summary", lambda lat, lon: dict(WATER))
    monkeypatch.setattr(cache_store, "get", lambda k: None)
    monkeypatch.setattr(cache_store, "put", lambda k, v, ttl_seconds: None)
    return passport


def test_dong_dau_khong_goi_era5_la_lan_ngap(gia):
    d = gia.build(20.9716, 106.2834)
    head = d["headline"]
    assert "lần ngập" not in head.replace("không phải lần ngập", "") and "ngập lụt" not in head
    assert "radar Sentinel-1 thấy nước phủ thửa 5 lần" in head            # ngập quan sát được đứng trước
    assert "15 đợt mưa lớn dễ gây ngập" in head and "ERA5" in head
    assert head.index("radar") < head.index("15 đợt")


def test_tro_ly_tra_loi_ngap_bang_so_radar(gia):
    from app.services import copilot
    from app.schemas import Location
    facts = copilot._history_facts(Location(lat=20.9716, lon=106.2834), ["flood"])
    assert "radar Sentinel-1 (quan sát thật): 5 đợt" in facts
    assert "Lũ/ngập" not in facts and "đợt lũ/ngập" not in facts.lower()
    assert "chỉ số thời tiết ERA5" in facts and "KHÔNG phải số lần xảy ra đo được" in facts
    assert "radar" in copilot._system().lower() and "ERA5" in copilot._system()


def test_lich_su_null_thi_noi_ly_do(monkeypatch):
    from app.services import cache_store, passport, reqlang, water_history
    reqlang.set_lang("vi")
    monkeypatch.setattr(passport, "history", lambda lat, lon, years=10: None)
    monkeypatch.setattr(passport, "terrain", lambda lat, lon: {"elevation_m": 3, "lower_than_pct": 60, "radius_km": 3,
                                                               "slope_deg": 0.1, "meaning": "x"})
    monkeypatch.setattr(water_history, "summary", lambda lat, lon: {"cached": False})
    monkeypatch.setattr(cache_store, "get", lambda k: None)
    monkeypatch.setattr(cache_store, "put", lambda k, v, ttl_seconds: None)
    d = passport.build(20.9716, 106.2834)
    assert d["history"] is None and "hết lượt" in d["history_note"]


def test_tro_ly_co_tung_dot_nuoc_de_tra_loi_theo_nam(gia, monkeypatch):
    """Kiểm A–Z 24/11/2026: hỏi "Ruộng này năm 2024 có bị ngập không?" → trợ lý trả "không có dữ liệu" vì ngữ cảnh chỉ có
    số đợt + đợt gần nhất (2025), dù radar thấy 26/7 và 12/9/2024 (bão Yagi). Ngữ cảnh phải có TỪNG đợt kèm mức phủ."""
    from app.services import copilot, water_history
    from app.schemas import Location
    evs = [{"start": "2018-07-22", "end": "2018-07-22", "cover": "≥50%"},
           {"start": "2024-07-26", "end": "2024-07-26", "cover": "10–25%"},
           {"start": "2024-09-12", "end": "2024-09-24", "cover": "≥50%"}]
    monkeypatch.setattr(water_history, "summary", lambda lat, lon: {**WATER, "n_events": 3, "events": evs})
    facts = copilot._history_facts(Location(lat=20.9716, lon=106.2834), ["flood"])
    assert "26/7/2024 (phủ 10–25% thửa)" in facts and "12/9/2024–24/9/2024 (phủ ≥50% thửa)" in facts
    sysp = copilot._system()
    assert "KHÔNG khuyên" in sysp and "'nhẹ'" in sysp


def test_tom_tat_luu_tung_dot_tu_bo_nho_dem(monkeypatch):
    from app.services import cache_store, flood_season, water_history
    monkeypatch.setattr(flood_season, "season_cached", lambda lat, lon: None)
    hit = {"available": True, "first": "2017-01-01", "last": "2026-11-01",
           "events": [{"start": "2024-09-12", "end": "2024-09-24", "peak_cover": "≥50%"},
                      {"start": "2018-07-22", "end": "2018-07-22", "peak_cover": "25–50%"}]}
    monkeypatch.setattr(cache_store, "get", lambda k: hit)
    s = water_history.summary(20.9716, 106.2834)
    assert s["n_events"] == 2 and s["last_event"] == "2024-09-12"
    assert [e["start"] for e in s["events"]] == ["2018-07-22", "2024-09-12"]
    assert s["events"][1] == {"start": "2024-09-12", "end": "2024-09-24", "cover": "≥50%"}


def test_hoi_theo_nam_tra_loi_chac_chan_khong_can_llm(gia, monkeypatch):
    """Bộ chấm trợ lý 24/11/2026: năm KHÔNG có đợt → LLM trả "chưa đủ thông tin"; LLM bị chặn hạn mức → bản liệt kê thô."""
    from app.services import copilot, llm, water_history
    from app.schemas import Location
    evs = [{"start": "2024-07-26", "end": "2024-08-07", "cover": "10–25%"}, {"start": "2024-09-12", "end": "2024-09-12", "cover": "≥50%"}]
    monkeypatch.setattr(water_history, "summary", lambda lat, lon: {**WATER, "n_events": 2, "events": evs})
    monkeypatch.setattr(llm, "complete", lambda *a, **k: (_ for _ in ()).throw(AssertionError("không được gọi LLM")))
    loc = Location(lat=20.9716, lon=106.2834)
    a = copilot.answer("Năm 2024 thửa này có bị ngập không?", loc).answer
    assert a.startswith("Có. Năm 2024, radar Sentinel-1 thấy nước phủ thửa 2 đợt") and "26/7/2024–7/8/2024" in a and "12/9/2024" in a
    a = copilot.answer("Năm 2020 ruộng này có ngập không?", loc).answer
    assert "chưa thấy đợt nước phủ nào" in a and "KHÔNG có nghĩa là chắc chắn không ngập" in a
    assert "không nói được năm 2014" in copilot.answer("Năm 2014 ở đây có lụt không?", loc).answer


def test_du_phong_khong_lo_loi_nhan_cau_hinh(monkeypatch):
    from app.services import copilot_route as cr
    assert cr.asks_year_water("Năm 2024 thửa này có bị ngập không?") == 2024
    assert cr.asks_year_water("Năm 2024 giá đất bao nhiêu?") is None and cr.asks_year_water("Từ 2020 đến 2024 ngập mấy lần?") is None
    assert cr.asks_buy("Tôi có nên mua mảnh đất này không?") and not cr.asks_buy("Thửa này từng ngập chưa?")
    import inspect
    from app.services import copilot
    src = inspect.getsource(copilot)
    assert "TERRATWIN_LLM_API_KEY để bật" not in src and "Trợ lý AI đang bận" in src


def test_llm_bi_chan_han_muc_thi_thu_lai_mot_lan(monkeypatch):
    import io
    import urllib.error
    from app.services import llm
    goi = {"n": 0}

    class _R:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"ok": 1}'

    def fake(req, timeout=None):
        goi["n"] += 1
        if goi["n"] == 1:
            raise urllib.error.HTTPError(req.full_url, 429, "Too Many", {"retry-after": "1"}, io.BytesIO(b"rate"))
        return _R()
    monkeypatch.setattr(llm.urllib.request, "urlopen", fake)
    monkeypatch.setattr("time.sleep", lambda s: None)
    assert llm._post("https://x.test/v1", {}, {}) == {"ok": 1} and goi["n"] == 2


def test_so_dot_nuoc_luon_gan_nguon_radar():
    """Bộ chấm v2 (24/11/2026, Phan Rang): "đã từng có nước phủ thửa 5 đợt (…)" — đúng số nhưng không nói nguồn."""
    from app.services import copilot, reqlang
    reqlang.set_lang("vi")
    t = copilot._han_che("Thửa này đã từng có nước phủ thửa 5 đợt (18/6/2018, 5/8/2018).", "Đất này có hay bị lũ không?",
                         {}, {"n_events": 5, "last_event": "2026-09-23"})
    assert "5 đợt (radar Sentinel-1 nhìn xuyên mây)" in t
    t2 = copilot._han_che("Radar Sentinel-1 thấy 5 đợt nước.", "Đất này có hay bị lũ không?", {}, {"n_events": 5})
    assert t2.count("radar") == 1 or t2.lower().count("radar") == 1
