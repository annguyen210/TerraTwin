"""Phân tích ảnh quang học Sentinel-2 cho 4 mũi nhọn cần "nhìn thấy" thửa đất.

Bốn bài toán, một nguồn ảnh:
  pest          — cây bị stress bất thường và stress đó có LOANG LỔ không
  yield         — đường cong sinh trưởng NDVI: đang ở giai đoạn nào, còn bao lâu
  storm_damage  — mất thảm thực vật đột ngột giữa hai kỳ
  illegal_build — bề mặt xây dựng mới xuất hiện giữa hai kỳ

MỘT Ý QUAN TRỌNG VỀ SÂU BỆNH: hạn làm NDVI giảm ĐỀU cả thửa; sâu bệnh và nấm
làm NDVI giảm LOANG LỔ theo ổ. Vì vậy độ lệch chuẩn trong ô (std) tăng mạnh
trong khi trung bình giảm là dấu hiệu phân biệt được hai nguyên nhân — đó là
thứ một bản tin thời tiết cấp tỉnh không bao giờ nói được cho riêng thửa của bạn.

MỌI HÀM Ở ĐÂY TRẢ None KHI KHÔNG CÓ ẢNH. Không có nhánh nào sinh số giả.
"""
from __future__ import annotations

import statistics
from datetime import date, timedelta

from app.services import sentinel

# Ngưỡng đọc NDVI cho vùng nhiệt đới ẩm. Tổng hợp từ thực hành viễn thám phổ
# thông; là mốc ĐỊNH HƯỚNG, không phải hằng số vật lý.
NDVI_BARE = 0.20        # dưới mức này gần như không còn thảm thực vật
NDVI_SPARSE = 0.40      # thưa / mới gieo / vừa thu hoạch
NDVI_HEALTHY = 0.60     # tán kín, cây khỏe

MIN_COVERAGE = 40.0     # % pixel nhìn thấy đất thì mới coi là một quan sát


def _clear(series):
    return [r for r in (series or [])
            if r["mean"] is not None and r["coverage_pct"] >= MIN_COVERAGE]


def cover_label(ndvi: float) -> str:
    if ndvi >= NDVI_HEALTHY:
        return "tán kín, cây khỏe"
    if ndvi >= NDVI_SPARSE:
        return "thảm thực vật vừa phải"
    if ndvi >= NDVI_BARE:
        return "thưa — mới gieo, vừa thu hoạch, hoặc đang suy"
    return "gần như trống — đất trần, mặt nước hoặc bề mặt cứng"


# --------------------------------------------------------------- sâu bệnh

