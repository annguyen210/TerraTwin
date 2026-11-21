"""Trợ lý (copilot) — dùng LLM THẬT nếu đã cấu hình, không thì rule-based.

KHÔNG phụ thuộc nhà cung cấp: cắm key của OpenAI, Gemini, DeepSeek, Groq,
OpenRouter, Anthropic, hay máy chủ cục bộ (Ollama) đều chạy — xem services/llm.py.
Chưa có key thì vẫn trả lời được, chỉ là bám sát dữ liệu module thay vì diễn đạt
tự nhiên.
"""
from __future__ import annotations

from app.schemas import Assessment, CopilotAnswer, KnowledgeCitation, Location
from app.services import llm
from app.services import reqlang
from app.services.reqlang import tr

# Số ghi chép thực địa tối đa nạp vào ngữ cảnh. Giữ nhỏ có chủ đích: nhồi 20
# mẩu kinh nghiệm vào prompt làm loãng chính dữ liệu đo được, mà dữ liệu đo
# được mới là thứ kiểm chứng được.
_RAG_K = 3
_RAG_MIN_SIMILARITY = 35.0
NL = "\n"


def _know_head() -> str:
    return tr(
        "Kinh nghiệm thực địa từ vùng có bộ gen đất tương đồng (do người "
        "dùng khác chia sẻ, KHÔNG phải số đo — nói rõ điều đó nếu dùng tới):",
        "Field experience from areas with a similar soil genome (shared by "
        "other users, NOT a measurement — say so if you use it):",
    )


def _route(question: str) -> list[str]:
    # Kiểm 21/11/2026: bản cũ so chuỗi con, dừng ở luật đầu tiên ("manh" → mặn) — nay so theo từ, xét mọi hiểm hoạ.
    from app.services.copilot_route import route
    return route(question)


# Kiểm 21/11/2026: ở chế độ tiếng Việt, gpt-oss-120b thỉnh thoảng chen "additionally". Thay các từ nối tiếng Anh hay gặp —
# chỉ từ nối đứng riêng (ranh giới từ), không đụng tên riêng.
_EN_NOI = {"additionally": "ngoài ra", "in addition": "ngoài ra", "however": "tuy nhiên", "therefore": "vì vậy",
           "moreover": "hơn nữa", "furthermore": "hơn nữa", "overall": "nhìn chung", "meanwhile": "trong khi đó"}


def _viet_hoa(text: str) -> str:
    import re
    for en, vi in _EN_NOI.items():
        text = re.sub(r"(?i)\b" + re.escape(en) + r"\b", lambda m, vi=vi: vi.capitalize() if m.group(0)[0].isupper() else vi, text)
    return text


import re as _re

_CJK = _re.compile(r"[぀-ヿ㐀-䶿一-鿿豈-﫿가-힯　-〿＀-￯]+")


def _cau_du_bao(assessed: dict) -> str:
    """Câu dự báo ngập dựng TỪ dữ liệu thật của lượt này — KHÔNG viết cứng mức nguy cơ (kiểm 21/11/2026: câu cố định "ít
    nguy cơ" sẽ đảo ngược cảnh báo khi có bão)."""
    a = assessed.get("flood")
    h = str(getattr(a, "headline", "") or "").strip().rstrip(".")
    if h:
        return tr(f"Theo dự báo 7 ngày tới: {h} — đây là dự báo, không phải quan sát hiện trạng của thửa.",
                  f"Per the 7-day forecast: {h} — this is a forecast, not an observation of the plot now.")
    return tr("TerraTwin không quan sát hiện trạng của thửa, chỉ có dự báo 7 ngày tới.",
              "TerraTwin does not observe the plot's present state; it only has a 7-day forecast.")


