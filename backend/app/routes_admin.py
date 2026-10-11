"""QUẢN TRỊ NGƯỜI DÙNG + YÊU CẦU NÂNG CẤP (10/10/2026).

Nguyên tắc của chủ dự án: MỌI tài khoản có ĐỦ MỌI tính năng; "nâng cấp" chỉ là tăng HẠN MỨC (hồ sơ/ngày, lượt
quét/giờ, lượt API/tháng — services/plans.py). Quản trị là người CẤP: duyệt yêu cầu, cấp gói có hạn dùng, cấp vai
trò hợp tác xã. Mọi thao tác của quản trị ghi vào nhật ký của CẢ hai tài khoản (người làm và người được cấp).

Vai trò "admin" KHÔNG cấp được từ giao diện — chỉ qua biến TERRATWIN_ADMIN_EMAILS trên máy chủ. Lý do: một tài khoản
quản trị bị chiếm không được phép tự nhân bản quyền quản trị cho tài khoản khác của kẻ tấn công.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import auth
from app.db import AuditLog, Dossier, Plot, UpgradeRequest, User, get_session
from app.routes_account import log_audit
from app.services import plans

router = APIRouter(tags=["admin"])


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat(timespec="seconds") + "Z" if dt else None


def _plan_view(u: User) -> dict:
    eff = plans.effective(u)
    return {"plan": getattr(u, "plan", "free") or "free", "effective": eff, "name": plans.PLANS[eff]["name"],
            "until": _iso(getattr(u, "plan_until", None)), "note": getattr(u, "plan_note", "") or "",
            "mult": plans.PLANS[eff].get("mult", 1), "api_month": plans.quota_for(eff)}


def _req_view(r: UpgradeRequest, email: str | None = None) -> dict:
    return {"id": r.id, "user_id": r.user_id, "email": email, "created_at": _iso(r.created_at),
            "plan_wanted": r.plan_wanted, "plan_wanted_name": plans.PLANS.get(r.plan_wanted, {}).get("name", r.plan_wanted),
            "reason": r.reason, "status": r.status, "decided_at": _iso(r.decided_at), "admin_note": r.admin_note}


# ------------------------------------------------------------------ phía người dùng

class UpgradeIn(BaseModel):
    plan_wanted: str = Field(pattern="^(pro|enterprise)$")
    reason: str = Field(default="", max_length=1000)


@router.get("/api/account/plan")
def my_plan(user: User = Depends(auth.current_user), db: Session = Depends(get_session)) -> dict:
    """Gói & hạn mức của tôi + các yêu cầu nâng cấp đã gửi."""
    rows = db.execute(select(UpgradeRequest).where(UpgradeRequest.user_id == user.id)
                      .order_by(UpgradeRequest.created_at.desc()).limit(20)).scalars().all()
    from app.services import quota
    m = plans.mult_for(user)
    return {**_plan_view(user),
            "limits": {"dossier_per_day": quota.LIMITS["dossier"][1] * m, "screen_per_hour": quota.LIMITS["screen"][1] * m,
                       "api_per_month": plans.quota_for(plans.effective(user))},
            "principle": "Mọi tài khoản có đủ mọi tính năng. Gói chỉ đổi hạn mức và do quản trị cấp.",
            "catalogue": [{"id": k, "name": v["name"], "mult": v.get("mult", 1), "api_month": v["quota"], "for": v["for"]}
                          for k, v in plans.PLANS.items()],
            "requests": [_req_view(r) for r in rows]}


@router.post("/api/account/upgrade-request", status_code=201)
def request_upgrade(body: UpgradeIn, user: User = Depends(auth.current_user), db: Session = Depends(get_session)) -> dict:
    if db.scalar(select(func.count()).select_from(UpgradeRequest)
                 .where(UpgradeRequest.user_id == user.id, UpgradeRequest.status == "pending")):
        raise HTTPException(409, "Bạn đã có một yêu cầu đang chờ quản trị xem — chờ kết quả trước khi gửi yêu cầu mới.")
    r = UpgradeRequest(user_id=user.id, plan_wanted=body.plan_wanted, reason=body.reason.strip())
    db.add(r)
    log_audit(db, user.id, "upgrade_requested", plans.PLANS[body.plan_wanted]["name"])
    db.commit()
    db.refresh(r)
    return _req_view(r)


# ------------------------------------------------------------------ phía quản trị

@router.get("/api/admin/users")
def admin_users(q: str = "", limit: int = 50, admin: User = Depends(auth.require_admin),
                db: Session = Depends(get_session)) -> dict:
    """Danh sách tài khoản (tìm theo email/tên) kèm vai trò, gói, số thửa/hồ sơ, lần hoạt động gần nhất.
    Không lộ mật khẩu, bí mật hai lớp hay khoá API."""
    stmt = select(User).order_by(User.created_at.desc()).limit(max(1, min(limit, 200)))
    if q.strip():
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(or_(func.lower(User.email).like(like), func.lower(User.name).like(like)))
    users = db.execute(stmt).scalars().all()
    ids = [u.id for u in users]
    def counts(model):
        if not ids:
            return {}
        return dict(db.execute(select(model.user_id, func.count()).where(model.user_id.in_(ids)).group_by(model.user_id)).all())
    n_plots, n_dos = counts(Plot), counts(Dossier)
    last = dict(db.execute(select(AuditLog.user_id, func.max(AuditLog.at)).where(AuditLog.user_id.in_(ids))
                           .group_by(AuditLog.user_id)).all()) if ids else {}
    total = int(db.scalar(select(func.count()).select_from(User)) or 0)
    pending = int(db.scalar(select(func.count()).select_from(UpgradeRequest).where(UpgradeRequest.status == "pending")) or 0)
    return {"total": total, "pending_requests": pending, "users": [{
        "id": u.id, "email": u.email, "name": u.name, "role": u.role or "user", "created_at": _iso(u.created_at),
        "email_verified": bool(u.email_verified), "totp_enabled": bool(getattr(u, "totp_enabled", 0)),
        "plots": int(n_plots.get(u.id, 0)), "dossiers": int(n_dos.get(u.id, 0)), "last_active": _iso(last.get(u.id)),
        **{"plan_" + k: v for k, v in _plan_view(u).items()}} for u in users]}


class GrantIn(BaseModel):
    role: str | None = Field(default=None, pattern="^(user|coop)$")
    plan: str | None = Field(default=None, pattern="^(free|pro|enterprise)$")
    months: int | None = Field(default=None, ge=0, le=60)          # 0 hoặc None = không hạn
    note: str = Field(default="", max_length=200)


def _grant(db: Session, admin: User, u: User, body: GrantIn) -> list[str]:
    done = []
    if body.role and body.role != (u.role or "user"):
        if (u.role or "user") == "admin":
            raise HTTPException(409, "Không đổi vai trò của tài khoản quản trị từ giao diện — quyền quản trị theo TERRATWIN_ADMIN_EMAILS.")
        u.role = body.role
        done.append(f"vai trò → {body.role}")
    if body.plan:
        u.plan = body.plan
        u.plan_until = (_now() + timedelta(days=30 * body.months)) if (body.months and body.plan != "free") else None
        u.plan_note = body.note[:200]
        done.append(f"gói → {plans.PLANS[body.plan]['name']}" + (f" ({body.months} tháng)" if u.plan_until else ""))
    if done:
        log_audit(db, u.id, "admin_grant", f"bởi {admin.email}: " + "; ".join(done))
        log_audit(db, admin.id, "admin_grant_given", f"{u.email}: " + "; ".join(done))
    return done


@router.post("/api/admin/users/{user_id}")
def admin_update_user(user_id: int, body: GrantIn, admin: User = Depends(auth.require_admin),
                      db: Session = Depends(get_session)) -> dict:
    """Cấp vai trò hợp tác xã / người dùng và gói hạn mức (có hạn dùng) cho một tài khoản."""
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(404, "Không có tài khoản này.")
    done = _grant(db, admin, u, body)
    db.commit()
    return {"ok": True, "changed": done, "plan": _plan_view(u), "role": u.role}


@router.get("/api/admin/upgrade-requests")
def admin_requests(status: str = "pending", admin: User = Depends(auth.require_admin),
                   db: Session = Depends(get_session)) -> dict:
    stmt = select(UpgradeRequest, User.email).join(User, User.id == UpgradeRequest.user_id).order_by(UpgradeRequest.created_at.desc()).limit(200)
    if status in ("pending", "approved", "rejected"):
        stmt = stmt.where(UpgradeRequest.status == status)
    return {"requests": [_req_view(r, email) for r, email in db.execute(stmt).all()]}


class DecideIn(BaseModel):
    approve: bool
    plan: str | None = Field(default=None, pattern="^(pro|enterprise)$")
    months: int | None = Field(default=None, ge=0, le=60)
    note: str = Field(default="", max_length=300)


@router.post("/api/admin/upgrade-requests/{req_id}")
def admin_decide(req_id: int, body: DecideIn, admin: User = Depends(auth.require_admin),
                 db: Session = Depends(get_session)) -> dict:
    """Duyệt (cấp gói, có thể đổi gói/thời hạn so với yêu cầu) hoặc từ chối, kèm ghi chú người dùng đọc được."""
    r = db.get(UpgradeRequest, req_id)
    if r is None:
        raise HTTPException(404, "Không có yêu cầu này.")
    if r.status != "pending":
        raise HTTPException(409, "Yêu cầu này đã được xử lý.")
    u = db.get(User, r.user_id)
    r.status, r.decided_at, r.decided_by, r.admin_note = ("approved" if body.approve else "rejected"), _now(), admin.id, body.note[:300]
    if body.approve and u is not None:
        _grant(db, admin, u, GrantIn(plan=body.plan or r.plan_wanted, months=body.months, note=body.note[:200]))
    elif u is not None:
        log_audit(db, u.id, "upgrade_rejected", body.note[:200])
    db.commit()
    return _req_view(r, u.email if u else None)