def stress(lat: float, lon: float, buffer_m: float = 300.0) -> dict | None:
    """Phát hiện cây stress bất thường, và đoán xem đều hay loang lổ.

    So sánh quan sát mới nhất với chính thửa đó trong ~4 tháng trước, chứ không
    so với một ngưỡng cố định — vì NDVI 0,5 là tốt với lúa mới sạ và là tệ với
    vườn dừa trưởng thành. Nền so sánh phải là chính nó.
    """
    ndvi = _clear(sentinel.index_series(lat, lon, "NDVI", days=120,
                                        interval_days=10, buffer_m=buffer_m))
    if len(ndvi) < 4:
        return None

    latest = ndvi[-1]
    hist = ndvi[:-1]
    means = [r["mean"] for r in hist]
    base = statistics.median(means)
    spread = statistics.pstdev(means) if len(means) > 1 else 0.0

    # z-score so nền của CHÍNH thửa này.
    z = (latest["mean"] - base) / spread if spread > 0.02 else 0.0
    drop_pct = round(100.0 * (latest["mean"] - base) / base, 1) if base else 0.0

    # Loang lổ: std trong ô hiện tại so với std trung bình các kỳ trước.
    hist_std = statistics.median([r["std"] for r in hist]) or 0.0
    patchiness = (round(latest["std"] / hist_std, 2)
                  if hist_std > 0.005 else None)

    if latest["mean"] < NDVI_BARE:
        level, verdict = "danger", "thửa gần như không còn thảm thực vật"
    elif z <= -2.0 or drop_pct <= -25.0:
        level, verdict = "danger", "sức sống cây giảm mạnh bất thường"
    elif z <= -1.0 or drop_pct <= -12.0:
        level, verdict = "warning", "sức sống cây đang giảm so với chính thửa này"
    else:
        level, verdict = "safe", "sức sống cây trong khoảng bình thường của thửa"

    if level == "safe":
        cause = None
    elif patchiness is not None and patchiness >= 1.4:
        cause = ("LOANG LỔ — mức độ không đều trong thửa tăng "
                 f"{patchiness}× so với bình thường. Kiểu này hợp với sâu bệnh, "
                 "nấm hoặc ngập cục bộ hơn là hạn (hạn thường làm giảm đều).")
    elif patchiness is not None and patchiness <= 0.9:
        cause = ("ĐỀU khắp thửa — hợp với nguyên nhân toàn vùng (hạn, mặn, rét, "
                 "vừa thu hoạch) hơn là ổ sâu bệnh.")
    else:
        cause = "Mức độ không đều chưa rõ rệt để phân biệt nguyên nhân."

    return {
        "available": True, "level": level, "verdict": verdict, "cause_hint": cause,
        "ndvi_now": latest["mean"], "ndvi_baseline": round(base, 4),
        "change_pct": drop_pct, "z_score": round(z, 2),
        "patchiness_ratio": patchiness,
        "observed_on": latest["date"], "coverage_pct": latest["coverage_pct"],
        "observations": len(ndvi),
        "cover": cover_label(latest["mean"]),
        "series": ndvi,
        "method": ("NDVI Sentinel-2 mỗi 10 ngày trong 120 ngày. Nền so sánh là "
                   "trung vị của chính thửa này, không phải ngưỡng cố định. Độ "
                   "loang lổ = std hiện tại / std nền."),
        "caveat": ("Vệ tinh thấy CÂY YẾU, không thấy CON SÂU. Kết quả này nói "
                   "'chỗ này bất thường, ra xem ngay', không nói bệnh gì. Ô đo "
                   "600×600 m nên ổ nhỏ hơn ~0,1 ha có thể bị trung bình hoá mất."),
    }


# --------------------------------------------------------------- năng suất

