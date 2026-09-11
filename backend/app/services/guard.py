"""A2 — RÀO CHẮN CON SỐ cho đầu ra LLM.

Nguyên tắc của cả sản phẩm: "LLM chỉ được DỊCH/diễn giải, KHÔNG được SINH số."
Nguyên tắc đó đã viết trong prompt nhưng prompt không cưỡng chế được gì — một
model đủ tự tin vẫn bịa ra "độ mặn 8,5‰" hay "nguy cơ 73%". Một con số bịa lọt
tới người dùng phá huỷ toàn bộ giá trị của sổ điểm (thứ cả sản phẩm lấy làm bằng
chứng cho sự trung thực). Đây là lớp CƯỠNG CHẾ ở tầng mã: quét mọi số trong văn
bản LLM, số nào KHÔNG có trong tập số thật đã đưa cho model thì ẩn đi.

Rẻ nhất mà bảo vệ được nhiều nhất. Bọc mọi lối ra của LLM: copilot, whatif_nlp,
và bất cứ chỗ nào sau này nối LLM vào báo cáo.
"""
from __future__ import annotations

import re
import threading

# Đếm số lần đã chặn — thêm một con số nữa để CÔNG BỐ, đúng tinh thần sổ điểm:
# rào chắn có tác dụng thật hay không thì đo được, không phải lời hứa.
_lock = threading.Lock()
_stats = {"checked": 0, "redacted_answers": 0, "numbers_removed": 0}

REDACT = "[số đã ẩn]"

# Bắt số: nguyên/thập phân, có dấu phân cách nghìn (1.000.000 hoặc 1,000,000),
# dấu thập phân là "." hoặc "," (kiểu Việt: 4,2). Không nuốt số điện thoại dài
# hay mã — chỉ số thường trong câu văn.
_NUM = re.compile(r"-?\d[\d.,]*\d|-?\d")


def _parse(tok: str) -> float | None:
    t = tok.strip().rstrip(".,")
    # 1.000.000 / 1,234,567 → bỏ dấu phân cách nghìn.
    if re.fullmatch(r"-?\d{1,3}([.,]\d{3})+", t):
        return float(re.sub(r"[.,]", "", t))
    try:
        return float(t.replace(",", "."))   # 4,2 → 4.2
    except ValueError:
        return None


def _benign(v: float) -> bool:
    """Số gần như không bao giờ là 'số liệu bịa' và hay xuất hiện tự nhiên trong
    câu: số nguyên nhỏ 0–31 (ngày, đếm bước) và năm 1900–2100. Cho qua để không
    nuốt 'trong 7 ngày tới' hay 'mùa lũ 2020' — vốn không phải tuyên bố số liệu."""
    if v.is_integer():
        n = int(v)
        return 0 <= n <= 31 or 1900 <= n <= 2100
    return False


def numbers_in(text: str) -> set[float]:
    """Tập mọi số xuất hiện trong text (những số model ĐƯỢC PHÉP nhắc lại)."""
    out: set[float] = set()
    for m in _NUM.finditer(text or ""):
        v = _parse(m.group(0))
        if v is not None:
            out.add(v)
    return out


def strip_invented_numbers(
    text: str, allowed: set[float], tol: float = 0.005,
) -> tuple[str, list[str]]:
    """Ẩn mọi số trong `text` KHÔNG khớp (trong dung sai) với `allowed`.

    Trả về (văn bản đã lọc, danh sách số bị ẩn). Số benign (ngày/năm nhỏ) luôn
    qua. Khớp theo dung sai tương đối `tol` để không ẩn nhầm 72 vs 72,0.
    """
    if not text:
        return text, []
    removed: list[str] = []

    def ok(v: float) -> bool:
        if _benign(v):
            return True
        for a in allowed:
            if abs(v - a) <= max(tol * abs(a), 1e-9):
                return True
        return False

    def repl(m: re.Match) -> str:
        raw = m.group(0)
        v = _parse(raw)
        if v is None or ok(v):
            return raw
        removed.append(raw)
        return REDACT

    out = _NUM.sub(repl, text)
    with _lock:
        _stats["checked"] += 1
        if removed:
            _stats["redacted_answers"] += 1
            _stats["numbers_removed"] += len(removed)
    return out, removed


def guard_llm(text: str, source_text: str) -> tuple[str, list[str]]:
    """Tiện ích: ẩn số bịa trong `text`, lấy tập số cho phép từ `source_text`
    (chính là prompt + system mà model đã được đưa)."""
    return strip_invented_numbers(text, numbers_in(source_text))


def stats() -> dict:
    with _lock:
        s = dict(_stats)
    s["note"] = ("Số lần rào chắn ẩn một con số mà LLM bịa ra ngoài dữ liệu thật. "
                 "Công bố như sổ điểm: cơ chế chống bịa số có chạy hay không thì "
                 "đo được, không phải lời hứa trong prompt.")
    return s
