"""Backtest — KIỂM CHỨNG 'biết trước' bằng dữ liệu lịch sử THẬT.

Chạy ĐÚNG mô hình chỉ số đang dùng cho dự báo, nhưng trên dữ liệu thời tiết
quá khứ (Open-Meteo Archive / ERA5, không cần key), rồi đo:
  - model có vượt ngưỡng nguy hiểm trước khi sự kiện xảy ra không?
  - báo trước bao nhiêu ngày (lead time)?

Đây là bằng chứng trung thực cho lời hứa 'CẢNH BÁO TRƯỚC' — không phóng đại.
"""
from __future__ import annotations

from datetime import date

from app.services import calibration
from app.services import hazard
from app.services import realdata
from app.services.reqlang import tr


def _lbl(ev: dict) -> str:
    return tr(ev["label"], ev.get("label_en", ev["label"]))


def _note(ev: dict) -> str:
    return tr(ev["note"], ev.get("note_en", ev["note"]))

# Hai tầng cảnh báo sau khi hiệu chuẩn theo khí hậu từng điểm:
#   CẢNH BÁO (40 ≈ phân vi 90, nổ ~10% số cửa sổ) → "chuẩn bị", cho lead time dài
#   NGUY HIỂM (70 ≈ phân vi 97, nổ ~3%)           → "hành động ngay", nổ sát sự kiện
WARNING = 40.0
DANGER = 70.0

# Các sự kiện thiên tai THẬT, có tài liệu, ở Việt Nam.
EVENTS = {
    "hue_flood_2020": {
        "label": "Lũ lịch sử Thừa Thiên Huế – 10/2020",
        "label_en": "Historic flood, Thừa Thiên Huế – Oct 2020",
        "module": "flood", "lat": 16.46, "lon": 107.59,
        "start": "2020-10-05", "end": "2020-10-15", "event_date": "2020-10-11",
        "note": "Mưa cực lớn gây ngập diện rộng miền Trung.",
        "note_en": "Extreme rainfall caused widespread flooding in central Vietnam.",
    },
    "quangnam_flood_2022": {
        "label": "Lũ Quảng Nam – Đà Nẵng 10/2022",
        "label_en": "Quảng Nam – Đà Nẵng flood, Oct 2022",
        "module": "flood", "lat": 15.87, "lon": 108.33,
        "start": "2022-10-08", "end": "2022-10-16", "event_date": "2022-10-14",
        "note": "Mưa lớn do áp thấp, ngập nặng Hội An – Đà Nẵng.",
        "note_en": "Heavy rain from a depression, severe flooding in Hội An – Đà Nẵng.",
    },
    "traleng_landslide_2020": {
        "label": "Sạt lở Trà Leng, Quảng Nam – 28/10/2020",
        "label_en": "Trà Leng landslide, Quảng Nam – 28 Oct 2020",
        "module": "landslide", "lat": 15.33, "lon": 108.05,
        "start": "2020-10-20", "end": "2020-10-30", "event_date": "2020-10-28",
        "note": "Bão số 9 + mưa dài ngày gây sạt lở vùi lấp nhiều nhà.",
        "note_en": "Typhoon no. 9 plus prolonged rain triggered a landslide that buried many homes.",
    },
    "bentre_drought_2020": {
        "label": "Hạn – mặn ĐBSCL (Bến Tre) mùa khô 2020",
        "label_en": "Mekong Delta drought–salinity (Bến Tre), dry season 2020",
        "module": "drought", "lat": 10.24, "lon": 106.37,
        "start": "2020-02-15", "end": "2020-03-15", "event_date": "2020-03-05",
        "note": "Đợt hạn – xâm nhập mặn khốc liệt, nhiều tỉnh công bố khẩn cấp.",
        "note_en": "A severe drought–saltwater intrusion; several provinces declared emergencies.",
    },
}


def _index_for(module: str, lat: float, lon: float, rows):
    """Chạy đúng mô hình chỉ số của module trên chuỗi dữ liệu (lịch sử)."""
    _, note = hazard.terrain(module, lat, lon)
    return hazard.index_series(module, lat, lon, rows), note


