"""Trợ lý (copilot) — dùng LLM THẬT nếu đã cấu hình, không thì rule-based.

KHÔNG phụ thuộc nhà cung cấp: cắm key của OpenAI, Gemini, DeepSeek, Groq,
OpenRouter, Anthropic, hay máy chủ cục bộ (Ollama) đều chạy — xem services/llm.py.
Chưa có key thì vẫn trả lời được, chỉ là bám sát dữ liệu module thay vì diễn đạt
tự nhiên.
"""
from __future__ import annotations

from app.schemas import CopilotAnswer, Location
from app.services import llm


def _route(question: str) -> list[str]:
    q = (question or "").lower()
    if any(k in q for k in ["mặn", "man"]):
        return ["salinity"]
    if any(k in q for k in ["lũ", "ngập", "lu ", "ngap", "flood"]):
        return ["flood"]
    if any(k in q for k in ["hạn", "han", "tưới", "tuoi", "nước", "nuoc"]):
        return ["drought"]
    if any(k in q for k in ["cháy", "chay", "lửa", "fire"]):
        return ["wildfire"]
    if any(k in q for k in ["mua đất", "mua dat", "đầu tư", "dau tu", "rủi ro", "rui ro"]):
        return ["land_risk"]
    if any(k in q for k in ["điện", "dien", "mặt trời", "mat troi", "solar"]):
        return ["solar"]
    return ["salinity", "drought", "flood"]


_SYSTEM = (
    "Bạn là trợ lý nông nghiệp/đất đai của TerraTwin. Trả lời NGẮN GỌN, rõ ràng "
    "bằng tiếng Việt, CHỈ dựa trên dữ liệu được cung cấp. Tuyệt đối không bịa "
    "thêm số liệu. Nếu dữ liệu không đủ để trả lời, hãy nói thẳng là chưa đủ."
)


def answer(question: str, loc: Location) -> CopilotAnswer:
    from app.modules.registry import get_module
    from app.services import terrascore

    routes = _route(question)
    facts = []
    for r in routes:
        module = get_module(r)
        if module is None:
            continue
        a = module.assess(loc)
        facts.append(f"- {a.module_name}: {a.headline} | Khuyến nghị: {a.recommendation}")
    ts = terrascore.compute(loc)
    facts.append(f"- TerraScore: {ts.score}/100 (hạng {ts.grade}) — {ts.summary}")
    facts_txt = "\n".join(facts)

    prompt = (
        f"Dữ liệu về vị trí ({loc.lat:.4f}, {loc.lon:.4f}):\n{facts_txt}\n\n"
        f"Câu hỏi của người dùng: {question}\n\nTrả lời:"
    )

    text = llm.complete(prompt, system=_SYSTEM, max_tokens=600)
    if text:
        return CopilotAnswer(answer=text, used_modules=routes, llm=True)

    ans = (f"TerraScore {ts.score}/100 (hạng {ts.grade}). {ts.summary}\n{facts_txt}\n\n"
           "[Trợ lý rule-based. Đặt TERRATWIN_LLM_API_KEY (+ TERRATWIN_LLM_BASE_URL "
           "nếu không dùng OpenAI) để bật trả lời bằng LLM — hỗ trợ OpenAI, Gemini, "
           "DeepSeek, Groq, OpenRouter, Anthropic, Ollama…]")
    return CopilotAnswer(answer=ans, used_modules=routes, llm=False)
