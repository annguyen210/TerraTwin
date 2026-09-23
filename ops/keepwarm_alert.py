"""N11 — báo Telegram khi /api/health chuyển sang degraded/broken.

CHỈ báo khi ĐỔI TRẠNG THÁI (ok → degraded, degraded → broken, ...): cron này
chạy mỗi ~10 phút (xem keepwarm.yml) — báo mỗi lần chạy trong lúc service vẫn
đang hỏng sẽ spam Telegram vô ích và làm người nhận tắt thông báo luôn.

Không có secret TERRATWIN_ALERT_BOT_TOKEN / TERRATWIN_ALERT_CHAT_ID thì bỏ
qua ÊM (exit 0, không lỗi) — N11 là tính năng tuỳ chọn, thiếu secret không
được làm đỏ workflow keepwarm vốn đang làm việc quan trọng hơn (giữ service ấm).

Không dùng thư viện ngoài (urllib chuẩn) — script này chạy trong GitHub
Actions, không muốn thêm bước pip install chỉ để gọi hai API HTTP đơn giản.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

# Console Windows mặc định cp1252, không giải mã được tiếng Việt của print() ở
# dưới — CI (ubuntu-latest) vốn đã UTF-8 nên reconfigure là no-op ở đó, nhưng
# chạy thử trên máy Windows sẽ crash UnicodeEncodeError nếu thiếu dòng này.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

DEFAULT_HEALTH_URL = "https://terratwin-api.onrender.com/api/health"
DEFAULT_STATE_FILE = "keepwarm-state.txt"


def fetch_health(url: str, timeout: float = 30.0) -> dict | None:
    """Trả JSON của /api/health, hoặc None nếu không gọi được (service chết)."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def classify(health: dict | None) -> str:
    """broken = không gọi được / JSON hỏng. degraded/ok = đúng theo health.status."""
    if not health or "status" not in health:
        return "broken"
    status = str(health.get("status", "")).lower()
    return status if status in ("ok", "degraded") else "broken"


def format_message(prev: str, cur: str, health_url: str) -> str:
    icon = {"ok": "✅", "degraded": "⚠️", "broken": "🔴"}.get(cur, "❓")
    label = {"ok": "BÌNH THƯỜNG", "degraded": "SUY GIẢM (hết hạn mức nguồn dữ liệu miễn phí)",
             "broken": "HỎNG (không gọi được /api/health)"}.get(cur, cur)
    return (f"{icon} TerraTwin — đổi trạng thái: {prev} → {cur}\n"
            f"{label}\n{health_url}")


def notify_telegram(token: str, chat_id: str, text: str, timeout: float = 15.0) -> bool:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return 200 <= r.status < 300
    except Exception:
        return False


def read_state(path: str) -> str | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip() or None
    except FileNotFoundError:
        return None


def write_state(path: str, state: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(state)


def run(health_url: str, state_file: str, token: str | None, chat_id: str | None) -> str:
    """Trả về trạng thái mới (đã ghi vào state_file). Tách khỏi main() để test được
    không cần chạm biến môi trường / sys.exit."""
    health = fetch_health(health_url)
    cur = classify(health)
    prev = read_state(state_file)

    if prev is None:
        print(f"Chưa có trạng thái trước đó — ghi nhận lần đầu: {cur}.")
    elif prev == cur:
        print(f"Trạng thái không đổi ({cur}) — không báo.")
    else:
        print(f"ĐỔI TRẠNG THÁI: {prev} → {cur}.")
        if not token or not chat_id:
            print("Thiếu TERRATWIN_ALERT_BOT_TOKEN/TERRATWIN_ALERT_CHAT_ID — bỏ qua báo, chỉ ghi nhận.")
        else:
            ok = notify_telegram(token, chat_id, format_message(prev, cur, health_url))
            print("Đã gửi Telegram." if ok else "Gửi Telegram THẤT BẠI (không làm hỏng workflow).")

    write_state(state_file, cur)
    return cur


def main() -> int:
    health_url = os.environ.get("TERRATWIN_HEALTH_URL", DEFAULT_HEALTH_URL)
    state_file = os.environ.get("TERRATWIN_STATE_FILE", DEFAULT_STATE_FILE)
    token = os.environ.get("TERRATWIN_ALERT_BOT_TOKEN") or None
    chat_id = os.environ.get("TERRATWIN_ALERT_CHAT_ID") or None
    run(health_url, state_file, token, chat_id)
    return 0   # N11 không được làm đỏ workflow keepwarm dù báo lỗi hay không.


if __name__ == "__main__":
    sys.exit(main())
