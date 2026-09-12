"""A14 — PHÁT HIỆN TRÔI DỮ LIỆU & TRÔI HIỆU NĂNG.

Khí hậu đang đổi thật. Khí hậu nền 10 năm dùng để hiệu chuẩn sẽ dần lệch khỏi
hiện tại, và khi đó phần mềm sai một cách ÂM THẦM — không lỗi, không cảnh báo,
chỉ là kém dần đi. Đây là lớp giám sát để chuyện đó không âm thầm:

  · Trôi DỮ LIỆU: PSI giữa phân phối chỉ số gần đây và khí hậu nền. PSI > 0,25
    = trôi mạnh, nên làm mới bộ nhớ đệm khí hậu cho vùng đó.
  · Trôi HIỆU NĂNG: CSI 30 ngày gần nhất so với 90 ngày trước đó. Tụt nhiều =
    mô hình đang kém đi ở đây, cần xem lại.
"""
from __future__ import annotations

from datetime import timedelta

# Ngưỡng PSI quy ước: <0,1 ổn định · 0,1–0,25 dịch nhẹ · >0,25 trôi mạnh.
PSI_ALERT = 0.25
# CSI tụt quá ngần này điểm (%) giữa hai cửa sổ = trôi hiệu năng đáng lo.
CSI_DROP_ALERT = 10.0


def psi(expected: list[float], actual: list[float], bins: int = 10) -> float:
    """Population Stability Index giữa phân phối 'nền' và 'gần đây'.

    Chia bin theo PHÂN VỊ của phân phối nền (không phải bin đều) nên nhạy với
    dịch chuyển ở mọi vùng giá trị. Thiếu dữ liệu → trả 0,0 (đừng báo trôi khi
    chưa đủ mẫu — báo động giả ở tầng giám sát cũng tệ như ở tầng cảnh báo).
    """
    import numpy as np

    exp = np.asarray([x for x in expected if x is not None], dtype=float)
    act = np.asarray([x for x in actual if x is not None], dtype=float)
    if exp.size < bins or act.size < 1:
        return 0.0
    edges = np.unique(np.quantile(exp, np.linspace(0.0, 1.0, bins + 1)))
    if edges.size < 3:
        return 0.0
    e_hist, _ = np.histogram(exp, bins=edges)
    a_hist, _ = np.histogram(act, bins=edges)
    eps = 1e-4
    e_pct = np.clip(e_hist / max(1, e_hist.sum()), eps, None)
    a_pct = np.clip(a_hist / max(1, a_hist.sum()), eps, None)
    return round(float(np.sum((a_pct - e_pct) * np.log(a_pct / e_pct))), 4)


def performance_drift(db, module_id: str | None = None,
                      recent_days: int = 30, prior_days: int = 90) -> dict:
    """Trôi hiệu năng: CSI cửa sổ gần đây so với cửa sổ trước đó.

    Dùng chính bộ đếm theo-ĐỢT của sổ điểm (chỉ prod), nên số này khớp đúng với
    con số công bố ra ngoài — không có hai cách đếm lệch nhau.
    """
    from app.services import scorecard

    now = scorecard._now()
    r0 = now - timedelta(days=recent_days)
    p0 = now - timedelta(days=recent_days + prior_days)
    recent = scorecard._deduped_counts(db, r0, until=now, module_id=module_id)
    prior = scorecard._deduped_counts(db, p0, until=r0, module_id=module_id)
    r_csi = scorecard._rates(recent["hit"], recent["miss"], recent["false_alarm"])["csi_pct"]
    p_csi = scorecard._rates(prior["hit"], prior["miss"], prior["false_alarm"])["csi_pct"]
    drop = None if (r_csi is None or p_csi is None) else round(p_csi - r_csi, 1)
    return {
        "module_id": module_id or "all",
        "csi_recent_pct": r_csi, "csi_prior_pct": p_csi,
        "csi_drop_pct": drop,
        "recent_scored": recent["hit"] + recent["miss"] + recent["false_alarm"],
        "prior_scored": prior["hit"] + prior["miss"] + prior["false_alarm"],
        "degraded": drop is not None and drop > CSI_DROP_ALERT,
        "enough": r_csi is not None and p_csi is not None,
    }


def climate_psi(module_id: str, lat: float, lon: float) -> dict:
    """Trôi DỮ LIỆU khí hậu: PSI giữa phân phối chỉ số của những năm gần đây và
    của cả 10 năm nền. Best-effort — cần dữ liệu khí hậu; không lấy được thì nói
    thẳng 'chưa đủ dữ liệu' chứ không đoán."""
    try:
        from app.services import calibration
        base = calibration.climatology(module_id, lat, lon, years=10)
        recent = calibration.climatology(module_id, lat, lon, years=3)
        if not base or not recent:
            return {"available": False, "message": "Chưa đủ dữ liệu khí hậu cho điểm này."}
        p = psi(base, recent)
        return {
            "available": True, "psi": p, "drifting": p > PSI_ALERT,
            "message": ("Phân phối chỉ số gần đây đã LỆCH mạnh khỏi khí hậu nền — "
                        "nên làm mới hiệu chuẩn cho vùng này." if p > PSI_ALERT else
                        "Khí hậu gần đây còn khớp với nền 10 năm."),
        }
    except Exception as e:      # noqa: BLE001 — giám sát hỏng không được kéo sập API
        return {"available": False, "message": f"Chưa tính được: {type(e).__name__}."}


def overview(db) -> dict:
    """Toàn cảnh trôi hiệu năng theo từng mô-đun hiểm hoạ + tổng."""
    from app.services import hazard

    per_module = [performance_drift(db, m) for m in hazard.IDS]
    degraded = [d for d in per_module if d["degraded"]]
    return {
        "overall": performance_drift(db),
        "by_module": per_module,
        "degraded_modules": [d["module_id"] for d in degraded],
        "note": ("Trôi hiệu năng đo từ sổ điểm (chỉ prod). Trôi dữ liệu khí hậu "
                 "tính theo điểm qua /api/admin/drift?lat=..&lon=..&module=.. "
                 "vì phân phối khí hậu là theo VÙNG, không theo toàn hệ thống."),
    }
