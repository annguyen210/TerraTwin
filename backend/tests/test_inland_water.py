"""Điểm GIỮA LÒNG SÔNG không được chấm "đất an toàn" (kiểm toàn bộ 16/10/2026, việc 1).

Số đo thật 16/10/2026 tại 15.8712, 108.3381 (sông Thu Bồn, Hội An) — dùng nguyên làm dữ liệu giả lập:
    WorldCover 2021 (bán kính 60 m): Mặt nước 59,7% · Đồng cỏ 14,8% · Tán cây 14,3% · Trồng trọt 11,2%
    Nền radar Sentinel-1 (310 cảnh): p10 −19,11 · p25 −17,1 · p50 −12,68 · p75 −8,82 dB → 0 đợt nước
Trước khi sửa: TerraScore 100/A "Đất an toàn", lịch sử nước "0 đợt", phát hành được hồ sơ.
Đối chứng — đồng lúa Quảng Điền, Huế: WorldCover Trồng trọt 100%, nền p10 −11,83 dB, 7 đợt nước.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

HOI_AN = (15.8712, 108.3381)
HUE = (16.5751, 107.4952)
WC = {HOI_AN: {"item": "ESA_WorldCover_10m_2021_v200_N15E108", "hist": {"80": 597, "30": 148, "10": 143, "40": 112}},
      HUE: {"item": "ESA_WorldCover_10m_2021_v200_N15E105", "hist": {"40": 144}}}
BASE = {HOI_AN: {"p10": -19.11, "p25": -17.1, "p50": -12.68, "p75": -8.82},
        HUE: {"p10": -11.83, "p25": -10.37, "p50": -8.84, "p75": -7.44}}

pytestmark = pytest.mark.mat_nuoc_that


@pytest.fixture
def fake(monkeypatch):
    """WorldCover + lịch sử nước đã đọc (cache) + cao độ 1 m + quốc gia VN — không chạm mạng."""
    from app.services import cache_store, landuse, realdata, region, water_history as wh
    near = lambda la, lo, tbl: next((v for (a, b), v in tbl.items() if abs(a - la) < 1e-3 and abs(b - lo) < 1e-3), None)  # noqa: E731
    state = {"wc": dict(WC), "base": dict(BASE)}
    monkeypatch.setattr(landuse, "fetch_raw", lambda la, lo, radius_m=60.0: near(la, lo, state["wc"]))
    keys = {wh.cache_key(*p): p for p in (HOI_AN, HUE)}
    real_get = cache_store.get

    def get(key):
        if key in keys:
            b = near(*keys[key], state["base"])
            return None if b is None else {"available": True, "baseline_db": b, "n_events": 0, "events": [], "n_scenes": 310,
                                           "first": "2017-01-04", "last": "2026-10-10", "series": [], "method": "m", "limits": "l",
                                           "track": {"orbit": "descending", "relative_orbit": 18, "collection": "sentinel-1-rtc"}}
        return real_get(key)
    monkeypatch.setattr(cache_store, "get", get)
    monkeypatch.setattr(realdata, "elevation_m", lambda la, lo: 1.0)
    monkeypatch.setattr(region, "country_code", lambda la, lo: "vn")
    return state


def test_giua_song_hoi_an_la_mat_nuoc_thuong_xuyen(fake):
    from app.services import region
    r = region.classify(*HOI_AN)
    assert r["kind"] == "inland_water" and r["serviceable"] is False
    assert "MẶT NƯỚC THƯỜNG XUYÊN" in r["note"] and "dời ô ngắm" in r["note"] and "59.7%" in r["note"]
    assert r["water"]["worldcover_water_pct"] == 59.7 and r["water"]["radar_baseline_db"]["p10"] == -19.11


def test_dong_lua_hue_van_la_dat(fake):
    from app.services import region
    r = region.classify(*HUE)
    assert r["kind"] == "land" and r["serviceable"] is True


def test_khong_co_worldcover_thi_dua_vao_nen_radar_p25(fake):
    """WorldCover không gọi được: chỉ chặn khi nền p25 < −18 dB (≥ 1/4 khung là nước ở hầu hết lần chụp)."""
    from app.services import region
    fake["wc"].pop(HOI_AN)
    assert region.classify(*HOI_AN)["kind"] == "land"            # chỉ p10 < −18 → không chặn (xem cảnh báo bên dưới)
    fake["base"][HOI_AN] = {"p10": -21.0, "p25": -19.4, "p50": -16.0, "p75": -10.0}
    r = region.classify(*HOI_AN)
    assert r["kind"] == "inland_water" and "p25 = -19.4 dB" in r["note"]


def test_khong_co_nguon_nao_thi_khong_chan_ai(fake):
    from app.services import region
    fake["wc"].pop(HOI_AN); fake["base"].pop(HOI_AN)
    assert region.classify(*HOI_AN)["serviceable"] is True      # fail-open


def test_api_khong_cham_terrascore_khong_quet_khong_phat_hanh_ho_so(fake):
    from app.main import app
    lat, lon = HOI_AN
    with TestClient(app) as c:
        t = c.post("/api/terrascore", json={"lat": lat, "lon": lon}).json()
        assert t["grade"] == "—" and t["score"] is None and t["region"]["kind"] == "inland_water"   # null, không phải 0 (17/10)
        s = c.post("/api/scan", json={"lat": lat, "lon": lon}).json()
        assert s["modules"] == [] and s["terrascore"]["grade"] == "—" and s["terrascore"]["score"] is None
        assert s["terrascore"]["region"]["kind"] == "inland_water"      # thẻ thửa đọc region từ đây
        a = c.post("/api/assess/land_risk", json={"lat": lat, "lon": lon}).json()
        assert a["status"] == "out_of_scope" and "mặt nước thường xuyên" in a["headline"]
        d = c.post("/api/dossier", json={"lat": lat, "lon": lon})
        assert d.status_code == 422 and "MẶT NƯỚC THƯỜNG XUYÊN" in d.text


def test_lich_su_nuoc_ghi_ro_khung_do_co_mat_nuoc(fake):
    """0 đợt nước ở đây là vì nước có quanh năm — kết quả phải nói ra, không để người đọc hiểu là "không ngập"."""
    from app.services import water_history as wh
    ws = wh.water_surface(BASE[HOI_AN])
    assert ws["share"] == "≥10%" and ws["pct"] == 10 and "không có nghĩa là không ngập" in ws["note"]
    assert wh.water_surface(BASE[HUE]) is None
    assert wh.water_surface({"p10": -22, "p25": -20, "p50": -18.5})["share"] == "≥50%"


def test_tin_dang_khong_ngap_tai_diem_giua_song_la_mau_thuan(fake, monkeypatch):
    from app.services import listing_check as lc, passport
    monkeypatch.setattr(passport, "terrain", lambda la, lo: None)
    r = lc.check("Đất cao ráo, không bao giờ ngập", *HOI_AN)
    got = {c["type"]: c["verdict"] for c in r["claims"]}
    assert got == {"high_ground": "contradicted", "no_flood": "contradicted"} and r["on_water"] and r["needs_water"] is False


def test_ho_so_mang_canh_bao_khung_do_co_mat_nuoc(fake, monkeypatch):
    """Không chặn (chỉ p10 < −18, WorldCover không có) nhưng hồ sơ ký phải mang cảnh báo, lời diễn giải nói ra."""
    from app import routes_water
    from app.services import dossier, narrative
    monkeypatch.setattr(routes_water, "gate", lambda: {"passed": True})
    w = dossier._water_section(*HOI_AN)
    assert w["water_surface"] == {"share": "≥10%", "pct": 10, "baseline_db": -19.11}
    w_hue = dossier._water_section(*HUE)
    assert "water_surface" not in w_hue                           # đất thật: hồ sơ không đổi gì
    facts = {"water_history_radar": {**w, "events": []}}
    cat = narrative.catalog(facts) if hasattr(narrative, "catalog") else {"water.summary": {}}
    text = narrative.template_sentences(facts, cat)[0]["text"]
    assert "không có nghĩa là không ngập" in text and "p10" in text


def test_tham_dinh_hang_loat_cung_khong_cham_diem_giua_song(fake):
    """17/10/2026: hàng loạt từng gọi thẳng scan.scan (không qua cửa chặn vùng) nên dòng CSV giữa sông vẫn có điểm."""
    from app.services import batch
    r = batch.appraise({"id": "1", "lat": HOI_AN[0], "lon": HOI_AN[1], "area_ha": 1.0})
    assert r["score"] is None and r["grade"] is None and r["region"] == "inland_water" and "MẶT NƯỚC THƯỜNG XUYÊN" in r["error"]
