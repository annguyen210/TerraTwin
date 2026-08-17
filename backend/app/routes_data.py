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
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth
from app.db import Alert, Dataset, Plot, User, get_session
from app.schemas import VN_LAT_MAX, VN_LAT_MIN, VN_LON_MAX, VN_LON_MIN, Location

router = APIRouter(tags=["data"])

_MAX_ROWS = 2000
_MAX_BYTES = 2_000_000
_DEDUP_HOURS = 12       # cùng một cảnh báo trong 12 h thì không ghi lại


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

    Chống spam: cùng (thửa, module, mức) đã ghi trong 12 h thì bỏ qua, nên chạy
    định kỳ cũng không sinh trùng — điều kiện cần trước khi nối Zalo/email.
    """
    from app.services import scan as scan_svc

    plots = db.execute(select(Plot).where(Plot.user_id == user.id)).scalars().all()
    if not plots:
        return {"plots_scanned": 0, "new_alerts": 0, "alerts": [],
                "message": "Chưa có thửa nào được lưu. Lưu thửa rồi chạy lại."}

    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=_DEDUP_HOURS)
    created = []
    for p in plots:
        try:
            result = scan_svc.scan(Location(lat=p.lat, lon=p.lon, area_ha=p.area_ha))
        except Exception:
            continue
        for m in result.alerts:            # scan.alerts đã lọc chỉ dữ liệu thật
            dup = db.execute(
                select(Alert).where(
                    Alert.user_id == user.id, Alert.plot_id == p.id,
                    Alert.module_id == m.id, Alert.risk_level == m.risk_level,
                    Alert.created_at >= since)
            ).scalar_one_or_none()
            if dup:
                continue
            a = Alert(user_id=user.id, plot_id=p.id, module_id=m.id,
                      risk_level=m.risk_level,
                      headline=f"{p.name}: {m.headline}",
                      recommendation=m.recommendation)
            db.add(a)
            created.append(a)
    db.commit()
    return {
        "plots_scanned": len(plots),
        "new_alerts": len(created),
        "dedup_window_hours": _DEDUP_HOURS,
        "alerts": [{"plot_id": a.plot_id, "module_id": a.module_id,
                    "risk_level": a.risk_level, "headline": a.headline,
                    "recommendation": a.recommendation} for a in created],
    }


@router.get("/api/alerts", response_model=list[AlertOut])
def list_alerts(unread_only: bool = False, limit: int = 50,
                user: User = Depends(auth.current_user),
                db: Session = Depends(get_session)) -> list[AlertOut]:
    q = select(Alert).where(Alert.user_id == user.id)
    if unread_only:
        q = q.where(Alert.acknowledged == 0)
    rows = db.execute(
        q.order_by(Alert.created_at.desc()).limit(max(1, min(limit, 200)))
    ).scalars().all()
    return [AlertOut(id=a.id, plot_id=a.plot_id, module_id=a.module_id,
                     risk_level=a.risk_level, headline=a.headline,
                     recommendation=a.recommendation, created_at=a.created_at,
                     acknowledged=bool(a.acknowledged)) for a in rows]


@router.post("/api/alerts/{alert_id}/ack", response_model=AlertOut)
def ack_alert(alert_id: int, user: User = Depends(auth.current_user),
              db: Session = Depends(get_session)) -> AlertOut:
    a = db.get(Alert, alert_id)
    if a is None or a.user_id != user.id:
        raise HTTPException(404, "Không tìm thấy cảnh báo.")
    a.acknowledged = 1
    db.commit()
    return AlertOut(id=a.id, plot_id=a.plot_id, module_id=a.module_id,
                    risk_level=a.risk_level, headline=a.headline,
                    recommendation=a.recommendation, created_at=a.created_at,
                    acknowledged=True)
