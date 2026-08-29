"""HỒ SƠ THỬA ĐẤT — thứ không app thời tiết nào nói được.

VÌ SAO CÓ TỆP NÀY. Người dùng nói các tính năng "nghe giống mọi phần mềm
khác": cảnh báo lũ, cảnh báo hạn, bản đồ nhiệt, xem ảnh vệ tinh — app thời tiết
nào cũng có. Họ so sánh xong không thấy hơn ở đâu, và họ nói đúng: những tính
năng đó KHÔNG hơn ở đâu cả.

Thứ TerraTwin có mà app thời tiết không có là DỮ LIỆU RIÊNG CỦA MỘT THỬA: cao
độ của chính nó, độ dốc, vị trí tương đối so với đất xung quanh, và mười năm
lịch sử của đúng toạ độ đó. Ba câu dưới đây không một ứng dụng dự báo nào trả
lời được, vì chúng không biết thửa của bạn nằm ở đâu trong địa hình:

    "Ruộng bạn thấp hơn 78% đất trong bán kính 3 km — nước dồn về đây trước."
    "Mười năm qua chỗ này có 274 lần mưa vượt ngưỡng chung cả nước."
    "Tháng nguy hiểm nhất của thửa này là tháng 10, không phải tháng 9."

ĐO THẬT, và con số phân biệt được nơi này với nơi khác:
    Huế       ngập 274 lần (T10) · hạn  57 · cháy 290
    Bến Tre   ngập  24 lần (T10) · hạn  47 · cháy   7
    Phan Rang ngập  39 lần       · hạn 425 (T4) · cháy 296
Huế là rốn lũ miền Trung, Phan Rang khô hạn nhất nước — số liệu khớp với điều
ai cũng biết, và đó chính là cách kiểm tra nhanh rằng phép đo không bịa.

Câu thứ ba quan trọng hơn vẻ ngoài của nó: lịch mùa vụ dạy chung cho cả tỉnh,
còn thửa đất thì không theo lịch tỉnh.

CHI PHÍ. Cao độ 25 điểm gộp trong MỘT lượt gọi (đo được 1,1 giây). Phần lịch sử
dùng lại đúng mười năm dữ liệu mà bước hiệu chuẩn đã tải. Lần đầu ~25 giây, sau
đó lấy từ cache — và cache giữ 30 ngày vì lịch sử mười năm không đổi theo ngày.
"""
from __future__ import annotations

import math
from collections import Counter
from datetime import date, timedelta

from app.services import calibration as cal, realdata

RINGS_KM = (1.0, 2.0, 3.0)
PER_RING = 8
DANGER = 70.0
_TTL = 30 * 86400

_TEN = {"flood": "ngập lụt", "landslide": "sạt lở",
        "drought": "hạn thiếu nước", "wildfire": "cháy"}


def _ring_points(lat: float, lon: float) -> list[tuple[float, float]]:
    pts = [(lat, lon)]
    for r in RINGS_KM:
        dy = r / 111.32
        dx = r / (111.32 * max(0.2, math.cos(math.radians(lat))))
        for k in range(PER_RING):
            a = 2 * math.pi * k / PER_RING
            pts.append((lat + dy * math.sin(a), lon + dx * math.cos(a)))
    return pts


