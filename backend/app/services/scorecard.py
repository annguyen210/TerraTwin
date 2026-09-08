"""SỔ ĐIỂM CÔNG KHAI — con số mà TerraTwin không có quyền sửa.

Ai cũng tuyên bố mình chính xác. Không ai công bố tỉ lệ báo bừa của chính mình.
Module này tính đúng con số đó từ bảng `alerts` đã được verify.py chấm, và đưa
nó ra một endpoint công khai không cần đăng nhập.

ĐỌC SỔ ĐIỂM THẾ NÀO
===================
Bốn con số, mượn thẳng thuật ngữ khí tượng nghiệp vụ để người trong ngành đối
chiếu được ngay với bất kỳ cơ quan dự báo nào:

  hit          — đã báo, và hiểm họa xảy ra thật
  false_alarm  — đã báo, nhưng không có gì xảy ra
  miss         — hiểm họa xảy ra thật mà KHÔNG hề báo   (verify.sweep_misses)
  expired      — không tự chấm được và không ai trả lời (không tính vào tỉ lệ)

  POD  = hit / (hit + miss)          "bắt được bao nhiêu phần thực tế"
  FAR  = false_alarm / (hit + false_alarm)   "báo mười lần thì mấy lần hụt"
  CSI  = hit / (hit + miss + false_alarm)    điểm gộp, phạt cả hai loại sai

VÌ SAO PHẢI CÓ CẢ POD LẪN FAR: mỗi con số một mình đều bịp được. Không bao giờ
báo gì thì FAR = 0. Báo mọi ngày thì POD = 100%. Chỉ khi đứng cạnh nhau chúng
mới nói lên điều gì đó thật, và CSI là con số duy nhất không đánh lừa được.

ĐIỀU KIỆN CÔNG BỐ. Dưới MIN_SAMPLE lần chấm thì trả về con số kèm cờ
`enough: false` và KHÔNG làm tròn thành phần trăm đẹp. Khoe "độ chính xác 100%"
trên ba mẫu là chính xác về số học và dối trá về bản chất.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import Alert, Observation
from app.services import federated, hazard

# Dưới ngưỡng này thì công bố số thô, không công bố tỉ lệ.
MIN_SAMPLE = 10
# Số ô lưới tối thiểu để một vùng được lên bản đồ tin cậy — cùng lý do riêng tư
# như federated.MIN_OBS: vùng quá ít mẫu thì tỉ lệ vừa nhiễu vừa dễ truy ngược.
MIN_CELL_SAMPLE = 5
DEFAULT_WINDOW_DAYS = 90

# Cùng thửa + cùng mô-đun + các cảnh báo cách nhau ≤ ngần này ngày = MỘT đợt, MỘT
# phán quyết. Không gộp thì một trận mưa ba ngày sinh ba cảnh báo, rồi bị chấm
# thành ba lần báo bừa cho CÙNG MỘT chuyện — thổi phồng cả tử số lẫn mẫu của FAR.
# Lỗi này sinh ra ngay trên production nếu chỉ đếm từng cảnh báo, không ai thấy.
DEDUP_DAYS = 7
# Sổ điểm CÔNG KHAI chỉ tính cảnh báo prod; bản dev-phase bị loại NHƯNG đếm ra.
DEFAULT_ENV = "prod"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _rates(hit: int, miss: int, fa: int) -> dict:
    """POD / FAR / CSI. Mẫu số bằng 0 trả None chứ KHÔNG trả 0 — không có dữ
    liệu và làm đúng 0% là hai chuyện hoàn toàn khác nhau."""
    pod = hit / (hit + miss) if (hit + miss) else None
    far = fa / (hit + fa) if (hit + fa) else None
    csi = hit / (hit + miss + fa) if (hit + miss + fa) else None
    pct = lambda x: None if x is None else round(x * 100, 1)   # noqa: E731
    return {"pod_pct": pct(pod), "far_pct": pct(far), "csi_pct": pct(csi)}


def _deduped_counts(db: Session, since: datetime, until: datetime | None = None,
                    module_id: str | None = None,
                    env: str | None = DEFAULT_ENV) -> dict:
    """Đếm kết quả THEO ĐỢT, không theo từng cảnh báo.

    Nhiều cảnh báo cho cùng một đợt (cùng thửa + mô-đun, cách ≤ DEDUP_DAYS ngày)
    chỉ tính MỘT phán quyết. Bản ghi bỏ sót (retro=1) đã được verify gộp theo đợt
    nên đếm thẳng.
    """
    from collections import Counter, defaultdict
    q = select(Alert.outcome, Alert.plot_id, Alert.module_id,
               Alert.created_at, Alert.retro).where(
        Alert.outcome.in_(("hit", "miss", "false_alarm")),
        Alert.created_at >= since)
    if until is not None:
        q = q.where(Alert.created_at < until)
    if module_id:
        q = q.where(Alert.module_id == module_id)
    if env is not None:
        q = q.where(Alert.env == env)

    counts: Counter = Counter()
    groups: dict = defaultdict(list)
    for outcome, plot_id, mid, created, retro in db.execute(q).all():
        if retro:
            counts[outcome] += 1
        else:
            groups[(plot_id, mid)].append((created, outcome))
    for items in groups.values():
        items.sort(key=lambda t: t[0])
        last = None
        for created, outcome in items:
            if last is None or (created - last).days > DEDUP_DAYS:
                counts[outcome] += 1          # đợt mới
            last = created
    return {k: int(counts.get(k, 0)) for k in ("hit", "miss", "false_alarm")}


def summary(db: Session, days: int = DEFAULT_WINDOW_DAYS,
            module_id: str | None = None) -> dict:
    """Sổ điểm tổng — đây là thứ hiện trên trang đầu."""
    since = _now() - timedelta(days=max(1, days))

    # ĐẾM THEO ĐỢT + chỉ môi trường prod. Cảnh báo dev-phase bị loại nhưng đếm ra
    # để việc loại trừ là MINH BẠCH, không phải xoá lén.
    counts = _deduped_counts(db, since, module_id=module_id, env=DEFAULT_ENV)
    eq = select(func.count(Alert.id)).where(
        Alert.outcome == "expired", Alert.created_at >= since,
        Alert.env == DEFAULT_ENV)
    if module_id:
        eq = eq.where(Alert.module_id == module_id)
    counts["expired"] = int(db.execute(eq).scalar() or 0)

    xq = select(func.count(Alert.id)).where(
        Alert.outcome.in_(("hit", "miss", "false_alarm")),
        Alert.created_at >= since, Alert.env != DEFAULT_ENV)
    if module_id:
        xq = xq.where(Alert.module_id == module_id)
    excluded_dev = int(db.execute(xq).scalar() or 0)

    hit, miss, fa = counts["hit"], counts["miss"], counts["false_alarm"]
    scored = hit + miss + fa
    pending = db.execute(
        select(func.count(Alert.id)).where(
            Alert.outcome.is_(None), Alert.created_at >= since,
            Alert.env == DEFAULT_ENV)).scalar() or 0

    # Bao nhiêu phán quyết đến từ người thật đứng trên thửa, thay vì từ vệ tinh.
    by_user = db.execute(
        select(func.count(Alert.id)).where(
            Alert.verify_source == "user", Alert.created_at >= since,
            Alert.env == DEFAULT_ENV)).scalar() or 0

    out = {
        "window_days": days,
        "module_id": module_id,
        "counts": counts,
        "scored": scored,
        "pending": int(pending),
        "verified_by_people": int(by_user),
        "excluded_dev": excluded_dev,
        "enough": scored >= MIN_SAMPLE,
        "min_sample": MIN_SAMPLE,
        **_rates(hit, miss, fa),
    }
    out["headline"] = _headline(out)
    out["method"] = (
        "Mỗi cảnh báo được chấm lại sau khi cửa sổ dự báo trôi qua, bằng số "
        "liệu thực đo của chính khoảng thời gian đó (Open-Meteo Archive, nền "
        "ERA5). Lần bỏ sót tìm bằng cách quét ngược lịch sử từng thửa, nên tỉ "
        "lệ này KHÔNG chỉ tính trên những lần phần mềm dám báo. Người dùng trả "
        "lời một chạm được ưu tiên hơn số liệu vệ tinh."
    )
    return out


def _headline(s: dict) -> str:
    """Một câu tiếng Việt cho trang đầu. Không tô hồng khi mẫu còn ít."""
    c = s["counts"]
    # Loại trừ CÓ LÝ DO, nói ra chứ không giấu.
    excl = (f" (đã loại {s['excluded_dev']} cảnh báo giai đoạn phát triển)"
            if s.get("excluded_dev") else "")
    if s["scored"] == 0:
        return ("Chưa có cảnh báo prod nào tới hạn chấm. Sổ điểm sẽ tự hiện khi "
                "cảnh báo thật đầu tiên đủ 13 ngày tuổi." + excl)
    base = (f"{s['window_days']} ngày qua: báo trước {c['hit'] + c['false_alarm']} đợt, "
            f"đúng {c['hit']}, báo bừa {c['false_alarm']}, bỏ sót {c['miss']}")
    if not s["enough"]:
        return (base + f". Mới {s['scored']} đợt chấm — chưa đủ "
                f"{MIN_SAMPLE} để công bố tỉ lệ." + excl)
    return (base + f" — báo bừa {s['far_pct']}%, bắt được {s['pod_pct']}% số đợt "
            f"thực tế." + excl)


def by_module(db: Session, days: int = DEFAULT_WINDOW_DAYS) -> list[dict]:
    """Tách theo mô-đun. Gộp chung sẽ giấu mất chuyện phần mềm giỏi lũ mà kém
    hạn — mà đó chính là thứ người dùng cần biết trước khi tin một cảnh báo."""
    out = []
    for mid in hazard.IDS:
        s = summary(db, days, module_id=mid)
        ten, _ = hazard.name_unit(mid)
        out.append({"module_id": mid, "name": ten, "scored": s["scored"],
                    "counts": s["counts"], "enough": s["enough"],
                    "pod_pct": s["pod_pct"], "far_pct": s["far_pct"],
                    "csi_pct": s["csi_pct"]})
    out.sort(key=lambda r: (-r["scored"], r["module_id"]))
    return out


def timeline(db: Session, days: int = DEFAULT_WINDOW_DAYS,
             buckets: int = 12) -> list[dict]:
    """Sổ điểm theo thời gian — để thấy nó đang tốt lên hay xấu đi.

    Đây là bằng chứng cho câu "phần mềm tự tốt lên": nếu vòng lặp hiệu chỉnh có
    tác dụng thì cột báo bừa phải thấp dần. Nếu không thấp dần thì cũng phải
    hiện ra, chứ không giấu.
    """
    now = _now()
    span = max(1, days) / max(1, buckets)
    rows: list[dict] = []
    for i in range(buckets):
        hi = now - timedelta(days=span * i)
        lo = now - timedelta(days=span * (i + 1))
        # Cùng quy tắc với summary: đếm theo ĐỢT, chỉ prod.
        c = _deduped_counts(db, lo, until=hi, env=DEFAULT_ENV)
        c["expired"] = 0
        rows.append({"from": lo.strftime("%Y-%m-%d"),
                     "to": hi.strftime("%Y-%m-%d"),
                     "counts": c, "scored": c["hit"] + c["miss"] + c["false_alarm"],
                     **_rates(c["hit"], c["miss"], c["false_alarm"])})
    rows.reverse()
    return rows


# ---------------------------------------------------------------------------
# BẢN ĐỒ TIN CẬY THEO VÙNG — hào phòng thủ
# ---------------------------------------------------------------------------

def reliability(db: Session, days: int = 365,
                module_id: str | None = None) -> dict:
    """Phần mềm chính xác Ở ĐÂU — theo ô lưới 0,5° (~55 km).

    VÌ SAO ĐÂY MỚI LÀ HÀO PHÒNG THỦ THẬT: mỗi người dùng thêm trong một vùng
    làm sản phẩm tốt lên cho tất cả những người còn lại trong vùng đó. Đối thủ
    nhiều tiền hơn không mua được thứ này, vì nó không phải dữ liệu bán trên
    thị trường — nó là dữ liệu chỉ tồn tại vì người ta đã dùng phần mềm này, ở
    đây. Nó cũng đổi luôn đơn vị bán tự nhiên từ từng hộ sang cả một vùng.

    DÙNG Ô LƯỚI, KHÔNG DÙNG RANH GIỚI HÀNH CHÍNH — có chủ đích. Bản đồ hành
    chính Việt Nam vừa thay đổi lớn; gắn số liệu vào một danh sách huyện sai
    còn tệ hơn không gắn. Ô lưới 0,5° cũng chính là ô mà federated.py dùng, nên
    độ tin cậy công bố ở đây khớp đúng với vùng được hiệu chỉnh — không có hai
    hệ toạ độ lệch nhau. Làm tròn xuống lưới nên không lộ toạ độ thửa cụ thể.
    """
    since = _now() - timedelta(days=max(1, days))
    from app.db import Plot

    q = (select(Alert.outcome, Plot.lat, Plot.lon)
         .join(Plot, Plot.id == Alert.plot_id)
         .where(Alert.outcome.is_not(None), Alert.created_at >= since,
                Alert.env == DEFAULT_ENV))
    if module_id:
        q = q.where(Alert.module_id == module_id)

    cells: dict[str, dict] = {}
    for outcome, lat, lon in db.execute(q).all():
        if outcome == "expired":
            continue
        key = federated.cell_of(lat, lon)
        c = cells.setdefault(key, {"cell": key, "hit": 0, "miss": 0,
                                   "false_alarm": 0})
        if outcome in c:
            c[outcome] += 1

    out = []
    for c in cells.values():
        n = c["hit"] + c["miss"] + c["false_alarm"]
        lat_s, lon_s = c["cell"].split(",")
        row = {
            **c, "scored": n,
            "lat": float(lat_s), "lon": float(lon_s),
            "grid_deg": federated.GRID,
            "enough": n >= MIN_CELL_SAMPLE,
            **_rates(c["hit"], c["miss"], c["false_alarm"]),
        }
        row["label"] = (
            f"Đã kiểm chứng {n} lần, đúng {c['hit']}."
            if n >= MIN_CELL_SAMPLE
            else f"Mới {n} lần kiểm chứng — chưa đủ để công bố tỉ lệ."
        )
        out.append(row)
    out.sort(key=lambda r: -r["scored"])
    return {"cells": out, "window_days": days, "module_id": module_id,
            "min_cell_sample": MIN_CELL_SAMPLE, "grid_deg": federated.GRID,
            "note": ("Ô lưới 0,5° (~55 km), làm tròn xuống nên không lộ vị trí "
                     "thửa. Vùng dưới 5 lần kiểm chứng không công bố tỉ lệ.")}


def ground_truth(db: Session) -> dict:
    """Kho quan sát thực địa đã lớn tới đâu, và đường một chạm gánh bao nhiêu.

    Con số `by_onetap` là phép thử của cả kiến nghị 03: nếu nó không lớn lên
    thì đường một chạm chưa chạy, dù mã có tồn tại.
    """
    total = db.execute(select(func.count(Observation.id))).scalar() or 0
    rows = db.execute(
        select(Observation.source, func.count(Observation.id))
        .group_by(Observation.source)).all()
    by_source = {str(s or "user"): int(n) for s, n in rows}
    cells = db.execute(select(Observation.lat, Observation.lon)).all()
    distinct_cells = len({federated.cell_of(la, lo) for la, lo in cells})
    return {
        "observations": int(total),
        "by_source": by_source,
        "by_onetap": int(by_source.get("onetap", 0)),
        "cells_covered": distinct_cells,
        "note": ("Quan sát thực địa là tài sản duy nhất trong TerraTwin không "
                 "tải được từ vệ tinh và không mua được ở đâu."),
    }
