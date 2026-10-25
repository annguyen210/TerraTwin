"""HẠN MỨC THAO TÁC NẶNG — theo IP (ẩn danh) hoặc theo tài khoản, cửa sổ trượt.

Giới hạn chung theo IP (main.py, 240/phút từ 25/10/2026) bảo vệ khỏi dội request, nhưng KHÔNG đủ
cho các loại thao tác dưới đây (và cho dò mật khẩu/mã hai lớp của MỘT tài khoản — "login", "otp"):
  · PHÁT HÀNH HỒ SƠ — ghi vào sổ minh bạch CHỈ-ĐƯỢC-THÊM, không xoá được. Không giới hạn
    thì một script ẩn danh làm bẩn sổ vĩnh viễn bằng hàng nghìn hồ sơ rác.
  · SÀNG LỌC VỆ TINH — mỗi lần ~15 lượt gọi Planetary Computer; dội liên tục là làm
    hỏng nguồn dữ liệu chung của mọi người dùng.
Ẩn danh được dùng thử thoải mái ở mức một nông hộ; nhiều hơn thì đăng nhập (gắn trách
nhiệm với tài khoản). Bộ đếm trong bộ nhớ: khởi động lại thì đếm lại — chấp nhận được
cho máy chủ một tiến trình; nhiều tiến trình thì chuyển sang bảng CSDL.
"""
from __future__ import annotations

import hashlib
import os
import threading
import time
from collections import OrderedDict, defaultdict

_LOCK = threading.Lock()
# loại → (khoá → danh sách thời điểm), theo thứ tự chạm gần nhất (cũ nhất ở đầu). Kiểm 25/10/2026: bản cũ là MỘT dict
# defaultdict(deque) không bao giờ dọn — blocked() tạo deque rỗng ngay cả khi chỉ đọc, mỗi email sai thêm một khoá:
# đo 100.000 email ngẫu nhiên = +86 MB (~900 byte/khoá, deque rỗng đã ~600 byte), hết cửa sổ vẫn còn đủ 100.000 khoá.
_HITS: dict[str, "OrderedDict[str, list[float]]"] = defaultdict(OrderedDict)
MAX_KEYS = {"login": 50_000, "login_ip": 50_000}    # trần cứng số khoá; vượt thì bỏ khoá ít được chạm nhất
SWEEP_EVERY_OPS, SWEEP_EVERY_S = 1_000, 60.0         # dọn khoá đã quá cửa sổ: mỗi ~1.000 lượt gọi hoặc mỗi 60 s
_ops = 0
_last_sweep = 0.0

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
    # GĐ7 — lượt nhập mã hai lớp theo tài khoản: chặn dò 10^6 mã khi mật khẩu đã lộ. Không tắt qua env.
    "otp": (5, 5, 900),
    # Kiểm 25/10/2026 — lượt nhập SAI mật khẩu theo email (chặn dò mật khẩu một tài khoản; giới hạn chung theo IP
    # 240/phút không đủ). Chỉ đếm lượt sai: blocked() xem trước, hit() ghi lượt sai, clear() khi đăng nhập đúng.
    # Theo email CHUNG (mọi IP) — rộng hơn, để người ngoài không khoá được tài khoản admin chỉ bằng 10 lần gõ sai.
    "login": (50, 50, 900),
    # Theo email + IP — chặn dò mật khẩu từ một máy (kiểm 25/10/2026: 2 bộ đếm thay cho 1).
    "login_ip": (10, 10, 900),
    "feedback": (int(os.environ.get("TERRATWIN_ANON_FEEDBACK_PER_DAY", "10")),
                 int(os.environ.get("TERRATWIN_USER_FEEDBACK_PER_DAY", "300")), 86_400),
}


def _window(kind: str) -> float:
    return LIMITS[kind][2] if kind in LIMITS else 86_400


def _prune(ts: list[float], now: float, window: float) -> None:
    i = 0
    while i < len(ts) and now - ts[i] > window:
        i += 1
    if i:
        del ts[:i]


def _sweep_locked(now: float) -> None:
    """Xoá khoá rỗng hoặc có lượt cuối đã quá cửa sổ của loại đó."""
    for kind, od in list(_HITS.items()):
        w = _window(kind)
        stale = [k for k, ts in od.items() if not ts or now - ts[-1] > w]
        for k in stale:
            del od[k]
        # Bảng băm của dict không tự co khi xoá — xoá quá nửa thì dựng lại để trả bộ nhớ (đo: còn ~11 MB sau khi dọn
        # 100.000 khoá nếu không dựng lại).
        if stale and len(stale) * 2 > len(od) + len(stale):
            _HITS[kind] = OrderedDict(od)


