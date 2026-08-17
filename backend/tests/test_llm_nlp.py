"""Lớp LLM không phụ thuộc nhà cung cấp + C03 What-If NLP.

Điểm quan trọng nhất được test ở đây: LLM chỉ được DỊCH câu hỏi thành tham số.
Mọi con số phải do mô hình vật lý tính. Nếu ranh giới đó vỡ, phần mềm quay lại
đúng bệnh "AI bịa số" mà cả dự án đã mất nhiều đợt để dọn.
"""
from __future__ import annotations

import pytest

from app.services import hazard, llm, realdata, whatif_nlp

LAT, LON = 15.87, 108.33
ENV_VARS = [
    "TERRATWIN_LLM_PROVIDER", "TERRATWIN_LLM_API_KEY",
    "TERRATWIN_LLM_BASE_URL", "TERRATWIN_LLM_MODEL",
    "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL",
    "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
]


@pytest.fixture
def clean_env(monkeypatch):
    for v in ENV_VARS:
        monkeypatch.delenv(v, raising=False)


def _rows(precip=20.0):
    return [{"day": i, "date": f"2026-08-{17+i:02d}",
             "precip": precip, "et0": 4.0, "tmax": 33.0} for i in range(7)]


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(realdata, "elevation_m", lambda la, lo: 3.0)
    monkeypatch.setattr(realdata, "slope_deg", lambda la, lo, step_m=500.0: 20.0)
    monkeypatch.setattr(realdata, "weather_7d", lambda la, lo: _rows())
    monkeypatch.setattr(realdata, "historical_weather", lambda *a: None)


# ---------- Dò cấu hình nhà cung cấp ----------

def test_no_key_means_unavailable(clean_env):
    assert llm.available() is False
    assert llm.complete("xin chào") is None


def test_generic_key_defaults_to_openai_compatible(clean_env, monkeypatch):
    monkeypatch.setenv("TERRATWIN_LLM_API_KEY", "sk-test")
    i = llm.info()
    assert i["available"] and i["provider"] == "openai"
    assert i["base_url"].endswith("/v1")


def test_custom_base_url_for_other_providers(clean_env, monkeypatch):
    monkeypatch.setenv("TERRATWIN_LLM_API_KEY", "sk-test")
    monkeypatch.setenv("TERRATWIN_LLM_BASE_URL", "https://api.deepseek.com/v1/")
    monkeypatch.setenv("TERRATWIN_LLM_MODEL", "deepseek-chat")
    i = llm.info()
    assert i["base_url"] == "https://api.deepseek.com/v1"      # bỏ dấu / cuối
    assert i["model"] == "deepseek-chat"


@pytest.mark.parametrize("env,expected", [
    ("ANTHROPIC_API_KEY", "anthropic"),
    ("GEMINI_API_KEY", "gemini"),
    ("OPENAI_API_KEY", "openai"),
])
def test_auto_detects_each_legacy_key(clean_env, monkeypatch, env, expected):
    monkeypatch.setenv(env, "k")
    assert llm.info()["provider"] == expected


def test_local_server_needs_no_key(clean_env, monkeypatch):
    monkeypatch.setenv("TERRATWIN_LLM_PROVIDER", "openai")
    monkeypatch.setenv("TERRATWIN_LLM_BASE_URL", "http://localhost:11434/v1")
    assert llm.available() is True


