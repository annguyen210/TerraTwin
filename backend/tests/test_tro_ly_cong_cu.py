"""Nâng cấp 25/11/2026 — trợ lý TỰ GỌI CÔNG CỤ chỉ-đọc (copilot_agent): LLM giả theo kịch bản, không gọi mạng."""
from __future__ import annotations

import json

import pytest

from app.schemas import Assessment, Location
from app.services import copilot, copilot_agent, llm, reqlang

LOC = Location(lat=20.9716, lon=106.2834)

CLIMATE = {"available": True, "scenario": "phát thải cao", "caveats": ["Khí hậu mô phỏng của VÙNG ~55 km."],
           "indicators": [{"id": "tx35", "name": "Ngày nắng nóng ≥ 35 °C", "base_txt": "7 ngày", "future_txt": "19.8 ngày",
                           "change": "+11.3 ngày (3 mô hình: +11.3 đến +16.5)", "trend": "các mô hình cùng chiều"}]}


def _call(name, args=None, cid="c1"):
    return {"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(args or {})}}


class FakeLLM:
    def __init__(self, script):
        self.script, self.seen = list(script), []

    def __call__(self, messages, tools=None, tool_choice="auto", max_tokens=700):
        self.seen.append({"messages": [dict(m) for m in messages], "tool_choice": tool_choice, "tools": tools})
        step = self.script.pop(0)
        return step(messages) if callable(step) else step


@pytest.fixture
def tools_on(monkeypatch):
    reqlang.set_lang("vi")
    monkeypatch.setattr(llm, "tools_available", lambda: True)
    monkeypatch.setattr(copilot_agent, "_run_tool", copilot_agent._run_tool)
    from app.services import climate_2050
    monkeypatch.setattr(climate_2050, "assess", lambda lat, lon: CLIMATE)
    yield
    reqlang.set_lang("vi")


def test_du_du_kien_thi_tra_loi_mot_luot(tools_on, monkeypatch):
    fake = FakeLLM([{"role": "assistant", "content": "Trả lời ngay."}])
    monkeypatch.setattr(llm, "chat", fake)
    r = copilot_agent.run("SYS", "PROMPT", LOC)
    assert r["text"] == "Trả lời ngay." and r["trace"] == [] and len(fake.seen) == 1
    assert fake.seen[0]["tools"] and fake.seen[0]["tool_choice"] == "auto"


def test_goi_cong_cu_khi_hau_roi_tra_loi(tools_on, monkeypatch):
    def final(messages):
        tool_msgs = [m for m in messages if m["role"] == "tool"]
        assert tool_msgs and "+11.3 ngày" in tool_msgs[0]["content"]          # kết quả công cụ tới được LLM
        return {"role": "assistant", "content": "Đến 2050 số ngày nắng nóng tăng khoảng 11.3 ngày mỗi năm."}
    fake = FakeLLM([{"role": "assistant", "content": "", "tool_calls": [_call("khi_hau_2050")]}, final])
    monkeypatch.setattr(llm, "chat", fake)
    r = copilot_agent.run("SYS", "PROMPT", LOC)
    assert "11.3" in r["text"] and r["modules"] == ["climate_2050"]
    assert r["trace"][0]["tool"] == "khi_hau_2050" and r["trace"][0]["ok"] and r["trace"][0]["label"] == "khí hậu 2050"
    assert "+11.3 ngày" in r["context"]


def test_vong_cuoi_khong_cho_goi_them(tools_on, monkeypatch):
    loop = {"role": "assistant", "content": "", "tool_calls": [_call("mua_7_ngay")]}
    fake = FakeLLM([loop, loop, {"role": "assistant", "content": "Xong."}])
    monkeypatch.setattr(llm, "chat", fake)
    from app.services import realdata
    monkeypatch.setattr(realdata, "weather_7d", lambda lat, lon: [{"date": "2026-11-26", "precip": 3.0}])
    r = copilot_agent.run("SYS", "PROMPT", LOC)
    assert r["text"] == "Xong." and [s["tool_choice"] for s in fake.seen] == ["auto", "auto", "none"]
    assert len(r["trace"]) == copilot_agent.MAX_ROUNDS


def test_cong_cu_loi_khong_sap_va_ham_hiem_hoa_la_bi_chan(tools_on, monkeypatch):
    from app.services import water_history

    def boom(lat, lon):
        raise RuntimeError("radar hỏng")
    monkeypatch.setattr(water_history, "summary", boom)
    fake = FakeLLM([{"role": "assistant", "content": "", "tool_calls": [
        _call("lich_su_ngap_radar", cid="a"), _call("danh_gia_hiem_hoa", {"hazard": "rm -rf"}, cid="b")]},
        {"role": "assistant", "content": "Chưa tra được."}])
    monkeypatch.setattr(llm, "chat", fake)
    r = copilot_agent.run("SYS", "PROMPT", LOC)
    assert r["text"] == "Chưa tra được."
    assert [t["ok"] for t in r["trace"]] == [False, True]
    assert "Không có hiểm hoạ" in r["context"]


def test_danh_gia_hiem_hoa_dung_module(tools_on, monkeypatch):
    from app.modules import registry
    a = Assessment(module_id="landslide", module_name="Cảnh báo sạt lở", location=LOC, status="ok", risk_level="low",
                   headline="Độ dốc 2°, nguy cơ thấp", detail="Đồng bằng.", recommendation="Không cần làm gì.", is_real=True)

    class M:
        def assess(self, loc):
            return a
    monkeypatch.setattr(registry, "get_module", lambda mid: M() if mid == "landslide" else None)
    txt, mods, _ = copilot_agent._run_tool("danh_gia_hiem_hoa", {"hazard": "landslide"}, LOC)
    assert "Độ dốc 2°" in txt and "dữ liệu thật" in txt and mods == ["landslide"]


def test_llm_hong_thi_tra_none(tools_on, monkeypatch):
    monkeypatch.setattr(llm, "chat", lambda *a, **k: None)
    assert copilot_agent.run("SYS", "PROMPT", LOC) is None


def test_tat_bang_bien_moi_truong(monkeypatch):
    monkeypatch.setattr(llm, "tools_available", lambda: True)
    monkeypatch.setenv("TERRATWIN_COPILOT_TOOLS", "0")
    assert copilot_agent.enabled() is False
    monkeypatch.setattr(llm, "tools_available", lambda: False)
    monkeypatch.delenv("TERRATWIN_COPILOT_TOOLS")
    assert copilot_agent.enabled() is False


def test_tron_luong_answer_so_tu_cong_cu_khong_bi_che(tools_on, monkeypatch):
    """Số lấy từ KẾT QUẢ CÔNG CỤ (không có trong dữ kiện ban đầu) phải qua được guard; số bịa thì bị che."""
    from app.services import cache_store
    monkeypatch.setattr(cache_store, "get", lambda k: None)
    monkeypatch.setattr(cache_store, "put", lambda *a, **k: None)
    monkeypatch.setattr(copilot, "_history_facts", lambda loc, routes: "")
    monkeypatch.setattr(copilot, "_knowledge", lambda q, loc: ([], ""))
    from app.services import realdata, water_history
    monkeypatch.setattr(realdata, "weather_7d", lambda lat, lon: None)
    monkeypatch.setattr(water_history, "summary", lambda lat, lon: {"available": False})
    fake = FakeLLM([{"role": "assistant", "content": "", "tool_calls": [_call("khi_hau_2050")]},
                    {"role": "assistant", "content": "Đến 2050 thêm khoảng 11.3 ngày nắng nóng, có nơi tới 987 ngày."}])
    monkeypatch.setattr(llm, "chat", fake)
    monkeypatch.setattr(llm, "complete", lambda *a, **k: pytest.fail("không được rơi về một lượt gọi"))
    out = copilot.answer("Đến năm 2050 ở đây nóng hơn bao nhiêu?", LOC)
    assert out.llm and "11.3" in out.answer and "987" not in out.answer
    assert out.tools and out.tools[0]["tool"] == "khi_hau_2050" and "climate_2050" in out.used_modules


def test_cau_hoi_nhieu_nam_tra_loi_tung_nam_khong_qua_llm(monkeypatch):
    reqlang.set_lang("vi")
    from app.services import water_history
    monkeypatch.setattr(water_history, "summary", lambda lat, lon: {
        "available": True, "first": "2017-01-03", "n_scenes": 460,
        "events": [{"start": "2024-09-12", "end": "2024-09-12", "cover": "62%"}]})
    monkeypatch.setattr(llm, "chat", lambda *a, **k: pytest.fail("không được gọi LLM"))
    monkeypatch.setattr(llm, "complete", lambda *a, **k: pytest.fail("không được gọi LLM"))
    out = copilot.answer("Năm 2020 và năm 2024 thửa này có bị nước phủ không?", LOC)
    assert not out.llm and "2020" in out.answer and "12/9/2024" in out.answer
