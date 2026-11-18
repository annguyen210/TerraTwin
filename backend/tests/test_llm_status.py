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
    assert h["llm"] == {"available": True, "provider": "anthropic", "model": llm._DEFAULT_MODEL["anthropic"], "vision": True}
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
