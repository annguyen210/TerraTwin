"""RÀO CHẮN ĐẦU VÀO CHO AI (nâng cấp 25/11/2026) — chạy TRƯỚC khi văn bản người dùng tới LLM.

Hai việc, đều không cần mô hình:
  1. CHE DỮ LIỆU CÁ NHÂN: số điện thoại Việt Nam, số CCCD/CMND (9 hoặc 12 chữ số), email → nhãn "[số điện thoại]"…
     Người dùng hay dán nguyên tin rao ("liên hệ 0912 345 678 anh Tâm") — số đó không cần cho câu trả lời và không được
     rời máy chủ sang nhà cung cấp LLM.
  2. CHỐNG CHÈN LỆNH (prompt injection): câu đòi bỏ qua hướng dẫn, đổi vai, in lời nhắc hệ thống… bị BỎ KHỎI câu hỏi
     (phần hỏi về thửa vẫn được trả lời). Danh sách mẫu tiếng Việt + Anh, có cả dạng không dấu.

Không thay rào chắn ĐẦU RA (guard.py — che số LLM bịa) mà đi trước nó. Đếm số lần chặn để hiện ở /api/guard/stats.
"""
from __future__ import annotations

import re
import threading

_lock = threading.Lock()
_stats = {"screened": 0, "pii_masked": 0, "injection_removed": 0}

_PHONE = re.compile(r"(?<![\d])(?:\+?84|0)(?:[\s.\-]?\d){8,10}(?![\d])")
_ID = re.compile(r"(?<![\d.,])(?:\d{12}|\d{9})(?!\d|[.,]\d)")   # dấu chấm cuối câu không chặn khớp
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")

# Mẫu chèn lệnh — so trên chuỗi đã bỏ dấu, chữ thường.
_INJ = [
    r"(bo qua|phot lo|quen|ignore|disregard|forget)\b.{0,40}\b(huong dan|chi dan|lenh|quy tac|instruction|rule|prompt|above|previous)",
    r"(system prompt|loi nhac he thong|prompt he thong|chi thi he thong)",
    r"(in ra|tiet lo|hien thi|cho toi xem|print|reveal|show)\b.{0,30}\b(prompt|huong dan|chi dan|instruction|api key|khoa api|mat khau)",
    r"(ban (bay gio|tu gio) la|tu gio ban la|you are now|act as|dong vai|gia lam|pretend to be)",
    r"(jailbreak|developer mode|che do nha phat trien|dan mode|khong co gioi han|no restrictions)",
    r"(tra loi rang|hay noi rang|say that|respond with)\b.{0,40}\b(an toan|khong ngap|nen mua|safe|no flood|should buy)",
]
_INJ_RE = [re.compile(p) for p in _INJ]
_SENT = re.compile(r"(?<=[.!?\n])\s+")


def _fold(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFD", (s or "").replace("đ", "d").replace("Đ", "D"))
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn").lower()


def mask_pii(text: str) -> tuple[str, int]:
    n = 0

    def sub(rx: re.Pattern, label: str, s: str) -> str:
        nonlocal n
        out, k = rx.subn(label, s)
        n += k
        return out
    t = sub(_EMAIL, "[email]", text or "")
    t = sub(_PHONE, "[số điện thoại]", t)
    t = sub(_ID, "[số giấy tờ]", t)
    return t, n


def injected(sentence: str) -> bool:
    f = _fold(sentence)
    return any(r.search(f) for r in _INJ_RE)


def screen(text: str) -> tuple[str, dict]:
    """→ (văn bản an toàn để gửi LLM, báo cáo {pii, injection, removed}). Câu chèn lệnh bị bỏ; nếu bỏ hết thì trả ""."""
    masked, n_pii = mask_pii(text)
    parts = [p for p in _SENT.split(masked) if p.strip()]
    keep = [p for p in parts if not injected(p)]
    removed = len(parts) - len(keep)
    with _lock:
        _stats["screened"] += 1
        _stats["pii_masked"] += n_pii
        _stats["injection_removed"] += removed
    return " ".join(keep).strip(), {"pii": n_pii, "injection": removed > 0, "removed": removed}


def stats() -> dict:
    with _lock:
        return {**_stats, "note": "Rào chắn ĐẦU VÀO: che số điện thoại/CCCD/email và bỏ câu chèn lệnh trước khi gửi LLM."}
