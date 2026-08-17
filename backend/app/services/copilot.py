"""Trợ lý (copilot) — gắn LLM THẬT (Anthropic) nếu có ANTHROPIC_API_KEY,
nếu không thì trả lời rule-based (vẫn bám dữ liệu module + TerraScore).

Bật LLM: đặt biến môi trường ANTHROPIC_API_KEY (và tùy chọn ANTHROPIC_MODEL).
"""
from __future__ import annotations

import json
import os
import urllib.request

from app.schemas import CopilotAnswer, Location

_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")


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


def _call_llm(prompt: str):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        body = json.dumps({
            "model": _MODEL,
            "max_tokens": 600,
            "messages": [{"role": "user", "content": prompt}],
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages", data=body,
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read().decode("utf-8"))
        return d["content"][0]["text"]
    except Exception:
        return None


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
        "Bạn là trợ lý nông nghiệp/đất đai của TerraTwin. Trả lời NGẮN GỌN, rõ ràng bằng "
        f"tiếng Việt, CHỈ dựa trên dữ liệu sau về vị trí ({loc.lat:.4f}, {loc.lon:.4f}). "
        "Không bịa thêm số liệu.\n\n"
        f"Dữ liệu hiện có:\n{facts_txt}\n\n"
        f"Câu hỏi của người dùng: {question}\n\nTrả lời:"
    )

    llm = _call_llm(prompt)
    if llm:
        return CopilotAnswer(answer=llm.strip(), used_modules=routes, llm=True)

    ans = (f"TerraScore {ts.score}/100 (hạng {ts.grade}). {ts.summary}\n{facts_txt}\n\n"
           "[Đang dùng trợ lý rule-based. Đặt ANTHROPIC_API_KEY để bật trả lời bằng LLM thật.]")
    return CopilotAnswer(answer=ans, used_modules=routes, llm=False)
