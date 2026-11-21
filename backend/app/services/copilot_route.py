"""Chọn mô-đun dữ liệu cho câu hỏi trợ lý — so THEO TỪ sau khi bỏ dấu, xét MỌI hiểm hoạ (kiểm 21/11/2026).

Bản cũ (copilot._route) so CHUỖI CON và dừng ở luật khớp đầu tiên:
  · "manh dat nay co bi ngap khong" → "man" nằm trong "manh" → chỉ nạp MẶN → trợ lý nói "chưa đủ để xác định có bị
    ngập" dù radar thấy nước phủ thửa 5 đợt;
  · "han" khớp "thanh"/"khan", "man" khớp "many";
  · "Tóm tắt các rủi ro chính…" → chỉ land_risk → trợ lý nói radar và ERA5 "hiện chưa có".
"""
from __future__ import annotations

import re
import unicodedata

# Mỗi mục: mô-đun → các cụm TỪ đã bỏ dấu (một hoặc nhiều từ liền nhau).
_KEYS: dict[str, tuple[str, ...]] = {
    "flood": ("ngap", "lu", "lut", "lu lut", "nuoc len", "nuoc phu", "flood", "floods", "flooded", "flooding",
              "inundation", "inundated"),
    "salinity": ("man", "nhiem man", "xam nhap man", "salt", "salty", "saline", "salinity"),
    "drought": ("han", "kho han", "han han", "thieu nuoc", "tuoi", "drought", "dry", "dryness", "irrigation"),
    "wildfire": ("chay rung", "lua", "fire", "wildfire", "wildfires"),
    "landslide": ("sat lo", "lo dat", "landslide", "landslides"),
    "solar": ("dien mat troi", "mat troi", "solar"),
}
# Câu hỏi tổng quát ("rủi ro", "tóm tắt", "nên làm gì", "mua đất") → nạp đánh giá nền đất + các hiểm hoạ chính.
_TONG_QUAT = ("rui ro", "tom tat", "tong quan", "tong hop", "nen lam gi", "mua dat", "dau tu", "risk", "risks",
              "summary", "summarize", "summarise", "overview", "invest", "investment", "buy", "buying")
_THU_TU = ("flood", "salinity", "drought", "landslide", "wildfire", "solar")
_MAC_DINH = ["salinity", "drought", "flood"]


def fold(s: str) -> str:
    """Thường hoá + bỏ dấu tiếng Việt (đ → d)."""
    s = unicodedata.normalize("NFD", (s or "").lower().replace("đ", "d"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _words(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", fold(s))


def _has(words: list[str], phrase: str) -> bool:
    p = phrase.split()
    n = len(p)
    return any(words[i:i + n] == p for i in range(len(words) - n + 1))


def route(question: str) -> list[str]:
    w = _words(question)
    hit = [m for m in _THU_TU if any(_has(w, k) for k in _KEYS[m])]
    if any(_has(w, k) for k in _TONG_QUAT):
        return ["land_risk"] + [m for m in ("flood", "drought", "salinity") if m not in hit] + hit
    return hit or list(_MAC_DINH)


_MUA = ("mua kho", "mua mua", "mua toi", "thang toi", "thang sau", "nam toi", "nam sau", "ca mua", "lau dai",
        "season", "seasons", "seasonal", "next month", "next year", "long term", "long-term")


def asks_long_range(question: str) -> bool:
    """Hỏi về mùa/tháng/năm tới — TerraTwin chỉ có dự báo 7 ngày."""
    w = _words(question)
    return any(_has(w, k.replace("-", " ")) for k in _MUA)
