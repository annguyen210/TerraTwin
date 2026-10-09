"""GĐ6 · NĂNG LỰC 5 + 6 — NHẬT KÝ THỬA: "từ lần mở trước có gì đổi", và ĐỐI CHIẾU BA CHIỀU.

Lý do người ta mở TerraTwin mỗi sáng. Không bảng mới, không tác vụ nền tốn giờ máy: nhật ký dựng KHI
MỞ từ những gì đã có — cảnh báo đã phát + kết quả chấm, câu trả lời một chạm / quan sát thực địa, ảnh
thực địa đã kiểm, số đo cảm biến ĐÃ KÝ, mưa đo được (Open-Meteo, vài ngày gần nhất), cảnh radar
Sentinel-1 mới (so với nền của chính thửa nếu đã đọc lịch sử nước).

QUY TẮC "KHÔNG CÓ THAY ĐỔI THẬT THÌ IM": mỗi sự kiện có cờ `significant`. Chỉ những thứ sau là thay đổi
thật: mưa ≥ 50 mm/ngày (mưa rất to), radar thấy nước phủ, cảnh báo mới / kết quả chấm cảnh báo, người
dùng trả lời hoặc gửi ảnh, cảm biến vượt ngưỡng nhắc (đất khô, mặn). Cảnh radar mới KHÔNG thấy nước,
mưa nhỏ, số đo bình thường → chỉ là bối cảnh, không bật cờ "có thay đổi".

ĐỐI CHIẾU BA CHIỀU: mỗi câu trả lời "ruộng có ngập không" của người dùng được đặt cạnh radar cùng tuần
(±6 ngày) và mưa 3 ngày trước đó → khớp / lệch / chưa đủ dữ liệu. (Nhận nước TRONG ẢNH bằng SegFormer
cần mô hình qua cổng GĐ5 — chưa bật; ảnh hiện vào nhật ký như bằng chứng người dùng, không chấm tự động.)
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.services import cache_store
from app.services.reqlang import tr

RAIN_HEAVY_MM = 50.0        # mưa rất to: > 50 mm/24 giờ (phân cấp mưa của KTTV)
RAIN_CONTEXT_MM = 16.0      # mưa to: hiện làm bối cảnh, không bật cờ
SALINITY_PPT = 4.0          # nhắc chung: lúa thường bị hại khi nước > 4‰ — không phải khuyến cáo theo giống
DEVICE_NEAR_M = 500.0
RECONCILE_DAYS = 6
_EXT_TTL = 3600
_SEEN_TTL = 400 * 86400
DEFAULT_LOOKBACK = timedelta(days=7)
MAX_LOOKBACK = timedelta(days=30)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat() + "Z"


def _dist_m(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


# ------------------------------------------------------------------ "lần mở trước"

def _seen_key(user_id: int, plot_id: int) -> str:
    return cache_store.make_key("journal-seen", user_id, plot_id)


def last_seen(user_id: int, plot_id: int) -> datetime | None:
    v = cache_store.get(_seen_key(user_id, plot_id))
    try:
        return datetime.fromisoformat(v.rstrip("Z")) if v else None
    except (TypeError, ValueError):
        return None


def mark_seen(user_id: int, plot_id: int, at: datetime | None = None) -> str:
    at = at or _now()
    cache_store.put(_seen_key(user_id, plot_id), _iso(at), _SEEN_TTL)
    return _iso(at)


# ------------------------------------------------------------------ nguồn ngoài (cache 1 giờ)

def rain(lat: float, lon: float, days: int) -> list[dict] | None:
    """Mưa ngày đo được các ngày vừa qua (Open-Meteo, phân tích mô hình gần thời gian thực)."""
    from app.services import realdata
    url = ("https://api.open-meteo.com/v1/forecast"
           f"?latitude={realdata._snap(lat)}&longitude={realdata._snap(lon)}"
           f"&daily=precipitation_sum&past_days={max(1, min(days, 31))}&forecast_days=1&timezone=auto")
    d = realdata._get(url)
    try:
        t, p = d["daily"]["time"], d["daily"]["precipitation_sum"]
    except (KeyError, TypeError):
        return None
    today = date.today().isoformat()
    return [{"date": t[i], "precip": float(p[i])} for i in range(len(t)) if p[i] is not None and t[i] <= today]


def radar(lat: float, lon: float, since: date) -> dict | None:
    """Cảnh Sentinel-1 RTC mới từ `since`. Nếu đã đọc lịch sử nước của thửa (cache) thì so với nền của
    chính thửa và cùng quỹ đạo → có nước / không; chưa đọc thì chỉ báo có cảnh mới."""
    from app.services import mpc, water_history as wh
    box = mpc.bbox_around(lat, lon, wh.RADIUS_M)
    r = mpc._call(mpc.STAC, {"collections": [wh.COLLECTION], "bbox": box,
                             "datetime": f"{since.isoformat()}/{date.today().isoformat()}", "limit": 50})
    if r is None:
        return None
    feats = r.get("features") or []
    hist = cache_store.get(cache_store.make_key("water", round(lat, 4), round(lon, 4), int(wh.RADIUS_M)))
    base = track = None
    if hist and hist.get("available"):
        base = hist["baseline_db"]
        track = (hist["track"]["orbit"], hist["track"]["relative_orbit"])
        feats = [f for f in feats if (f["properties"].get("sat:orbit_state"),
                                      f["properties"].get("sat:relative_orbit")) == track]
    seen, rows = set(), []
    for f in sorted(feats, key=lambda f: f["properties"]["datetime"])[-8:]:
        d = f["properties"]["datetime"][:10]
        if d in seen:
            continue
        seen.add(d)
        s = wh._scene(f["id"], box) if base else None
        rows.append({"date": d, "p50": s["p50"] if s else None,
                     "water": wh.flag({"date": d, **s}, base) if (s and base) else None,
                     "judged": bool(s and base)})
    return {"scenes": rows, "has_baseline": base is not None}


def _external(lat: float, lon: float, since: datetime) -> dict:
    key = cache_store.make_key("journal-ext", round(lat, 4), round(lon, 4), since.date().isoformat())
    hit = cache_store.get(key)
    if hit is not None:
        return hit
    days = max(1, (date.today() - since.date()).days + 1)
    out = {"rain": None, "radar": None}
    try:
        out["rain"] = rain(lat, lon, days + 3)          # +3 ngày để đối chiếu mưa trước câu trả lời
    except Exception:  # noqa: BLE001 — nguồn hỏng thì nhật ký ghi "không lấy được", không sập
        pass
    try:
        out["radar"] = radar(lat, lon, since.date() - timedelta(days=RECONCILE_DAYS))
    except Exception:  # noqa: BLE001
        pass
    cache_store.put(key, out, _EXT_TTL)
    return out


# ------------------------------------------------------------------ đối chiếu ba chiều

def reconcile(observed_on: str, occurred: bool, rain_rows: list[dict] | None, scenes: list[dict] | None) -> dict:
    """Câu trả lời của người dùng ↔ radar cùng tuần ↔ mưa 3 ngày trước. Không phán ai đúng — chỉ nói khớp/lệch."""
    d = date.fromisoformat(observed_on)
    near = [s for s in (scenes or []) if s.get("judged") and abs((date.fromisoformat(s["date"]) - d).days) <= RECONCILE_DAYS]
    r3 = None
    if rain_rows:
        win = [x["precip"] for x in rain_rows if 0 <= (d - date.fromisoformat(x["date"])).days <= 3]
        r3 = round(sum(win), 1) if win else None
    radar_wet = any(s["water"] for s in near) if near else None
    rain_heavy = (r3 >= RAIN_HEAVY_MM) if r3 is not None else None
    votes = [v for v in (radar_wet, rain_heavy) if v is not None]
    if not votes:
        verdict = "insufficient"
    elif all(v == occurred for v in votes):
        verdict = "match"
    elif any(v == occurred for v in votes):
        verdict = "partial"
    else:
        verdict = "mismatch"
    return {"verdict": verdict, "radar_water": radar_wet, "radar_dates": [s["date"] for s in near],
            "rain_3d_mm": r3, "user_says": "flooded" if occurred else "not_flooded"}


# ------------------------------------------------------------------ nhật ký

def _ev(at: str, kind: str, significant: bool, text: str, source: str, **extra) -> dict:
    return {"at": at, "kind": kind, "significant": significant, "text": text, "source": source, **extra}


def _db_events(db: Session, user_id: int, plot, since: datetime) -> list[dict]:
    from app.db import Alert, Device, FieldPhoto, Observation, SensorReading
    from app.services import iot
    out: list[dict] = []

    for a in db.execute(select(Alert).where(Alert.plot_id == plot.id, Alert.retro == 0,
                                            Alert.created_at >= since)).scalars():
        out.append(_ev(_iso(a.created_at), "alert", True, a.headline, "TerraTwin radar",
                       module_id=a.module_id, risk_level=a.risk_level))
    for a in db.execute(select(Alert).where(Alert.plot_id == plot.id, Alert.verified_at.is_not(None),
                                            Alert.verified_at >= since)).scalars():
        lab = {"hit": tr("ĐÚNG", "CORRECT"), "false_alarm": tr("báo nhầm", "false alarm"),
               "miss": tr("BỎ SÓT", "MISSED"), "expired": tr("hết hạn, không chấm được", "expired, ungradable")}
        out.append(_ev(_iso(a.verified_at), "graded", a.outcome != "expired",
                       tr(f"Chấm cảnh báo {a.module_id} ngày {a.created_at.date()}: {lab.get(a.outcome, a.outcome)}",
                          f"Graded {a.module_id} alert of {a.created_at.date()}: {lab.get(a.outcome, a.outcome)}"),
                       tr("Sổ điểm tự chấm", "Self-graded scorecard"), outcome=a.outcome))

    obs = db.execute(select(Observation).where(Observation.user_id == user_id, Observation.created_at >= since)).scalars().all()
    for o in obs:
        if o.plot_id != plot.id and _dist_m(o.lat, o.lon, plot.lat, plot.lon) > DEVICE_NEAR_M:
            continue
        occurred = o.outcome == "occurred"
        out.append(_ev(_iso(o.created_at), "answer", True,
                       tr(f"Bạn báo {o.module_id} ngày {o.observed_on}: {'có xảy ra' if occurred else 'không xảy ra'}",
                          f"You reported {o.module_id} on {o.observed_on}: {'happened' if occurred else 'did not happen'}"),
                       tr("Câu trả lời của bạn", "Your answer"), module_id=o.module_id, observed_on=o.observed_on,
                       occurred=occurred))

    for ph in db.execute(select(FieldPhoto).where(FieldPhoto.user_id == user_id, FieldPhoto.created_at >= since)).scalars():
        if _dist_m(ph.plot_lat, ph.plot_lon, plot.lat, plot.lon) > DEVICE_NEAR_M:
            continue
        out.append(_ev(_iso(ph.created_at), "photo", True,
                       tr(f"Ảnh thực địa mới (kiểm GPS/thời điểm: {ph.verdict})", f"New field photo (GPS/time check: {ph.verdict})"),
                       tr("Ảnh của bạn", "Your photo"), photo_id=ph.id))

    devs = [d for d in db.execute(select(Device).where(Device.user_id == user_id, Device.revoked == 0)).scalars()
            if d.lat is not None and d.lon is not None and _dist_m(d.lat, d.lon, plot.lat, plot.lon) <= DEVICE_NEAR_M]
    for dv in devs:
        rows = db.execute(select(SensorReading).where(SensorReading.device_id == dv.id, SensorReading.received_at >= since)
                          .order_by(SensorReading.measured_at.desc()).limit(200)).scalars().all()
        if not rows:
            continue
        last = json.loads(rows[0].metrics_json)
        sim = tr(" (giả lập)", " (simulated)") if dv.kind == "simulator" else ""
        parts = [f"{iot.METRICS[k][3] if k in iot.METRICS else k} {v}{iot.METRICS[k][2] if k in iot.METRICS else ''}"
                 for k, v in last.items() if k != "battery_v"]
        sal = last.get("salinity_ppt")
        dry = last.get("soil_moisture_pct")
        alarm = (sal is not None and sal >= SALINITY_PPT) or (dry is not None and dry < iot.DRY_SOIL_PCT)
        text = tr(f"Cảm biến “{dv.name}”{sim}: {', '.join(parts)} ({len(rows)} số đo mới)",
                  f"Sensor “{dv.name}”{sim}: {', '.join(parts)} ({len(rows)} new readings)")
        if sal is not None and sal >= SALINITY_PPT:
            text += tr(f" — mặn ≥ {SALINITY_PPT:g}‰ (ngưỡng nhắc chung)", f" — salinity ≥ {SALINITY_PPT:g}‰ (generic reminder)")
        out.append(_ev(_iso(rows[0].measured_at), "sensor", alarm, text, tr("Số đo đã ký Ed25519", "Ed25519-signed readings"),
                       device_id=dv.id, metrics=last, simulated=dv.kind == "simulator",
                       received_at=_iso(rows[0].received_at)))
    return out


def _ext_events(ext: dict, since: datetime) -> tuple[list[dict], dict]:
    out: list[dict] = []
    ctx: dict = {"rain_total_mm": None, "radar_latest": None, "rain_ok": ext.get("rain") is not None,
                 "radar_ok": ext.get("radar") is not None}
    rr = [x for x in (ext.get("rain") or []) if x["date"] >= since.date().isoformat()]
    if ext.get("rain") is not None:
        ctx["rain_total_mm"] = round(sum(x["precip"] for x in rr), 1)
    for x in rr:
        if x["precip"] >= RAIN_HEAVY_MM:
            out.append(_ev(x["date"] + "T00:00:00Z", "rain", True,
                           tr(f"Mưa rất to {x['precip']:.0f} mm ngày {x['date']}", f"Very heavy rain {x['precip']:.0f} mm on {x['date']}"),
                           "Open-Meteo", precip_mm=x["precip"]))
        elif x["precip"] >= RAIN_CONTEXT_MM:
            out.append(_ev(x["date"] + "T00:00:00Z", "rain", False,
                           tr(f"Mưa to {x['precip']:.0f} mm ngày {x['date']}", f"Heavy rain {x['precip']:.0f} mm on {x['date']}"),
                           "Open-Meteo", precip_mm=x["precip"]))
    rad = ext.get("radar") or {}
    for s in rad.get("scenes") or []:
        if s["date"] < since.date().isoformat():
            continue
        if s["water"]:
            out.append(_ev(s["date"] + "T00:00:00Z", "water", True,
                           tr(f"Radar ngày {s['date']} thấy nước phủ {s['water']} thửa", f"Radar on {s['date']} saw water over {s['water']} of the plot"),
                           "Sentinel-1 RTC", cover=s["water"]))
        else:
            out.append(_ev(s["date"] + "T00:00:00Z", "radar", False,
                           tr(f"Ảnh radar mới ngày {s['date']}" + (": không thấy nước" if s["judged"] else " (chưa đọc lịch sử nước nên chưa so với nền)"),
                              f"New radar image on {s['date']}" + (": no water" if s["judged"] else " (water history not read yet, no baseline)")),
                           "Sentinel-1 RTC"))
        ctx["radar_latest"] = s
    return out, ctx


def journal(db: Session, user_id: int, plot, since: datetime | None = None, fast: bool = False) -> dict:
    """Nhật ký một thửa từ `since` (mặc định: lần mở trước, chưa mở bao giờ thì 7 ngày)."""
    seen = last_seen(user_id, plot.id)
    since = since or seen or (_now() - DEFAULT_LOOKBACK)
    since = max(since, _now() - MAX_LOOKBACK)
    events = _db_events(db, user_id, plot, since)
    ctx: dict = {}
    ext = None
    if not fast:
        ext = _external(plot.lat, plot.lon, since)
        more, ctx = _ext_events(ext, since)
        events += more
        scenes = (ext.get("radar") or {}).get("scenes")
        for e in events:
            if e["kind"] == "answer" and e.get("module_id") == "flood":
                e["reconcile"] = reconcile(e["observed_on"], e["occurred"], ext.get("rain"), scenes)
    events.sort(key=lambda e: e["at"], reverse=True)
    sig = [e for e in events if e["significant"]]
    return {
        "plot_id": plot.id, "since": _iso(since), "first_open": seen is None, "fast": fast,
        "changed": bool(sig), "n_significant": len(sig),
        "summary": summary(since, sig, ctx) if not fast else None,
        "events": events, "context": ctx,
        "rule": tr("Chỉ báo khi có thay đổi thật: mưa ≥ 50 mm/ngày, radar thấy nước, cảnh báo mới hoặc kết quả chấm, "
                   "câu trả lời/ảnh của bạn, cảm biến vượt ngưỡng nhắc. Còn lại là bối cảnh.",
                   "Only real changes count: rain ≥ 50 mm/day, radar sees water, a new alert or grading, your "
                   "answer/photo, a sensor crossing a reminder threshold. Everything else is context."),
    }


def summary(since: datetime, sig: list[dict], ctx: dict) -> str:
    when = since.strftime("%d/%m %H:%M")
    bits: list[str] = []
    if ctx.get("rain_total_mm") is not None:
        bits.append(tr(f"mưa tổng {ctx['rain_total_mm']:g} mm", f"total rain {ctx['rain_total_mm']:g} mm"))
    s = ctx.get("radar_latest")
    if s and not any(e["kind"] == "water" for e in sig):
        bits.append(tr(f"ảnh radar mới ngày {s['date']} " + ("thấy nước" if s["water"] else "không thấy nước" if s["judged"] else "chưa so nền"),
                       f"new radar image {s['date']} " + ("shows water" if s["water"] else "no water" if s["judged"] else "no baseline yet")))
    head = [e["text"] for e in sig if e["kind"] != "rain"][:3]
    if not sig:
        return tr(f"Từ {when}: không có thay đổi đáng kể" + (f" ({', '.join(bits)})." if bits else "."),
                  f"Since {when}: no significant change" + (f" ({', '.join(bits)})." if bits else "."))
    return tr(f"Từ {when}: ", f"Since {when}: ") + "; ".join(bits + head) + "."