def growth(lat: float, lon: float, buffer_m: float = 300.0) -> dict | None:
    """Đường cong sinh trưởng NDVI — đang ở giai đoạn nào của mùa vụ.

    CỐ Ý KHÔNG trả tấn/ha. Quy từ NDVI ra sản lượng cần hệ số hiệu chuẩn theo
    giống và theo vùng; không có hệ số đó mà vẫn in ra "6,2 tấn/ha" là con số
    nghe như đo được nhưng thực chất là bịa. Thứ trả về là những gì ảnh THẬT SỰ
    cho biết: cây đang lên hay đang chín, đỉnh sinh trưởng ở đâu, tích luỹ sinh
    khối cả vụ so với chính thửa này ra sao.
    """
    s = _clear(sentinel.index_series(lat, lon, "NDVI", days=180,
                                     interval_days=10, buffer_m=buffer_m))
    if len(s) < 5:
        return None

    peak = max(s, key=lambda r: r["mean"])
    latest = s[-1]
    i_peak = s.index(peak)
    since_peak = (date.fromisoformat(latest["date"])
                  - date.fromisoformat(peak["date"])).days

    # Xu thế 3 kỳ gần nhất (~30 ngày).
    tail = [r["mean"] for r in s[-3:]]
    slope = (tail[-1] - tail[0]) / max(1, len(tail) - 1)

    # Tích phân NDVI ≈ tổng sinh khối tích luỹ — chỉ báo năng suất kinh điển.
    integral = round(sum(r["mean"] for r in s) * 10.0 / 30.0, 2)  # đơn vị "NDVI·tháng"

    if latest["mean"] < NDVI_BARE:
        stage = "đất trống / vừa thu hoạch"
        advice = "Chưa có cây trên thửa. Theo dõi lại sau khi xuống giống."
    elif slope > 0.02:
        stage = "đang sinh trưởng, chưa tới đỉnh"
        advice = ("Cây còn đang lên. Đây là lúc bón thúc và giữ nước có hiệu quả "
                  "nhất — sau đỉnh thì can thiệp gần như không thay đổi được nữa.")
    elif since_peak <= 15 and abs(slope) <= 0.02:
        stage = "quanh đỉnh sinh trưởng"
        advice = ("Cây đạt tán tối đa. Từ đây NDVI giảm là chín tự nhiên, không "
                  "phải hỏng — đừng nhầm hai thứ đó.")
    elif slope < -0.02:
        stage = f"đang chín / xuống lá (qua đỉnh {since_peak} ngày)"
        advice = ("Đang vào giai đoạn chín. Với lúa, thu hoạch thường rơi vào "
                  "khoảng 25–35 ngày sau đỉnh NDVI — bám thêm khuyến cáo giống "
                  "và quan sát trực tiếp bông.")
    else:
        stage = "ổn định"
        advice = "Chưa thấy chuyển giai đoạn rõ rệt."

    return {
        "available": True,
        "stage": stage, "advice": advice,
        "ndvi_now": latest["mean"], "ndvi_peak": peak["mean"],
        "peak_date": peak["date"], "days_since_peak": since_peak,
        "observed_on": latest["date"],
        "trend_per_10d": round(slope, 4),
        "vigor_vs_peak_pct": round(100.0 * latest["mean"] / peak["mean"], 1)
        if peak["mean"] else None,
        "ndvi_integral": integral,
        "observations": len(s), "peak_index": i_peak,
        "series": s,
        "method": ("NDVI Sentinel-2 mỗi 10 ngày trong 180 ngày. Giai đoạn suy ra "
                   "từ vị trí so với đỉnh và độ dốc 30 ngày gần nhất. Tích phân "
                   "NDVI là chỉ báo sinh khối tích luỹ."),
        "caveat": ("KHÔNG quy ra tấn/ha. Muốn có con số sản lượng phải hiệu chuẩn "
                   "bằng năng suất thật đã thu của chính vùng này với chính giống "
                   "đó — hãy gửi kết quả thu hoạch qua mục Ghi nhận thực tế, đủ "
                   "vài vụ là phần mềm hiệu chuẩn được."),
    }


# --------------------------------------------------------------- thay đổi bề mặt

def _windows(days_gap: int, window: int) -> tuple[tuple[date, date], tuple[date, date]]:
    today = date.today()
    a_end = today
    a_start = today - timedelta(days=window)
    b_end = today - timedelta(days=days_gap)
    b_start = b_end - timedelta(days=window)
    return (b_start, b_end), (a_start, a_end)


