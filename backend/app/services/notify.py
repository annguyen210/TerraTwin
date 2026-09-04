"""U01 Action & Automation — đưa cảnh báo RA KHỎI phần mềm.

Một hệ thống cảnh báo thiên tai chỉ có giá trị nếu người cần biết thực sự nhận
được. Radar (C05) sinh cảnh báo; module này gửi chúng đi.

Bốn kênh, cả bốn đều chạy thật:
  zalo     — Zalo ZNS, gửi theo SỐ ĐIỆN THOẠI. Kênh của người Việt.
  telegram — Bot API, gửi theo chat_id. Chạy được ngay, không cần xét duyệt.
  webhook  — POST JSON tới URL của bạn, để nối vào hệ thống nội bộ.
  email    — SMTP (đặt TERRATWIN_SMTP_* trong .env).

VÌ SAO THÊM ZALO VÀ TELEGRAM — một phép đo phơi ra lỗ hổng chí mạng: radar chạy
đều 6 giờ một lần và đã sinh hàng trăm cảnh báo, nhưng KHÔNG cảnh báo nào có
đường tới điện thoại một người làm ruộng. Webhook là thứ của lập trình viên;
email không phải kênh của nông dân Việt Nam. Cả một hệ thống cảnh báo sớm dừng
lại ở đúng bước cuối cùng.

  · Zalo là kênh thật của thị trường này, nhưng OA/ZNS đòi giấy phép kinh doanh
    và duyệt mẫu tin — mất thời gian LỊCH, không phải thời gian làm.
  · Telegram vì thế được thêm cùng lúc: nó chạy được ngay hôm nay với một bot
    token miễn phí, không xét duyệt gì, nên tính năng cảnh báo đến tay người
    dùng không phải nằm chờ một hồ sơ hành chính.

NGUYÊN TẮC: gửi hỏng KHÔNG được làm hỏng việc quét. Mọi lỗi đều bắt lại và ghi
vào `last_error` của kênh để người dùng tự xem, thay vì làm sập cả lượt rà soát.

KHÔNG BAO GIỜ IM LẶNG GIẢ VỜ THÀNH CÔNG: kênh chưa cấu hình trả về câu báo lỗi
nói rõ thiếu biến môi trường nào. Một hệ thống cảnh báo báo "đã gửi" trong khi
không gửi gì là thứ nguy hiểm hơn hẳn một hệ thống không có cảnh báo.

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


# ---------- Zalo (ZNS — gửi theo số điện thoại) ----------

ZALO_ZNS = "https://business.openapi.zalo.me/message/template"
_ZNS_MAX = 400          # trần một tham số ZNS; cắt trước để Zalo khỏi từ chối


def zalo_configured() -> bool:
    return bool(os.environ.get("TERRATWIN_ZALO_TOKEN")
                and os.environ.get("TERRATWIN_ZALO_TEMPLATE_ID"))


def normalize_phone(raw: str) -> str | None:
    """Số điện thoại Việt Nam về dạng 84xxxxxxxxx mà ZNS đòi hỏi.

    Nhận mọi cách người ta thật sự gõ: "0912 345 678", "+84912345678",
    "84912345678". Trả None nếu không phải số di động Việt Nam hợp lệ — thà từ
    chối lúc tạo kênh còn hơn im lặng không gửi được về sau.
    """
    d = "".join(c for c in (raw or "") if c.isdigit())
    if d.startswith("84"):
        d = d[2:]
    elif d.startswith("0"):
        d = d[1:]
    # Di động Việt Nam sau khi bỏ số 0 đầu: 9 chữ số, bắt đầu bằng 3/5/7/8/9.
    if len(d) != 9 or d[0] not in "35789":
        return None
    return "84" + d


def send_zalo(phone: str, text: str) -> str | None:
    """Gửi một tin ZNS. Trả None nếu gửi được, hoặc chuỗi mô tả lỗi."""
    token = os.environ.get("TERRATWIN_ZALO_TOKEN")
    template = os.environ.get("TERRATWIN_ZALO_TEMPLATE_ID")
    if not token or not template:
        return ("Chưa cấu hình Zalo — đặt TERRATWIN_ZALO_TOKEN và "
                "TERRATWIN_ZALO_TEMPLATE_ID trong .env. "
                "(OA/ZNS cần giấy phép kinh doanh và duyệt mẫu tin.)")
    num = normalize_phone(phone)
    if not num:
        return f"Số điện thoại không hợp lệ: {phone!r}."

    # ZNS chỉ gửi được nội dung đã điền vào MẪU TIN đã duyệt trước; không thể
    # gửi văn bản tự do. Tên tham số phải khớp mẫu bạn đăng ký với Zalo —
    # TERRATWIN_ZALO_PARAM đổi được mà không phải sửa mã.
    key = os.environ.get("TERRATWIN_ZALO_PARAM", "content")
    body = {"phone": num, "template_id": template,
            "template_data": {key: text[:_ZNS_MAX]}}
    try:
        req = urllib.request.Request(
            ZALO_ZNS, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"content-type": "application/json", "access_token": token})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        return f"Zalo trả mã {e.code}."
    except Exception as e:
        return f"Không gửi được tới Zalo: {type(e).__name__}."
    # Zalo trả HTTP 200 kèm mã lỗi TRONG thân tin. Không đọc `error` ở đây thì
    # mọi lần gửi hỏng đều bị ghi nhận là thành công.
    if int(data.get("error", 0) or 0) != 0:
        return f"Zalo báo lỗi {data.get('error')}: {data.get('message')}"
    return None


# ---------- Telegram (chạy được ngay, không cần xét duyệt) ----------

def telegram_configured() -> bool:
    return bool(os.environ.get("TERRATWIN_TELEGRAM_TOKEN"))


def send_telegram(chat_id: str, text: str) -> str | None:
    token = os.environ.get("TERRATWIN_TELEGRAM_TOKEN")
    if not token:
        return ("Chưa cấu hình Telegram — tạo bot với @BotFather rồi đặt "
                "TERRATWIN_TELEGRAM_TOKEN trong .env.")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = {"chat_id": str(chat_id).strip(), "text": text[:4000],
            "disable_web_page_preview": False}
    try:
        req = urllib.request.Request(
            url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        return f"Telegram trả mã {e.code}."
    except Exception as e:
        return f"Không gửi được tới Telegram: {type(e).__name__}."
    if not data.get("ok"):
        return f"Telegram báo lỗi: {data.get('description')}"
    return None


def channel_status() -> dict:
    """Kênh nào đã sẵn sàng gửi thật — để giao diện nói thẳng thay vì để người
    dùng tạo một kênh rồi mới phát hiện nó chưa bao giờ gửi được."""
    return {
        "zalo": zalo_configured(),
        "telegram": telegram_configured(),
        "email": smtp_configured(),
        "webhook": True,          # không cần cấu hình phía máy chủ
    }


# ---------- Gửi một loạt cảnh báo ----------

def _format_text(alerts: list[dict]) -> str:
    """Bản ngắn cho Zalo/Telegram. Điện thoại, không phải màn hình máy tính."""
    n = len(alerts)
    nguy = any(a["risk_level"] == "danger" for a in alerts)
    lines = [f"{'‼️ NGUY HIỂM' if nguy else '⚠️ Cảnh báo'} — TerraTwin phát hiện "
             f"{n} việc trên thửa của bác:", ""]
    for a in alerts[:5]:
        lines.append(f"• {a['headline']}")
        if a.get("recommendation"):
            lines.append(f"  → {a['recommendation']}")
    if n > 5:
        lines.append(f"…và {n - 5} cảnh báo nữa.")
    lines += ["", "Dựa trên dữ liệu vệ tinh và thời tiết thật, có sai số. "
                  "Hãy đối chiếu với những gì bác thấy ngoài đồng."]
    return "\n".join(lines)


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
        elif ch.kind == "zalo":
            err = send_zalo(ch.target, _format_text(picked))
        elif ch.kind == "telegram":
            err = send_telegram(ch.target, _format_text(picked))
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


# ---------- Hỏi lại sau khi cảnh báo đã trôi qua ----------

def _format_question(q: dict, link: str) -> str:
    return (
        f"TerraTwin hỏi lại một câu thôi ạ:\n\n"
        f"{q['question']}\n\n"
        f"Bấm để trả lời (một chạm, không cần đăng nhập):\n{link}\n\n"
        f"Câu trả lời của bác dùng để chỉnh lại ngưỡng cảnh báo cho chính vùng "
        f"này. Không hiện tên bác ở đâu cả."
    )


def ask(channels: list, questions: list[dict]) -> dict:
    """Gửi câu hỏi một chạm ra các kênh của người dùng.

    Tách hẳn khỏi `dispatch()` vì đây là việc khác về bản chất và xảy ra vào lúc
    khác: dispatch báo trước khi chuyện xảy ra, ask hỏi lại sau khi nó đã qua.
    Gộp chung sẽ khiến câu hỏi bị lọc theo `min_level` của kênh — mà mức rủi ro
    của một cảnh báo đã trôi qua thì không còn liên quan gì tới việc có nên hỏi
    hay không. Cảnh báo mức nhẹ hoá ra lại là loại đáng hỏi nhất, vì đó chính
    là chỗ hay báo bừa.

    Mỗi lượt chỉ hỏi MỘT câu, kể cả khi có nhiều câu đang chờ. Nhồi ba câu vào
    một tin là cách chắc chắn nhất để không nhận được câu trả lời nào.
    """
    if not questions:
        return {"asked": 0, "failed": 0, "results": []}

    q = questions[0]
    link = q.get("link") or ""
    text = _format_question(q, link)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    results, asked, failed = [], 0, 0

    for ch in channels:
        if not ch.enabled:
            continue
        # Webhook nhận nguyên dạng máy đọc được; ba kênh còn lại nhận chữ.
        if ch.kind == "webhook":
            err = send_webhook(ch.target, {
                "source": "terratwin", "type": "question",
                "question": q, "link": link,
                "sent_at": now.isoformat(timespec="seconds")})
        elif ch.kind == "email":
            err = send_email(ch.target, "[TerraTwin] Một câu hỏi về thửa của bạn",
                             text)
        elif ch.kind == "zalo":
            err = send_zalo(ch.target, text)
        elif ch.kind == "telegram":
            err = send_telegram(ch.target, text)
        else:
            err = f"Kênh không hỗ trợ: {ch.kind}"

        ch.last_error = err
        if err is None:
            ch.last_sent_at = now
            asked += 1
        else:
            failed += 1
        results.append({"channel_id": ch.id, "kind": ch.kind,
                        "alert_id": q.get("alert_id"), "error": err})

    return {"asked": asked, "failed": failed, "alert_id": q.get("alert_id"),
            "results": results}