def _tick_locked(now: float) -> None:
    global _ops, _last_sweep
    _ops += 1
    if _ops >= SWEEP_EVERY_OPS or now - _last_sweep >= SWEEP_EVERY_S:
        _ops, _last_sweep = 0, now
        _sweep_locked(now)


def _series_locked(kind: str, key: str, create: bool) -> list[float] | None:
    """Danh sách thời điểm của khoá; create=False thì KHÔNG tạo khoá mới (chỉ đọc)."""
    od = _HITS[kind] if create else _HITS.get(kind)
    if od is None:
        return None
    ts = od.get(key)
    if not create:
        return ts
    if ts is None:
        cap = MAX_KEYS.get(kind)
        while cap and len(od) >= cap:
            od.popitem(last=False)
        ts = od[key] = []
    else:
        od.move_to_end(key)
    return ts


def take(kind: str, key: str, signed_in: bool, mult: int = 1) -> int | None:
    """Ghi một lượt. Trả None nếu còn hạn mức, hoặc số giây phải chờ nếu đã hết.
    `mult` = hệ số của gói người đăng nhập (plans.mult_for) — chỉ nhân hạn mức, không mở khoá gì thêm."""
    anon, user, window = LIMITS[kind]
    cap = user * max(1, mult) if signed_in else anon
    if cap <= 0:
        return None
    now = time.time()
    with _LOCK:
        _tick_locked(now)
        ts = _series_locked(kind, key, True)
        _prune(ts, now, window)
        if len(ts) >= cap:
            return int(window - (now - ts[0])) + 1
        ts.append(now)
    return None


def blocked(kind: str, key: str, signed_in: bool = True) -> int | None:
    """Như take() nhưng KHÔNG ghi lượt và KHÔNG tạo khoá: số giây phải chờ nếu đã hết hạn mức, None nếu còn."""
    anon, user, window = LIMITS[kind]
    cap = user if signed_in else anon
    if cap <= 0:
        return None
    now = time.time()
    with _LOCK:
        _tick_locked(now)
        ts = _series_locked(kind, key, False)
        if not ts:
            return None
        _prune(ts, now, window)
        return int(window - (now - ts[0])) + 1 if len(ts) >= cap else None


def hit(kind: str, key: str) -> None:
    """Ghi một lượt (vd. một lần nhập sai) mà không chặn — chặn là việc của blocked()."""
    now = time.time()
    with _LOCK:
        _tick_locked(now)
        ts = _series_locked(kind, key, True)
        _prune(ts, now, _window(kind))
        ts.append(now)


def clear(kind: str, key: str) -> None:
    with _LOCK:
        od = _HITS.get(kind)
        if od is not None:
            od.pop(key, None)


def size(kind: str | None = None) -> int:
    """Số khoá đang giữ (đo bộ nhớ / test)."""
    with _LOCK:
        return sum(len(od) for k, od in _HITS.items() if kind is None or k == kind)


# ---- Đăng nhập: HAI bộ đếm lượt SAI (kiểm 25/10/2026) ----
def _ip_key(email_key: str, ip: str) -> str:
    return hashlib.sha256(f"{email_key}|{ip}".encode("utf-8")).hexdigest()[:32]


def login_blocked(email_key: str, ip: str) -> int | None:
    """Số giây phải chờ nếu email+IP đã sai 10 lần HOẶC email đã sai 50 lần (mọi IP) trong 15 phút; None nếu còn."""
    waits = [w for w in (blocked("login_ip", _ip_key(email_key, ip)), blocked("login", email_key)) if w is not None]
    return max(waits) if waits else None


def login_failed(email_key: str, ip: str) -> None:
    hit("login_ip", _ip_key(email_key, ip))
    hit("login", email_key)


def login_ok(email_key: str, ip: str) -> None:
    clear("login_ip", _ip_key(email_key, ip))
    clear("login", email_key)


def reset(kind: str | None = None) -> None:
    with _LOCK:
        if kind is None:
            _HITS.clear()
        else:
            _HITS.pop(kind, None)
            if kind == "login":
                _HITS.pop("login_ip", None)
