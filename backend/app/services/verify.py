"""SỔ ĐIỂM TỰ CHẤM — phần mềm tự kiểm tra cảnh báo của CHÍNH NÓ.

VÌ SAO MODULE NÀY TỒN TẠI
=========================
Trước đây TerraTwin chứng minh được nó *sẽ* bắt được lũ Huế 2020 — backtest.py
diễn lại một danh sách sự kiện lịch sử chọn sẵn. Đó là bằng chứng thật, nhưng
là bằng chứng về một mô hình đứng yên: nó không nói gì về hàng trăm cảnh báo
phần mềm đã phát ra cho người dùng thật, và nó không bao giờ đổi.

Module này làm việc ngược lại và khó hơn: lấy đúng những cảnh báo đã phát, đợi
cửa sổ dự báo trôi qua, kéo SỐ LIỆU THỰC ĐO của chính khoảng thời gian đó về,
rồi chấm trúng hay trượt. Không ai cho điểm hộ, và không sửa được về sau.

BA QUYẾT ĐỊNH THIẾT KẾ QUAN TRỌNG
=================================

① ĐẾM CẢ LẦN BỎ SÓT, KHÔNG CHỈ LẦN BÁO SAI.
   Nếu chỉ chấm những cảnh báo đã phát thì mọi lần bỏ sót đều vô hình, và con
   số thu được chỉ là "tỉ lệ báo đúng trên số lần dám báo" — đẹp và vô nghĩa.
   Một hệ thống không bao giờ báo gì sẽ đạt 100%. Vì vậy `sweep_misses()` quét
   ngược lịch sử từng thửa để tìm những đợt hiểm họa THẬT SỰ đã xảy ra mà phần
   mềm im lặng, và ghi chúng lại bằng hàng `retro=1`.

② NGƯỜI DÙNG THẮNG DỮ LIỆU.
   Khi người trả lời một chạm nói khác với số liệu vệ tinh, câu trả lời của họ
   được ghi đè. Họ đứng trên thửa đất; ERA5 là ô lưới ~9 km nội suy. Ở đây dữ
   liệu là phương án khi không có người, không phải trọng tài.

③ CHẤM Ở NGƯỠNG "CÓ XẢY RA KHÔNG", KHÔNG PHẢI "CÓ ĐÚNG MỨC KHÔNG".
   Một cảnh báo NGUY HIỂM mà thực tế chỉ tới mức cảnh báo thì hiểm họa vẫn đã
   xảy ra thật — gọi đó là báo bừa là tự vu oan cho mình. Ngược lại gọi nó là
   trúng hoàn toàn thì lại tự khen. Nên: chấm trúng/trượt ở ngưỡng SAFE (hiểm
   họa có thành hình hay không), đồng thời LƯU LẠI `observed_peak` để ai cũng
   tự đối chiếu được mức độ. Sổ điểm công bố cả hai con số.

ĐỘ TRỄ. Open-Meteo Archive (nền ERA5) chậm khoảng 5 ngày so với thực tại. Cộng
thêm biên an toàn thành SETTLE_DAYS = 6. Một cảnh báo 7 ngày vì thế được chấm
sau 13 ngày. Chấm sớm hơn sẽ nhận về dữ liệu rỗng và kết luận sai là "báo bừa"
— tự bôi nhọ mình bằng một lỗi kỹ thuật.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Alert, Plot
from app.services import hazard, realdata

# Độ trễ của kho lưu trữ ERA5 + biên an toàn.
SETTLE_DAYS = 6
# Chuỗi chỉ số cần lịch sử chạy đà; 60 ngày khớp với WARMUP của tầng ML.
WARMUP_DAYS = 60
# Quá hạn này mà không tự chấm được và cũng không ai trả lời thì thôi.
EXPIRE_DAYS = 60
# Quét ngược tìm lần bỏ sót trong ngần này ngày.
MISS_LOOKBACK_DAYS = 90

_OUTCOMES = ("hit", "miss", "false_alarm", "expired")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _observed_peak(module_id: str, lat: float, lon: float,
                   start: datetime, end: datetime) -> tuple[float | None, str]:
    """Đỉnh chỉ số THỰC ĐO trong [start, end]. Trả (đỉnh, ghi chú) — None nếu
    không lấy được dữ liệu (mất mạng, ngoài vùng phủ)."""
    lead = start - timedelta(days=WARMUP_DAYS)
    rows = realdata.historical_weather(
        lat, lon, lead.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
    if not rows:
        return None, "Chưa kéo được số liệu thực đo cho khoảng này."

    series = hazard.index_series(module_id, lat, lon, rows)
    if not series:
        return None, "Không dựng được chuỗi chỉ số từ số liệu thực đo."

    # Chỉ lấy phần TRONG cửa sổ cảnh báo. Phần chạy đà chỉ để chỉ số có trí nhớ,
    # tính cả vào đỉnh là chấm nhầm sang chuyện đã xảy ra trước khi báo.
    want = {(start + timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range((end - start).days + 1)}
    inside = [v for r, v in zip(rows, series) if r.get("date") in want]
    if not inside:
        return None, "Số liệu trả về không phủ đúng cửa sổ cảnh báo."

    peak = max(float(v) for v in inside)
    return peak, f"Đỉnh thực đo {peak:.1f} trên {len(inside)} ngày."


def due_query(now: datetime | None = None):
    """Cảnh báo đã tới hạn chấm: chưa có kết quả và cửa sổ đã trôi qua đủ lâu."""
    now = now or _now()
    # window_days + SETTLE_DAYS tính bằng SQL sẽ khác nhau giữa SQLite và
    # Postgres, nên lọc thô ở đây rồi lọc tinh bằng Python — số hàng nhỏ.
    cutoff = now - timedelta(days=SETTLE_DAYS)
    return (select(Alert)
            .where(Alert.outcome.is_(None), Alert.created_at <= cutoff)
            .order_by(Alert.created_at.asc()))


def verify_alert(a: Alert, db: Session, now: datetime | None = None) -> dict:
    """Chấm MỘT cảnh báo. Sửa thẳng vào đối tượng ORM, KHÔNG commit."""
    now = now or _now()
    start = a.created_at
    end = start + timedelta(days=a.window_days or 7)

    if now < end + timedelta(days=SETTLE_DAYS):
        return {"alert_id": a.id, "skipped": "chưa tới hạn chấm"}

    if not hazard.supports(a.module_id):
        # Mô-đun quang học/địa hình chưa có cách tự chấm từ số liệu ngày. Chúng
        # chỉ được chấm khi người dùng trả lời một chạm — nói thẳng như vậy
        # thay vì im lặng bỏ qua để rồi hàng này treo mãi.
        if now > start + timedelta(days=EXPIRE_DAYS):
            a.outcome = "expired"
            a.verified_at = now
            a.verify_source = "data"
            a.verify_note = ("Mô-đun này chưa tự chấm được từ số liệu khí tượng "
                             "ngày, và không có ai trả lời trong 60 ngày.")
            return {"alert_id": a.id, "outcome": "expired"}
        return {"alert_id": a.id, "skipped": "chờ người dùng trả lời"}

    lat, lon = _coords(a, db)
    peak, note = _observed_peak(a.module_id, lat, lon, start, end)
    if peak is None:
        if now > start + timedelta(days=EXPIRE_DAYS):
            a.outcome = "expired"
            a.verified_at = now
            a.verify_source = "data"
            a.verify_note = note
            return {"alert_id": a.id, "outcome": "expired"}
        return {"alert_id": a.id, "skipped": note}

    a.observed_peak = round(peak, 1)
    a.outcome = "hit" if peak >= hazard.SAFE else "false_alarm"
    a.verified_at = now
    a.verify_source = "data"
    a.verify_note = (
        f"{note} Ngưỡng thành hình {hazard.SAFE:.0f}, "
        f"ngưỡng nguy hiểm {hazard.WARNING:.0f}. "
        f"Đã báo mức “{a.risk_level}”. Nguồn: Open-Meteo Archive (ERA5)."
    )
    return {"alert_id": a.id, "module": a.module_id, "outcome": a.outcome,
            "observed_peak": a.observed_peak}


def _coords(a: Alert, db: Session) -> tuple[float | None, float | None]:
    """Toạ độ của cảnh báo — lấy từ thửa gắn kèm.

    Có thể trả (None, None): thửa đã bị xoá sau khi cảnh báo được phát. Bên gọi
    phải xử lý, vì cảnh báo mồ côi không chấm được nhưng cũng không được treo
    mãi trong hàng đợi.
    """
    if a.plot_id is None:
        return None, None
    p = db.get(Plot, a.plot_id)
    return (p.lat, p.lon) if p is not None else (None, None)


def sweep(db: Session, limit: int = 200) -> dict:
    """Chấm mọi cảnh báo tới hạn. An toàn khi gọi lại nhiều lần."""
    now = _now()
    rows = db.execute(due_query(now).limit(max(1, limit))).scalars().all()

    counts = {k: 0 for k in _OUTCOMES}
    skipped, done = 0, []
    for a in rows:
        lat, _lon = _coords(a, db)
        if lat is None:
            # Không định vị được thì không chấm được — nhưng cũng không được
            # treo mãi trong hàng đợi, nếu không mỗi lượt quét sau lại tải về
            # đúng những hàng này rồi bỏ qua.
            a.outcome = "expired"
            a.verified_at = now
            a.verify_source = "data"
            a.verify_note = ("Thửa đất gắn với cảnh báo này đã bị xoá."
                             if a.plot_id is not None
                             else "Cảnh báo không gắn với thửa nào nên không "
                                  "có toạ độ để đối chiếu.")
            counts["expired"] += 1
            continue
        try:
            r = verify_alert(a, db, now)
        except Exception as e:                 # một hàng hỏng không chặn cả lượt
            skipped += 1
            done.append({"alert_id": a.id, "error": type(e).__name__})
            continue
        if r.get("outcome"):
            counts[r["outcome"]] += 1
            done.append(r)
        else:
            skipped += 1
    db.commit()
    return {"checked": len(rows), "verified": sum(counts.values()),
            "skipped": skipped, "counts": counts, "details": done[:50]}


# ---------------------------------------------------------------------------
# LẦN BỎ SÓT — phần khiến sổ điểm này không phải một lời tự khen
# ---------------------------------------------------------------------------

def sweep_misses(db: Session, days: int = MISS_LOOKBACK_DAYS,
                 max_plots: int = 200) -> dict:
    """Tìm những đợt hiểm họa ĐÃ XẢY RA THẬT mà phần mềm không hề báo.

    Một lời gọi mạng cho mỗi thửa là đủ: kho lưu trữ trả cả dải ngày trong một
    lần, các cửa sổ được cắt tại chỗ. 9 thửa × 4 mô-đun × 90 ngày = 9 lời gọi.

    Chỉ tính là bỏ sót khi đỉnh thực đo đạt ngưỡng NGUY HIỂM. Ngưỡng thấp hơn
    sẽ sinh ra vô số "bỏ sót" cho những đợt mưa vừa mà không ai coi là hiểm
    họa, và sổ điểm sẽ vô dụng vì quá bi quan.
    """
    now = _now()
    end = (now - timedelta(days=SETTLE_DAYS)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=days)

    plots = db.execute(select(Plot).limit(max_plots)).scalars().all()
    found, scanned, failed = 0, 0, 0

    for p in plots:
        lead = start - timedelta(days=WARMUP_DAYS)
        rows = realdata.historical_weather(
            p.lat, p.lon, lead.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        if not rows:
            failed += 1
            continue
        scanned += 1

        for module_id in hazard.IDS:
            series = hazard.index_series(module_id, p.lat, p.lon, rows)
            if not series or len(series) != len(rows):
                continue
            found += _record_misses(db, p, module_id, rows, series, start, now)

    db.commit()
    return {"plots_scanned": scanned, "plots_failed": failed,
            "misses_recorded": found, "lookback_days": days,
            "threshold": hazard.WARNING}


def _record_misses(db: Session, p: Plot, module_id: str, rows, series,
                   start: datetime, now: datetime) -> int:
    """Ghi lại các đợt vượt ngưỡng nguy hiểm không có cảnh báo tương ứng.

    Gộp các ngày vượt ngưỡng liền nhau thành MỘT đợt. Không gộp thì một trận
    mưa bảy ngày sẽ đếm thành bảy lần bỏ sót và bóp méo sổ điểm.
    """
    added = 0
    run_start: datetime | None = None
    run_peak = 0.0

    def close(run_start: datetime, run_peak: float) -> int:
        # Đã từng báo gì cho thửa+mô-đun này quanh đợt đó chưa? Nới ±3 ngày:
        # báo trước hai ngày rồi hiểm họa mới tới vẫn là báo trúng.
        lo = run_start - timedelta(days=10)
        hi = run_start + timedelta(days=3)
        seen = db.execute(
            select(Alert.id).where(
                Alert.plot_id == p.id, Alert.module_id == module_id,
                Alert.created_at >= lo, Alert.created_at <= hi)
        ).first()
        if seen:
            return 0
        # Đã ghi nhận đợt bỏ sót này ở lượt quét trước chưa?
        dup = db.execute(
            select(Alert.id).where(
                Alert.plot_id == p.id, Alert.module_id == module_id,
                Alert.retro == 1,
                Alert.created_at >= run_start - timedelta(days=1),
                Alert.created_at <= run_start + timedelta(days=1))
        ).first()
        if dup:
            return 0
        ten, _ = hazard.name_unit(module_id)
        db.add(Alert(
            user_id=p.user_id, plot_id=p.id, module_id=module_id,
            risk_level="danger",
            headline=f"[HỒI CỨU] {p.name}: {ten} đạt {run_peak:.0f} điểm — "
                     f"phần mềm ĐÃ KHÔNG báo trước.",
            recommendation="",
            created_at=run_start, acknowledged=1,
            outcome="miss", verified_at=now, verify_source="data",
            observed_peak=round(run_peak, 1), window_days=1, retro=1,
            verify_note=(f"Phát hiện khi quét ngược lịch sử. Đỉnh thực đo "
                         f"{run_peak:.1f} ≥ ngưỡng nguy hiểm "
                         f"{hazard.WARNING:.0f}, không có cảnh báo nào trong "
                         f"khoảng −10/+3 ngày. Nguồn: Open-Meteo Archive (ERA5)."),
        ))
        return 1

    for r, v in zip(rows, series):
        try:
            d = datetime.strptime(r["date"], "%Y-%m-%d")
        except (KeyError, TypeError, ValueError):
            continue
        if d < start:
            continue
        if float(v) >= hazard.WARNING:
            if run_start is None:
                run_start, run_peak = d, float(v)
            else:
                run_peak = max(run_peak, float(v))
        elif run_start is not None:
            added += close(run_start, run_peak)
            run_start, run_peak = None, 0.0

    if run_start is not None:
        added += close(run_start, run_peak)
    return added