def run_event(event_id: str) -> dict | None:
    ev = EVENTS.get(event_id)
    if ev is None:
        return None
    rows = realdata.historical_weather(ev["lat"], ev["lon"], ev["start"], ev["end"])
    if not rows:
        return {
            "event_id": event_id, "label": _lbl(ev), "module": ev["module"],
            "note": _note(ev), "available": False,
            "message": tr("Không tải được dữ liệu lịch sử (kiểm tra kết nối mạng).",
                          "Couldn't load historical data (check network)."),
        }

    series, terrain = _index_for(ev["module"], ev["lat"], ev["lon"], rows)
    points = [{"date": dt, "value": v, "precip": rows[i]["precip"],
               "warning": v >= WARNING, "danger": v >= DANGER}
              for i, (_, dt, v) in enumerate(series)]

    ev_date = date.fromisoformat(ev["event_date"])

    def _lead(flag: str):
        p = next((p for p in points if p[flag]), None)
        if p is None:
            return None, None
        return p, (ev_date - date.fromisoformat(p["date"])).days

    first_warning, lead_warning = _lead("warning")
    first_danger, lead_days = _lead("danger")

    # TỈ LỆ BÁO ĐỘNG: lead time một mình là vô nghĩa nếu model hét cả năm.
    # Một model luôn báo "nguy hiểm" cũng đạt 4/4 trên các sự kiện nổi tiếng.
    far = calibration.alarm_rate(ev["module"], ev["lat"], ev["lon"], threshold=DANGER)
    far_warn = calibration.alarm_rate(ev["module"], ev["lat"], ev["lon"], threshold=WARNING)

    peak = max(points, key=lambda p: p["value"]) if points else None
    if lead_warning is not None and lead_warning >= 0:
        verdict = tr(f"✅ Mức CẢNH BÁO bật ngày {first_warning['date']} — báo trước "
                     f"{lead_warning} ngày so với sự kiện {ev['event_date']}",
                     f"✅ WARNING triggered on {first_warning['date']} — "
                     f"{lead_warning} days before the event {ev['event_date']}")
        if lead_days is not None and lead_days >= 0:
            verdict += tr(f"; mức NGUY HIỂM bật trước {lead_days} ngày",
                          f"; DANGER triggered {lead_days} days ahead")
        verdict += "."
        if far and far_warn:
            verdict += tr(f" Tại điểm này ngưỡng cảnh báo chỉ nổ "
                          f"{far_warn['alarm_rate_pct']}% và ngưỡng nguy hiểm "
                          f"{far['alarm_rate_pct']}% số cửa sổ trong 10 năm — "
                          "không phải báo bừa.",
                          f" At this point the warning threshold fires only "
                          f"{far_warn['alarm_rate_pct']}% and danger "
                          f"{far['alarm_rate_pct']}% of windows over 10 years — "
                          "not a false-alarm machine.")
        success = True
    elif first_warning:
        verdict = tr(f"⚠️ Chỉ bật cảnh báo ngày {first_warning['date']}, sau mốc sự "
                     f"kiện {ev['event_date']} ({-lead_warning} ngày).",
                     f"⚠️ Only warned on {first_warning['date']}, after the event "
                     f"{ev['event_date']} ({-lead_warning} days late).")
        success = False
    else:
        verdict = tr("❌ Model không vượt ngưỡng cảnh báo trong cửa sổ này.",
                     "❌ The model didn't cross the warning threshold in this window.")
        success = False

    return {
        "event_id": event_id, "label": _lbl(ev), "module": ev["module"],
        "note": _note(ev), "available": True, "location": {"lat": ev["lat"], "lon": ev["lon"]},
        "event_date": ev["event_date"], "terrain": terrain,
        "threshold": DANGER, "threshold_warning": WARNING,
        "lead_days": lead_days, "lead_days_warning": lead_warning,
        "success": success, "verdict": verdict,
        "peak": peak, "first_danger": first_danger, "first_warning": first_warning,
        "series": points,
        "alarm_rate": far, "alarm_rate_warning": far_warn,
        "honesty_note": ("Lead time chỉ có nghĩa khi đi kèm tỉ lệ báo động — một "
                         "model luôn hét 'nguy hiểm' cũng đạt 4/4 trên các sự kiện "
                         "nổi tiếng. `alarm_rate` là % cửa sổ 7 ngày trong 10 năm mà "
                         "model vượt ngưỡng tại CHÍNH điểm này. Trước hiệu chuẩn, "
                         "mức nguy hiểm nổ 46–61% số ngày ở miền Trung; sau hiệu "
                         "chuẩn theo phân vi khí hậu còn ~3%."),
        "data_source": tr("Open-Meteo Archive (ERA5) — dữ liệu thời tiết lịch sử thật",
                          "Open-Meteo Archive (ERA5) — real historical weather data"),
    }


def list_events() -> list[dict]:
    return [{"id": k, "label": _lbl(v), "module": v["module"], "note": _note(v)}
            for k, v in EVENTS.items()]
