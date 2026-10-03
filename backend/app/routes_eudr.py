"""Hồ sơ vườn chuẩn EUDR — kiểm ranh, sàng lọc phá rừng, lô thửa, hồ sơ ký số.

Xem services/eudr_geo.py (chuẩn GeoJSON EU), services/eudr_forest.py (sàng lọc) và
services/eudr.py (lô + hồ sơ). Kiểm ranh và xuất tệp KHÔNG cần đăng nhập (nông hộ,
đại lý chưa có tài khoản vẫn dùng được); lô thửa chạy nền cần đăng nhập vì kết
quả là danh sách nhà cung cấp của một doanh nghiệp.
"""
from __future__ import annotations

import json
import os

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth
from app.db import EudrSet, FieldPhoto, User, get_session
from app.services import dossier, eudr, eudr_forest, eudr_geo, evidence, jobs_db, onetap, reqlang, signing

router = APIRouter(tags=["eudr"])

_MAX_TEXT = 8_000_000            # ~8 MB văn bản — trần của máy chủ miễn phí (EU cho tới 25 MB)


class TextIn(BaseModel):
    text: str = Field(min_length=1, max_length=_MAX_TEXT)
    filename: str = Field(default="", max_length=200)


class GeometryIn(BaseModel):
    geometry: dict
    ref: str = Field(default="", max_length=80)
    producer: str = Field(default="", max_length=120)
    area_ha: float | None = Field(default=None, gt=0, le=100_000)
    gps_accuracy_m: float | None = Field(default=None, ge=0, le=10_000)


class ExportIn(BaseModel):
    text: str | None = Field(default=None, max_length=_MAX_TEXT)
    filename: str = Field(default="", max_length=200)
    geometry: dict | None = None
    ref: str = Field(default="", max_length=80)
    producer: str = Field(default="", max_length=120)
    area_ha: float | None = Field(default=None, gt=0, le=100_000)
    only_valid: bool = True


def _plot_from(body: GeometryIn) -> dict:
    return eudr_geo.validate_geometry(body.geometry, ref=body.ref, area_declared=body.area_ha,
                                      gps_accuracy_m=body.gps_accuracy_m, producer=body.producer or None)


