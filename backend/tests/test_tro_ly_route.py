"""Kiểm 21/11/2026 — hai lỗi trợ lý trên bản chính thức (471d4e2):
1) trả lời vượt quá dữ liệu: "Will this land get salty in the dry season?" → "not expected to become salty in the upcoming
   dry season" từ một số mặn is_real=False, chỉ 7 ngày;
2) _route so chuỗi con: "manh dat nay co bi ngap khong" → chỉ nạp MẶN; "Tóm tắt các rủi ro chính…" → chỉ land_risk."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.copilot_route import asks_long_range, route


def test_manh_khong_phai_man_ngap_phai_thang():
    r = route("manh dat nay co bi ngap khong")
    assert "flood" in r and "salinity" not in r


def test_tom_tat_rui_ro_nap_du():
    r = route("Tóm tắt các rủi ro chính của thửa này và nên làm gì tiếp?")
    assert {"land_risk", "flood", "drought", "salinity"} <= set(r)


def test_cau_man_mua_kho():
    r = route("Will this land get salty in the dry season?")
    assert "salinity" in r
    assert asks_long_range("Will this land get salty in the dry season?")
    assert asks_long_range("mùa khô năm nay đất có bị mặn không")


def test_khong_khop_chuoi_con():
    # "thanh", "khan", "many", "manh" không còn kéo theo hạn/mặn
    assert route("thanh pho nay khan hiem nhieu thu, many manh dat") == ["salinity", "drought", "flood"]
    assert route("dat nay co han khong") == ["drought"]
    assert route("o day co bi lu lut khong") == ["flood"]
    assert route("ruộng có bị nhiễm mặn không") == ["salinity"]
    assert not asks_long_range("thửa này từng ngập chưa")


@pytest.fixture()
def tro_ly(monkeypatch):
    """Trợ lý với mô-đun giả (không gọi mạng), LLM giả trả đúng câu sai của production."""
    from app.services import copilot, llm, passport, reqlang, water_history
    reqlang.set_lang("en")
    est = SimpleNamespace(is_real=False, module_name="Salinity intrusion", headline="salinity index 12",
                          recommendation="No action needed", risk_level="safe", score=12, status="ok",
                          forecast=[], confidence=None)
    monkeypatch.setattr("app.modules.registry.get_module",
                        lambda mid: SimpleNamespace(assess=lambda loc: est))
    monkeypatch.setattr(passport, "history", lambda lat, lon, years=10: None)
    monkeypatch.setattr(water_history, "summary", lambda lat, lon: {"cached": False})
    monkeypatch.setattr(copilot, "_knowledge", lambda q, loc: ([], ""))
    monkeypatch.setattr(llm, "complete", lambda *a, **k: "The land is not expected to become salty in the upcoming dry season.")
    yield copilot
    reqlang.set_lang("vi")


def test_uoc_luong_va_ca_mua_duoc_ghi_chu(tro_ly):
    from app.schemas import Location
    a = tro_ly.answer("Will this land get salty in the dry season?", Location(lat=10.2415, lon=106.3759))
    assert a.llm and "estimate" in a.answer.lower() and "7 days" in a.answer
    assert "no forecast for the whole season" in a.answer


def test_luon_nap_radar_du_route_nao(monkeypatch):
    from app.schemas import Location
    from app.services import copilot, passport, reqlang, water_history
    reqlang.set_lang("vi")
    monkeypatch.setattr(passport, "history", lambda lat, lon, years=10: None)
    monkeypatch.setattr(water_history, "summary", lambda lat, lon: {"cached": True, "available": True, "n_events": 7,
                                                                    "first": "2017-01-01", "last_event": "2026-01-30"})
    facts = copilot._history_facts(Location(lat=16.5751, lon=107.4952), ["land_risk"])
    assert "radar Sentinel-1 (quan sát thật): 7 đợt" in facts


def test_loi_dan_7_ngay_va_khong_noi_chua_co():
    from app.services import copilot, reqlang
    reqlang.set_lang("vi")
    s = copilot._system()
    assert "7 NGÀY TỚI" in s and "không được nói nguồn đó 'chưa có'" in s


def test_lua_khong_phai_lua_chay():
    """21/11/2026: "lúa" và "lửa" bỏ dấu đều là "lua" — câu về lúa không được kéo theo mô-đun cháy."""
    assert "wildfire" not in route("Đất này trồng lúa được không?")
    r = route("Ruộng lúa này có bị ngập không?")
    assert "flood" in r and "wildfire" not in r
    assert "wildfire" in route("Khu này có nguy cơ cháy rừng không?")


def test_cau_ket_hien_trang_duoc_ghi_chu():
    from app.services.copilot_route import claims_present_dry
    assert claims_present_dry("Radar thấy 5 đợt. Vì vậy hiện tại đất này không có dấu hiệu ngập.")
    assert claims_present_dry("Radar thấy 5 đợt. Hiện tại ruộng lúa không bị ngập.")
    assert claims_present_dry("The plot is currently not flooded.")
    assert not claims_present_dry("Trong 7 ngày tới ít nguy cơ ngập; radar đã thấy nước phủ thửa 5 đợt.")
    assert not claims_present_dry("Hiện tại radar ghi nhận 5 đợt ngập.")


def test_loi_dan_cau_ket_7_ngay():
    from app.services import copilot, reqlang
    reqlang.set_lang("vi")
    assert "trong 7 ngày tới ít nguy cơ" in copilot._system() and "hiện tại không ngập" in copilot._system()
    reqlang.set_lang("en")
    try:
        assert "next 7 days" in copilot._system()
    finally:
        reqlang.set_lang("vi")


def test_cau_hien_trang_bi_thay_han():
    """PR #37 trên bản chính thức: 3/6 câu vẫn kết "hiện tại không có dấu hiệu ngập" — nay THAY câu đó."""
    from app.services import copilot, reqlang
    reqlang.set_lang("vi")
    s = ("Trong 7 ngày tới, thửa đất này có ít nguy cơ ngập (chỉ số 7.9). Radar Sentinel-1 đã quan sát nước phủ thửa 5 đợt. "
         "Vì vậy, hiện tại không có dấu hiệu ngập, nhưng có tiền sử ngập.")
    out = copilot._han_che(s, "manh dat nay co bi ngap khong", {})
    assert "hiện tại không có dấu hiệu ngập" not in out
    # chỉ bỏ vế "hiện tại không…", giữ vế "có tiền sử ngập" và dòng radar
    assert "Radar Sentinel-1 đã quan sát nước phủ thửa 5 đợt" in out and out.endswith("Có tiền sử ngập.")


