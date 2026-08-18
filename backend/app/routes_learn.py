"""S05 Federated · S09 Model Engine · U02 Marketplace · U04 Closed-Loop.

Bốn luồng này tạo thành xương sống HỌC HỎI của TerraTwin:

  quan sát thực địa (S05) → chấm điểm mô hình (S09) → hiệu chỉnh ngưỡng
        ↑                                                      ↓
  xác nhận kết quả (U04) ←──── khuyến nghị ←──── cảnh báo chính xác hơn

Chợ tri thức (U02) chạy song song: ghép người theo Twin Genome để kinh nghiệm
đi từ vùng giống nhau, chứ không phải lời khuyên chung chung.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth
from app.db import (
    ActionLog, Alert, KnowledgeNote, Observation, Plot, User, get_session,
)
from app.schemas import Location
from app.services import federated, hazard, model_engine

router = APIRouter(tags=["learning"])


# ---------- S05: gửi quan sát thực địa ----------

class ObservationIn(BaseModel):
    location: Location
    module_id: str
    observed_on: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    outcome: str = Field(pattern="^(occurred|none)$")
    severity: str | None = Field(default=None, pattern="^(nhe|vua|nang)$")
    note: str = Field(default="", max_length=2000)
    plot_id: int | None = None


class ObservationOut(BaseModel):
    # `model_index` trùng namespace bảo vệ "model_" của Pydantic; tên này mô tả
    # đúng thứ nó chứa (chỉ số MÔ HÌNH tính cho ngày quan sát) nên giữ tên và
    # tắt cảnh báo, thay vì đổi thành tên khó hiểu hơn.
    model_config = {"protected_namespaces": ()}

    id: int
    lat: float
    lon: float
    module_id: str
    observed_on: str
    outcome: str
    severity: str | None
    note: str
    model_index: float | None
    created_at: datetime


def _model_index_on(module_id: str, lat: float, lon: float,
                    day: str) -> float | None:
    """Chỉ số model tính cho ĐÚNG ngày người dùng quan sát.

    Chốt lại ngay lúc gửi. Nếu để tính lại về sau thì mỗi lần hiệu chuẩn mô hình
    sẽ làm thay đổi cả điểm chấm quá khứ — không còn cách nào biết mô hình có
    khá lên hay không.
    """
    from app.services import realdata
    if not hazard.supports(module_id):
        return None
    try:
        d = date.fromisoformat(day)
    except ValueError:
        return None
    # Cửa sổ 7 ngày KẾT THÚC ở ngày quan sát — đúng cửa sổ mô hình dùng để dự báo.
    start = (d - timedelta(days=6)).isoformat()
    rows = realdata.historical_weather(lat, lon, start, d.isoformat())
    if not rows:
        return None
    rows = [{**r, "day": i} for i, r in enumerate(rows)]
    series = hazard.index_series(module_id, lat, lon, rows)
    return round(hazard.peak_of(series), 1) if series else None


@router.post("/api/observations", response_model=ObservationOut, status_code=201)
def add_observation(body: ObservationIn, user: User = Depends(auth.current_user),
                    db: Session = Depends(get_session)) -> ObservationOut:
    """Gửi quan sát thực địa: sự việc CÓ xảy ra, hoặc model báo mà KHÔNG xảy ra.

    Đây là dữ liệu quý nhất của TerraTwin — thứ duy nhất không tải được từ vệ tinh.
    """
    if not hazard.supports(body.module_id):
        raise HTTPException(
            422, f"Chỉ nhận quan sát cho: {', '.join(hazard.IDS)}.")
    try:
        d = date.fromisoformat(body.observed_on)
    except ValueError:
        raise HTTPException(422, "Ngày không hợp lệ.")
    if d > date.today():
        raise HTTPException(422, "Không nhận quan sát ở tương lai.")

    idx = _model_index_on(body.module_id, body.location.lat,
                          body.location.lon, body.observed_on)
    o = Observation(
        user_id=user.id, plot_id=body.plot_id,
        lat=body.location.lat, lon=body.location.lon,
        module_id=body.module_id, observed_on=body.observed_on,
        outcome=body.outcome, severity=body.severity,
        note=body.note, model_index=idx)
    db.add(o)
    db.commit()
    db.refresh(o)
    return ObservationOut(
        id=o.id, lat=o.lat, lon=o.lon, module_id=o.module_id,
        observed_on=o.observed_on, outcome=o.outcome, severity=o.severity,
        note=o.note, model_index=o.model_index, created_at=o.created_at)


@router.get("/api/observations", response_model=list[ObservationOut])
def list_observations(user: User = Depends(auth.current_user),
                      db: Session = Depends(get_session)) -> list[ObservationOut]:
    """CHỈ trả quan sát của chính người gọi — dữ liệu thô không bao giờ chia sẻ."""
    rows = db.execute(
        select(Observation).where(Observation.user_id == user.id)
        .order_by(Observation.observed_on.desc())).scalars().all()
    return [ObservationOut(
        id=o.id, lat=o.lat, lon=o.lon, module_id=o.module_id,
        observed_on=o.observed_on, outcome=o.outcome, severity=o.severity,
        note=o.note, model_index=o.model_index, created_at=o.created_at)
        for o in rows]


@router.delete("/api/observations/{obs_id}", status_code=204,
               response_class=Response, response_model=None)
def delete_observation(obs_id: int, user: User = Depends(auth.current_user),
                      db: Session = Depends(get_session)):
    o = db.get(Observation, obs_id)
    if o is None or o.user_id != user.id:
        raise HTTPException(404, "Không tìm thấy quan sát.")
    db.delete(o)
    db.commit()


@router.get("/api/federated")
def federated_status(db: Session = Depends(get_session)) -> dict:
    """S05 — bảng hiệu chỉnh ngưỡng tổng hợp. CÔNG KHAI được vì đã ẩn danh.

    Không cần đăng nhập: đây đúng là phần "chia sẻ" của federated learning —
    ai cũng hưởng lợi từ hiệu chỉnh, nhưng không ai thấy quan sát thô của ai.
    """
    obs = db.execute(select(Observation)).scalars().all()
    return federated.aggregate(obs)


@router.get("/api/federated/shift")
def federated_shift(lat: float, lon: float, module_id: str,
                    db: Session = Depends(get_session)) -> dict:
    """Độ dịch ngưỡng đang áp cho một vị trí cụ thể."""
    agg = federated.aggregate(db.execute(select(Observation)).scalars().all())
    shift = federated.shift_for(agg["adjustments"], lat, lon, module_id)
    return {
        "cell": federated.cell_of(lat, lon), "module_id": module_id,
        "threshold_shift": shift,
        "applied": shift != 0.0,
        "note": ("Ngưỡng vùng này đã được hiệu chỉnh từ quan sát thực địa."
                 if shift else
                 f"Vùng này chưa đủ {federated.MIN_OBS} quan sát nên chưa hiệu chỉnh."),
    }


# ---------- S09: chấm điểm mô hình ----------

@router.get("/api/model/evaluate")
def evaluate_model(db: Session = Depends(get_session)) -> dict:
    """S09 — đo mô hình bằng POD/FAR/CSI trên quan sát thực địa."""
    obs = db.execute(select(Observation)).scalars().all()
    return model_engine.evaluate(obs)


# ---------- U04: vòng khép kín ----------

class ActionIn(BaseModel):
    module_id: str
    recommendation: str = Field(min_length=1, max_length=2000)
    status: str = Field(default="done", pattern="^(done|skipped|other)$")
    acted_on: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    note: str = Field(default="", max_length=2000)
    alert_id: int | None = None
    plot_id: int | None = None


class OutcomeIn(BaseModel):
    outcome: str = Field(pattern="^(avoided|reduced|no_effect|too_late)$")
    outcome_note: str = Field(default="", max_length=2000)


class ActionOut(BaseModel):
    id: int
    module_id: str
    recommendation: str
    status: str
    acted_on: str
    note: str
    outcome: str | None
    outcome_note: str
    created_at: datetime


def _act_out(a: ActionLog) -> ActionOut:
    return ActionOut(id=a.id, module_id=a.module_id,
                     recommendation=a.recommendation, status=a.status,
                     acted_on=a.acted_on, note=a.note, outcome=a.outcome,
                     outcome_note=a.outcome_note, created_at=a.created_at)


@router.post("/api/actions", response_model=ActionOut, status_code=201)
def log_action(body: ActionIn, user: User = Depends(auth.current_user),
               db: Session = Depends(get_session)) -> ActionOut:
    """U04 — ghi lại người dùng ĐÃ LÀM GÌ theo khuyến nghị.

    Mắt xích hầu hết phần mềm cảnh báo bỏ qua: chúng không bao giờ biết lời
    khuyên của mình có ai làm theo không.
    """
    if body.alert_id is not None:
        al = db.get(Alert, body.alert_id)
        if al is None or al.user_id != user.id:
            raise HTTPException(404, "Không tìm thấy cảnh báo.")
    a = ActionLog(user_id=user.id, alert_id=body.alert_id, plot_id=body.plot_id,
                  module_id=body.module_id, recommendation=body.recommendation,
                  status=body.status, acted_on=body.acted_on, note=body.note)
    db.add(a)
    db.commit()
    db.refresh(a)
    return _act_out(a)


@router.post("/api/actions/{action_id}/outcome", response_model=ActionOut)
def record_outcome(action_id: int, body: OutcomeIn,
                   user: User = Depends(auth.current_user),
                   db: Session = Depends(get_session)) -> ActionOut:
    """Khép vòng: hành động đó có hiệu quả không."""
    a = db.get(ActionLog, action_id)
    if a is None or a.user_id != user.id:
        raise HTTPException(404, "Không tìm thấy hành động.")
    a.outcome = body.outcome
    a.outcome_note = body.outcome_note
    db.commit()
    db.refresh(a)
    return _act_out(a)


@router.get("/api/actions", response_model=list[ActionOut])
def list_actions(user: User = Depends(auth.current_user),
                 db: Session = Depends(get_session)) -> list[ActionOut]:
    rows = db.execute(
        select(ActionLog).where(ActionLog.user_id == user.id)
        .order_by(ActionLog.created_at.desc())).scalars().all()
    return [_act_out(a) for a in rows]


@router.get("/api/loop")
def loop_status(user: User = Depends(auth.current_user),
                db: Session = Depends(get_session)) -> dict:
    """U04 — vòng khép kín đã đóng được đến đâu."""
    acts = db.execute(
        select(ActionLog).where(ActionLog.user_id == user.id)).scalars().all()
    obs = db.execute(
        select(Observation).where(Observation.user_id == user.id)).scalars().all()
    alerts = db.execute(
        select(Alert).where(Alert.user_id == user.id)).scalars().all()

    acted = [a for a in acts if a.status == "done"]
    verified = [a for a in acts if a.outcome is not None]
    helped = [a for a in verified if a.outcome in ("avoided", "reduced")]

    stages = [
        {"stage": "1. Cảnh báo sinh ra", "count": len(alerts)},
        {"stage": "2. Người dùng hành động", "count": len(acted)},
        {"stage": "3. Kết quả được xác nhận", "count": len(verified)},
        {"stage": "4. Quan sát nạp lại mô hình", "count": len(obs)},
    ]
    closed = len(verified) > 0 and len(obs) > 0

    return {
        "closed": closed,
        "stages": stages,
        "actions_taken": len(acted),
        "outcomes_verified": len(verified),
        "helped_count": len(helped),
        "help_rate": round(len(helped) / len(verified), 2) if verified else None,
        "headline": (
            f"Vòng đã đóng: {len(alerts)} cảnh báo → {len(acted)} lần hành động → "
            f"{len(verified)} kết quả xác nhận → {len(obs)} quan sát nạp lại mô hình."
            if closed else
            "Vòng chưa đóng. Cần ít nhất một hành động có xác nhận kết quả và "
            "một quan sát thực địa."),
        "note": (
            "Cơ cấu chấp hành ở đây là CON NGƯỜI, không phải van bơm IoT. Vòng "
            "vẫn khép kín theo đúng nghĩa: đo → khuyến nghị → hành động → đối "
            "chiếu kết quả → hiệu chỉnh mô hình. Tự động hoá phần chấp hành cần "
            "thiết bị ngoài đồng, chưa có."),
    }


# ---------- U02: chợ tri thức ----------

class NoteIn(BaseModel):
    location: Location
    title: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=10, max_length=5000)
    topic: str = Field(min_length=2, max_length=48)


class NoteOut(BaseModel):
    id: int
    lat: float
    lon: float
    title: str
    body: str
    topic: str
    author_name: str
    helpful_count: int
    created_at: datetime


def _note_out(n: KnowledgeNote) -> NoteOut:
    return NoteOut(id=n.id, lat=n.lat, lon=n.lon, title=n.title, body=n.body,
                   topic=n.topic, author_name=n.author_name,
                   helpful_count=n.helpful_count, created_at=n.created_at)


@router.post("/api/knowledge", response_model=NoteOut, status_code=201)
def share_knowledge(body: NoteIn, user: User = Depends(auth.current_user),
                    db: Session = Depends(get_session)) -> NoteOut:
    """U02 — chia sẻ kinh nghiệm. Người khác tìm thấy nó qua Twin Genome."""
    n = KnowledgeNote(user_id=user.id, lat=body.location.lat,
                      lon=body.location.lon, title=body.title, body=body.body,
                      topic=body.topic.strip().lower(),
                      author_name=user.name or user.email.split("@")[0])
    db.add(n)
    db.commit()
    db.refresh(n)
    return _note_out(n)


@router.get("/api/knowledge")
def find_knowledge(lat: float, lon: float, topic: str | None = None,
                   k: int = 5, db: Session = Depends(get_session)) -> dict:
    """Tìm kinh nghiệm từ vùng có BỘ GEN ĐẤT giống bạn.

    Vì sao ghép theo bộ gen chứ không theo khoảng cách: một hộ cách 200 km nhưng
    cùng cao độ, cùng chế độ mưa, cùng mức mặn thì kinh nghiệm dùng được ngay;
    một hộ cách 20 km nhưng ở trên đồi thì không.
    """
    from app.services import genome

    q = select(KnowledgeNote)
    if topic:
        q = q.where(KnowledgeNote.topic == topic.strip().lower())
    notes = db.execute(q).scalars().all()
    if not notes:
        return {"available": True, "matched_by": None, "notes": [],
                "message": "Chưa có ai chia sẻ kinh nghiệm cho chủ đề này."}

    mine = None
    try:
        mine = genome.genome_of(lat, lon)
        ref = genome.build_reference()
        stats = ref["stats"] if ref.get("cells") else None
    except Exception:
        stats = None

    scored = []
    for n in notes:
        sim, how = None, "khoảng cách địa lý"
        if mine is not None and stats is not None:
            try:
                theirs = genome.genome_of(n.lat, n.lon)
                if theirs is not None:
                    d = genome._distance(mine, theirs, stats)
                    sim = round(100.0 / (1.0 + d), 1)
                    how = "bộ gen đất đai"
            except Exception:
                pass
        if sim is None:
            from app.services import datasources as ds
            km = ds._haversine_km(lat, lon, n.lat, n.lon)
            sim = round(max(0.0, 100.0 - km / 10.0), 1)
        scored.append((sim, how, n))

    scored.sort(key=lambda t: t[0], reverse=True)
    top = scored[:max(1, min(int(k), 20))]
    return {
        "available": True,
        "matched_by": top[0][1] if top else None,
        "notes": [{**_note_out(n).model_dump(), "similarity_pct": sim}
                  for sim, _, n in top],
        "why": ("Ghép theo bộ gen đất đai, không theo khoảng cách: một hộ cách "
                "200 km nhưng cùng cao độ, chế độ mưa và mức mặn thì kinh nghiệm "
                "dùng được ngay; một hộ cách 20 km nhưng ở trên đồi thì không."),
        "note": ("Chợ TRI THỨC, không có thanh toán. Chợ có giao dịch tiền cần "
                 "cổng thanh toán và pháp lý — chưa làm."),
    }


@router.post("/api/knowledge/{note_id}/helpful", response_model=NoteOut)
def mark_helpful(note_id: int, user: User = Depends(auth.current_user),
                 db: Session = Depends(get_session)) -> NoteOut:
    n = db.get(KnowledgeNote, note_id)
    if n is None:
        raise HTTPException(404, "Không tìm thấy ghi chú.")
    n.helpful_count += 1
    db.commit()
    db.refresh(n)
    return _note_out(n)