def _han_che(text: str, question: str, assessed: dict, radar: dict | None = None) -> str:
    """Lớp chặn bằng code (kiểm 21/11/2026): "Will this land get salty in the dry season?" → LLM khẳng định "not expected
    to become salty in the upcoming dry season" từ một số mặn is_real=False (ước lượng chưa hiệu chỉnh, chỉ 7 ngày).
    Có mô-đun ước lượng mà câu trả lời không nói "ước lượng"/"estimate", hoặc câu hỏi về mùa/tháng/năm tới → tự thêm ghi chú."""
    import re
    from app.services.copilot_route import (_words, asks_crop, asks_long_range, claims_present_dry, doubts_past_water,
                                            strip_present_dry)
    # Kiểm PR #37/#38: lời dặn không đủ — LLM vẫn kết "hiện tại không có dấu hiệu ngập". Bỏ ĐÚNG vế đó, giữ vế cảnh báo;
    # không còn gì thì thay bằng câu dự báo dựng từ assessed["flood"]. Tách theo câu VÀ theo xuống dòng, GIỮ nguyên dấu
    # phân cách — trước đây " ".join làm gạch đầu dòng dính thành một đoạn, và dòng không có dấu chấm bị gộp rồi bị thay.
    n_radar = int((radar or {}).get("n_events") or 0)
    sua = False
    phan = re.split(r"(\n+|(?<=[.!?])[ \t]+)", text)
    for i in range(0, len(phan), 2):
        c = phan[i]
        if claims_present_dry(c):
            phan[i] = strip_present_dry(c, _cau_du_bao(assessed))
            sua = True
        elif n_radar and doubts_past_water(c):
            last = (radar or {}).get("last_event")
            phan[i] = tr(f"Thửa đã từng có nước phủ: radar Sentinel-1 thấy {n_radar} đợt"
                         + (f", gần nhất {last}" if last else "") + ".",
                         f"The plot has had water over it before: Sentinel-1 radar saw {n_radar} episode(s)"
                         + (f", latest {last}" if last else "") + ".")
    text = "".join(phan)
    if sua:
        w = " ".join(_words(text))
        if not any(k in w for k in ("du bao", "7 ngay", "forecast", "7 day")):
            text = text.rstrip() + "\n\n" + _cau_du_bao(assessed)
    low = text.lower()
    notes = []
    if asks_crop(question) and any(k in " ".join(_words(text)) for k in ("phu hop", "thich hop", "suitable", "suited")):
        notes.append(tr("Lưu ý: chỉ số hiểm hoạ 7 ngày không cho biết đất có hợp với cây trồng hay không — việc đó cần xét "
                        "thổ nhưỡng, nước tưới và mùa vụ. Giai đoạn sinh trưởng của cây xem ở mô-đun Dự báo năng suất & "
                        "thu hoạch (ảnh Sentinel-2, chạy riêng vì mất vài phút).",
                        "Note: 7-day hazard indices do not tell whether the land suits a crop — that needs soil, irrigation "
                        "and season. The crop's growth stage is in the Yield & harvest forecast module (Sentinel-2 imagery, "
                        "run separately as it takes a few minutes)."))
    est = [a.module_name for a in assessed.values() if not a.is_real]
    if est and "ước lượng" not in low and "estimate" not in low:
        notes.append(tr(f"Lưu ý: số {', '.join(est)} là ước lượng vật lý chưa hiệu chỉnh, chỉ cho 7 ngày tới — chưa đủ để khẳng định.",
                        f"Note: the {', '.join(est)} figure is an uncalibrated physical estimate for the next 7 days only — "
                        f"not enough to be sure."))
    if asks_long_range(question):
        notes.append(tr("TerraTwin chỉ có dự báo 7 ngày tới; không có dự báo cho cả mùa hay các tháng sau.",
                        "TerraTwin only forecasts the next 7 days; it has no forecast for the whole season or later months."))
    return text + ("\n\n" + " ".join(notes) if notes else "")


def _plain(text: str) -> str:
    """Kiểm 21/11/2026: LLM vẫn trả "**5 đợt**" dù đã dặn — khung trả lời in nguyên văn nên dấu ** lộ ra. Bỏ markdown thừa
    (**, __, tiêu đề #) trước khi trả; giao diện vẫn có lớp vẽ chữ đậm an toàn nếu sót."""
    import re
    text = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: m.group(1) or m.group(2), text)
    text = text.replace("**", "")
    return re.sub(r"(?m)^#{1,6}\s+", "", text).strip()


