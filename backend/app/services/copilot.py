"""Trợ lý (copilot) — dùng LLM THẬT nếu đã cấu hình, không thì rule-based.

KHÔNG phụ thuộc nhà cung cấp: cắm key của OpenAI, Gemini, DeepSeek, Groq,
OpenRouter, Anthropic, hay máy chủ cục bộ (Ollama) đều chạy — xem services/llm.py.
Chưa có key thì vẫn trả lời được, chỉ là bám sát dữ liệu module thay vì diễn đạt
tự nhiên.
"""
from __future__ import annotations

from app.schemas import CopilotAnswer, KnowledgeCitation, Location
from app.services import llm

# Số ghi chép thực địa tối đa nạp vào ngữ cảnh. Giữ nhỏ có chủ đích: nhồi 20
# mẩu kinh nghiệm vào prompt làm loãng chính dữ liệu đo được, mà dữ liệu đo
# được mới là thứ kiểm chứng được.
_RAG_K = 3
_RAG_MIN_SIMILARITY = 35.0
NL = "\n"
KNOW_HEAD = ("Kinh nghiệm thực địa từ vùng có bộ gen đất tương đồng (do người "
             "dùng khác chia sẻ, KHÔNG phải số đo — nói rõ điều đó nếu dùng tới):")


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


# Từ quá phổ biến trong tiếng Việt, xuất hiện ở mọi ghi chép nên không phân
# biệt được gì. Bỏ đi để một ghi chép không "khớp" chỉ vì có chữ "của".
_STOP = {
    "cua", "va", "la", "co", "khong", "cho", "voi", "thi", "ma", "nhung",
    "duoc", "nay", "do", "cac", "nhu", "de", "tu", "o", "den", "ra", "vao",
    "toi", "ban", "minh", "roi", "se", "da", "rat", "hon", "nhieu", "it",
    "nen", "vi", "sao", "gi", "the", "nao", "bao", "nhieu", "mot", "hai",
}


def _tokens(text: str) -> set[str]:
    from app.services.whatif_nlp import _norm
    raw = _norm(text or "").replace("/", " ").replace("-", " ")
    out = set()
    for w in raw.split():
        w = "".join(c for c in w if c.isalnum())
        if len(w) >= 2 and w not in _STOP:
            out.add(w)
    return out


def _relevance(question: str, note) -> int:
    """Ghi chép này có nói về đúng thứ đang được hỏi không.

    Chấm bằng số từ trùng nhau sau khi bỏ dấu — nông dân gõ không dấu rất
    nhiều, nên "man" phải khớp được với "mặn". Tiêu đề và chủ đề tính nặng hơn
    thân bài vì chúng cô đọng hơn.

    Cố ý KHÔNG dùng embedding: nó cần một lời gọi API cho mỗi ghi chép, tốn
    tiền và làm chậm, trong khi kho hiện có vài chục mẩu và trùng từ đã đủ để
    loại thứ lạc đề. Khi kho lên hàng nghìn mẩu thì hãy đổi — không phải trước.
    """
    q = _tokens(question)
    if not q:
        return 0
    title = _tokens(getattr(note, "title", ""))
    topic = _tokens(getattr(note, "topic", ""))
    body = _tokens(getattr(note, "body", ""))
    return (3 * len(q & topic) + 2 * len(q & title) + len(q & body))


