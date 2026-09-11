"""C11 Bring-Your-Own-Data · C05 Proactive Radar / S08 Autonomous Agent.

C11: người dùng tải lên danh sách điểm của mình (CSV hoặc GeoJSON) rồi chấm
     rủi ro hàng loạt — hợp tác xã có 200 thửa không phải bấm 200 lần.
C05: quét lại toàn bộ thửa đã lưu, chỉ ghi cảnh báo MỚI (không lặp lại cùng
     một cảnh báo mỗi lần quét), để về sau nối Zalo/email mà không spam.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import auth
from app.db import Alert, Dataset, Event, NotifyChannel, Twin, User, get_session
from app.schemas import VN_LAT_MAX, VN_LAT_MIN, VN_LON_MAX, VN_LON_MIN, Location
from app.services import notify, radar, twin as twin_svc

router = APIRouter(tags=["data"])

_MAX_ROWS = 2000
_MAX_BYTES = 2_000_000


# ---------- Kiểu dữ liệu ----------

class UploadIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: str = Field(pattern="^(csv|geojson)$")
    content: str = Field(max_length=_MAX_BYTES)


class DatasetOut(BaseModel):
    id: int
    name: str
    kind: str
    row_count: int
    created_at: datetime


class AlertOut(BaseModel):
    id: int
    plot_id: int | None
    module_id: str
    risk_level: str
    headline: str
    recommendation: str
    created_at: datetime
    acknowledged: bool
    # Kết quả chấm lại sau khi cửa sổ dự báo trôi qua (services/verify.py).
    # None = chưa tới hạn chấm. Trả cả bằng chứng chứ không chỉ kết luận, để
    # người dùng đối chiếu được thay vì phải tin.
    outcome: str | None = None
    observed_peak: float | None = None
    verify_source: str = ""
    verify_note: str = ""


def _alert_out(a: Alert) -> AlertOut:
    return AlertOut(
        id=a.id, plot_id=a.plot_id, module_id=a.module_id,
        risk_level=a.risk_level, headline=a.headline,
        recommendation=a.recommendation, created_at=a.created_at,
        acknowledged=bool(a.acknowledged), outcome=a.outcome,
        observed_peak=a.observed_peak, verify_source=a.verify_source or "",
        verify_note=a.verify_note or "")


# ---------- Phân tích tệp tải lên ----------

def _in_vn(lat: float, lon: float) -> bool:
    return VN_LAT_MIN <= lat <= VN_LAT_MAX and VN_LON_MIN <= lon <= VN_LON_MAX


def _parse_csv(text: str) -> list[dict]:
    """Chấp nhận cột lat/lon đặt tên linh hoạt (tiếng Việt lẫn tiếng Anh)."""
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(422, "CSV không có dòng tiêu đề.")
    norm = {(f or "").strip().lower(): f for f in reader.fieldnames}

    def pick(*names):
        for n in names:
            if n in norm:
                return norm[n]
        return None

    f_lat = pick("lat", "latitude", "vido", "vĩ độ", "vi_do")
    f_lon = pick("lon", "lng", "longitude", "kinhdo", "kinh độ", "kinh_do")
    f_name = pick("name", "ten", "tên", "label", "thua", "thửa")
    if not f_lat or not f_lon:
        raise HTTPException(
            422, f"CSV cần cột toạ độ. Đang có: {', '.join(reader.fieldnames)}. "
                 "Chấp nhận tên: lat/latitude/vido và lon/lng/longitude/kinhdo.")

    rows, skipped = [], 0
    for i, r in enumerate(reader):
        if len(rows) >= _MAX_ROWS:
            break
        try:
            lat, lon = float(r[f_lat]), float(r[f_lon])
        except (TypeError, ValueError):
            skipped += 1
            continue
        if not _in_vn(lat, lon):
            skipped += 1
            continue
        rows.append({"name": (r.get(f_name) or f"Điểm {i+1}").strip()[:120],
                     "lat": lat, "lon": lon})
    if not rows:
        raise HTTPException(422, "Không có dòng nào hợp lệ (toạ độ phải nằm trong Việt Nam).")
    return rows


def _parse_geojson(text: str) -> list[dict]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise HTTPException(422, f"GeoJSON không hợp lệ: {e.msg}")
    feats = data.get("features") if isinstance(data, dict) else None
    if not isinstance(feats, list):
        raise HTTPException(422, "GeoJSON cần có mảng 'features'.")

    rows = []
    for i, f in enumerate(feats):
        if len(rows) >= _MAX_ROWS:
            break
        geom = (f or {}).get("geometry") or {}
        if geom.get("type") != "Point":
            continue                     # bản này chỉ nhận điểm
        coords = geom.get("coordinates") or []
        if len(coords) < 2:
            continue
        lon, lat = float(coords[0]), float(coords[1])
        if not _in_vn(lat, lon):
            continue
        props = f.get("properties") or {}
        rows.append({"name": str(props.get("name") or f"Điểm {i+1}")[:120],
                     "lat": lat, "lon": lon})
    if not rows:
        raise HTTPException(422, "Không tìm thấy điểm hợp lệ trong Việt Nam.")
    return rows


# ---------- C11 endpoints ----------

@router.post("/api/datasets", response_model=DatasetOut, status_code=201)
def upload(body: UploadIn, user: User = Depends(auth.current_user),
           db: Session = Depends(get_session)) -> DatasetOut:
    rows = _parse_csv(body.content) if body.kind == "csv" else _parse_geojson(body.content)
    d = Dataset(user_id=user.id, name=body.name, kind=body.kind,
                payload=json.dumps(rows, ensure_ascii=False), row_count=len(rows))
    db.add(d)
    db.commit()
    db.refresh(d)
    return DatasetOut(id=d.id, name=d.name, kind=d.kind,
                      row_count=d.row_count, created_at=d.created_at)


@router.get("/api/datasets", response_model=list[DatasetOut])
def list_datasets(user: User = Depends(auth.current_user),
                  db: Session = Depends(get_session)) -> list[DatasetOut]:
    rows = db.execute(
        select(Dataset).where(Dataset.user_id == user.id)
        .order_by(Dataset.created_at.desc())).scalars().all()
    return [DatasetOut(id=d.id, name=d.name, kind=d.kind,
                       row_count=d.row_count, created_at=d.created_at) for d in rows]


@router.delete("/api/datasets/{ds_id}", status_code=204,
               response_class=Response, response_model=None)
def delete_dataset(ds_id: int, user: User = Depends(auth.current_user),
                   db: Session = Depends(get_session)):
    d = db.get(Dataset, ds_id)
    if d is None or d.user_id != user.id:
        raise HTTPException(404, "Không tìm thấy dữ liệu.")
    db.delete(d)
    db.commit()


@router.post("/api/datasets/{ds_id}/score")
def score_dataset(ds_id: int, limit: int = 50,
                  user: User = Depends(auth.current_user),
                  db: Session = Depends(get_session)) -> dict:
    """Chấm TerraScore hàng loạt cho các điểm đã tải lên, xếp rủi ro cao trước."""
    from app.services import terrascore

    d = db.get(Dataset, ds_id)
    if d is None or d.user_id != user.id:
        raise HTTPException(404, "Không tìm thấy dữ liệu.")

    points = json.loads(d.payload)[:max(1, min(limit, 200))]
    scored = []
    for p in points:
        try:
            ts = terrascore.compute(Location(lat=p["lat"], lon=p["lon"]))
            scored.append({"name": p["name"], "lat": p["lat"], "lon": p["lon"],
                           "score": ts.score, "grade": ts.grade,
                           "summary": ts.summary,
                           "real_data_ratio": ts.real_data_ratio})
        except Exception:
            scored.append({"name": p["name"], "lat": p["lat"], "lon": p["lon"],
                           "score": None, "grade": None,
                           "summary": "Không chấm được điểm này.",
                           "real_data_ratio": 0.0})
    scored.sort(key=lambda r: (r["score"] is None, r["score"] if r["score"] is not None else 999))
    ok = [r for r in scored if r["score"] is not None]
    return {
        "dataset_id": d.id, "dataset_name": d.name,
        "total_points": d.row_count, "scored": len(scored),
        "truncated": d.row_count > len(points),
        "worst": scored[0] if scored else None,
        "average_score": round(sum(r["score"] for r in ok) / len(ok), 1) if ok else None,
        "results": scored,
    }


# ---------- C05 Proactive Radar / S08 ----------

@router.post("/api/radar/run")
def run_radar(user: User = Depends(auth.current_user),
              db: Session = Depends(get_session)) -> dict:
    """Quét lại mọi thửa đã lưu, ghi CẢNH BÁO MỚI.

    Logic nằm ở services/radar.py vì bộ hẹn giờ nền cũng gọi đúng logic đó —
    không được để hai bản khác nhau rồi lệch nhau.
    """
    return radar.sweep_user(user.id, db)


# ---------- C01 Twin Builder ----------

class TwinIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    location: Location
    plot_id: int | None = None


class TwinSummary(BaseModel):
    id: int
    name: str
    lat: float
    lon: float
    area_ha: float | None
    score: int | None
    grade: str | None
    built_at: datetime


@router.post("/api/twins", status_code=201)
def create_twin(body: TwinIn, user: User = Depends(auth.current_user),
                db: Session = Depends(get_session)) -> dict:
    """Dựng Twin đầy đủ rồi LƯU LẠI — ảnh chụp tại thời điểm dựng."""
    layers = twin_svc.build_layers(body.location)
    ts = layers.get("terrascore") or {}
    t = Twin(user_id=user.id, plot_id=body.plot_id, name=body.name,
             lat=body.location.lat, lon=body.location.lon,
             area_ha=body.location.area_ha,
             layers=twin_svc.to_json(layers),
             score=ts.get("score"), grade=ts.get("grade"))
    db.add(t)
    db.commit()
    db.refresh(t)
    return {"id": t.id, "name": t.name, "lat": t.lat, "lon": t.lon,
            "area_ha": t.area_ha, "score": t.score, "grade": t.grade,
            "built_at": t.built_at, "persisted": True, "layers": layers}


@router.get("/api/twins", response_model=list[TwinSummary])
def list_twins(user: User = Depends(auth.current_user),
               db: Session = Depends(get_session)) -> list[TwinSummary]:
    rows = db.execute(
        select(Twin).where(Twin.user_id == user.id)
        .order_by(Twin.built_at.desc())).scalars().all()
    return [TwinSummary(id=t.id, name=t.name, lat=t.lat, lon=t.lon,
                        area_ha=t.area_ha, score=t.score, grade=t.grade,
                        built_at=t.built_at) for t in rows]


@router.get("/api/twins/{twin_id}")
def get_twin(twin_id: int, user: User = Depends(auth.current_user),
             db: Session = Depends(get_session)) -> dict:
    t = db.get(Twin, twin_id)
    if t is None or t.user_id != user.id:
        raise HTTPException(404, "Không tìm thấy Twin.")
    return {"id": t.id, "name": t.name, "lat": t.lat, "lon": t.lon,
            "area_ha": t.area_ha, "score": t.score, "grade": t.grade,
            "built_at": t.built_at, "persisted": True,
            "layers": twin_svc.from_json(t.layers)}


@router.delete("/api/twins/{twin_id}", status_code=204,
               response_class=Response, response_model=None)
def delete_twin(twin_id: int, user: User = Depends(auth.current_user),
                db: Session = Depends(get_session)):
    t = db.get(Twin, twin_id)
    if t is None or t.user_id != user.id:
        raise HTTPException(404, "Không tìm thấy Twin.")
    db.delete(t)
    db.commit()


# ---------- U01 Kênh gửi cảnh báo ----------

class ChannelIn(BaseModel):
    kind: str = Field(pattern="^(webhook|email|zalo|telegram)$")
    target: str = Field(min_length=3, max_length=500)
    min_level: str = Field(default="warning", pattern="^(warning|danger)$")


class ChannelOut(BaseModel):
    id: int
    kind: str
    target: str
    min_level: str
    enabled: bool
    created_at: datetime
    last_sent_at: datetime | None
    last_error: str | None


def _ch_out(c: NotifyChannel) -> ChannelOut:
    return ChannelOut(id=c.id, kind=c.kind, target=c.target,
                      min_level=c.min_level, enabled=bool(c.enabled),
                      created_at=c.created_at, last_sent_at=c.last_sent_at,
                      last_error=c.last_error)


@router.get("/api/channels", response_model=list[ChannelOut])
def list_channels(user: User = Depends(auth.current_user),
                  db: Session = Depends(get_session)) -> list[ChannelOut]:
    rows = db.execute(
        select(NotifyChannel).where(NotifyChannel.user_id == user.id)
        .order_by(NotifyChannel.created_at.desc())).scalars().all()
    return [_ch_out(c) for c in rows]


@router.post("/api/channels", response_model=ChannelOut, status_code=201)
def create_channel(body: ChannelIn, user: User = Depends(auth.current_user),
                   db: Session = Depends(get_session)) -> ChannelOut:
    # Kiểm ngay lúc tạo, không đợi tới lúc gửi — một kênh sai địa chỉ mà im
    # lặng nằm đó là kiểu hỏng tệ nhất: người dùng tin là mình đang được bảo vệ.
    target = body.target.strip()
    if body.kind == "webhook":
        err = notify.validate_webhook(target)
        if err:
            raise HTTPException(422, err)
    elif body.kind == "zalo":
        num = notify.normalize_phone(target)
        if not num:
            raise HTTPException(
                422, "Số điện thoại không hợp lệ. Nhập số di động Việt Nam, "
                     "ví dụ 0912345678.")
        target = num          # lưu dạng chuẩn 84xxxxxxxxx mà ZNS đòi hỏi
    elif body.kind == "telegram":
        if not target.lstrip("-").isdigit():
            raise HTTPException(
                422, "chat_id Telegram phải là một dãy số. Nhắn /start cho bot "
                     "của bạn rồi lấy chat_id từ getUpdates.")
    elif "@" not in target:
        raise HTTPException(422, "Địa chỉ email không hợp lệ.")

    c = NotifyChannel(user_id=user.id, kind=body.kind, target=target,
                      min_level=body.min_level)
    db.add(c)
    db.commit()
    db.refresh(c)
    return _ch_out(c)


@router.delete("/api/channels/{channel_id}", status_code=204,
               response_class=Response, response_model=None)
def delete_channel(channel_id: int, user: User = Depends(auth.current_user),
                   db: Session = Depends(get_session)):
    c = db.get(NotifyChannel, channel_id)
    if c is None or c.user_id != user.id:
        raise HTTPException(404, "Không tìm thấy kênh.")
    db.delete(c)
    db.commit()


@router.post("/api/channels/{channel_id}/test")
def test_channel(channel_id: int, user: User = Depends(auth.current_user),
                 db: Session = Depends(get_session)) -> dict:
    """Gửi thử một cảnh báo giả — để người dùng biết kênh có chạy không."""
    c = db.get(NotifyChannel, channel_id)
    if c is None or c.user_id != user.id:
        raise HTTPException(404, "Không tìm thấy kênh.")
    demo = [{
        "plot_id": None, "module_id": "test", "risk_level": "danger",
        "headline": "[GỬI THỬ] Đây là cảnh báo mẫu từ TerraTwin.",
        "recommendation": "Không cần làm gì — chỉ để kiểm tra kênh nhận được.",
    }]
    res = notify.dispatch([c], demo)
    db.commit()
    ok = res["sent"] > 0
    return {"ok": ok, "detail": res["results"][0] if res["results"] else None,
            "smtp_configured": notify.smtp_configured(),
            "channels_ready": notify.channel_status()}


# ---------------------------------------------------------------------------
# N6 — ĐẾM SỰ KIỆN ẨN DANH + PHỄU CHUYỂN ĐỔI
# ---------------------------------------------------------------------------

# Đúng SÁU sự kiện, không hơn. Mỗi tên thêm vào là một chỗ để lỡ tay nhét dữ
# liệu định danh — giữ danh sách đóng thì chuyện đó không xảy ra được.
_FUNNEL = ["open", "scan", "save_plot", "view_scorecard", "tap_open", "tap_answer"]
_ALLOWED_EVENTS = set(_FUNNEL)


class EventIn(BaseModel):
    name: str = Field(..., max_length=32)
    meta: dict | None = None


@router.post("/api/events", status_code=204, response_class=Response,
             response_model=None)
def record_event(body: EventIn, db: Session = Depends(get_session)):
    """Ghi một sự kiện ẨN DANH. KHÔNG đăng nhập, KHÔNG lưu ai gửi, KHÔNG lưu IP.

    Chỉ nhận đúng sáu tên đã định; tên lạ thì lặng lẽ bỏ qua và vẫn trả 204 —
    không biến endpoint đo lường thành kênh dò cho kẻ xấu.
    """
    name = body.name.strip()
    if name in _ALLOWED_EVENTS:
        meta = ""
        if body.meta:
            try:
                # Chỉ giữ cặp khoá-chuỗi ngắn; không bao giờ lưu thứ định danh.
                clean = {str(k): str(v)[:64] for k, v in body.meta.items()
                         if isinstance(k, str)}
                meta = json.dumps(clean, ensure_ascii=False)[:500]
            except (TypeError, ValueError):
                meta = ""
        db.add(Event(name=name, meta_json=meta))
        db.commit()


@router.get("/api/admin/funnel")
def funnel(days: int = 30, user: User = Depends(auth.current_user),
           db: Session = Depends(get_session)) -> dict:
    """Phễu sáu bước — nhìn một bảng là biết người dùng rơi rụng ở đâu.

    Đòi đăng nhập vì là thông tin vận hành. Con số vẫn ẩn danh: không cách nào
    lần ngược từ đây ra một người cụ thể.
    """
    from datetime import timedelta, timezone
    since = (datetime.now(timezone.utc).replace(tzinfo=None)
             - timedelta(days=max(1, min(days, 365))))
    rows = db.execute(
        select(Event.name, func.count(Event.id))
        .where(Event.at >= since).group_by(Event.name)).all()
    counts = {k: 0 for k in _FUNNEL}
    for name, n in rows:
        if name in counts:
            counts[name] = int(n)
    base = counts["open"]
    steps = [{"step": k, "count": counts[k],
              "pct_of_open": round(100.0 * counts[k] / base, 1) if base else None}
             for k in _FUNNEL]
    return {
        "window_days": days, "counts": counts, "steps": steps,
        "note": ("Đếm ẩn danh, không id người dùng, không IP. open=mở app · "
                 "scan=chạy quét · save_plot=lưu thửa · view_scorecard=xem sổ "
                 "điểm · tap_open=mở liên kết một chạm · tap_answer=trả lời."),
    }


@router.get("/api/channels/status")
def channels_status() -> dict:
    """Kênh nào đã cấu hình xong ở phía máy chủ.

    Công khai vì giao diện cần biết TRƯỚC khi người dùng gõ số điện thoại vào
    một kênh chưa bao giờ gửi được. Không lộ gì: chỉ trả có/không, không trả
    token hay địa chỉ nào.
    """
    st = notify.channel_status()
    return {
        "ready": st,
        "note": {
            "zalo": ("Cần TERRATWIN_ZALO_TOKEN + TERRATWIN_ZALO_TEMPLATE_ID. "
                     "Zalo OA/ZNS đòi giấy phép kinh doanh và duyệt mẫu tin — "
                     "nộp hồ sơ sớm vì đó là thời gian chờ, không phải thời "
                     "gian làm."),
            "telegram": ("Cần TERRATWIN_TELEGRAM_TOKEN. Tạo bot với @BotFather "
                         "mất khoảng một phút, không phải xét duyệt gì."),
            "email": "Cần TERRATWIN_SMTP_HOST và các biến SMTP kèm theo.",
            "webhook": "Không cần cấu hình phía máy chủ.",
        },
    }


@router.get("/api/alerts", response_model=list[AlertOut])
def list_alerts(unread_only: bool = False, limit: int = 50,
                user: User = Depends(auth.current_user),
                db: Session = Depends(get_session)) -> list[AlertOut]:
    # retro == 0: hàng hồi cứu là những đợt phần mềm ĐÃ BỎ SÓT, ghi lại để tính
    # vào sổ điểm. Chúng chưa từng được gửi cho ai, nên hiện chúng ở đây sẽ là
    # nói dối rằng người dùng từng được cảnh báo.
    q = select(Alert).where(Alert.user_id == user.id, Alert.retro == 0)
    if unread_only:
        q = q.where(Alert.acknowledged == 0)
    rows = db.execute(
        q.order_by(Alert.created_at.desc()).limit(max(1, min(limit, 200)))
    ).scalars().all()
    return [_alert_out(a) for a in rows]


@router.post("/api/alerts/{alert_id}/ack", response_model=AlertOut)
def ack_alert(alert_id: int, user: User = Depends(auth.current_user),
              db: Session = Depends(get_session)) -> AlertOut:
    a = db.get(Alert, alert_id)
    if a is None or a.user_id != user.id:
        raise HTTPException(404, "Không tìm thấy cảnh báo.")
    a.acknowledged = 1
    db.commit()
    return _alert_out(a)
