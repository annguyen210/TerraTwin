"""Backtest — KIỂM CHỨNG 'biết trước' bằng dữ liệu lịch sử THẬT.

Chạy ĐÚNG mô hình chỉ số đang dùng cho dự báo, nhưng trên dữ liệu thời tiết
quá khứ (Open-Meteo Archive / ERA5, không cần key), rồi đo:
  - model có vượt ngưỡng nguy hiểm trước khi sự kiện xảy ra không?
  - báo trước bao nhiêu ngày (lead time)?

Đây là bằng chứng trung thực cho lời hứa 'CẢNH BÁO TRƯỚC' — không phóng đại.
"""
from __future__ import annotations

from datetime import date

from app.services import hazard
from app.services import realdata

DANGER = 70.0  # ngưỡng 'nguy hiểm' dùng chung cho lũ/sạt lở/hạn

# Các sự kiện thiên tai THẬT, có tài liệu, ở Việt Nam.
EVENTS = {
    "hue_flood_2020": {
        "label": "Lũ lịch sử Thừa Thiên Huế – 10/2020",
        "module": "flood", "lat": 16.46, "lon": 107.59,
        "start": "2020-10-05", "end": "2020-10-15", "event_date": "2020-10-11",
        "note": "Mưa cực lớn gây ngập diện rộng miền Trung.",
    },
    "quangnam_flood_2022": {
        "label": "Lũ Quảng Nam – Đà Nẵng 10/2022",
        "module": "flood", "lat": 15.87, "lon": 108.33,
        "start": "2022-10-08", "end": "2022-10-16", "event_date": "2022-10-14",
        "note": "Mưa lớn do áp thấp, ngập nặng Hội An – Đà Nẵng.",
    },
    "traleng_landslide_2020": {
        "label": "Sạt lở Trà Leng, Quảng Nam – 28/10/2020",
        "module": "landslide", "lat": 15.33, "lon": 108.05,
        "start": "2020-10-20", "end": "2020-10-30", "event_date": "2020-10-28",
        "note": "Bão số 9 + mưa dài ngày gây sạt lở vùi lấp nhiều nhà.",
    },
    "bentre_drought_2020": {
        "label": "Hạn – mặn ĐBSCL (Bến Tre) mùa khô 2020",
        "module": "drought", "lat": 10.24, "lon": 106.37,
        "start": "2020-02-15", "end": "2020-03-15", "event_date": "2020-03-05",
        "note": "Đợt hạn – xâm nhập mặn khốc liệt, nhiều tỉnh công bố khẩn cấp.",
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
            "event_id": event_id, "label": ev["label"], "module": ev["module"],
            "note": ev["note"], "available": False,
            "message": "Không tải được dữ liệu lịch sử (kiểm tra kết nối mạng).",
        }

    series, terrain = _index_for(ev["module"], ev["lat"], ev["lon"], rows)
    points = [{"date": dt, "value": v, "precip": rows[i]["precip"],
               "danger": v >= DANGER} for i, (_, dt, v) in enumerate(series)]

    first_danger = next((p for p in points if p["danger"]), None)
    ev_date = date.fromisoformat(ev["event_date"])
    lead_days = None
    if first_danger:
        lead_days = (ev_date - date.fromisoformat(first_danger["date"])).days

    peak = max(points, key=lambda p: p["value"]) if points else None
    if first_danger and lead_days is not None and lead_days >= 0:
        verdict = (f"✅ Model vượt ngưỡng nguy hiểm ngày {first_danger['date']}, "
                   f"tức BÁO TRƯỚC {lead_days} ngày so với sự kiện {ev['event_date']}.")
        success = True
    elif first_danger:
        verdict = (f"⚠️ Model chỉ vượt ngưỡng ngày {first_danger['date']}, "
                   f"sau mốc sự kiện {ev['event_date']} ({-lead_days} ngày).")
        success = False
    else:
        verdict = "❌ Model không vượt ngưỡng nguy hiểm trong cửa sổ này."
        success = False

    return {
        "event_id": event_id, "label": ev["label"], "module": ev["module"],
        "note": ev["note"], "available": True, "location": {"lat": ev["lat"], "lon": ev["lon"]},
        "event_date": ev["event_date"], "terrain": terrain, "threshold": DANGER,
        "lead_days": lead_days, "success": success, "verdict": verdict,
        "peak": peak, "first_danger": first_danger, "series": points,
        "data_source": "Open-Meteo Archive (ERA5) — dữ liệu thời tiết lịch sử thật",
    }


def list_events() -> list[dict]:
    return [{"id": k, "label": v["label"], "module": v["module"], "note": v["note"]}
            for k, v in EVENTS.items()]