def test_chu_han_duoc_hoi_lai(monkeypatch):
    from app.schemas import Location
    from app.services import copilot, llm, passport, reqlang, water_history
    reqlang.set_lang("vi")
    flood = SimpleNamespace(is_real=True, module_name="Cảnh báo lũ/ngập sớm", headline="ít nguy cơ (7.9)",
                            recommendation="Chưa cần hành động", risk_level="safe", score=8, status="ok",
                            forecast=[], confidence=None)
    monkeypatch.setattr("app.modules.registry.get_module", lambda mid: SimpleNamespace(assess=lambda loc: flood))
    monkeypatch.setattr(passport, "history", lambda lat, lon, years=10: None)
    monkeypatch.setattr(water_history, "summary", lambda lat, lon: {"cached": False})
    monkeypatch.setattr(copilot, "_knowledge", lambda q, loc: ([], ""))
    tra = iter(["Ruộng lúa có 5 đợt nước, nhưng這些 không影響當前的預測.", "Ruộng lúa đã có 5 đợt nước phủ theo radar."])
    monkeypatch.setattr(llm, "complete", lambda *a, **k: next(tra))
    a = copilot.answer("Ruộng lúa này có bị ngập không?", Location(lat=20.9716, lon=106.2834))
    assert not copilot._CJK.search(a.answer) and "5 đợt nước phủ" in a.answer


# ---- Kiểm PR #37/#38 trên 9bba22d: câu thay KHÔNG được đảo ngược cảnh báo khi có bão ----

def _lu(level, headline):
    return SimpleNamespace(is_real=True, module_name="Cảnh báo lũ/ngập sớm", headline=headline, risk_level=level,
                           recommendation="Chuẩn bị bơm", score=82, status="ok", forecast=[], confidence=None)


