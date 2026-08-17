"""Lớp LLM KHÔNG phụ thuộc nhà cung cấp — cắm key nào cũng chạy.

Trước đây copilot gắn cứng vào Anthropic. Nay hỗ trợ ba giao thức, phủ gần như
mọi nhà cung cấp phổ biến:

  1. openai   — chuẩn /v1/chat/completions. Dùng được cho OpenAI, DeepSeek,
                Groq, Together, OpenRouter, xAI, Qwen, Mistral, Ollama, LM
                Studio, vLLM... chỉ cần đổi TERRATWIN_LLM_BASE_URL.
  2. gemini   — Google Generative Language API (v1beta:generateContent).
  3. anthropic— /v1/messages.

Cấu hình (xem .env.example):
  TERRATWIN_LLM_PROVIDER  auto | openai | gemini | anthropic | off
  TERRATWIN_LLM_API_KEY   khóa API
  TERRATWIN_LLM_BASE_URL  gốc URL (chỉ cần cho openai-compatible ngoài OpenAI)
  TERRATWIN_LLM_MODEL     tên model

`auto` tự dò theo khóa nào đang có, nên người dùng chỉ cần đặt đúng một biến.
Các biến cũ (ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY) vẫn dùng được.

NGUYÊN TẮC: hàm complete() KHÔNG BAO GIỜ ném lỗi. Trả None khi hỏng để bên gọi
tự lùi về rule-based — trợ lý mất chữ còn hơn cả trang web sập.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

TIMEOUT = 30.0

# Gốc URL mặc định cho các nhà cung cấp openai-compatible phổ biến,
# để người dùng chỉ cần dán khóa mà không phải tra URL.
KNOWN_BASES = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "together": "https://api.together.xyz/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "xai": "https://api.x.ai/v1",
    "mistral": "https://api.mistral.ai/v1",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "ollama": "http://localhost:11434/v1",
}

_DEFAULT_MODEL = {
    "openai": "gpt-4o-mini",
    "gemini": "gemini-2.0-flash",
    "anthropic": "claude-haiku-4-5-20251001",
}


def _env(*names: str) -> str | None:
    for n in names:
        v = os.environ.get(n)
        if v and v.strip():
            return v.strip()
    return None


def _detect() -> tuple[str | None, str | None, str | None, str | None]:
    """(provider, api_key, base_url, model). provider=None ⇒ chưa cấu hình."""
    provider = (_env("TERRATWIN_LLM_PROVIDER") or "auto").lower()
    if provider == "off":
        return None, None, None, None

    key = _env("TERRATWIN_LLM_API_KEY")
    base = _env("TERRATWIN_LLM_BASE_URL")
    model = _env("TERRATWIN_LLM_MODEL")

    if provider == "auto":
        if key:
            # Có khóa chung nhưng chưa nói rõ giao thức → mặc định openai-compatible,
            # vì đó là chuẩn được nhiều nhà cung cấp hỗ trợ nhất.
            provider = "openai"
        elif _env("ANTHROPIC_API_KEY"):
            provider, key = "anthropic", _env("ANTHROPIC_API_KEY")
        elif _env("GEMINI_API_KEY", "GOOGLE_API_KEY"):
            provider, key = "gemini", _env("GEMINI_API_KEY", "GOOGLE_API_KEY")
        elif _env("OPENAI_API_KEY"):
            provider, key = "openai", _env("OPENAI_API_KEY")
        else:
            return None, None, None, None
    else:
        key = key or {
            "anthropic": _env("ANTHROPIC_API_KEY"),
            "gemini": _env("GEMINI_API_KEY", "GOOGLE_API_KEY"),
            "openai": _env("OPENAI_API_KEY"),
        }.get(provider)

    if provider not in ("openai", "gemini", "anthropic"):
        return None, None, None, None
    # Ollama và các máy chủ cục bộ không cần khóa.
    if not key and not (base and "localhost" in base):
        return None, None, None, None

    if provider == "openai" and not base:
        base = KNOWN_BASES["openai"]
    if base:
        base = base.rstrip("/")

    model = model or _env("ANTHROPIC_MODEL") or _DEFAULT_MODEL[provider]
    return provider, key, base, model


def info() -> dict:
    """Mô tả cấu hình hiện tại — KHÔNG bao giờ trả về khóa."""
    provider, key, base, model = _detect()
    return {
        "available": provider is not None,
        "provider": provider,
        "model": model,
        "base_url": base,
        "key_source": "đã cấu hình" if key else ("máy chủ cục bộ" if base else None),
    }


def available() -> bool:
    return _detect()[0] is not None


def _post(url: str, payload: dict, headers: dict) -> dict | None:
    try:
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"),
            headers={"content-type": "application/json", **headers})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def _dig(d, *path):
    """Lấy giá trị lồng nhau, trả None nếu thiếu bất kỳ mắt xích nào."""
    for p in path:
        if d is None:
            return None
        d = d[p] if isinstance(p, int) and isinstance(d, list) and len(d) > p \
            else (d.get(p) if isinstance(d, dict) else None)
    return d


def complete(prompt: str, system: str | None = None,
             max_tokens: int = 600) -> str | None:
    """Gọi LLM. Trả văn bản, hoặc None nếu chưa cấu hình / lỗi mạng / hỏng."""
    provider, key, base, model = _detect()
    if provider is None:
        return None

    if provider == "openai":
        msgs = ([{"role": "system", "content": system}] if system else []) + \
               [{"role": "user", "content": prompt}]
        d = _post(f"{base}/chat/completions",
                  {"model": model, "messages": msgs, "max_tokens": max_tokens},
                  {"Authorization": f"Bearer {key}"} if key else {})
        text = _dig(d, "choices", 0, "message", "content")

    elif provider == "gemini":
        body: dict = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max_tokens},
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        d = _post(
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={key}", body, {})
        text = _dig(d, "candidates", 0, "content", "parts", 0, "text")

    else:  # anthropic
        body = {"model": model, "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}]}
        if system:
            body["system"] = system
        d = _post("https://api.anthropic.com/v1/messages", body,
                  {"x-api-key": key, "anthropic-version": "2023-06-01"})
        text = _dig(d, "content", 0, "text")

    if isinstance(text, str) and text.strip():
        return text.strip()
    return None
