"""API IoT ký số — đăng ký thiết bị bằng khoá công khai, nhận số đo đã ký, xuất để kiểm độc lập.

Nhận số đo KHÔNG cần đăng nhập: thiết bị ở vườn không giữ mật khẩu người dùng; danh tính
của nó LÀ chữ ký Ed25519. Mọi đường còn lại (đăng ký, xem, thu hồi, xuất) chỉ chủ thiết bị.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import auth
from app.db import Device, Dossier, SensorReading, User, get_session
from app.services import iot, quota, reqlang
from app.services.reqlang import tr

router = APIRouter(tags=["iot"])


class DeviceIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    public_key: str = Field(min_length=40, max_length=64)
    kind: str = Field(default="sensor", pattern="^(sensor|simulator)$")
    lat: float | None = Field(default=None, ge=8.0, le=24.0)
    lon: float | None = Field(default=None, ge=102.0, le=110.0)
    dossier_id: str | None = Field(default=None, max_length=16)


class SignedReading(BaseModel):
    payload: str = Field(min_length=10, max_length=4000)
    sig: str = Field(min_length=80, max_length=96)


class IngestIn(BaseModel):
    device_id: str = Field(min_length=6, max_length=16)
    readings: list[SignedReading] = Field(min_length=1, max_length=iot.MAX_BATCH)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _own(db: Session, user: User, device_id: str) -> Device:
    dv = db.get(Device, device_id)
    if dv is None or dv.user_id != user.id:
        raise HTTPException(404, tr("Không có thiết bị này.", "No such device."))
    return dv


def _view(dv: Device, latest: SensorReading | None) -> dict:
    return {"id": dv.id, "name": dv.name, "kind": dv.kind, "public_key": dv.public_b64,
            "lat": dv.lat, "lon": dv.lon, "dossier_id": dv.dossier_id, "revoked": bool(dv.revoked),
            "created_at": dv.created_at.isoformat() + "Z",
            "last_seen": dv.last_seen.isoformat() + "Z" if dv.last_seen else None,
            "last_seq": dv.last_seq,
            "latest": None if latest is None else {
                "measured_at": latest.measured_at.isoformat() + "Z",
                "metrics": json.loads(latest.metrics_json)}}


@router.get("/api/iot/metrics")
def metrics_catalog(lang: str = "vi") -> dict:
    """Danh mục chỉ số nhận được, đơn vị và ngưỡng vật lý — cho người làm thiết bị."""
    reqlang.set_lang(lang)
    return {"metrics": {k: {"min": v[0], "max": v[1], "unit": v[2], "label": tr(v[3], v[4])}
                        for k, v in iot.METRICS.items()},
            "max_batch": iot.MAX_BATCH,
            "signing": tr("Ed25519 trên ĐÚNG chuỗi payload UTF-8 gửi lên; payload là JSON "
                          "{device_id, seq (tăng dần), ts (ISO 8601 UTC hoặc epoch giây), metrics}.",
                          "Ed25519 over the EXACT UTF-8 payload string sent; payload is JSON "
                          "{device_id, seq (increasing), ts (ISO 8601 UTC or epoch seconds), metrics}.")}


@router.post("/api/iot/devices")
def register_device(body: DeviceIn, lang: str = "vi", user: User = Depends(auth.current_user),
                    db: Session = Depends(get_session)) -> dict:
    reqlang.set_lang(lang)
    try:
        pub = iot.parse_public_key(body.public_key)
    except iot.Rejected as e:
        raise HTTPException(422, tr("Khoá công khai không hợp lệ (cần base64 của 32 byte Ed25519).",
                                    "Invalid public key (need base64 of 32-byte Ed25519).")) from e
    if body.dossier_id:
        d = db.get(Dossier, body.dossier_id)
        if d is None or d.user_id != user.id:
            raise HTTPException(404, tr("Chỉ gắn được thiết bị vào hồ sơ do chính bạn phát hành.",
                                        "You can only attach a device to a dossier you issued."))
    if db.scalar(select(Device).where(Device.public_b64 == pub)) is not None:
        raise HTTPException(409, tr("Khoá này đã đăng ký cho một thiết bị khác.", "This key is already registered."))
    dv = Device(id=iot.new_id(), user_id=user.id, name=body.name.strip(), kind=body.kind,
                public_b64=pub, lat=body.lat, lon=body.lon, dossier_id=body.dossier_id)
    db.add(dv)
    db.commit()
    return _view(dv, None)


@router.get("/api/iot/devices")
def my_devices(lang: str = "vi", user: User = Depends(auth.current_user),
               db: Session = Depends(get_session)) -> dict:
    reqlang.set_lang(lang)
    devs = db.execute(select(Device).where(Device.user_id == user.id)
                      .order_by(Device.created_at.desc())).scalars().all()
    out = []
    for dv in devs:
        last = db.execute(select(SensorReading).where(SensorReading.device_id == dv.id)
                          .order_by(SensorReading.seq.desc()).limit(1)).scalars().first()
        out.append(_view(dv, last))
    return {"devices": out}


@router.delete("/api/iot/devices/{device_id}")
def revoke_device(device_id: str, user: User = Depends(auth.current_user),
                  db: Session = Depends(get_session)) -> dict:
    """THU HỒI (không xoá): số đo cũ vẫn kiểm được, thiết bị không gửi thêm được."""
    dv = _own(db, user, device_id)
    dv.revoked = 1
    db.commit()
    return {"id": dv.id, "revoked": True}


@router.post("/api/iot/ingest")
def ingest(body: IngestIn, lang: str = "vi", db: Session = Depends(get_session)) -> dict:
    reqlang.set_lang(lang)
    dv = db.get(Device, body.device_id)
    if dv is None or dv.revoked:
        raise HTTPException(404, tr("Thiết bị chưa đăng ký hoặc đã bị thu hồi.", "Device not registered or revoked."))
    wait = quota.take("iot", f"dev{dv.id}", False)
    if wait is not None:
        raise HTTPException(429, tr("Thiết bị gửi quá dày — giãn chu kỳ đo.", "Device sending too often — lengthen the interval."),
                            headers={"Retry-After": str(wait)})
    now = _now()
    accepted, rejected = 0, []
    for i, r in enumerate(body.readings):
        try:
            ok = iot.check(dv, r.payload, r.sig, now=now)
        except iot.Rejected as e:
            rejected.append({"index": i, "reason": e.code, "detail": str(e)})
            continue
        db.add(SensorReading(device_id=dv.id, seq=ok["seq"], measured_at=ok["measured_at"],
                             metrics_json=json.dumps(ok["metrics"]), signed=r.payload, signature=r.sig))
        dv.last_seq = ok["seq"]
        accepted += 1
    if accepted:
        dv.last_seen = now
    try:
        db.commit()
    except IntegrityError:                      # hai lượt gửi cùng seq chạy song song
        db.rollback()
        raise HTTPException(409, tr("Trùng số thứ tự — gói đã được nhận.", "Duplicate sequence — already received."))
    if accepted == 0 and rejected:
        bad_sig = all(x["reason"] == "bad_signature" for x in rejected)
        raise HTTPException(401 if bad_sig else 422, {"accepted": 0, "rejected": rejected})
    return {"accepted": accepted, "rejected": rejected, "last_seq": dv.last_seq}


@router.get("/api/iot/devices/{device_id}/readings")
def readings(device_id: str, hours: int = 168, lang: str = "vi", user: User = Depends(auth.current_user),
             db: Session = Depends(get_session)) -> dict:
    reqlang.set_lang(lang)
    dv = _own(db, user, device_id)
    since = _now() - timedelta(hours=max(1, min(hours, 24 * 90)))
    rows = db.execute(select(SensorReading).where(SensorReading.device_id == dv.id,
                                                  SensorReading.measured_at >= since)
                      .order_by(SensorReading.measured_at).limit(5000)).scalars().all()
    return {"device": _view(dv, rows[-1] if rows else None),
            "series": [{"t": r.measured_at.isoformat() + "Z", **json.loads(r.metrics_json)} for r in rows],
            "catalog": {k: {"unit": v[2], "label": tr(v[3], v[4])} for k, v in iot.METRICS.items()}}


@router.get("/api/iot/devices/{device_id}/export")
def export(device_id: str, user: User = Depends(auth.current_user), db: Session = Depends(get_session)) -> dict:
    """Bản xuất KIỂM ĐƯỢC ĐỘC LẬP: khoá công khai + từng chuỗi đã ký + chữ ký."""
    dv = _own(db, user, device_id)
    rows = db.execute(select(SensorReading).where(SensorReading.device_id == dv.id)
                      .order_by(SensorReading.seq)).scalars().all()
    return {"schema": "terratwin.iot-export/1", "device_id": dv.id, "kind": dv.kind,
            "algorithm": "Ed25519", "public_key": dv.public_b64,
            "verify": "Với mỗi bản ghi: Ed25519.verify(public_key, signature, payload.encode('utf-8')).",
            "readings": [{"payload": r.signed, "signature": r.signature} for r in rows]}


def today_items(db: Session, user: User) -> list[dict]:
    """Việc cho trang Hôm nay từ thiết bị của người dùng (im lặng / đất khô)."""
    devs = db.execute(select(Device).where(Device.user_id == user.id, Device.revoked == 0)).scalars().all()
    if not devs:
        return []
    latest = {}
    for dv in devs:
        r = db.execute(select(SensorReading).where(SensorReading.device_id == dv.id)
                       .order_by(SensorReading.seq.desc()).limit(1)).scalars().first()
        if r:
            latest[dv.id] = (r.measured_at, json.loads(r.metrics_json))
    return iot.status_items(devs, latest, now=_now(), tr=tr)