def _geojson_response(fc: dict, name: str) -> Response:
    data = json.dumps(fc, ensure_ascii=False)
    if len(data.encode("utf-8")) > eudr_geo.EU_MAX_FILE_BYTES:
        raise HTTPException(413, reqlang.tr("Tệp xuất vượt 25 MB — trần một tờ khai EU. Chia lô nhỏ hơn.",
                                            "Export exceeds 25 MB — the EU per-statement limit. Split the set."))
    return Response(data, media_type="application/geo+json",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ------------------------------------------------------------------ không cần đăng nhập

@router.post("/api/eudr/validate")
def validate_file(body: TextIn, lang: str = "vi") -> dict:
    """Đọc tệp ranh thửa (GeoJSON, KML, CSV/Excel) → từng thửa đúng/sai chuẩn EU,
    chỗ sai, cách sửa; lỗi nhỏ đã tự sửa thì ghi rõ."""
    reqlang.set_lang(lang)
    return eudr_geo.validate_text(body.text, body.filename)


@router.post("/api/eudr/validate-geometry")
def validate_geometry(body: GeometryIn, lang: str = "vi") -> dict:
    reqlang.set_lang(lang)
    return _plot_from(body)


@router.post("/api/eudr/export")
def export_file(body: ExportIn, lang: str = "vi") -> Response:
    """Tệp GeoJSON đúng mẫu TRACES (6 chữ số, ranh khép kín, ngược chiều kim đồng hồ)."""
    reqlang.set_lang(lang)
    if body.text:
        plots = eudr_geo.validate_text(body.text, body.filename)["plots"]
    elif body.geometry:
        plots = [eudr_geo.validate_geometry(body.geometry, ref=body.ref, area_declared=body.area_ha,
                                            producer=body.producer or None)]
    else:
        raise HTTPException(422, reqlang.tr("Cần tệp hoặc ranh thửa.", "A file or a boundary is required."))
    fc = eudr_geo.to_eu_geojson(plots, producer_name=body.producer or None, only_valid=body.only_valid)
    if not fc["features"]:
        raise HTTPException(422, reqlang.tr("Không có thửa nào đúng chuẩn EU để xuất — sửa lỗi trước.",
                                            "No plot meets the EU rules to export — fix the errors first."))
    return _geojson_response(fc, "terratwin-eudr.geojson")


@router.post("/api/eudr/screen")
def screen_one(body: GeometryIn, lang: str = "vi") -> dict:
    """Kiểm chuẩn EU + sàng lọc phá rừng MỘT thửa (đồng bộ, ~10–20 giây)."""
    reqlang.set_lang(lang)
    plot = _plot_from(body)
    if not plot["valid"]:
        return {"plot": plot, "screening": None}
    return {"plot": plot, "screening": eudr_forest.screen(plot)}


def _photos(db: Session, ids: list[str], lat: float, lon: float) -> list[FieldPhoto]:
    out = []
    for pid in dict.fromkeys(ids):
        ph = db.get(FieldPhoto, pid)
        if ph is None:
            raise HTTPException(422, reqlang.tr(f"Không có ảnh mã {pid}.", f"No photo with ID {pid}."))
        if evidence.haversine_m(ph.plot_lat, ph.plot_lon, lat, lon) > evidence.SAME_PLOT_M:
            raise HTTPException(422, reqlang.tr(f"Ảnh {pid} được kiểm cho một thửa khác.",
                                                f"Photo {pid} was checked for a different plot."))
        out.append(ph)
    return out


def _issue(db: Session, plot: dict, screening: dict, commodity: str | None, producer: str | None,
           user_id: int | None, photos: list[FieldPhoto] | None = None):
    from app.routes_dossier import _payload

    facts = eudr.dossier_facts(plot, screening, commodity=commodity, producer=producer)
    if photos:
        facts["field_evidence"] = [evidence.public(p) for p in photos]
    c = plot["centroid"]
    try:
        row = dossier.issue(db, facts, c["lat"], c["lon"], user_id=user_id)
    except signing.SigningKeyMissing as e:
        raise HTTPException(503, str(e))
    for p in photos or []:
        p.dossier_id = p.dossier_id or row.id
    db.commit()
    return row, _payload(db, row)


class DossierIn(GeometryIn):
    commodity: str = Field(default="coffee", max_length=24)
    evidence_ids: list[str] = Field(default_factory=list, max_length=6)


@router.post("/api/eudr/dossier")
def issue_dossier(body: DossierIn, lang: str = "vi",
                  user: User | None = Depends(auth.optional_user),
                  db: Session = Depends(get_session)) -> dict:
    """Phát hành Hồ sơ vườn chuẩn EUDR ký số cho MỘT thửa. Không cần đăng nhập."""
    reqlang.set_lang(lang)
    plot = _plot_from(body)
    if not plot["valid"]:
        raise HTTPException(422, {"message": reqlang.tr(
            "Ranh thửa chưa đúng chuẩn EU — sửa lỗi rồi phát hành.",
            "The boundary does not meet the EU rules — fix it before issuing."), "plot": plot})
    photos = _photos(db, body.evidence_ids, plot["centroid"]["lat"], plot["centroid"]["lon"])
    screening = eudr_forest.screen(plot)
    commodity = body.commodity if body.commodity in eudr.COMMODITIES else "other"
    _, payload = _issue(db, plot, screening, commodity, body.producer or None,
                        user.id if user else None, photos)
    return payload


@router.get("/api/eudr/method")
def method(lang: str = "vi") -> dict:
    """Phương pháp, nguồn, ngưỡng, và KẾT QUẢ KIỂM ĐỊNH ĐỘC LẬP (nếu đã chạy)."""
    reqlang.set_lang(lang)
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
    validation = protocol = None
    try:
        with open(os.path.join(base, "eudr_validation.json"), encoding="utf-8") as f:
            v = json.load(f)
        validation = {k: v.get(k) for k in ("run_at", "rule_version", "n", "metrics", "pass_thresholds",
                                            "passed", "counts")}
    except (OSError, ValueError):
        pass
    try:
        with open(os.path.join(base, "eudr_validation_protocol.json"), encoding="utf-8") as f:
            protocol = json.load(f)
    except (OSError, ValueError):
        pass
    return {"rule_version": eudr_forest.METHOD_VERSION, "cutoff": eudr_forest.CUTOFF.isoformat(),
            "thresholds": eudr_forest.THRESHOLDS, "sources": eudr_forest.sources(),
            "levels": {k: eudr_forest.label(k) for k in eudr_forest.LEVELS},
            "eu_rules": {"min_decimals": eudr_geo.EU_MIN_DECIMALS, "point_max_ha": eudr_geo.EU_POINT_MAX_HA,
                         "default_point_ha": eudr_geo.EU_DEFAULT_POINT_HA,
                         "max_file_mb": eudr_geo.EU_MAX_FILE_BYTES // (1024 * 1024)},
            "max_screen_per_set": eudr.max_screen(),
            "validation": validation, "validation_protocol": protocol}


# ------------------------------------------------------------------ lô thửa (cần đăng nhập)

class SetIn(TextIn):
    title: str = Field(default="", max_length=200)
    commodity: str = Field(default="coffee", max_length=24)
    producer: str = Field(default="", max_length=120)


def _own(db: Session, set_id: str, user: User) -> EudrSet | None:
    r = db.get(EudrSet, set_id)
    return r if r is not None and r.user_id == user.id else None


def _active(db: Session, user_id: int) -> EudrSet | None:
    return db.execute(select(EudrSet).where(EudrSet.user_id == user_id,
                                            EudrSet.state.in_(("queued", "running")))
                      .order_by(EudrSet.created_at.desc())).scalars().first()


@router.post("/api/eudr/sets")
def submit_set(body: SetIn, lang: str = "vi", user: User = Depends(auth.current_user),
               db: Session = Depends(get_session)) -> dict:
    reqlang.set_lang(lang)
    v = eudr_geo.validate_text(body.text, body.filename)
    if not any(p["valid"] for p in v["plots"]):
        raise HTTPException(422, {"message": reqlang.tr("Không có thửa nào đúng chuẩn EU để sàng lọc.",
                                                        "No plot meets the EU rules to screen."),
                                  "validation": v})
    act = _active(db, user.id)
    if act is not None:
        raise HTTPException(409, {"message": reqlang.tr(
            "Bạn đang có một lô chưa sàng lọc xong — đợi xong rồi gửi lô mới.",
            "You already have a set being screened — wait for it to finish."), "set_id": act.id})
    n_valid = sum(1 for p in v["plots"] if p["valid"])
    job_id = jobs_db.submit(db, eudr.JOB_KIND, {"lang": reqlang.cur_lang()},
                            label=f"EUDR {min(n_valid, eudr.max_screen())} thửa")
    commodity = body.commodity if body.commodity in eudr.COMMODITIES else "other"
    db.add(EudrSet(id=job_id, user_id=user.id, title=body.title[:200], commodity=commodity,
                   producer=body.producer[:120], n_plots=len(v["plots"]),
                   plots_json=json.dumps(v["plots"], ensure_ascii=False), results_json="{}", state="queued"))
    db.commit()
    warn = None
    if n_valid > eudr.max_screen():
        warn = reqlang.tr(f"Lô có {n_valid} thửa đúng chuẩn — chỉ sàng lọc {eudr.max_screen()} thửa đầu "
                          "(trần gói miễn phí). Chia phần còn lại thành lô khác.",
                          f"{n_valid} valid plots — only the first {eudr.max_screen()} are screened (free-tier "
                          "cap). Split the rest into another set.")
    return {"set_id": job_id, "validation": v["summary"], "file_errors": v["file_errors"],
            "screening": min(n_valid, eudr.max_screen()), "warning": warn}


def _progress(db: Session, r: EudrSet) -> dict:
    st = jobs_db.status(db, r.id) or {}
    p = st.get("progress") or {}
    done = len(json.loads(r.results_json or "{}"))
    plots = json.loads(r.plots_json or "[]")
    total = min(sum(1 for x in plots if x["valid"]), eudr.max_screen())
    return {"done": max(done, int(p.get("done") or 0)), "total": total,
            "current": p.get("current") or "", "phase": p.get("phase") or r.state}


@router.get("/api/eudr/sets")
def list_sets(user: User = Depends(auth.current_user), db: Session = Depends(get_session)) -> dict:
    rows = db.execute(select(EudrSet).where(EudrSet.user_id == user.id)
                      .order_by(EudrSet.created_at.desc()).limit(50)).scalars().all()
    return {"max_screen": eudr.max_screen(),
            "sets": [{"id": r.id, "title": r.title, "commodity": r.commodity, "n_plots": r.n_plots,
                      "state": r.state, "created_at": r.created_at.isoformat(timespec="seconds") + "Z",
                      "headline": json.loads(r.summary_json or "{}").get("headline"),
                      "progress": _progress(db, r) if r.state != "done" else None} for r in rows]}


@router.get("/api/eudr/sets/{set_id}")
def get_set(set_id: str, lang: str = "vi", user: User = Depends(auth.current_user),
            db: Session = Depends(get_session)) -> dict:
    reqlang.set_lang(lang)
    r = _own(db, set_id, user)
    if r is None:
        raise HTTPException(404, reqlang.tr("Không có lô thửa này.", "No such set."))
    plots = json.loads(r.plots_json or "[]")
    results = json.loads(r.results_json or "{}")
    out = {"id": r.id, "state": r.state, "title": r.title, "commodity": r.commodity, "producer": r.producer,
           "created_at": r.created_at.isoformat(timespec="seconds") + "Z", "plots": plots,
           "results": {k: eudr_forest._localize(v) if v.get("forest_2020") else v for k, v in results.items()},
           "summary": eudr.summarize(plots, results)}
    if r.state != "done":
        st = jobs_db.status(db, set_id) or {}
        out.update(progress=_progress(db, r), error=st.get("error"))
    return out


@router.get("/api/eudr/sets/{set_id}/geojson")
def set_geojson(set_id: str, which: str = "valid", user: User = Depends(auth.current_user),
                db: Session = Depends(get_session)) -> Response:
    r = _own(db, set_id, user)
    if r is None:
        raise HTTPException(404, reqlang.tr("Không có lô thửa này.", "No such set."))
    fc = eudr.export_geojson(json.loads(r.plots_json), json.loads(r.results_json or "{}"),
                             which="passed" if which == "passed" else "valid", producer=r.producer)
    if not fc["features"]:
        raise HTTPException(422, reqlang.tr("Không có thửa nào để xuất.", "No plot to export."))
    return _geojson_response(fc, f"terratwin-eudr-{r.id[:8]}-{'dat' if which == 'passed' else 'chuan-eu'}.geojson")


@router.get("/api/eudr/sets/{set_id}/csv")
def set_csv(set_id: str, lang: str = "vi", user: User = Depends(auth.current_user),
            db: Session = Depends(get_session)) -> Response:
    reqlang.set_lang(lang)
    r = _own(db, set_id, user)
    if r is None:
        raise HTTPException(404, reqlang.tr("Không có lô thửa này.", "No such set."))
    results = {k: eudr_forest._localize(v) if v.get("forest_2020") else v
               for k, v in json.loads(r.results_json or "{}").items()}
    return Response(eudr.to_csv(json.loads(r.plots_json), results, onetap.base_url()),
                    media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="terratwin-eudr-{r.id[:8]}.csv"'})


@router.post("/api/eudr/sets/{set_id}/dossiers")
def set_dossiers(set_id: str, lang: str = "vi", user: User = Depends(auth.current_user),
                 db: Session = Depends(get_session)) -> dict:
    """Phát hành hồ sơ ký số cho MỌI thửa đã sàng lọc chưa có hồ sơ (dùng lại kết quả
    đã lưu — không gọi vệ tinh lại). Mỗi nông hộ nhận mã + QR của vườn mình."""
    reqlang.set_lang(lang)
    r = _own(db, set_id, user)
    if r is None:
        raise HTTPException(404, reqlang.tr("Không có lô thửa này.", "No such set."))
    if r.state != "done":
        raise HTTPException(409, reqlang.tr("Lô chưa sàng lọc xong.", "The set is not screened yet."))
    plots = {str(p["index"]): p for p in json.loads(r.plots_json)}
    results = json.loads(r.results_json or "{}")
    issued = []
    for k, res in results.items():
        if res.get("dossier_id") or not res.get("forest_2020") or k not in plots:
            continue
        row, _ = _issue(db, plots[k], eudr_forest._localize(res), r.commodity, r.producer or None, user.id)
        res["dossier_id"] = row.id
        issued.append({"ref": plots[k]["ref"], "id": row.id, "url": f"{onetap.base_url()}/h/{row.id}"})
        r.results_json = json.dumps(results, ensure_ascii=False)
        db.commit()
    return {"issued": issued, "n": len(issued)}


@router.delete("/api/eudr/sets/{set_id}", status_code=204)
def delete_set(set_id: str, user: User = Depends(auth.current_user),
               db: Session = Depends(get_session)) -> Response:
    r = _own(db, set_id, user)
    if r is None:
        raise HTTPException(404, reqlang.tr("Không có lô thửa này.", "No such set."))
    db.delete(r)
    db.commit()
    return Response(status_code=204)