def vegetation_loss(lat: float, lon: float, gap_days: int = 45,
                    window: int = 25, buffer_m: float = 300.0) -> dict | None:
    """Mất thảm thực vật đột ngột giữa hai kỳ — nền của bản đồ thiệt hại.

    Đây là phát hiện MẤT THẢM THỰC VẬT, không phải "thiệt hại do bão" nói riêng:
    bão, lũ, cháy, chặt phá hay thu hoạch đều làm NDVI sụt. Phần mềm nói đúng
    thứ nó đo được rồi để người dùng đối chiếu với sự việc họ biết — nhận vơ
    nguyên nhân là cách nhanh nhất để một cảnh báo mất uy tín.
    """
    before, after = _windows(gap_days, window)
    ch = sentinel.change_between(lat, lon, "NDVI", before, after, buffer_m)
    if ch is None:
        return None

    d = ch["delta"]
    if d <= -0.25:
        level, verdict = "danger", "thảm thực vật mất trên diện rộng"
    elif d <= -0.12:
        level, verdict = "warning", "thảm thực vật suy giảm rõ rệt"
    elif d >= 0.12:
        level, verdict = "safe", "thảm thực vật đang phục hồi / phát triển"
    else:
        level, verdict = "safe", "không thấy thay đổi đáng kể"

    return {
        "available": True, "level": level, "verdict": verdict,
        **ch,
        "before_cover": cover_label(ch["before"]["mean"]),
        "after_cover": cover_label(ch["after"]["mean"]),
        "possible_causes": (
            ["bão hoặc gió mạnh", "ngập lụt kéo dài", "cháy", "chặt/phá",
             "thu hoạch theo lịch"] if d <= -0.12 else []),
        "method": ("So NDVI trung bình hai cửa sổ Sentinel-2 "
                   f"({window} ngày mỗi kỳ, cách nhau {gap_days} ngày), đã lọc mây."),
        "caveat": ("Vệ tinh đo MẤT THẢM THỰC VẬT, không tự biết nguyên nhân. "
                   "Thu hoạch đúng lịch cũng làm NDVI sụt y hệt bão. Hãy đối "
                   "chiếu với việc bạn biết đã xảy ra trên thửa."),
    }


def new_construction(lat: float, lon: float, gap_days: int = 365,
                     window: int = 45, buffer_m: float = 300.0) -> dict | None:
    """Bề mặt xây dựng mới giữa hai kỳ (mặc định cách nhau 1 năm).

    Dùng ĐỒNG THỜI hai chỉ số: NDBI tăng (thêm bê tông/mái/đường) VÀ NDVI giảm
    (mất cây ở chỗ đó). Một mình NDBI dễ báo nhầm vì đất khô mùa nắng cũng làm
    NDBI tăng; đòi hỏi cả hai cùng đổi loại được phần lớn báo nhầm theo mùa.
    """
    before, after = _windows(gap_days, window)
    ndbi = sentinel.change_between(lat, lon, "NDBI", before, after, buffer_m)
    ndvi = sentinel.change_between(lat, lon, "NDVI", before, after, buffer_m)
    if ndbi is None or ndvi is None:
        return None

    built_up = ndbi["delta"] >= 0.08
    veg_lost = ndvi["delta"] <= -0.10
    both = built_up and veg_lost

    if both and ndbi["delta"] >= 0.15:
        level = "danger"
        verdict = "bề mặt cứng mới xuất hiện trên diện đáng kể"
    elif both:
        level = "warning"
        verdict = "có dấu hiệu bề mặt cứng mới"
    elif built_up:
        level = "safe"
        verdict = ("chỉ số xây dựng tăng nhưng cây không giảm — nhiều khả năng "
                   "là đất khô theo mùa, chưa đủ cơ sở kết luận")
    else:
        level, verdict = "safe", "không thấy bề mặt xây dựng mới"

    return {
        "available": True, "level": level, "verdict": verdict,
        "ndbi": ndbi, "ndvi": ndvi,
        "built_up_signal": built_up, "vegetation_loss_signal": veg_lost,
        "both_signals": both,
        "method": ("So hai kỳ Sentinel-2 cách nhau "
                   f"{gap_days} ngày ({window} ngày mỗi kỳ). Kết luận chỉ đưa ra "
                   "khi NDBI tăng ≥0,08 VÀ NDVI giảm ≥0,10 — đòi hỏi cả hai để "
                   "loại báo nhầm do mùa khô."),
        "caveat": ("ĐÂY KHÔNG PHẢI KẾT LUẬN PHÁP LÝ. Phần mềm chỉ nói 'chỗ này "
                   "có thay đổi, đi kiểm tra'. Việc công trình có phép hay không "
                   "phải tra hồ sơ địa chính — vệ tinh không biết giấy phép. Ô đo "
                   "600×600 m nên một căn nhà lẻ có thể chìm trong trung bình."),
    }
