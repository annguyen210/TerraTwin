"""U01 Action & Automation — đưa cảnh báo RA KHỎI phần mềm.

Một hệ thống cảnh báo thiên tai chỉ có giá trị nếu người cần biết thực sự nhận
được. Radar (C05) sinh cảnh báo; module này gửi chúng đi.

Hai kênh, cả hai đều chạy thật:
  webhook — POST JSON tới URL của bạn. Đây cũng là cách nối sang Zalo OA,
            Telegram, Slack, hay hệ thống nội bộ: nhận webhook rồi chuyển tiếp.
  email   — SMTP (đặt TERRATWIN_SMTP_* trong .env).

NGUYÊN TẮC: gửi hỏng KHÔNG được làm hỏng việc quét. Mọi lỗi đều bắt lại và ghi
vào `last_error` của kênh để người dùng tự xem, thay vì làm sập cả lượt rà soát.

BẢO MẬT: webhook chỉ cho phép http/https và CHẶN địa chỉ nội bộ — nếu không,
người dùng có thể biến máy chủ thành công cụ quét mạng nội bộ (SSRF).
"""
from __future__ import annotations

import ipaddress
import json
import os
import smtplib
import socket
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.message import EmailMessage

TIMEOUT = 10.0
_LEVEL_ORDER = {"safe": 0, "unknown": 0, "warning": 1, "danger": 2}


def level_at_least(level: str, minimum: str) -> bool:
    return _LEVEL_ORDER.get(level, 0) >= _LEVEL_ORDER.get(minimum, 1)


# ---------- Webhook ----------

def validate_webhook(url: str) -> str | None:
    """Trả thông báo lỗi nếu URL không an toàn, None nếu hợp lệ.

    Chặn địa chỉ nội bộ (loopback, link-local, private, metadata cloud) để máy
    chủ TerraTwin không bị dùng làm bàn đạp quét mạng nội bộ.
    """
    try:
        u = urllib.parse.urlparse(url)
    except ValueError:
        return "URL không hợp lệ."
    if u.scheme not in ("http", "https"):
        return "Chỉ chấp nhận http hoặc https."
    if not u.hostname:
        return "URL thiếu tên máy chủ."
    try:
        infos = socket.getaddrinfo(u.hostname, None)
    except socket.gaierror:
        return f"Không phân giải được tên miền '{u.hostname}'."
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast):
            return ("Địa chỉ nội bộ không được phép (chống lạm dụng máy chủ để "
                    "quét mạng riêng).")
    return None


def send_webhook(url: str, payload: dict) -> str | None:
    """Trả None nếu gửi được, hoặc chuỗi mô tả lỗi."""
    err = validate_webhook(url)
    if err:
        return err
    try:
        req = urllib.request.Request(
            url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"content-type": "application/json",
                     "user-agent": "TerraTwin/1.0"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            if 200 <= r.status < 300:
                return None
            return f"Máy chủ trả mã {r.status}."
    except urllib.error.HTTPError as e:
        return f"Máy chủ trả mã {e.code}."
    except Exception as e:
        return f"Không gửi được: {type(e).__name__}."


# ---------- Email (SMTP) ----------

def smtp_configured() -> bool:
    return bool(os.environ.get("TERRATWIN_SMTP_HOST"))


def send_email(to: str, subject: str, body: str) -> str | None:
    host = os.environ.get("TERRATWIN_SMTP_HOST")
    if not host:
        return "Chưa cấu hình SMTP (đặt TERRATWIN_SMTP_HOST trong .env)."
    port = int(os.environ.get("TERRATWIN_SMTP_PORT", "587"))
    user = os.environ.get("TERRATWIN_SMTP_USER")
    pw = os.environ.get("TERRATWIN_SMTP_PASSWORD")
    sender = os.environ.get("TERRATWIN_SMTP_FROM", user or "terratwin@localhost")

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(host, port, timeout=TIMEOUT) as s:
            if port != 25:
                try:
                    s.starttls()
                except smtplib.SMTPException:
                    pass          # máy chủ không hỗ trợ TLS — vẫn thử gửi
            if user and pw:
                s.login(user, pw)
            s.send_message(msg)
        return None
    except Exception as e:
        return f"SMTP lỗi: {type(e).__name__}."


# ---------- Gửi một loạt cảnh báo ----------

def _format_email(alerts: list[dict]) -> tuple[str, str]:
    n = len(alerts)
    worst = "NGUY HIỂM" if any(a["risk_level"] == "danger" for a in alerts) else "cảnh báo"
    subject = f"[TerraTwin] {n} {worst} mới trên thửa đất của bạn"
    lines = [f"TerraTwin phát hiện {n} cảnh báo mới:", ""]
    for a in alerts:
        mark = "‼️" if a["risk_level"] == "danger" else "⚠️"
        lines += [f"{mark} {a['headline']}", f"   → {a['recommendation']}", ""]
    lines += ["—",
              "Cảnh báo dựa trên dữ liệu vệ tinh và thời tiết thật, kèm sai số.",
              "Không đảm bảo 100% — hãy đối chiếu với quan sát thực địa."]
    return subject, "\n".join(lines)


def dispatch(channels: list, alerts: list[dict]) -> dict:
    """Gửi `alerts` tới mọi kênh đang bật. Trả tóm tắt; không bao giờ ném lỗi.

    `channels` là list NotifyChannel (ORM); hàm cập nhật last_sent_at/last_error
    nhưng KHÔNG commit — bên gọi commit.
    """
    if not alerts:
        return {"sent": 0, "failed": 0, "results": []}

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    results, sent, failed = [], 0, 0

    for ch in channels:
        if not ch.enabled:
            continue
        picked = [a for a in alerts if level_at_least(a["risk_level"], ch.min_level)]
        if not picked:
            results.append({"channel_id": ch.id, "kind": ch.kind,
                            "skipped": True,
                            "reason": f"không có cảnh báo đạt mức {ch.min_level}"})
            continue

        if ch.kind == "webhook":
            err = send_webhook(ch.target, {
                "source": "terratwin", "alert_count": len(picked),
                "alerts": picked,
                "sent_at": now.isoformat(timespec="seconds"),
            })
        elif ch.kind == "email":
            subject, body = _format_email(picked)
            err = send_email(ch.target, subject, body)
        else:
            err = f"Kênh không hỗ trợ: {ch.kind}"

        ch.last_error = err
        if err is None:
            ch.last_sent_at = now
            sent += 1
        else:
            failed += 1
        results.append({"channel_id": ch.id, "kind": ch.kind,
                        "alerts_sent": len(picked), "error": err})

    return {"sent": sent, "failed": failed, "results": results}
