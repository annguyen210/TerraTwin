"""HẠN MỨC THAO TÁC NẶNG — theo IP (ẩn danh) hoặc theo tài khoản, cửa sổ trượt.

Giới hạn chung 120 request/phút/IP (main.py) bảo vệ khỏi dội request, nhưng KHÔNG đủ
cho hai loại thao tác:
  · PHÁT HÀNH HỒ SƠ — ghi vào sổ minh bạch CHỈ-ĐƯỢC-THÊM, không xoá được. Không giới hạn
    thì một script ẩn danh làm bẩn sổ vĩnh viễn bằng hàng nghìn hồ sơ rác.
  · SÀNG LỌC VỆ TINH — mỗi lần ~15 lượt gọi Planetary Computer; dội liên tục là làm
    hỏng nguồn dữ liệu chung của mọi người dùng.
Ẩn danh được dùng thử thoải mái ở mức một nông hộ; nhiều hơn thì đăng nhập (gắn trách
nhiệm với tài khoản). Bộ đếm trong bộ nhớ: khởi động lại thì đếm lại — chấp nhận được
cho máy chủ một tiến trình; nhiều tiến trình thì chuyển sang bảng CSDL.
"""
from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque

_LOCK = threading.Lock()
_HITS: dict[str, deque] = defaultdict(deque)

# (ẩn danh, đã đăng nhập) — số lần trong cửa sổ (giây). Chỉnh qua biến môi trường.
LIMITS = {
    "dossier": (int(os.environ.get("TERRATWIN_ANON_DOSSIERS_PER_DAY", "5")),
                int(os.environ.get("TERRATWIN_USER_DOSSIERS_PER_DAY", "300")), 86_400),
    "screen": (int(os.environ.get("TERRATWIN_ANON_SCREENS_PER_HOUR", "20")),
               int(os.environ.get("TERRATWIN_USER_SCREENS_PER_HOUR", "200")), 3_600),
    # Lượt GỬI của một thiết bị IoT (mỗi lượt tới 200 số đo gửi bù) — theo thiết bị.
    "iot": (int(os.environ.get("TERRATWIN_IOT_POSTS_PER_HOUR", "120")),
            int(os.environ.get("TERRATWIN_IOT_POSTS_PER_HOUR", "120")), 3_600),
    # Phiếu góp ý thí điểm: ẩn danh đủ cho một người, đăng nhập đủ cho cán bộ HTX nhập
    # lại cả xấp phiếu giấy sau buổi tập huấn.
    "feedback": (int(os.environ.get("TERRATWIN_ANON_FEEDBACK_PER_DAY", "10")),
                 int(os.environ.get("TERRATWIN_USER_FEEDBACK_PER_DAY", "300")), 86_400),
}


def take(kind: str, key: str, signed_in: bool) -> int | None:
    """Ghi một lượt. Trả None nếu còn hạn mức, hoặc số giây phải chờ nếu đã hết."""
    anon, user, window = LIMITS[kind]
    cap = user if signed_in else anon
    if cap <= 0:
        return None
    now = time.time()
    k = f"{kind}:{key}"
    with _LOCK:
        dq = _HITS[k]
        while dq and now - dq[0] > window:
            dq.popleft()
        if len(dq) >= cap:
            return int(window - (now - dq[0])) + 1
        dq.append(now)
    return None


def reset() -> None:
    with _LOCK:
        _HITS.clear()