def terrain(lat: float, lon: float) -> dict | None:
    """Thửa này nằm ở đâu trong địa hình xung quanh.

    Đây là câu app thời tiết không trả lời được: nó biết trời sắp mưa bao nhiêu,
    nhưng không biết nước sẽ chảy về phía nào.
    """
    pts = _ring_points(lat, lon)
    els = realdata.elevation_multi(pts)
    if not els or els[0] is None:
        return None
    me = float(els[0])
    quanh = [float(e) for e in els[1:] if e is not None]
    if len(quanh) < PER_RING:
        return None

    cao_hon = sum(1 for e in quanh if e > me)
    pct_thap_hon = round(100.0 * cao_hon / len(quanh))
    slope = realdata.slope_deg(lat, lon)

    if pct_thap_hon >= 70:
        y = ("Thửa này TRŨNG hơn hầu hết đất xung quanh — khi mưa lớn, nước từ "
             "vùng lân cận dồn về đây trước và rút sau cùng.")
    elif pct_thap_hon <= 30:
        y = ("Thửa này CAO hơn hầu hết đất xung quanh — ít bị nước từ nơi khác "
             "dồn về, nhưng cũng giữ nước kém hơn khi hạn.")
    else:
        y = "Thửa này ở mức trung bình so với đất xung quanh về độ cao."

    return {
        "elevation_m": round(me, 1),
        "neighbours_sampled": len(quanh),
        "radius_km": max(RINGS_KM),
        "lower_than_pct": pct_thap_hon,
        "around_min_m": round(min(quanh), 1),
        "around_max_m": round(max(quanh), 1),
        "slope_deg": round(slope, 2) if slope is not None else None,
        "meaning": y,
    }


def history(lat: float, lon: float, years: int = 10) -> dict | None:
    """Mười năm hiểm hoạ của RIÊNG thửa này.

    ĐÂY LÀ CHỖ TÔI VIẾT SAI MỘT LẦN VÀ PHẢI LÀM LẠI, vì bản đầu tự tạo ra một
    con số vô nghĩa trông như sự thật.

    Bản đầu đếm số cửa sổ vượt ngưỡng nguy hiểm SAU hiệu chuẩn. Nhưng hiệu
    chuẩn định nghĩa ngưỡng đó là phân vị 97 của CHÍNH NƠI ĐÓ, nên theo đúng
    định nghĩa luôn có ~3% số cửa sổ vượt — ở bất kỳ đâu. Kết quả: Huế 109 lần,
    Bến Tre cũng 109 lần, và mọi nơi khác cũng sẽ 109. Một giám khảo bấm hai
    thửa rồi thấy cùng một con số là mất sạch niềm tin, một cách xứng đáng.

    Nay đo hai thứ THẬT SỰ phân biệt được nơi này với nơi khác:

      · MỨC NẶNG NHẤT trong mười năm, kèm ngày. Đây là con số tuyệt đối, so
        được giữa mọi nơi, và là thứ người ta nhớ ("trận năm 2020").
      · SỐ LẦN VƯỢT NGƯỠNG CHUNG CẢ NƯỚC — dùng lại đúng hằng số đã đo cho khối
        đối chiếu (58.336 cửa sổ, 16 điểm phủ cả nước). Ngưỡng này giống nhau ở
        mọi nơi nên đếm ra con số khác nhau, và chênh lệch đó có nghĩa.

    Mùa vụ thì giữ nguyên: tháng nào nguy hiểm nhất là đặc tính thật của một
    nơi, và lịch mùa vụ dạy chung cho cả tỉnh thường không khớp với thửa.
    """
    end = date.today() - timedelta(days=cal._LAG_DAYS)
    start = end.replace(year=end.year - years)
    rows = realdata.historical_weather(lat, lon, start.isoformat(), end.isoformat())
    if not rows or len(rows) < 365 * 3:
        return None

    W = cal._WINDOW
    out = {}
    for mid in ("flood", "landslide", "drought", "wildfire"):
        muc_chung = cal.NATIONAL_P97.get(mid)
        if muc_chung is None:
            continue
        floor = cal._FLOOR.get(mid, 0.0)

        # Tra địa hình MỘT LẦN, ngoài vòng lặp — cùng lý do như trong
        # calibration._rolling_peaks: toạ độ không di chuyển giữa các cửa sổ,
        # nên hỏi cao độ 3.646 lần là hỏi lại đúng một câu.
        fn = cal._RAW_FIXED.get(mid)
        dh = cal._TERRAIN.get(mid)
        if fn is None:
            continue
        terrain = dh(lat, lon) if dh else None
        if dh is not None and terrain is None:
            continue

        nang_nhat = (0.0, None)
        vuot = []
        for i in range(len(rows) - W):
            w = [{**r, "day": j} for j, r in enumerate(rows[i:i + W])]
            sr = fn(w, terrain)
            if not sr:
                continue
            v = max(x for _, _, x in sr)
            ngay = rows[i + W - 1]["date"]
            if v > nang_nhat[0]:
                nang_nhat = (v, ngay)
            if v >= muc_chung and v >= floor:
                vuot.append(ngay)

        if not vuot:
            out[mid] = {
                "name": _TEN[mid], "events": 0, "peak_month": None, "latest": None,
                "worst_value": round(nang_nhat[0], 1), "worst_date": nang_nhat[1],
                "national_threshold": muc_chung,
                "note": (f"Mười năm qua thửa này chưa lần nào {_TEN[mid]} vượt "
                         f"ngưỡng chung cả nước. Mức nặng nhất là "
                         f"{nang_nhat[0]:.0f} ngày {nang_nhat[1]}."),
            }
            continue

        thang = Counter(d[5:7] for d in vuot)
        top, dem = thang.most_common(1)[0]
        out[mid] = {
            "name": _TEN[mid],
            "events": len(vuot),
            "peak_month": int(top),
            "peak_month_events": dem,
            "latest": vuot[-1],
            "worst_value": round(nang_nhat[0], 1),
            "worst_date": nang_nhat[1],
            "national_threshold": muc_chung,
            "note": (f"Mười năm qua thửa này có {len(vuot)} lần {_TEN[mid]} vượt "
                     f"ngưỡng chung cả nước. Tháng {int(top)} nhiều nhất "
                     f"({dem} lần). Nặng nhất ngày {nang_nhat[1]}. "
                     f"Gần nhất {vuot[-1]}."),
        }
    return out or None


