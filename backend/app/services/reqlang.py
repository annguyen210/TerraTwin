"""Ngôn ngữ theo TỪNG REQUEST cho nội dung máy chủ sinh (tên mô-đun, headline,
recommendation…).

VÌ SAO cần: frontend đã song ngữ phần vỏ, nhưng nội dung do máy chủ dựng động
(mỗi module tự ghép câu từ số liệu) thì frontend không chạm tới được. Bật EN mà
máy chủ vẫn trả tiếng Việt = quá nửa màn hình vẫn tiếng Việt.

CÁCH: một contextvar giữ ngôn ngữ của request hiện tại. Endpoint đọc ?lang= (hoặc
Accept-Language) rồi set_lang(); module gọi tr(vi, en) để chọn. scan chạy ĐA
LUỒNG nên jobs.gather phải copy context sang luồng con (xem jobs.py) — nếu không
luồng con mất ngôn ngữ và rơi về tiếng Việt.
"""
from __future__ import annotations

import contextvars

_LANG: contextvars.ContextVar[str] = contextvars.ContextVar("terratwin_lang", default="vi")


def set_lang(lang: str | None) -> None:
    _LANG.set("en" if (lang or "").lower().startswith("en") else "vi")


def cur_lang() -> str:
    return _LANG.get()


def tr(vi: str, en: str) -> str:
    """Chọn chuỗi theo ngôn ngữ request. Mặc định tiếng Việt."""
    return en if _LANG.get() == "en" else vi


def from_accept_language(header: str | None) -> str:
    """Suy ngôn ngữ từ header Accept-Language khi không có ?lang=."""
    if header and "en" in header.lower().split(",")[0]:
        return "en"
    return "vi"