@pytest.mark.parametrize("lang,s,canh", [
    ("vi", "Hiện tại thửa không bị ngập, nhưng trong 7 ngày tới có nguy cơ ngập cao do mưa lớn, nên chuẩn bị bơm và gia "
           "cố bờ.", "Trong 7 ngày tới có nguy cơ ngập cao do mưa lớn, nên chuẩn bị bơm và gia cố bờ."),
    ("vi", "Hiện tại chưa bị ngập; dự báo 7 ngày tới cảnh báo nguy hiểm, chỉ số 82.",
           "Dự báo 7 ngày tới cảnh báo nguy hiểm, chỉ số 82."),
    ("en", "The plot is not currently flooded, but the 7-day forecast shows a HIGH flood risk.",
           "The 7-day forecast shows a HIGH flood risk."),
])
def test_canh_bao_khong_bi_dao_nguoc(lang, s, canh):
    from app.services import copilot, reqlang
    from app.services.copilot_route import claims_present_dry
    reqlang.set_lang(lang)
    try:
        out = copilot._han_che(s, "Ruộng này có bị ngập không?", {"flood": _lu("danger", "Nguy hiểm — chỉ số ngập 82")})
    finally:
        reqlang.set_lang("vi")
    assert "ít nguy cơ" not in out and "low flood risk" not in out.lower() and "risk is low" not in out.lower()
    assert canh in out and not claims_present_dry(out)


def test_cau_thay_dung_theo_du_bao_that():
    from app.services import copilot, reqlang
    reqlang.set_lang("vi")
    out = copilot._han_che("Radar thấy 5 đợt. Vì vậy hiện tại chưa có dấu hiệu ngập.", "co bi ngap khong",
                           {"flood": _lu("danger", "Nguy hiểm — chỉ số ngập 82")})
    assert "Theo dự báo 7 ngày tới: Nguy hiểm — chỉ số ngập 82" in out and "ít nguy cơ" not in out
    out = copilot._han_che("Hiện tại không ngập.", "co bi ngap khong", {})
    assert "TerraTwin không quan sát hiện trạng" in out and "ít nguy cơ" not in out


def test_giu_xuong_dong_va_dong_khong_dau_cham():
    from app.services import copilot, reqlang
    reqlang.set_lang("vi")
    s = ("Rủi ro chính:\n- Radar Sentinel-1 thấy 5 đợt nước phủ thửa\n- Hiện tại không bị ngập\n- Hạn: độ ẩm đủ\n\n"
         "Trong 7 ngày tới cần theo dõi.")
    out = copilot._han_che(s, "Tóm tắt rủi ro", {"flood": _lu("warning", "Cảnh báo — chỉ số ngập 55")})
    dong = out.split("\n")
    assert dong[0] == "Rủi ro chính:" and dong[1] == "- Radar Sentinel-1 thấy 5 đợt nước phủ thửa"
    assert dong[2] == "- Theo dự báo 7 ngày tới: Cảnh báo — chỉ số ngập 55 — đây là dự báo, không phải quan sát hiện trạng của thửa."
    assert dong[3] == "- Hạn: độ ẩm đủ" and out.endswith("Trong 7 ngày tới cần theo dõi.")


def test_radar_da_thay_nuoc_thi_khong_noi_khong_du():
    from app.services import copilot, reqlang
    reqlang.set_lang("vi")
    s = ("Tuy nhiên dữ liệu hiện tại không đủ để khẳng định ruộng lúa đã ngập hay chưa. Vì radar chỉ ghi nhận 5 đợt, nên "
         "không thể kết luận hiện tại ruộng đang ngập.")
    radar = {"available": True, "n_events": 5, "last_event": "2025-10-01"}
    out = copilot._han_che(s, "Ruộng lúa này có bị ngập không?", {}, radar)
    assert "không đủ để khẳng định" not in out
    assert "Thửa đã từng có nước phủ: radar Sentinel-1 thấy 5 đợt, gần nhất 2025-10-01." in out
    assert "không thể kết luận hiện tại ruộng đang ngập" in out          # câu về HIỆN TRẠNG giữ nguyên
    assert copilot._han_che(s, "q", {}, {"available": True, "n_events": 0}) == s


def test_trong_lua_khong_ket_luan_phu_hop():
    from app.services import copilot, reqlang
    from app.services.copilot_route import asks_crop
    reqlang.set_lang("vi")
    out = copilot._han_che("Thửa đất này phù hợp để trồng lúa.", "Đất này trồng lúa được không?", {})
    assert "không cho biết đất có hợp với cây trồng" in out
    assert asks_crop("Can this land grow rice?") and not asks_crop("Can I build a solar plant here?")
    assert not asks_crop("Trong 7 ngày tới có ngập không?")
    s = copilot._system()
    assert "nguy cơ ngập cao" in s and "ĐÃ TỪNG có nước phủ" in s and "'phù hợp' để trồng" in s


def test_thien_tai_khong_phai_hien_tai():
    from app.services.copilot_route import claims_present_dry
    assert not claims_present_dry("Thiên tai không ngập được vùng cao này.")
