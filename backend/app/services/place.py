"""Tìm địa điểm theo TÊN — để người dùng gõ "Ba Tri, Bến Tre" thay vì mò bản đồ.

VÌ SAO CẦN: màn hình đầu trước đây mở ra là một bản đồ trống, và cách duy nhất
để bắt đầu là tự tìm đúng thửa của mình giữa bản đồ cả nước. Với người mở lần
đầu, đó là một bài đố chứ không phải một sản phẩm. Gõ tên xã là cách mà bất kỳ
ai cũng biết làm mà không cần hướng dẫn.

Đây là chiều XUÔI (tên → toạ độ). Chiều ngược (toạ độ → tên) đã có trong
region.py và phục vụ việc khác: xác định điểm có nằm trong đất liền Việt Nam
hay không.

TÔN TRỌNG CHÍNH SÁCH NOMINATIM — đây là dịch vụ cộng đồng, miễn phí, dễ bị lạm
dụng: tối đa một lời gọi mỗi giây (ép bằng cổng một khe), có User-Agent nhận
dạng được, và cache kết quả. Tên xã không đổi, nên cache một tháng là hợp lý và
gần như mọi lần gõ lại đều không chạm mạng.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request

from app.services import cache_store

SEARCH = "https://nominatim.openstreetmap.org/search"
# Phải THUẦN ASCII: header HTTP mã hoá latin-1, một chữ có dấu là hỏng cả lời gọi.
USER_AGENT = "TerraTwin/0.7 (Vietnam land digital twin; contact via repo)"
TIMEOUT = 12.0
_TTL = 30 * 86400
_LIMIT = 6

# Nominatim cho phép tối đa 1 lời gọi/giây. Một khe, và tự giãn cách.
_GATE = threading.BoundedSemaphore(1)
_last = [0.0]
_MIN_GAP = 1.1


def _query(q: str) -> list | None:
    url = SEARCH + "?" + urllib.parse.urlencode({
        "q": q,
        "format": "jsonv2",
        "countrycodes": "vn",     # chỉ Việt Nam — sản phẩm không phục vụ nơi khác
        "limit": _LIMIT,
        "addressdetails": 1,
    })
    with _GATE:
        gap = time.time() - _last[0]
        if gap < _MIN_GAP:
            time.sleep(_MIN_GAP - gap)
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": USER_AGENT,
                              "Accept-Language": "vi,en"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            return None
        finally:
            _last[0] = time.time()


def _label(item: dict) -> str:
    """Tên gọn, bỏ phần đuôi lặp lại.

    Nominatim trả về chuỗi rất dài kiểu "Xã An Đức, Huyện Ba Tri, Tỉnh Bến Tre,
    Đồng bằng sông Cửu Long, 86000, Việt Nam". Giữ hết thì không đọc nổi trên
    một dòng, nên lấy ba đoạn đầu — đủ để phân biệt hai xã trùng tên.
    """
    full = item.get("display_name") or ""
    parts = [p.strip() for p in full.split(",") if p.strip()]
    drop = {"việt nam", "vietnam"}
    parts = [p for p in parts if p.lower() not in drop and not p.isdigit()]
    return ", ".join(parts[:3]) if parts else full


def search(q: str) -> dict:
    """Tìm địa điểm ở Việt Nam theo tên. Không bao giờ bịa kết quả."""
    q = (q or "").strip()
    if len(q) < 2:
        return {"query": q, "results": [],
                "message": "Gõ ít nhất hai ký tự."}

    key = f"place:{q.lower()}"
    hit = cache_store.get(key)
    if hit is not None:
        return {"query": q, "results": hit, "cached": True}

    raw = _query(q)
    if raw is None:
        return {"query": q, "results": [],
                "message": ("Chưa tìm được — dịch vụ tra cứu địa danh đang bận. "
                            "Bạn có thể bấm thẳng lên bản đồ.")}

    out = []
    for it in raw:
        try:
            out.append({
                "label": _label(it),
                "lat": float(it["lat"]),
                "lon": float(it["lon"]),
                "kind": it.get("addresstype") or it.get("type") or "",
            })
        except (KeyError, TypeError, ValueError):
            continue

    if not out:
        # CỐ Ý KHÔNG CACHE KẾT QUẢ RỖNG. Rỗng có thể chỉ là nhất thời — dịch vụ
        # trả về danh sách trống lúc quá tải, hoặc địa danh mới được thêm vào
        # OpenStreetMap hôm sau. Cache 30 ngày một câu "không tìm thấy" nghĩa là
        # người dùng gõ đúng tên xã của mình vẫn bị từ chối suốt một tháng, và
        # không cách nào tự sửa được.
        return {"query": q, "results": [],
                "message": f"Không tìm thấy “{q}” ở Việt Nam. Thử tên xã hoặc huyện."}

    cache_store.put(key, out, ttl_seconds=_TTL)
    return {"query": q, "results": out}
