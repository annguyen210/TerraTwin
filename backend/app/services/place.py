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
_LIMIT = 10

# Nominatim cho phép tối đa 1 lời gọi/giây. Một khe, và tự giãn cách.
_GATE = threading.BoundedSemaphore(1)
_last = [0.0]
_MIN_GAP = 1.1


# BA NGUỒN, thử lần lượt — và đây là bài học phải trả giá.
#
# Bản đầu chỉ dùng Nominatim. Nó bị CHẶN HẲN từ máy này ("connection forcibly
# closed"), nên ô tìm kiếm trả rỗng cho MỌI truy vấn. Người dùng gõ tên xã của
# mình, không ra gì, và kết luận phần mềm chỉ chạy được ở tám nơi có sẵn trong
# danh sách chọn nhanh. Họ kết luận đúng với thứ họ trải nghiệm.
#
# Một dịch vụ cộng đồng miễn phí CÓ THỂ chặn bất kỳ ai bất kỳ lúc nào. Cho
# đường vào chính của sản phẩm phụ thuộc vào đúng một dịch vụ như thế là lỗi
# thiết kế, không phải rủi ro vận hành.
#
# Đo thật, cùng truy vấn "Ba Tri Ben Tre":
#   Open-Meteo Geocoding  1,0s  · sạch, chỉ địa danh hành chính
#   Photon (Komoot)       1,0s  · phủ dày hơn (tìm được Trà Leng, Đất Mũi)
#                                 nhưng lẫn quán ăn, nhà hát → phải lọc
#   Nominatim             HỎNG  · bị chặn
GEO_OM = "https://geocoding-api.open-meteo.com/v1/search"
PHOTON = "https://photon.komoot.io/api/"

# Loại địa điểm Photon được nhận. Không lọc thì "Ba Tri" ra "Bánh Bao Bến Tre".
_PHOTON_OK = {
    "city", "town", "village", "hamlet", "suburb", "quarter", "neighbourhood",
    "municipality", "administrative", "county", "state", "province", "region",
    "district", "locality", "island", "national_park",
}


def _get(url: str, timeout: float = TIMEOUT) -> dict | None:
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": USER_AGENT, "Accept-Language": "vi,en"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def _from_open_meteo(q: str) -> list | None:
    d = _get(GEO_OM + "?" + urllib.parse.urlencode(
        {"name": q, "count": _LIMIT, "language": "vi"}))
    if not d:
        return None
    out = []
    for it in d.get("results", []):
        if it.get("country_code") != "VN":
            continue
        # admin3 = xã/phường, admin2 = huyện/quận, admin1 = tỉnh — nêu đủ để phân
        # biệt hàng nghìn thửa cùng tên khác xã.
        phu = " · ".join(x for x in (it.get("admin3"), it.get("admin2"),
                                     it.get("admin1")) if x)
        try:
            out.append({"label": f"{it['name']}" + (f" · {phu}" if phu else ""),
                        "lat": float(it["latitude"]), "lon": float(it["longitude"]),
                        "kind": it.get("feature_code") or "", "source": "open-meteo"})
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _from_photon(q: str) -> list | None:
    d = _get(PHOTON + "?" + urllib.parse.urlencode(
        {"q": q, "limit": _LIMIT * 3, "lang": "en"}))
    if not d:
        return None
    out = []
    for f in d.get("features", []):
        p = f.get("properties", {})
        if p.get("countrycode") != "VN":
            continue
        if p.get("osm_value") not in _PHOTON_OK:
            continue
        try:
            c = f["geometry"]["coordinates"]
            phu = " · ".join(x for x in (p.get("county"), p.get("state")) if x)
            out.append({"label": f"{p.get('name')}" + (f" · {phu}" if phu else ""),
                        "lat": float(c[1]), "lon": float(c[0]),
                        "kind": p.get("osm_value") or "", "source": "photon"})
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        if len(out) >= _LIMIT:
            break
    return out


def _from_nominatim(q: str) -> list | None:
    """Giữ lại làm nguồn cuối. Bị chặn từ máy phát triển nhưng có thể chạy được
    ở nơi khác, và nó phủ dày nhất trong ba nguồn khi hoạt động."""
    with _GATE:
        gap = time.time() - _last[0]
        if gap < _MIN_GAP:
            time.sleep(_MIN_GAP - gap)
        try:
            d = _get(SEARCH + "?" + urllib.parse.urlencode({
                "q": q, "format": "jsonv2", "countrycodes": "vn",
                "limit": _LIMIT, "addressdetails": 1}))
        finally:
            _last[0] = time.time()
    if not d:
        return None
    out = []
    for it in d:
        try:
            out.append({"label": _label(it), "lat": float(it["lat"]),
                        "lon": float(it["lon"]),
                        "kind": it.get("addresstype") or it.get("type") or "",
                        "source": "nominatim"})
        except (KeyError, TypeError, ValueError):
            continue
    return out


_SOURCES = (_from_open_meteo, _from_photon, _from_nominatim)


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

    # Thử lần lượt, dừng ở nguồn ĐẦU TIÊN có kết quả. Không gộp kết quả các
    # nguồn: chúng đặt tên khác nhau nên gộp lại sinh ra danh sách trùng lặp
    # trông như lỗi.
    out, hong = [], 0
    for lay in _SOURCES:
        r = lay(q)
        if r is None:
            hong += 1
            continue
        if r:
            out = r
            break

    if not out and hong == len(_SOURCES):
        return {"query": q, "results": [],
                "message": ("Chưa tìm được — cả ba dịch vụ tra cứu địa danh đều "
                            "không phản hồi. Bạn vẫn bấm thẳng lên bản đồ được, "
                            "hoặc dùng nút định vị.")}

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
