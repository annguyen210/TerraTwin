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