def build(lat: float, lon: float) -> dict:
    """Hồ sơ đầy đủ. Luôn trả dict, không ném lỗi lên API."""
    from app.services import cache_store, jobs
    key = cache_store.make_key("passport", round(lat, 3), round(lon, 3))
    hit = cache_store.get(key)
    if hit is not None:
        return hit

    dh, ls = jobs.gather([lambda: terrain(lat, lon), lambda: history(lat, lon)])

    if dh is None and ls is None:
        return {"available": False,
                "message": ("Chưa tải được địa hình và lịch sử cho điểm này. "
                            "Nguồn dữ liệu đang bận — thử lại sau ít phút.")}

    diem = []
    if dh:
        diem.append(f"cao {dh['elevation_m']} m, thấp hơn {dh['lower_than_pct']}% "
                    f"đất trong bán kính {dh['radius_km']:.0f} km")
    if ls:
        nhieu = max(ls.values(), key=lambda v: v["events"])
        if nhieu["events"]:
            diem.append(f"{nhieu['events']} lần {nhieu['name']} chạm ngưỡng nguy "
                        f"hiểm trong 10 năm, nhiều nhất tháng {nhieu['peak_month']}")

    out = {
        "available": True,
        "terrain": dh,
        "history": ls,
        "headline": " · ".join(diem) if diem else None,
        "why_unique": (
            "Ba con số trên là của RIÊNG thửa này, không phải của tỉnh hay của "
            "vùng. Một ứng dụng dự báo biết trời sắp mưa bao nhiêu, nhưng không "
            "biết thửa của bạn nằm cao hay trũng so với xung quanh, và không "
            "biết mười năm qua đã có bao nhiêu lần nước lên tới đây."),
        "caveat": (
            "Cao độ lấy từ mô hình số độ cao ~90 m, nên bờ ruộng và mương nhỏ "
            "không hiện ra. Số lần trong lịch sử đếm theo ngưỡng đã hiệu chuẩn "
            "cho chính nơi này — so được giữa các vùng khí hậu khác nhau, nhưng "
            "không phải số trận lụt được ghi nhận chính thức."),
    }
    cache_store.put(key, out, ttl_seconds=_TTL)
    return out
