"""Khoá Open-Meteo TRẢ PHÍ — bắt buộc trước khi thu tiền (GĐ0 kế hoạch tổng).

Gói miễn phí của Open-Meteo chỉ cho mục đích PHI THƯƠNG MẠI. Có TERRATWIN_OPENMETEO_API_KEY thì
mọi lượt gọi *.open-meteo.com đổi sang máy chủ khách hàng (customer-<host>) kèm &apikey=; không có
thì giữ nguyên như cũ.

KHOÁ KHÔNG BAO GIỜ đi vào khoá cache hay log: chỉ chèn vào URL ở ĐÚNG bước gửi đi
(realdata._fetch, place._get); khoá cache vẫn tính từ URL gốc, nên bật/tắt khoá không làm mất cache.
"""
from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit


def _key() -> str:
    return os.environ.get("TERRATWIN_OPENMETEO_API_KEY", "").strip()


def plan() -> dict:
    """Cho /api/health: đang dùng gói nào (không lộ khoá)."""
    k = _key()
    return {"plan": "commercial" if k else "free_non_commercial", "key_configured": bool(k),
            "note": None if k else ("Gói miễn phí Open-Meteo chỉ cho phi thương mại — đặt "
                                    "TERRATWIN_OPENMETEO_API_KEY trước khi thu tiền.")}


def sign(url: str) -> str:
    """URL gốc → URL gửi đi. Chỉ đụng tới *.open-meteo.com; không có khoá thì trả nguyên."""
    k = _key()
    if not k:
        return url
    p = urlsplit(url)
    host = p.hostname or ""
    if not host.endswith("open-meteo.com"):
        return url
    if not host.startswith("customer-"):
        host = "customer-" + host
    q = p.query + ("&" if p.query else "") + "apikey=" + k
    return urlunsplit((p.scheme, host + (f":{p.port}" if p.port else ""), p.path, q, p.fragment))


def redact(text: str) -> str:
    """Xoá khoá khỏi chuỗi bất kỳ trước khi ghi log/trả lỗi."""
    k = _key()
    return text.replace(k, "***") if k else text
