"""C05 Proactive Radar — quét thửa đất và sinh cảnh báo.

Tách khỏi route vì có HAI nơi gọi cùng một logic:
  1. Người dùng bấm "Rà soát ngay"      → sweep_user()
  2. Bộ hẹn giờ nội bộ chạy nền          → sweep_all()

VÌ SAO CÓ BỘ HẸN GIỜ NỘI BỘ: cảnh báo chủ động là điểm bán hàng số một của phần
mềm, nhưng nó chỉ chủ động nếu có thứ gì đó gọi nó khi người dùng đang ngủ. Gói
miễn phí của Render/Fly không có cron, nên nếu chỉ dựa vào cron ngoài thì deploy
xong tính năng này im lặng không chạy — người dùng tưởng có, thực tế không có.
Bộ hẹn giờ nằm trong tiến trình nên đi theo app tới bất kỳ chỗ nào deploy.

GIỚI HẠN PHẢI BIẾT: chạy trong tiến trình nghĩa là nếu chạy nhiều worker thì mỗi
worker quét một lần. Chống trùng 12 giờ ở dưới hấp thụ việc đó (cảnh báo trùng bị
bỏ), nhưng vẫn tốn lượt gọi Open-Meteo. Nhiều worker thì đặt
TERRATWIN_RADAR_INTERVAL_H=0 và dùng cron ngoài gọi /api/radar/run.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Alert, NotifyChannel, Plot, User
from app.schemas import Location
from app.services import notify, verify

DEDUP_HOURS = 12       # cùng một cảnh báo trong 12 h thì không ghi lại


def sweep_user(user_id: int, db: Session) -> dict:
    """Quét mọi thửa của MỘT người dùng. Trả về số liệu lượt quét."""
    from app.services import scan as scan_svc

    plots = db.execute(
        select(Plot).where(Plot.user_id == user_id)).scalars().all()
    if not plots:
        return {"plots_scanned": 0, "new_alerts": 0, "alerts": [],
                "message": "Chưa có thửa nào được lưu. Lưu thửa rồi chạy lại."}

    since = (datetime.now(timezone.utc).replace(tzinfo=None)
             - timedelta(hours=DEDUP_HOURS))
    created: list[Alert] = []
    for p in plots:
        try:
            # include_heavy=True: rà soát nền là chỗ DUY NHẤT chạy được mô-đun
            # quét cả vùng. Lũ từ thượng nguồn ập tới lúc ba giờ sáng, không
            # phải lúc người dùng đang mở app — bỏ nó ở đây là bỏ đúng lúc nó
            # đáng giá nhất.
            result = scan_svc.scan(
                Location(lat=p.lat, lon=p.lon, area_ha=p.area_ha),
                include_heavy=True)
        except Exception:
            # Một thửa hỏng (mất mạng, nguồn dữ liệu lỗi) không được làm hỏng
            # cả lượt quét của những thửa còn lại.
            continue
        for m in result.alerts:            # scan.alerts đã lọc chỉ dữ liệu thật
            dup = db.execute(
                select(Alert).where(
                    Alert.user_id == user_id, Alert.plot_id == p.id,
                    Alert.module_id == m.id, Alert.risk_level == m.risk_level,
                    Alert.created_at >= since)
            ).scalar_one_or_none()
            if dup:
                continue
            a = Alert(user_id=user_id, plot_id=p.id, module_id=m.id,
                      risk_level=m.risk_level,
                      headline=f"{p.name}: {m.headline}",
                      recommendation=m.recommendation)
            db.add(a)
            created.append(a)
    db.commit()

    payload = [{"plot_id": a.plot_id, "module_id": a.module_id,
                "risk_level": a.risk_level, "headline": a.headline,
                "recommendation": a.recommendation} for a in created]

    # U01 — đưa cảnh báo ra khỏi phần mềm. Gửi hỏng không được làm hỏng lượt quét.
    channels = db.execute(
        select(NotifyChannel).where(NotifyChannel.user_id == user_id,
                                    NotifyChannel.enabled == 1)).scalars().all()
    delivery = notify.dispatch(channels, payload)
    db.commit()

    # M1 — đẩy Web Push cho cảnh báo mới. Kênh cảnh báo sống-được-ngay: không cần
    # người dùng nối Zalo/Telegram, chỉ cần đã bật thông báo trên trình duyệt.
    # Best-effort: chưa cấu hình VAPID / chưa đăng ký thiết bị thì bỏ qua êm.
    if created:
        try:
            from app.services import push
            worst = max(created, key=lambda a: {"danger": 2, "warning": 1}.get(a.risk_level, 0))
            n = len(created)
            title = "⚠️ TerraTwin — cảnh báo mới" if n == 1 else f"⚠️ TerraTwin — {n} cảnh báo mới"
            push.send_to_user(db, user_id, title, worst.headline, "/")
        except Exception:      # noqa: BLE001 — push hỏng không làm hỏng lượt quét
            pass

    # ĐÓNG VÒNG LẶP — hỏi lại về một cảnh báo cũ đã tới lúc biết kết quả.
    #
    # Đặt ở đây, ngay sau khi gửi cảnh báo mới, là có chủ đích: đây là thời điểm
    # DUY NHẤT trong cả phần mềm chắc chắn chạy đều đặn mà không cần ai nhớ ra.
    # Hỏi bằng một lượt gửi riêng chứ không kèm vào cảnh báo mới, vì trộn "sắp
    # có lũ" với "hôm trước có lũ thật không" trong cùng một tin là cách chắc
    # chắn để không nhận được câu trả lời nào.
    asking = _ask_one(user_id, channels, db)

    return {
        "plots_scanned": len(plots),
        "new_alerts": len(created),
        "dedup_window_hours": DEDUP_HOURS,
        "alerts": payload,
        "delivery": delivery,
        "asked": asking,
    }


def _ask_one(user_id: int, channels: list, db: Session) -> dict:
    """Gửi đúng MỘT câu hỏi một chạm, nếu có câu nào đang chờ."""
    from app.services import onetap

    if not channels:
        return {"asked": 0, "reason": "người dùng chưa nối kênh nhận tin nào"}
    try:
        pend = onetap.pending_questions(db, user_id, limit=1)
        if not pend:
            return {"asked": 0, "reason": "không có câu hỏi nào tới hạn"}
        q = dict(pend[0])
        q["link"] = f"{onetap.base_url()}/tap/{q['token']}"
        return notify.ask(channels, [q])
    except Exception as e:
        # Hỏi hỏng tuyệt đối không được làm hỏng việc cảnh báo. Cảnh báo là thứ
        # cứu được mùa màng; câu hỏi chỉ làm mô hình tốt lên.
        return {"asked": 0, "error": type(e).__name__}


_LAST_SWEEP_KEY = "radar:last_sweep"
_LAST_MISS_SWEEP_KEY = "radar:last_miss_sweep"
# sweep_misses quét ngược 90 ngày × mọi thửa — nặng hơn hẳn lượt quét cảnh báo
# thường (7 ngày tới). Không nên chạy mỗi lần sweep_all được gọi (cron ngoài
# gọi mỗi 6h) — throttle về ~1 lần/ngày. 20h chứ không phải 24h để chừa biên
# cho lịch cron lệch giờ (xem ghi chú keepwarm.yml).
MISS_SWEEP_MIN_GAP_H = 20


def sweep_all(db: Session) -> dict:
    """Quét cho MỌI người dùng có thửa đã lưu. Dùng cho lượt chạy nền."""
    ids = db.execute(
        select(User.id).join(Plot, Plot.user_id == User.id).distinct()
    ).scalars().all()

    users, plots, alerts, sent, failed, asked = 0, 0, 0, 0, 0, 0
    for uid in ids:
        try:
            r = sweep_user(uid, db)
        except Exception:
            db.rollback()
            continue
        users += 1
        plots += r["plots_scanned"]
        alerts += r["new_alerts"]
        d = r.get("delivery") or {}
        sent += int(d.get("sent", 0) or 0)
        failed += int(d.get("failed", 0) or 0)
        asked += int((r.get("asked") or {}).get("asked", 0) or 0)

    # CHẤM ĐIỂM những cảnh báo cũ đã tới hạn. Gắn vào lượt quét nền thay vì làm
    # một bộ hẹn giờ thứ hai: gói miễn phí của Render/Fly không có cron, thêm
    # một tiến trình nữa là thêm một thứ im lặng không chạy sau khi deploy.
    try:
        scored = verify.sweep(db)
    except Exception as e:
        db.rollback()
        scored = {"error": type(e).__name__}

    # A — LẦN BỎ SÓT PHẢI ĐƯỢC QUÉT, KHÔNG CHỈ CHẤM CẢNH BÁO ĐÃ PHÁT.
    #
    # Trước đây sweep_all() không hề gọi verify.sweep_misses() ở đâu cả — nghĩa
    # là số "miss" trong sổ điểm luôn = 0 và POD tự động = 100%, bất kể phần
    # mềm thật sự bỏ sót bao nhiêu lần. Gọi ở đây, cùng chỗ với verify.sweep(),
    # vì lý do y hệt: không dựng thêm một tiến trình nền thứ hai.
    misses = _maybe_sweep_misses(db)

    result = {"notifications_asked": asked, "scored": scored, "misses": misses,
              "users_scanned": users, "plots_scanned": plots,
              "new_alerts": alerts, "notifications_sent": sent,
              "notifications_failed": failed}
    _log_sweep(result)
    return result


def _maybe_sweep_misses(db: Session) -> dict:
    from datetime import datetime, timedelta, timezone

    from app.services import cache_store, verify as verify_svc

    now = datetime.now(timezone.utc)
    last = cache_store.get(_LAST_MISS_SWEEP_KEY)
    if last:
        try:
            if now - datetime.fromisoformat(last) < timedelta(hours=MISS_SWEEP_MIN_GAP_H):
                return {"skipped": "đã quét trong ~24h qua"}
        except ValueError:
            pass
    try:
        r = verify_svc.sweep_misses(db)
    except Exception as e:
        db.rollback()
        return {"error": type(e).__name__}
    cache_store.put(_LAST_MISS_SWEEP_KEY, now.isoformat(), ttl_seconds=7 * 86400)
    return r


def _log_sweep(result: dict) -> None:
    """Ghi lại MỌI lượt quét (kể cả 0 cảnh báo) vào nơi bền (bảng kv_cache),
    để /api/health có thể báo lần quét gần nhất thật sự chạy khi nào — kể cả
    khi nó hoàn toàn im lặng vì không có gì để báo."""
    from datetime import datetime, timezone

    from app.services import cache_store

    misses = result.get("misses") or {}
    scored = result.get("scored") or {}
    cache_store.put(_LAST_SWEEP_KEY, {
        "at": datetime.now(timezone.utc).isoformat(),
        "users_scanned": result["users_scanned"],
        "plots_scanned": result["plots_scanned"],
        "plots_with_real_data": misses.get("plots_scanned"),
        "plots_skipped_429": misses.get("plots_failed"),
        "new_alerts": result["new_alerts"],
        "notifications_sent": result["notifications_sent"],
        "notifications_failed": result["notifications_failed"],
        "verified": scored.get("verified"),
        "misses_recorded": misses.get("misses_recorded"),
    }, ttl_seconds=7 * 86400)


def last_sweep() -> dict | None:
    """Bản ghi lượt quét nền gần nhất, cho /api/health. None nếu chưa quét lần nào."""
    from app.services import cache_store
    return cache_store.get(_LAST_SWEEP_KEY)
