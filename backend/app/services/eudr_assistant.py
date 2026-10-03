"""TRỢ LÝ EUDR — hỏi đáp tiếng Việt có TRÍCH DẪN (RAG: tìm rồi mới sinh).

Câu hỏi thật của nông hộ, hợp tác xã: "vườn 3 ha có phải vẽ ranh không?", "cà phê
trồng xen cây rừng có bị coi là rừng không?", "phạt bao nhiêu?". Trả lời sai về pháp
lý còn tệ hơn không trả lời — nên:

  1. TÌM: BM25 (Robertson–Spärck Jones, k1=1,5, b=0,75) trên kho đoạn trích có nguồn
     (data/eudr_corpus.json). Tiếng Việt viết theo âm tiết nên chỉ mục cả âm tiết lẫn
     CẶP âm tiết liền nhau ("phá rừng", "thửa đất"), và bỏ dấu để người gõ không dấu
     vẫn tìm ra ("pha rung" → "phá rừng").
  2. SINH: có khoá LLM thì mô hình chỉ được trả lời TỪ các đoạn đã tìm, bắt buộc ghi
     [mã đoạn]; câu trả lời không trích được đoạn nào thì bỏ, lùi về trích nguyên văn.
     Không có khoá → trả nguyên các đoạn liên quan nhất (vẫn đúng, chỉ kém mượt).
  3. KHÔNG TÌM THẤY → nói thẳng, không đoán.
"""
from __future__ import annotations

import json
import math
import os
import re
import unicodedata
from functools import lru_cache

from app.services.reqlang import tr

K1, B = 1.5, 0.75
TOP_K = 3
MIN_SCORE = 1.0
MIN_COVER = 0.6
_STOP = {"la", "va", "cua", "co", "cho", "thi", "nhu", "nao", "gi", "the", "duoc", "khi", "voi", "mot", "cac",
         "nhung", "toi", "ban", "minh", "em", "anh", "a", "a?", "o", "de", "ve", "tu", "den", "hay", "neu", "ma"}


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d")


def _syllables(text: str) -> list[str]:
    return re.findall(r"[^\W_]+", unicodedata.normalize("NFC", text.lower()))


def tokens(text: str) -> list[str]:
    """Âm tiết + cặp âm tiết, ở CẢ dạng có dấu ("phạt") lẫn bỏ dấu ("f:phat"). Bỏ dấu
    đơn thuần làm "phạt" trùng "phát" — nên dạng có dấu khớp được tính nặng hơn."""
    syl = [w for w in _syllables(text) if _fold(w) not in _STOP]
    fold = [_fold(w) for w in syl]
    out = syl + [f"{a}_{b}" for a, b in zip(syl, syl[1:])]
    out += [f"f:{w}" for w in fold] + [f"f:{a}_{b}" for a, b in zip(fold, fold[1:])]
    return out


@lru_cache(maxsize=1)
def _index():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "eudr_corpus.json")
    with open(path, encoding="utf-8") as f:
        docs = json.load(f)["passages"]
    # Tiêu đề và CÂU HỎI MẪU nặng gấp đôi (mở rộng tài liệu bằng câu hỏi thật người dùng hay hỏi).
    toks = [tokens(d["title"]) * 2 + tokens(" . ".join(d.get("q") or [])) * 2 + tokens(d["text"]) for d in docs]
    df: dict[str, int] = {}
    for t in toks:
        for w in set(t):
            df[w] = df.get(w, 0) + 1
    avg = sum(len(t) for t in toks) / max(1, len(toks))
    tfs = []
    for t in toks:
        tf: dict[str, int] = {}
        for w in t:
            tf[w] = tf.get(w, 0) + 1
        tfs.append((tf, len(t)))
    return docs, tfs, df, avg


def search(q: str, k: int = TOP_K) -> list[dict]:
    docs, tfs, df, avg = _index()
    n = len(docs)
    qt = set(tokens(q))
    accented = any(ord(c) > 127 for c in q)
    # Độ phủ tính trên âm tiết ĐÚNG DẠNG người hỏi gõ: có dấu thì so có dấu ("giá" ≠ "gia súc").
    content = {w for w in qt if "_" not in w and (not w.startswith("f:") if accented else w.startswith("f:"))}
    scored = []
    for d, (tf, dl) in zip(docs, tfs):
        s, hit = 0.0, set()
        for w in qt:
            f = tf.get(w)
            if not f:
                continue
            # Câu hỏi có dấu: khớp có dấu tính đủ, khớp bỏ dấu chỉ 0,4. Không dấu: chỉ có bỏ dấu.
            wt = (0.4 if accented else 1.0) if w.startswith("f:") else 1.0
            idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
            s += wt * idf * f * (K1 + 1) / (f + K1 * (1 - B + B * dl / avg))
            if w in content:
                hit.add(w)
        cover = len(hit) / len(content) if content else 0.0
        # Phải khớp phần lớn ý của câu hỏi — "giá cà phê hôm nay" chỉ khớp "cà phê" → không trả lời bừa.
        if s >= MIN_SCORE and cover >= MIN_COVER:
            scored.append({**d, "score": round(s, 2), "coverage": round(cover, 2)})
    return sorted(scored, key=lambda x: -x["score"])[:k]


SYSTEM = ("Bạn là trợ lý pháp lý về Quy định chống phá rừng của EU (EUDR) cho nông dân và doanh nghiệp Việt Nam. "
          "CHỈ được dùng thông tin trong các ĐOẠN TRÍCH được cung cấp. Mỗi ý phải ghi mã đoạn trong ngoặc vuông, ví "
          "dụ [eudr-art9]. Nếu các đoạn trích không đủ để trả lời, nói rõ là không đủ thông tin và khuyên hỏi chuyên "
          "gia pháp lý. Trả lời bằng tiếng Việt, ngắn gọn, dễ hiểu, tối đa 150 từ. Không bịa số, ngày, điều khoản.")


def ask(q: str) -> dict:
    from app.services import llm

    q = (q or "").strip()[:500]
    hits = search(q)
    cites = [{k: h[k] for k in ("id", "title", "source", "url", "text", "score", "coverage")} for h in hits]
    if not hits:
        return {"mode": "none", "citations": [], "answer": tr(
            "Kho quy định của TerraTwin chưa có đoạn nào trả lời câu này. Hãy hỏi chuyên gia pháp lý hoặc đọc văn bản "
            "gốc Quy định (EU) 2023/1115.",
            "TerraTwin's regulation library has no passage answering this. Ask a legal expert or read Regulation "
            "(EU) 2023/1115.")}
    if llm.available():
        ctx = "\n\n".join(f"[{h['id']}] {h['title']} ({h['source']}): {h['text']}" for h in hits)
        out = llm.complete(f"ĐOẠN TRÍCH:\n{ctx}\n\nCÂU HỎI: {q}", system=SYSTEM, max_tokens=500)
        ids = {h["id"] for h in hits}
        if out and any(f"[{i}]" in out for i in ids):          # phải trích đúng đoạn đã tìm
            return {"mode": "llm", "answer": out, "citations": cites}
    top = hits[0]
    return {"mode": "extractive", "citations": cites,
            "answer": tr(f"Theo {top['source']}: {top['text']} [{top['id']}]",
                         f"Per {top['source']} (Vietnamese summary): {top['text']} [{top['id']}]")}