def test_off_switch_wins_over_keys(clean_env, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("TERRATWIN_LLM_PROVIDER", "off")
    assert llm.available() is False


def test_info_never_leaks_the_key(clean_env, monkeypatch):
    monkeypatch.setenv("TERRATWIN_LLM_API_KEY", "sk-bi-mat-tuyet-doi")
    assert "sk-bi-mat-tuyet-doi" not in str(llm.info())


def test_network_failure_returns_none_not_exception(clean_env, monkeypatch):
    monkeypatch.setenv("TERRATWIN_LLM_API_KEY", "sk-test")
    monkeypatch.setattr(llm, "_post", lambda *a, **k: None)
    assert llm.complete("xin chào") is None      # không được ném lỗi


def test_malformed_response_returns_none(clean_env, monkeypatch):
    monkeypatch.setenv("TERRATWIN_LLM_API_KEY", "sk-test")
    monkeypatch.setattr(llm, "_post", lambda *a, **k: {"rác": True})
    assert llm.complete("xin chào") is None


# ---------- Bộ luật tiếng Việt (không cần key) ----------

@pytest.mark.parametrize("q,mult", [
    ("nếu mưa gấp đôi thì sao", 2.0),
    ("neu mua gap doi thi sao", 2.0),          # không dấu
    ("mưa gấp 3 lần", 3.0),
    ("mưa tăng 50%", 1.5),
    ("mưa giảm 60%", 0.4),
    ("nếu không mưa nữa", 0.0),
    ("mưa rất to thì sao", 2.0),
])
def test_rules_parse_rain(q, mult):
    assert whatif_nlp.parse_rules(q)["rain_mult"] == pytest.approx(mult, abs=0.01)


@pytest.mark.parametrize("q,temp", [
    ("nóng thêm 3 độ", 3.0),
    ("lạnh đi 2 độ", -2.0),
    ("nắng nóng hơn", 2.0),
])
def test_rules_parse_temperature(q, temp):
    assert whatif_nlp.parse_rules(q)["temp_delta"] == pytest.approx(temp)


def test_rules_return_none_when_nothing_matches():
    assert whatif_nlp.parse_rules("hôm nay trời thế nào") is None


@pytest.mark.parametrize("q,mid", [
    ("mưa gấp đôi có ngập không", "flood"),
    ("mưa giảm 70% thì hạn thế nào", "drought"),
    ("nóng thêm 5 độ có cháy rừng không", "wildfire"),
    ("mưa gấp đôi có sạt lở không", "landslide"),
])
def test_module_detected_from_question(offline, q, mid):
    assert whatif_nlp.ask(q, LAT, LON)["module_id"] == mid


# ---------- Ranh giới quan trọng nhất ----------

def test_numbers_come_from_the_model_not_the_llm(offline, clean_env):
    """Con số trả về phải TRÙNG KHỚP kết quả chạy trực tiếp mô hình vật lý."""
    r = whatif_nlp.ask("nếu mưa gấp đôi thì có ngập không", LAT, LON)
    expected = hazard.peak_of(hazard.index_series(
        "flood", LAT, LON, hazard.transform(_rows(), rain_mult=2.0)))
    assert r["scenario_peak"] == pytest.approx(round(expected, 1), abs=0.11)


def test_lying_llm_cannot_inject_a_number(offline, clean_env, monkeypatch):
    """LLM trả về tham số kèm 'kết quả' bịa — kết quả đó phải bị bỏ qua."""
    monkeypatch.setenv("TERRATWIN_LLM_API_KEY", "sk-test")
    monkeypatch.setattr(
        llm, "complete",
        lambda *a, **k: '{"module":"flood","rain_mult":2.0,"temp_delta":0,'
                        '"scenario_peak":999,"risk_level":"danger"}')
    r = whatif_nlp.ask("câu hỏi tự do không khớp luật nào", LAT, LON)
    assert r["scenario_peak"] != 999
    expected = hazard.peak_of(hazard.index_series(
        "flood", LAT, LON, hazard.transform(_rows(), rain_mult=2.0)))
    assert r["scenario_peak"] == pytest.approx(round(expected, 1), abs=0.11)


def test_absurd_llm_parameters_are_clamped(offline, clean_env, monkeypatch):
    monkeypatch.setenv("TERRATWIN_LLM_API_KEY", "sk-test")
    monkeypatch.setattr(
        llm, "complete",
        lambda *a, **k: '{"module":"flood","rain_mult":99999,"temp_delta":500}')
    r = whatif_nlp.ask("câu hỏi tự do không khớp luật nào", LAT, LON)
    assert r["rain_mult"] <= 10.0 and r["temp_delta"] <= 15.0


def test_llm_garbage_output_is_survived(offline, clean_env, monkeypatch):
    monkeypatch.setenv("TERRATWIN_LLM_API_KEY", "sk-test")
    monkeypatch.setattr(llm, "complete", lambda *a, **k: "xin lỗi tôi không biết")
    r = whatif_nlp.ask("câu hỏi tự do không khớp luật nào", LAT, LON)
    assert r["understood"] is False and "Thử diễn đạt" in r["message"]


def test_llm_json_in_markdown_fence_is_parsed(offline, clean_env, monkeypatch):
    monkeypatch.setenv("TERRATWIN_LLM_API_KEY", "sk-test")
    monkeypatch.setattr(
        llm, "complete",
        lambda *a, **k: '```json\n{"module":"flood","rain_mult":1.5,"temp_delta":0}\n```')
    r = whatif_nlp.ask("câu hỏi tự do không khớp luật nào", LAT, LON)
    assert r["understood"] and r["rain_mult"] == pytest.approx(1.5)


# ---------- Hoạt động không cần LLM ----------

def test_works_with_no_llm_configured(offline, clean_env):
    r = whatif_nlp.ask("nếu mưa gấp đôi thì có ngập không", LAT, LON)
    assert r["understood"] and r["available"]
    assert r["parsed_by"] == "rule" and r["llm_available"] is False


def test_refuses_to_simulate_without_real_weather(clean_env, monkeypatch):
    monkeypatch.setattr(realdata, "weather_7d", lambda la, lo: None)
    monkeypatch.setattr(realdata, "elevation_m", lambda la, lo: 3.0)
    r = whatif_nlp.ask("mưa gấp đôi thì sao", LAT, LON)
    assert r["understood"] is True and r["available"] is False
