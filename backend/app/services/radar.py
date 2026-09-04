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

    return {"notifications_asked": asked, "scored": scored,
            "users_scanned": users, "plots_scanned": plots,
            "new_alerts": alerts, "notifications_sent": sent,
            "notifications_failed": failed}
