"""Làm sạch câu cảnh báo ĐÃ LƯU từ trước một bản sửa chữ — sửa LÚC ĐỌC RA, không ghi lại CSDL (cùng cách với tab GĐ3).

Kiểm 20/11/2026: cảnh báo cũ của ann953201 vẫn ghi "Có khu khai thác/công nghiệp cách 1.99 km ((không tên))" — câu được
ghép lúc tạo cảnh báo (trước PR #31) rồi lưu nguyên trong Alert.headline, nên sửa osm.py chỉ đúng cho cảnh báo MỚI."""
from __future__ import annotations

import re

_KM_VI = re.compile(r"(cách )(\d+)\.(\d+)( km)")


def alert_text(s: str | None) -> str | None:
    if not s:
        return s
    s = s.replace("((không tên))", "(chưa có tên)").replace("((unnamed))", "(unnamed)")
    return _KM_VI.sub(r"\1\2,\3\4", s)
