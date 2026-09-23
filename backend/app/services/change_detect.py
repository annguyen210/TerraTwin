"""A7 — phát hiện biến động NDVI 24 tháng bằng BFAST/CUSUM rút gọn.

Ý TƯỞNG. mrv.build() đã có so sánh NDVI "năm nay vs năm ngoái" — hai điểm,
nhạy với đúng MỘT cảnh chụp xui (mây, góc chụp, mùa vụ lệch ngày). Ở đây dùng
CẢ chuỗi 24 tháng để tách "mùa vụ lặp lại" (lúa ba vụ lên-xuống đều đặn) khỏi
"đổi thật" (mất tán cây một lần, không hồi phục) — đúng câu hỏi A7 đặt ra.

HAI BƯỚC, RÚT GỌN TỪ BFAST (Verbesselt 2010) + CUSUM cổ điển:

  1. TÁCH MÙA VỤ (giống bước "Seasonal" của BFAST) — hồi quy tuyến tính với
     các số hạng sin/cos ở chu kỳ năm (~365 ngày) VÀ chu kỳ ~4 tháng (lúa ba
     vụ/năm ≈ 121,75 ngày). Phần dư (residual) sau khi trừ mùa vụ đã fit thì
     lúa gần như phẳng — dao động mùa vụ đã bị hồi quy "nuốt" hết.
  2. CUSUM trên phần dư — tổng tích luỹ độ lệch so với trung bình. Một đổi
     THẬT (mất tán cây, không hồi phục) tạo một khúc gãy dốc trong đường CUSUM;
     nhiễu ngẫu nhiên thì đường CUSUM dập dềnh quanh 0. Điểm |CUSUM| lớn nhất
     là ƯỚC LƯỢNG mốc thời gian đổi; thống kê kiểm định dùng xấp xỉ cầu Brown
     (ngưỡng 1,36 ≈ mức ý nghĩa 5%, xem Page 1954 / Kolmogorov-Smirnov).

KHÔNG dùng statsmodels/scipy — chỉ numpy (bắt buộc theo yêu cầu), vì backend
production chỉ đảm bảo có numpy (xem requirements.txt), không có scipy.
"""
from __future__ import annotations

from datetime import date

import numpy as np

# Phải sụt sâu, không chỉ lệch nhẹ mùa vụ — 0,15 là khoảng cách hợp lý giữa
# tán rừng khép kín (NDVI 0,6–0,8) và đất trống/dọn quang (NDVI 0,1–0,3).
MIN_LEVEL_DROP = 0.15
# Ngưỡng thống kê CUSUM chuẩn hoá (cầu Brown), xấp xỉ mức ý nghĩa 5%.
CUSUM_THRESHOLD = 1.36
MIN_POINTS = 8            # cần đủ điểm hai phía mốc gãy mới tin được
MIN_SIDE_POINTS = 3


def _design_matrix(t_days: np.ndarray) -> np.ndarray:
    """Cột hằng số + hai bộ hài (năm, và lúa ba vụ). CỐ Ý không có cột xu
    hướng tuyến tính: một đợt mất tán cây là một BƯỚC NHẢY, không phải dốc
    tuyến tính — thêm cột trend sẽ khiến hồi quy "chia sẻ" một phần bước nhảy
    đó vào đường trend, làm nhạt tín hiệu CUSUM cần bắt (đã thấy khi test)."""
    year = 2 * np.pi * t_days / 365.25
    tri = 2 * np.pi * t_days / (365.25 / 3.0)   # ba vụ/năm ≈ 121,75 ngày/vụ
    return np.column_stack([
        np.ones_like(t_days),
        np.sin(year), np.cos(year),
        np.sin(tri), np.cos(tri),
    ])


def detect_from_series(dates: list[str], values: list[float]) -> dict:
    """Lõi thuật toán, tách khỏi việc gọi mạng — để test được bằng chuỗi giả lập
    (lúa ba vụ / phá rừng biết trước tháng) mà không cần ảnh vệ tinh thật.
    """
    n = len(values)
    if n < MIN_POINTS:
        return {
            "available": False,
            "reason": "not_enough_points",
            "message": f"Cần ít nhất {MIN_POINTS} cảnh sống trong 24 tháng, "
                       f"chỉ có {n}. Không đủ để phân biệt mùa vụ với đổi thật.",
        }

    d0 = date.fromisoformat(dates[0])
    t = np.array([(date.fromisoformat(d) - d0).days for d in dates], dtype=float)
    y = np.array(values, dtype=float)

    X = _design_matrix(t)
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ coef

    centered = resid - resid.mean()
    cusum = np.cumsum(centered)
    k = int(np.argmax(np.abs(cusum)))

    s = float(resid.std(ddof=1)) if n > 1 else 0.0
    test_stat = (float(np.max(np.abs(cusum))) / (s * np.sqrt(n))) if s > 1e-9 else 0.0

    before, after = resid[:k + 1], resid[k + 1:]
    enough_both_sides = len(before) >= MIN_SIDE_POINTS and len(after) >= MIN_SIDE_POINTS
    level_shift = float(after.mean() - before.mean()) if enough_both_sides else 0.0

    # CHỈ tính là "mất tán cây": khúc gãy có ý nghĩa thống kê VÀ mức giảm đủ
    # sâu VÀ đi xuống (âm) — một khúc gãy đi LÊN (vd ruộng mới trồng lại) không
    # phải là mất tán, dù cùng độ mạnh thống kê.
    changed = (enough_both_sides and test_stat > CUSUM_THRESHOLD
              and level_shift <= -MIN_LEVEL_DROP)

    return {
        "available": True,
        "n_scenes": n,
        "window": [dates[0], dates[-1]],
        "change_detected": bool(changed),
        "change_date": dates[k] if changed else None,
        "level_shift_ndvi": round(level_shift, 4),
        "test_statistic": round(test_stat, 3),
        "threshold": CUSUM_THRESHOLD,
        "message": (
            f"Phát hiện mất tán cây quanh {dates[k]} — NDVI giảm "
            f"{abs(level_shift):.3f} và không hồi phục trong phần còn lại "
            f"của chuỗi 24 tháng."
            if changed else
            "Không phát hiện đổi bền vững — dao động quan sát được nằm trong "
            "biên độ mùa vụ hoặc nhiễu bình thường."
        ),
    }


def detect(lat: float, lon: float, buffer_m: float = 300.0,
          months: int = 24) -> dict:
    """A7 — mặt tiền: tự lấy chuỗi NDVI 24 tháng qua Microsoft Planetary
    Computer rồi chạy detect_from_series(). Tách riêng để detect_from_series()
    test được không chạm mạng."""
    from app.services import mpc

    series = mpc.index_series(lat, lon, "NDVI", days=months * 31, buffer_m=buffer_m)
    if series is None:
        return {"available": False, "reason": "no_imagery",
                "message": "Không lấy được ảnh Sentinel-2 cho vị trí này."}
    if not series:
        return {"available": False, "reason": "no_clear_scenes",
                "message": "Không có cảnh đủ quang mây trong 24 tháng qua."}

    return detect_from_series([r["date"] for r in series], [r["mean"] for r in series])