def _knowledge(question: str, loc: Location) -> tuple[list[KnowledgeCitation], str]:
    """Lấy kinh nghiệm thực địa từ vùng có BỘ GEN ĐẤT giống nơi đang hỏi.

    Đây là phần "kho tri thức ngành" của RAG. Ghép theo bộ gen chứ không theo
    khoảng cách, vì một hộ cách 200 km nhưng cùng cao độ, chế độ mưa và mức mặn
    cho kinh nghiệm dùng được ngay, còn hộ cách 20 km trên đồi thì không.

    Lỗi ở đây (chưa có database, chưa dựng được lưới gen, mất mạng) KHÔNG được
    làm hỏng câu trả lời: kinh nghiệm là phần bổ sung, dữ liệu đo được mới là
    phần chính. Vì vậy mọi lỗi đều nuốt và trả về rỗng.
    """
    try:
        from sqlalchemy import select

        from app import db as _db
        from app.db import KnowledgeNote
        from app.services import datasources as ds
        from app.services import genome

        session = _db.SessionLocal()
        try:
            notes = session.execute(select(KnowledgeNote)).scalars().all()
            if not notes:
                return [], ""

            mine = genome.genome_of(loc.lat, loc.lon)
            ref = genome.build_reference() if mine is not None else None
            stats = ref["stats"] if ref and ref.get("cells") else None

            scored = []
            for n in notes:
                sim = None
                if mine is not None and stats is not None:
                    try:
                        theirs = genome.genome_of(n.lat, n.lon)
                        if theirs is not None:
                            d = genome._distance(mine, theirs, stats)
                            sim = round(100.0 / (1.0 + d), 1)
                    except Exception:
                        sim = None
                km = ds._haversine_km(loc.lat, loc.lon, n.lat, n.lon)
                if sim is None:
                    sim = round(max(0.0, 100.0 - km / 10.0), 1)
                if sim >= _RAG_MIN_SIMILARITY:
                    scored.append((sim, km, n))

            # Xếp theo CẢ hai: giống về đất, VÀ đúng thứ đang được hỏi.
            #
            # Chỉ xếp theo bộ gen là bug thật đã có: hỏi về lũ vẫn có thể được
            # nạp một ghi chép về cà phê, chỉ vì nó ở vùng cùng bộ gen. Đưa văn
            # bản lạc đề vào prompt làm loãng chính dữ liệu đo được — thứ duy
            # nhất kiểm chứng được trong câu trả lời.
            rel = {id(n): _relevance(question, n) for _, _, n in scored}
            has_relevant = any(v > 0 for v in rel.values())
            if has_relevant:
                scored = [t for t in scored if rel[id(t[2])] > 0]
            scored.sort(key=lambda t: (rel[id(t[2])], t[0]), reverse=True)
            top = scored[:_RAG_K]
            if not top:
                return [], ""

            cites = [
                KnowledgeCitation(id=n.id, title=n.title,
                                  author_name=n.author_name,
                                  similarity_pct=sim, distance_km=round(km, 0))
                for sim, km, n in top
            ]
            lines = [f"- [{n.author_name}, vùng tương đồng {sim}%] {n.title}: "
                     f"{n.body[:400]}" for sim, _, n in top]
            return cites, "\n".join(lines)
        finally:
            session.close()
    except Exception:
        return [], ""


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

    cites, know_txt = _knowledge(question, loc)
    know_block = ((NL + NL + KNOW_HEAD + NL + know_txt) if know_txt else '')

    prompt = (
        f"Dữ liệu về vị trí ({loc.lat:.4f}, {loc.lon:.4f}):\n{facts_txt}{know_block}\n\n"
        f"Câu hỏi của người dùng: {question}\n\nTrả lời:"
    )

    text = llm.complete(prompt, system=_SYSTEM, max_tokens=600)
    if text:
        return CopilotAnswer(answer=text, used_modules=routes,
                             llm=True, knowledge_used=cites)

    ans = (f"TerraScore {ts.score}/100 (hạng {ts.grade}). {ts.summary}\n{facts_txt}"
           f"{know_block}\n\n"
           "[Trợ lý rule-based. Đặt TERRATWIN_LLM_API_KEY để bật trả lời bằng LLM. "
           "Nhà cung cấp openai-compatible (DeepSeek, Groq, OpenRouter, Together, "
           "xAI, Qwen, Ollama) chỉ cần thêm TERRATWIN_LLM_BASE_URL. Gemini hoặc "
           "Anthropic PHẢI đặt thêm TERRATWIN_LLM_PROVIDER=gemini|anthropic — "
           "thiếu biến đó thì khóa bị gửi sai giao thức và im lặng không chạy.]")
    return CopilotAnswer(answer=ans, used_modules=routes, llm=False,
                         knowledge_used=cites)
