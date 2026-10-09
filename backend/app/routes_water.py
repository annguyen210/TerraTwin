"""API LỊCH SỬ NƯỚC (radar Sentinel-1) — GĐ2 kế hoạch tổng. Xem services/water_history.py.

Lần đầu một thửa cần đọc vài trăm cảnh radar (vài phút) → chạy qua hàng đợi việc BỀN; các lần sau
trả ngay từ cache. Chỉ bật cho người dùng khi CỔNG GĐ2 đạt (data/water_gate.json: thấy đúng lũ Huế
10/2020 và miền Trung 10/2025, 0 đợt ở đất cao) — không đạt thì nói rõ là chưa bật.
"""
from __future__ import annotations

import json
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import auth
from app.db import User, get_session
from app.services import cache_store, jobs_db, reqlang, water_history
from app.services.reqlang import tr

router = APIRouter(tags=["water"])
GATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "water_gate.json")


def gate() -> dict:
    try:
        with open(GATE, encoding="utf-8") as f:
            g = json.load(f)
        return {"passed": bool(g.get("passed")), "run_at": g.get("run_at"),
                "cases": [{"case": c["case"], "n_events": c["n_events"], "checks": c["checks"]} for c in g.get("cases", [])]}
    except (OSError, ValueError):
        return {"passed": False, "run_at": None, "cases": []}


class WaterIn(BaseModel):
    lat: float = Field(ge=8.0, le=24.0)
    lon: float = Field(ge=102.0, le=110.0)


@router.get("/api/water/status")
def water_status(lang: str = "vi") -> dict:
    reqlang.set_lang(lang)
    g = gate()
    return {"enabled": g["passed"], "gate": g, "method": {"water_db": water_history.WATER_DB, "drop_db": water_history.DROP_DB,
            "merge_gap_days": water_history.MERGE_GAP_DAYS, "collection": water_history.COLLECTION}}


@router.post("/api/water/history")
def water_history_start(body: WaterIn, request: Request, lang: str = "vi",
                        user: User | None = Depends(auth.optional_user),
                        db: Session = Depends(get_session)) -> dict:
    reqlang.set_lang(lang)
    if not gate()["passed"]:
        raise HTTPException(409, tr("Lịch sử nước radar chưa bật: chưa qua cổng kiểm chứng (lũ Huế 10/2020, miền Trung 10/2025, đất cao 0 đợt).",
                                    "Radar water history not enabled: it has not passed its verification gate yet."))
    key = cache_store.make_key("water", round(body.lat, 4), round(body.lon, 4), int(water_history.RADIUS_M))
    hit = cache_store.get(key)
    if hit is not None:
        return {"state": "done", "result": hit}
    from app.routes_eudr import enforce_quota
    enforce_quota("screen", request, user)
    job_id = jobs_db.submit(db, water_history.JOB_KIND, {"lat": body.lat, "lon": body.lon},
                            label=f"Lịch sử nước {body.lat:.4f},{body.lon:.4f}")
    return {"state": "queued", "job_id": job_id}


@router.get("/api/water/scene")
def water_scene(lat: float, lon: float, date: str, lang: str = "vi") -> dict:
    """Ô ảnh radar + mặt nạ nước của cảnh chụp thửa ngày `date` — để kéo thanh thời gian trên bản đồ."""
    import re
    reqlang.set_lang(lang)
    if not gate()["passed"]:
        raise HTTPException(409, tr("Lịch sử nước radar chưa bật.", "Radar water history not enabled."))
    if not (8.0 <= lat <= 24.0 and 102.0 <= lon <= 110.0) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise HTTPException(422, tr("Toạ độ hoặc ngày không hợp lệ.", "Invalid coordinates or date."))
    s = water_history.scene(lat, lon, date)
    if s is None:
        raise HTTPException(404, tr("Không có cảnh radar nào chụp thửa vào ngày này.", "No radar scene over this plot on that day."))
    return s


@router.get("/api/water/history/{job_id}")
def water_history_poll(job_id: str, db: Session = Depends(get_session)) -> dict:
    st = jobs_db.status(db, job_id)
    if st is None or st.get("kind") != water_history.JOB_KIND:
        raise HTTPException(404, "Không có việc này.")
    return st


# ------------------------------------------------------------------ GĐ3: kiểm chứng tin đăng

class ListingIn(BaseModel):
    text: str = Field(min_length=3, max_length=5000)
    lat: float = Field(ge=8.0, le=24.0)
    lon: float = Field(ge=102.0, le=110.0)


@router.post("/api/listing/check")
def listing_check_api(body: ListingIn, request: Request, lang: str = "vi",
                      user: User | None = Depends(auth.optional_user)) -> dict:
    """Tách câu khẳng định trong tin đăng người dùng TỰ DÁN và đối chiếu với số đo của thửa. Không lưu nội dung."""
    from app.routes_eudr import enforce_quota
    from app.services import listing_check
    reqlang.set_lang(lang)
    enforce_quota("screen", request, user)
    return listing_check.check(body.text, body.lat, body.lon)
