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
from app.services import jobs_db, notify, verify
from app.services.reqlang import tr

# Cùng (thửa, mô-đun) chỉ báo lại khi mức rủi ro TĂNG (warning → danger), hoặc
# khi đã quá DEDUP_HOURS kể từ lần báo gần nhất. Bản trước là 12h và so khớp
# ĐÚNG mức: một tình trạng không đổi (vd Bến Tre ngập ở cùng mức) bị báo lại
# 2 lần/ngày — mỗi lần là một tin đẩy/email cho cùng một sự việc cũ.
DEDUP_HOURS = 72
_RISK_RANK = {"warning": 1, "danger": 2}


def sweep_user(user_id: int, db: Session, on_progress=None) -> dict:
    """Quét mọi thửa của MỘT người dùng. Trả về số liệu lượt quét.

    `on_progress(done, total, current_name)` — gọi trước mỗi thửa và khi xong,
    để việc chạy nền (radar_run) báo tiến độ ra giao diện."""
    from app.services import scan as scan_svc

    plots = db.execute(
        select(Plot).where(Plot.user_id == user_id)).scalars().all()
    if not plots:
        return {"plots_scanned": 0, "new_alerts": 0, "alerts": [],
                "message": tr("Chưa có thửa nào được lưu. Lưu thửa rồi chạy lại.",
                             "No plot saved yet. Save a plot then run this again.")}

    since = (datetime.now(timezone.utc).replace(tzinfo=None)
             - timedelta(hours=DEDUP_HOURS))
    created: list[Alert] = []
    for i, p in enumerate(plots):
        if on_progress:
            on_progress(i, len(plots), p.name)
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
            recent = db.execute(
                select(Alert.risk_level).where(
                    Alert.user_id == user_id, Alert.plot_id == p.id,
                    Alert.module_id == m.id, Alert.created_at >= since)
            ).scalars().all()
            # Đã báo trong cửa sổ ở mức BẰNG hoặc CAO HƠN → không báo lại.
            # Chỉ mức TĂNG mới đáng một tin mới trước khi hết cửa sổ.
            if recent and _RISK_RANK.get(m.risk_level, 0) <= max(
                    _RISK_RANK.get(lv, 0) for lv in recent):
                continue
            a = Alert(user_id=user_id, plot_id=p.id, module_id=m.id,
                      risk_level=m.risk_level,
                      headline=f"{p.name}: {m.headline}",
                      recommendation=m.recommendation)
            db.add(a)
            created.append(a)
    db.commit()
    if on_progress:
        on_progress(len(plots), len(plots), "")

    payload = [{"plot_id": a.plot_id, "module_id": a.module_id,
                "risk_level": a.risk_level, "headline": a.headline,
                "recommendation": a.recommendation} for a in created]

    # U01 — đưa cảnh báo ra khỏi phần mềm. Gửi hỏng không được làm hỏng lượt quét.
    #
    # N1 — email CHƯA XÁC THỰC thì KHÔNG gửi ra kênh ngoài nào (email/Zalo/
    # Telegram/webhook): một địa chỉ gõ sai lúc đăng ký hoặc một tài khoản tạo
    # hàng loạt không được phép biến TerraTwin thành máy gửi thư rác hộ tới
    # một hộp thư không phải của người đăng ký.
    #
    # N8 — VÀ phải đồng ý "nhận cảnh báo" (consent_alerts, mặc định BẬT — tắt
    # là lựa chọn chủ động). Cảnh báo vẫn được TẠO VÀ LƯU (đã add() ở trên) —
    # người dùng vẫn thấy trong app/sổ điểm dù thiếu MỘT trong hai điều kiện,
    # chỉ không phát ra kênh ngoài.
    user_row = db.get(User, user_id)
    can_dispatch = bool(user_row and getattr(user_row, "email_verified", 0)
                        and getattr(user_row, "consent_alerts", 1))
    channels = (db.execute(
        select(NotifyChannel).where(NotifyChannel.user_id == user_id,
                                    NotifyChannel.enabled == 1)).scalars().all()
               if can_dispatch else [])
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
    #
    # N8 — góp quan sát là một MỤC ĐÍCH riêng với "nhận cảnh báo": người đồng ý
    # nhận cảnh báo nhưng từ chối bị hỏi góp quan sát vẫn phải được tôn trọng,
    # kể cả khi kênh gửi (channels) đang mở vì consent_alerts đang bật.
    wants_asked = bool(user_row and getattr(user_row, "consent_observations", 1))
    asking = (_ask_one(user_id, channels, db) if wants_asked
              else {"asked": 0, "reason": tr("người dùng đã tắt góp quan sát",
                                             "user turned off observation sharing")})

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
        return {"asked": 0, "reason": tr("người dùng chưa nối kênh nhận tin nào",
                                         "user hasn't connected any notification channel")}
    try:
        pend = onetap.pending_questions(db, user_id, limit=1)
        if not pend:
            return {"asked": 0, "reason": tr("không có câu hỏi nào tới hạn",
                                             "no question is due")}
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


# ---------------------------------------------------------------- "Rà soát ngay"
#
# CHẠY NỀN qua hàng đợi BỀN (bảng jobs). Đo thật 27–28/9: 3 thửa mất 196–519
# giây vì lượt rà soát chạy đủ mô-đun nặng (ảnh vệ tinh). Giữ một kết nối HTTP
# ngần ấy thì 10 thửa chắc chắn vượt thời gian chờ của Render/proxy — người
# dùng thấy lỗi trong khi máy chủ vẫn đang quét đúng. Nay route trả job_id
# ngay, worker nền (main._jobs_poll_loop) chạy, giao diện hỏi tiến độ.

RADAR_JOB_KIND = "radar_run"


@jobs_db.register(RADAR_JOB_KIND)
def _radar_run_job(args: dict) -> dict:
    from app import db as _db          # tra lúc chạy — test đổi SessionLocal được
    from app.services import reqlang

    # Việc chạy trên luồng worker, không mang ngôn ngữ của request đã đẩy nó —
    # đặt lại để headline cảnh báo lưu xuống đúng ngữ người dùng đang dùng.
    reqlang.set_lang(args.get("lang"))
    job_id = args.get("_job_id")

    def _progress(done: int, total: int, current: str) -> None:
        jobs_db.report_progress(job_id, {"done": done, "total": total, "current": current})

    with _db.SessionLocal() as s:
        return sweep_user(int(args["user_id"]), s, on_progress=_progress)