def _system() -> str:
    return tr(
        "Bạn là trợ lý nông nghiệp/đất đai của TerraTwin. Trả lời NGẮN GỌN, rõ ràng "
        "bằng tiếng Việt, CHỈ dựa trên dữ liệu được cung cấp. Tuyệt đối không bịa "
        "thêm số liệu. Nếu dữ liệu không đủ để trả lời, hãy nói thẳng là chưa đủ. "
        "Hỏi thửa ĐÃ TỪNG NGẬP chưa thì trả lời bằng số đợt nước RADAR Sentinel-1 thấy phủ thửa; "
        "số đợt chỉ số thời tiết ERA5 vượt ngưỡng là ĐIỀU KIỆN có thể gây ngập, không phải lần ngập — "
        "nếu nêu thì nói riêng và gọi đúng tên. Radar không thấy nước thì không được kết luận là không ngập. "
        "Viết văn bản thuần, không định dạng — KHÔNG dùng markdown (không **, __, #, bảng); viết hoa đúng chính tả "
        "(đầu câu, tên riêng như Sentinel-1, ERA5). CHỈ dùng tiếng Việt — không chen từ tiếng Anh nào "
        "(trừ tên riêng, tên dữ liệu như Sentinel-1, ERA5, TerraScore). "
        "Dự báo chỉ có cho 7 NGÀY TỚI: hỏi về mùa, tháng hay năm tới thì nói rõ TerraTwin không có dự báo dài hạn, "
        "không được suy ra cả mùa từ 7 ngày. Dòng ghi 'ƯỚC LƯỢNG chưa hiệu chỉnh' phải được gọi là ước lượng, "
        "không khẳng định chắc chắn. Dữ liệu không có trong ngữ cảnh KHÔNG có nghĩa là không tồn tại — "
        "không được nói nguồn đó 'chưa có' hay 'không có dữ liệu'; chỉ nói câu trả lời này chưa xét tới. "
        "Chỉ số cảnh báo là DỰ BÁO 7 ngày, không phải quan sát hiện trạng: kết luận phải gắn với 'trong 7 ngày tới' và "
        "ĐÚNG mức của dự báo (vd. 'trong 7 ngày tới ít nguy cơ ngập' hoặc 'trong 7 ngày tới nguy cơ ngập cao'), KHÔNG được "
        "nói 'hiện tại không ngập' hay 'không có dấu hiệu ngập'. Radar đã thấy nước phủ thửa (số đợt lớn hơn 0) thì phải "
        "nói rõ thửa ĐÃ TỪNG có nước phủ — không được nói 'không đủ để khẳng định đã ngập hay chưa'. Không được kết luận "
        "đất 'phù hợp' để trồng một loại cây chỉ từ chỉ số hiểm hoạ 7 ngày — việc đó cần thổ nhưỡng, nước tưới, mùa vụ.",
        "You are TerraTwin's land/farming assistant. Answer BRIEFLY and clearly "
        "in English, based ONLY on the data provided. Never invent numbers. If "
        "the data isn't enough to answer, say so plainly. "
        "If asked whether the plot HAS FLOODED, answer with the number of water episodes Sentinel-1 RADAR saw over "
        "the plot; ERA5 weather-index exceedances are CONDITIONS that can cause flooding, not floods — mention them "
        "separately and by their proper name. Radar seeing no water does not prove the plot never floods. "
        "Write plain text, NO markdown (no **, __, #, tables). Answer ONLY in English — even though some data "
        "labels are in Vietnamese, translate them; keep proper names (Sentinel-1, ERA5) as they are. "
        "Forecasts cover the NEXT 7 DAYS only: if asked about the season, coming months or year, say TerraTwin has no "
        "long-range forecast and do not extrapolate a whole season from 7 days. A line marked 'uncalibrated ESTIMATE' "
        "must be called an estimate, never stated as certain. Data missing from the context does NOT mean it does not "
        "exist — never say a source is 'not available'; say this answer did not consider it. "
        "Alert indices are 7-DAY FORECASTS, not observations of the present: tie the conclusion to 'the next 7 days' and to "
        "the forecast's ACTUAL level (e.g. 'low flood risk over the next 7 days' or 'high flood risk over the next 7 days'), "
        "NEVER 'the plot is currently not flooded' or 'no sign of flooding'. If radar saw water over the plot (more than 0 "
        "episodes), say clearly the plot HAS had water over it — never 'not enough to say whether it has flooded'. Never "
        "conclude the land is 'suitable' for a crop from 7-day hazard indices alone — that needs soil, irrigation, season.",
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
            lines = [tr(
                f"- [{n.author_name}, vùng tương đồng {sim}%] {n.title}: {n.body[:400]}",
                f"- [{n.author_name}, {sim}% similar area] {n.title}: {n.body[:400]}",
            ) for sim, _, n in top]
            return cites, "\n".join(lines)
        finally:
            session.close()
    except Exception:
        return [], ""


_HAZ_VI = {"flood": "Lũ/ngập", "landslide": "Sạt lở", "drought": "Hạn/thiếu nước",
           "wildfire": "Cháy rừng", "salinity": "Xâm nhập mặn"}
_HAZ_EN = {"flood": "Flood", "landslide": "Landslide", "drought": "Drought",
           "wildfire": "Wildfire", "salinity": "Salinity intrusion"}


def _haz_label(r: str) -> str:
    return tr(_HAZ_VI.get(r, r), _HAZ_EN.get(r, r))


def _history_facts(loc: Location, routes: list[str]) -> str:
    """Lịch sử hiểm hoạ 10 NĂM của CHÍNH thửa này — nền ĐO ĐƯỢC, kiểm chứng được.

    Đây là thứ làm trợ lý khác hẳn app thời tiết: nó trả lời "nơi này từng bị
    gì, bao nhiêu lần, cao điểm tháng nào". Lỗi/nặng thì nuốt và trả rỗng — lịch
    sử là phần bổ sung, dữ liệu 7 ngày tới mới là phần chính.
    """
    try:
        from app.services import passport, water_history
        lines = []
        # Kiểm 20/11/2026: "Thửa này từng ngập chưa?" → trợ lý trả "15 đợt lũ/ngập" = số đợt CHỈ SỐ MƯA ERA5. Ngập quan sát
        # được là radar (chỉ đọc bộ nhớ đệm), đưa lên ĐẦU và gọi đúng tên; ERA5 gọi là chỉ số thời tiết.
        if True:      # 21/11/2026: luôn nạp tóm tắt radar (chỉ đọc bộ nhớ đệm) dù câu hỏi chọn mô-đun nào
            ws = water_history.summary(loc.lat, loc.lon)
            if ws.get("available"):
                y0 = (ws.get("first") or "")[:4]
                lines.append(tr(
                    f"- Nước phủ thửa đo bằng radar Sentinel-1 (quan sát thật): {ws['n_events']} đợt từ {y0}"
                    + (f", gần nhất {ws['last_event']}" if ws.get("last_event") else "")
                    + ("" if ws["n_events"] else " — radar chụp 6–12 ngày/lần nên chưa đủ để khẳng định không ngập") + ".",
                    f"- Water over the plot seen by Sentinel-1 radar (observed): {ws['n_events']} episode(s) since {y0}"
                    + (f", latest {ws['last_event']}" if ws.get("last_event") else "")
                    + ("" if ws["n_events"] else " — radar revisits every 6–12 days, so this does not rule out flooding") + "."))
        h = passport.history(loc.lat, loc.lon, years=10)
        if not h:
            return "\n".join(lines)
        for r in routes:
            row = h.get(r)
            if not row or not row.get("events"):
                continue
            pm = row.get("peak_month")
            when = tr(f", cao điểm tháng {pm}", f", peaking in month {pm}") if pm else ""
            latest = (tr(f", gần nhất {row['latest']}", f", most recent {row['latest']}")
                      if row.get("latest") else "")
            lines.append(tr(
                f"- {row.get('name') or _haz_label(r)} (chỉ số thời tiết ERA5 — điều kiện, KHÔNG phải số lần xảy ra đo được): "
                f"{row['events']} đợt vượt ngưỡng trong 10 năm{when}{latest}.",
                f"- {row.get('name') or _haz_label(r)} (ERA5 weather index — a condition, NOT observed occurrences): "
                f"{row['events']} threshold-exceeding episodes in 10 years{when}{latest}.",
            ))
        return "\n".join(lines)
    except Exception:
        return ""


def answer(question: str, loc: Location) -> CopilotAnswer:
    from app.modules.registry import get_module
    from app.services import terrascore

    routes = _route(question)
    facts = []
    assessed: dict[str, Assessment] = {}
    for r in routes:
        module = get_module(r)
        if module is None:
            continue
        a = module.assess(loc)
        assessed[r] = a
        # Đánh dấu thật/mẫu NGAY TRÊN từng dòng — nếu không, một chỉ số từ mô
        # hình mẫu (fallback khi mất mạng/hết hạn mức) đọc y hệt số đo thật,
        # và đứng cạnh dòng TerraScore "chưa đủ dữ liệu thật" bên dưới sẽ trông
        # như phần mềm tự mâu thuẫn — trong khi thực ra cả hai đều đang nói
        # đúng MỘT sự thật: lúc này không có dữ liệu thật cho hiểm họa đó.
        tag = (tr("dữ liệu thật, dự báo 7 ngày", "real data, 7-day forecast") if a.is_real
               else tr("ƯỚC LƯỢNG chưa hiệu chỉnh, 7 ngày", "uncalibrated ESTIMATE, 7 days"))
        facts.append(tr(f"- {a.module_name} ({tag}): {a.headline} | Khuyến nghị: {a.recommendation}",
                        f"- {a.module_name} ({tag}): {a.headline} | Recommendation: {a.recommendation}"))
    # Tái dùng assessment đã tính thay vì để terrascore.compute() gọi lại từ
    # đầu — trước đây nó luôn tự assess() lại CẢ 5 hiểm họa kể cả khi câu hỏi
    # chỉ hỏi về lũ, nên TerraScore có thể đọc is_real KHÁC với dòng flood vừa
    # in ở trên (mỗi bên tự gọi module một lần, độc lập).
    ts = terrascore.compute(loc, assessments=assessed)
    facts.append(tr(f"- TerraScore: {ts.score}/100 (hạng {ts.grade}) — {ts.summary}",
                    f"- TerraScore: {ts.score}/100 (grade {ts.grade}) — {ts.summary}"))
    facts_txt = "\n".join(facts)

    hist = _history_facts(loc, routes)
    hist_block = ((NL + tr("Lịch sử tại đây (radar Sentinel-1 = nước quan sát được; ERA5 = chỉ số thời tiết 10 năm):",
                           "History here (Sentinel-1 radar = observed water; ERA5 = 10-year weather index):")
                   + NL + hist) if hist else "")

    cites, know_txt = _knowledge(question, loc)
    know_block = ((NL + NL + _know_head() + NL + know_txt) if know_txt else '')

    system = _system()
    prompt = (
        f"{tr('Dữ liệu về vị trí', 'Data for location')} "
        f"({loc.lat:.4f}, {loc.lon:.4f}):\n{facts_txt}"
        f"{hist_block}{know_block}\n\n"
        f"{tr('Câu hỏi của người dùng', 'User question')}: {question}\n\n"
        f"{tr('Trả lời', 'Answer')}:"
    )

    text = llm.complete(prompt, system=system, max_tokens=600)
    if text and _CJK.search(text):
        # Kiểm 21/11/2026: gpt-oss-120b chen chữ Hán ("nhưng這些 không影響當前的預測"). Hỏi lại MỘT lần với lời dặn
        # thêm; vẫn còn thì gỡ phần chữ đó.
        lai = llm.complete(prompt, system=system + " " + tr(
            "TUYỆT ĐỐI không dùng chữ Hán, Nhật, Hàn — chỉ chữ cái tiếng Việt.",
            "NEVER use Chinese, Japanese or Korean characters — Latin script only."), max_tokens=600)
        text = lai if lai and not _CJK.search(lai) else _CJK.sub("", text).replace("  ", " ")
    if text:
        # A2 — cưỡng chế "LLM chỉ dịch, không sinh số": ẩn mọi số model bịa ra
        # ngoài dữ liệu thật đã đưa cho nó (facts + lịch sử + kiến thức + system).
        from app.services import guard
        text, _ = guard.guard_llm(text, system + NL + prompt)
        text = _plain(text)
        if reqlang.cur_lang() != "en":
            text = _viet_hoa(text)
        try:
            from app.services import water_history
            radar = water_history.summary(loc.lat, loc.lon)      # chỉ đọc bộ nhớ đệm
        except Exception:
            radar = None
        text = _han_che(text, question, assessed, radar if (radar or {}).get("available") else None)
        return CopilotAnswer(answer=text, used_modules=routes,
                             llm=True, knowledge_used=cites)

    ans = tr(
        f"TerraScore {ts.score}/100 (hạng {ts.grade}). {ts.summary}\n{facts_txt}"
        f"{hist_block}{know_block}\n\n"
        "[Trợ lý rule-based. Đặt TERRATWIN_LLM_API_KEY để bật trả lời bằng LLM. "
        "Nhà cung cấp openai-compatible (DeepSeek, Groq, OpenRouter, Together, "
        "xAI, Qwen, Ollama) chỉ cần thêm TERRATWIN_LLM_BASE_URL. Gemini hoặc "
        "Anthropic PHẢI đặt thêm TERRATWIN_LLM_PROVIDER=gemini|anthropic — "
        "thiếu biến đó thì khóa bị gửi sai giao thức và im lặng không chạy.]",
        f"TerraScore {ts.score}/100 (grade {ts.grade}). {ts.summary}\n{facts_txt}"
        f"{hist_block}{know_block}\n\n"
        "[Rule-based assistant. Set TERRATWIN_LLM_API_KEY to enable LLM answers. "
        "OpenAI-compatible providers (DeepSeek, Groq, OpenRouter, Together, xAI, "
        "Qwen, Ollama) only need TERRATWIN_LLM_BASE_URL added. Gemini or "
        "Anthropic MUST also set TERRATWIN_LLM_PROVIDER=gemini|anthropic — "
        "without it the key is sent with the wrong protocol and silently does "
        "nothing.]",
    )
    return CopilotAnswer(answer=ans, used_modules=routes, llm=False,
                         knowledge_used=cites)
