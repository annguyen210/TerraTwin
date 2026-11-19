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
import logging
import os
import urllib.error
import urllib.request

TIMEOUT = 30.0
UA = "TerraTwin/1.0 (+https://terratwin-web.vercel.app)"

# Kiểm 19/11/2026: bật Groq (openai/gpt-oss-120b) xong, trợ lý vẫn trả lời theo luật — _post nuốt mọi lỗi nên không ai biết
# vì sao. Giữ lại kết quả lần gọi GẦN NHẤT (giờ, thành/bại, lỗi rút gọn; KHÔNG BAO GIỜ có khoá) để /api/health hiện ra.
_LAST: dict = {}
log = logging.getLogger("terratwin.llm")


def _note(ok: bool, error: str | None = None) -> None:
    from datetime import datetime, timezone
    _LAST.clear()
    _LAST.update({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "ok": ok, "error": error})
    if not ok:
        log.warning("LLM call failed: %s", error)


def _reasoning(model: str | None) -> bool:
    """Mô hình "suy luận" (gpt-oss, o-series, R1…): token suy nghĩ tính chung với max_tokens — 600 token có thể hết trước
    khi viết được chữ trả lời nào, nội dung rỗng → trợ lý lặng lẽ rơi về luật viết sẵn."""
    m = (model or "").lower().split("/")[-1]
    return "gpt-oss" in m or m.startswith(("o1", "o3", "o4")) or "deepseek-r1" in m

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
    # 18/11/2026: gemini-2.0-flash đã TẮT từ 1/6/2026 (aistudio.google.com/docs/deprecations); 3.8-flash là bản Flash
    # ổn định hiện hành, nhận cả ảnh (đọc sổ đỏ). claude-haiku-4-5-20251001 vẫn là mã hiện hành.
    "gemini": "gemini-3.8-flash",
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
        "vision": vision_available(),
        "last_call": dict(_LAST) or None,
    }


def available() -> bool:
    return _detect()[0] is not None


def vision_available() -> bool:
    """Đọc ẢNH (sổ đỏ) bằng LLM. TERRATWIN_LLM_VISION=off tắt riêng phần này (18/11/2026): nhà cung cấp miễn phí như Groq
    không có mô hình đọc ảnh, và chủ dự án có thể không muốn ảnh sổ đỏ (tên chủ, số giấy tờ) đi lên gói miễn phí."""
    return available() and (_env("TERRATWIN_LLM_VISION") or "on").strip().lower() not in ("off", "0", "false", "no", "tat", "tắt")


def _post(url: str, payload: dict, headers: dict) -> dict | None:
    try:
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"),
            # 19/11/2026: Groq (sau Cloudflare) trả "HTTP 403: error code: 1010" cho User-Agent mặc định "Python-urllib/…"
            # — chặn theo chữ ký trình duyệt. Tự xưng rõ tên ứng dụng thì qua.
            headers={"content-type": "application/json", "user-agent": UA, **headers})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", "replace")[:240]
        except Exception:
            body = ""
        _note(False, f"HTTP {e.code}: {body}")
        return None
    except Exception as e:
        _note(False, f"{type(e).__name__}: {str(e)[:160]}")
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
        payload: dict = {"model": model, "messages": msgs, "max_tokens": max_tokens}
        if _reasoning(model):
            payload.update({"max_tokens": max(max_tokens * 4, 2400), "reasoning_effort": "low"})
        d = _post(f"{base}/chat/completions", payload, {"Authorization": f"Bearer {key}"} if key else {})
        text = _dig(d, "choices", 0, "message", "content")
        if d is not None and not (text or "").strip():
            _note(False, f"trả lời rỗng (finish_reason={_dig(d, 'choices', 0, 'finish_reason')})")

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
        _note(True)
        return text.strip()
    return None


def complete_vision(prompt: str, image_b64: str, media_type: str = "image/jpeg",
                    system: str | None = None, max_tokens: int = 900) -> str | None:
    """Gọi LLM ĐA PHƯƠNG THỨC với một ảnh (đọc giấy tờ). Cùng nguyên tắc với
    complete(): không bao giờ ném lỗi, trả None khi chưa cấu hình / hỏng — bên gọi
    lùi về nhập tay. Model văn bản thuần không đọc được ảnh thì cũng trả None."""
    provider, key, base, model = _detect()
    if provider is None:
        return None
    if provider == "openai":
        msgs = ([{"role": "system", "content": system}] if system else []) + [{
            "role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{image_b64}"}}]}]
        d = _post(f"{base}/chat/completions", {"model": model, "messages": msgs, "max_tokens": max_tokens},
                  {"Authorization": f"Bearer {key}"} if key else {})
        text = _dig(d, "choices", 0, "message", "content")
    elif provider == "gemini":
        body: dict = {"contents": [{"role": "user", "parts": [
            {"text": prompt}, {"inline_data": {"mime_type": media_type, "data": image_b64}}]}],
            "generationConfig": {"maxOutputTokens": max_tokens}}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        d = _post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
                  body, {})
        text = _dig(d, "candidates", 0, "content", "parts", 0, "text")
    else:  # anthropic
        body = {"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
            {"type": "text", "text": prompt}]}]}
        if system:
            body["system"] = system
        d = _post("https://api.anthropic.com/v1/messages", body,
                  {"x-api-key": key, "anthropic-version": "2023-06-01"})
        text = _dig(d, "content", 0, "text")
    if isinstance(text, str) and text.strip():
        _note(True)
        return text.strip()
    return None
