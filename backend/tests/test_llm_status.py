"""Chuẩn bị bật LLM (kiểm 18/11/2026): /api/health báo trạng thái trợ lý để kiểm được ngay sau khi đặt khoá — không bao
giờ lộ khoá; mô hình mặc định không được là mô hình đã bị nhà cung cấp tắt."""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_bao_llm_khong_lo_khoa(monkeypatch):
    from app.main import app
    from app.services import llm
    monkeypatch.setenv("TERRATWIN_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("TERRATWIN_LLM_API_KEY", "sk-thu-khong-duoc-lo-123")
    h = TestClient(app).get("/api/health").json()
    l = h["llm"]
    assert (l["available"], l["provider"], l["model"], l["vision"]) == (True, "anthropic", llm._DEFAULT_MODEL["anthropic"], True)
    assert "sk-thu-khong-duoc-lo-123" not in str(h)


def test_health_llm_tat(monkeypatch):
    from app.main import app
    for k in ("TERRATWIN_LLM_PROVIDER", "TERRATWIN_LLM_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY",
              "GOOGLE_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert TestClient(app).get("/api/health").json()["llm"]["available"] is False


def test_mo_hinh_mac_dinh_khong_phai_ban_da_tat():
    from app.services import llm
    assert llm._DEFAULT_MODEL["gemini"] != "gemini-2.0-flash"          # Google tắt từ 1/6/2026
    assert llm._DEFAULT_MODEL["anthropic"] == "claude-haiku-4-5-20251001"


def test_groq_mien_phi_tat_doc_anh(monkeypatch):
    """Cấu hình Groq (chuẩn OpenAI, miễn phí, không có mô hình đọc ảnh): trợ lý bật, đọc ảnh sổ tắt, ảnh không gửi đi."""
    from app.main import app
    from app.services import llm
    for k in ("TERRATWIN_LLM_PROVIDER", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("TERRATWIN_LLM_API_KEY", "gsk-thu")
    monkeypatch.setenv("TERRATWIN_LLM_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("TERRATWIN_LLM_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setenv("TERRATWIN_LLM_VISION", "off")
    i = llm.info()
    assert (i["available"], i["provider"], i["model"], i["vision"]) == (True, "openai", "openai/gpt-oss-120b", False)
    assert i["base_url"] == "https://api.groq.com/openai/v1"
    h = TestClient(app).get("/api/health").json()["llm"]
    assert h["available"] is True and h["vision"] is False and "gsk-thu" not in str(h)


def _fake_urlopen(resp_json, seen):
    import io
    import json as _j

    class R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def f(req, timeout=None):
        seen.append(_j.loads(req.data.decode()))
        return R(_j.dumps(resp_json).encode())
    return f


def test_groq_gpt_oss_gui_reasoning_low_va_du_token(monkeypatch):
    """19/11/2026: gpt-oss-120b là mô hình suy luận — 600 token có thể hết trước khi viết trả lời. Gửi reasoning_effort=low
    và nâng max_tokens; trả lời có chữ thì lần gọi gần nhất ghi ok."""
    from app.services import llm
    monkeypatch.setenv("TERRATWIN_LLM_API_KEY", "gsk-thu")
    monkeypatch.setenv("TERRATWIN_LLM_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("TERRATWIN_LLM_MODEL", "openai/gpt-oss-120b")
    seen: list = []
    monkeypatch.setattr(llm.urllib.request, "urlopen",
                        _fake_urlopen({"choices": [{"message": {"content": "Thửa này ngập 5 đợt."}, "finish_reason": "stop"}]}, seen))
    assert llm.complete("hỏi", system="hệ thống", max_tokens=600) == "Thửa này ngập 5 đợt."
    assert seen[0]["reasoning_effort"] == "low" and seen[0]["max_tokens"] >= 2400
    assert llm.info()["last_call"]["ok"] is True


def test_tra_loi_rong_va_loi_http_duoc_ghi_lai(monkeypatch):
    from app.services import llm
    monkeypatch.setenv("TERRATWIN_LLM_API_KEY", "gsk-thu")
    monkeypatch.setenv("TERRATWIN_LLM_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("TERRATWIN_LLM_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setattr(llm.urllib.request, "urlopen",
                        _fake_urlopen({"choices": [{"message": {"content": ""}, "finish_reason": "length"}]}, []))
    assert llm.complete("hỏi") is None
    last = llm.info()["last_call"]
    assert last["ok"] is False and "length" in last["error"]

    import urllib.error

    def boom(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)
    monkeypatch.setattr(llm.urllib.request, "urlopen", boom)
    assert llm.complete("hỏi") is None
    assert llm.info()["last_call"]["error"].startswith("HTTP 401") and "gsk-thu" not in str(llm.info())


def test_mo_hinh_thuong_khong_bi_them_tham_so(monkeypatch):
    from app.services import llm
    monkeypatch.setenv("TERRATWIN_LLM_API_KEY", "k")
    monkeypatch.setenv("TERRATWIN_LLM_MODEL", "llama-3.3-70b-versatile")
    seen: list = []
    monkeypatch.setattr(llm.urllib.request, "urlopen",
                        _fake_urlopen({"choices": [{"message": {"content": "ok"}}]}, seen))
    llm.complete("hỏi", max_tokens=600)
    assert "reasoning_effort" not in seen[0] and seen[0]["max_tokens"] == 600


def test_gui_user_agent_rieng(monkeypatch):
    """19/11/2026: Groq/Cloudflare chặn User-Agent mặc định 'Python-urllib' (HTTP 403, error code 1010)."""
    from app.services import llm
    monkeypatch.setenv("TERRATWIN_LLM_API_KEY", "gsk-thu")
    monkeypatch.setenv("TERRATWIN_LLM_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("TERRATWIN_LLM_MODEL", "openai/gpt-oss-120b")
    got = {}

    def f(req, timeout=None):
        got["ua"] = req.get_header("User-agent")
        raise OSError("dừng ở đây")
    monkeypatch.setattr(llm.urllib.request, "urlopen", f)
    llm.complete("hỏi")
    assert got["ua"] and "TerraTwin" in got["ua"] and "Python-urllib" not in got["ua"]


def test_doc_anh_dung_mo_hinh_rieng(monkeypatch):
    """19/11/2026 'bật đọc ảnh': trợ lý chữ giữ gpt-oss-120b, ảnh sổ đỏ gửi tới mô hình đọc ảnh riêng."""
    from app.services import llm
    monkeypatch.setenv("TERRATWIN_LLM_API_KEY", "gsk-thu")
    monkeypatch.setenv("TERRATWIN_LLM_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("TERRATWIN_LLM_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setenv("TERRATWIN_LLM_VISION", "on")
    monkeypatch.setenv("TERRATWIN_LLM_VISION_MODEL", "qwen/qwen3.8-27b")
    seen: list = []
    monkeypatch.setattr(llm.urllib.request, "urlopen",
                        _fake_urlopen({"choices": [{"message": {"content": '{"so_thua": "12"}'}}]}, seen))
    assert llm.complete_vision("đọc sổ", "AAAA") is not None
    assert seen[0]["model"] == "qwen/qwen3.8-27b"
    i = llm.info()
    assert i["model"] == "openai/gpt-oss-120b" and i["vision"] is True and i["vision_model"] == "qwen/qwen3.8-27b"


def test_ten_nha_cung_cap_that(monkeypatch):
    """20/11/2026: /privacy phải ghi đích danh "Groq", không chỉ "OpenAI-compatible"."""
    from app.main import app
    from app.services import llm
    for k in ("TERRATWIN_LLM_PROVIDER", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("TERRATWIN_LLM_API_KEY", "gsk-thu")
    monkeypatch.setenv("TERRATWIN_LLM_BASE_URL", "https://api.groq.com/openai/v1")
    assert llm.vendor() == "Groq"
    assert TestClient(app).get("/api/health").json()["llm"]["vendor"] == "Groq"
    monkeypatch.setenv("TERRATWIN_LLM_BASE_URL", "https://llm.vi-du.vn/v1")
    assert llm.vendor() == "llm.vi-du.vn"
    monkeypatch.delenv("TERRATWIN_LLM_API_KEY")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    assert llm.vendor() == "Anthropic (Claude)"
