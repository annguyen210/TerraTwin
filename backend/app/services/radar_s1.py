"""RADAR XUYÊN MÂY — Sentinel-1 phát hiện mất cây CẢ TRONG MÙA MƯA.

Ảnh quang học (Sentinel-2) mù suốt mùa mưa Tây Nguyên (tháng 5–10): mây che gần hết.
Một vườn bị chặt phá tháng 7 có thể tới tháng 12 mới lộ ra trên ảnh quang học. Radar
băng C của Sentinel-1 nhìn xuyên mây, chụp lại mỗi 6–12 ngày. Cùng nguyên lý với hệ
thống cảnh báo RADD (Đại học Wageningen, chạy trên Global Forest Watch): tán rừng tán
xạ khối mạnh ở phân cực VH; mất tán → tán xạ VH tụt vài dB.

PHƯƠNG PHÁP (đơn giản hơn RADD, nói rõ):
  · trung bình VH (dB) trong ranh thửa của các cảnh 60 ngày gần nhất, CÙNG HƯỚNG QUỸ ĐẠO
    (tăng/giảm — góc nhìn khác cho tán xạ khác), so với CÙNG KHOẢNG NGÀY NĂM TRƯỚC (khử
    mùa vụ: độ ẩm đất, lá non),
  · nền ≥ −15 dB (tán xạ khối kiểu rừng/cây cao; rừng dày −11…−18 dB theo tài liệu) VÀ
    tụt ≥ 3 dB → "tín hiệu mạnh"; tụt 1,5–3 dB → "tín hiệu yếu".
Đo thật (3/10/2026): rừng Yok Đôn VH −12,8 dB.

Đây là TÍN HIỆU GIÁM SÁT sống (không vào hồ sơ đã ký, không đổi quy tắc sàng lọc v1):
vườn có tín hiệu mạnh thì giám sát sau phát hành đánh dấu "cần sàng lọc lại".
"""
from __future__ import annotations

import math
import urllib.parse
from datetime import date, timedelta

from app.services import cache_store, eudr_geo, mpc
from app.services.reqlang import tr

COLLECTION = "sentinel-1-rtc"
WINDOW_DAYS = 60
MAX_SCENES = 6
FOREST_DB = -15.0
STRONG_DROP_DB = 3.0
WEAK_DROP_DB = 1.5
_TTL = 12 * 3600


def _vh_db(item: str, feature: dict) -> float | None:
    q = urllib.parse.urlencode({"collection": COLLECTION, "item": item, "assets": "vh"})
    r = mpc._call(f"{mpc.DATA}?{q}", feature)
    try:
        m = float(list(r["properties"]["statistics"].values())[0]["mean"])
        return 10 * math.log10(m) if m > 0 else None
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def _series(geom, start: date, end: date, orbit: str | None) -> tuple[list[float], str | None, list[str]]:
    r = mpc._call(mpc.STAC, {"collections": [COLLECTION], "bbox": list(geom.bounds),
                             "datetime": f"{start.isoformat()}/{end.isoformat()}", "limit": 40})
    feats = (r or {}).get("features") or []
    if orbit is None and feats:
        orbit = feats[0]["properties"].get("sat:orbit_state")
    feats = [f for f in feats if f["properties"].get("sat:orbit_state") == orbit][:MAX_SCENES]
    feature = {"type": "Feature", "properties": {}, "geometry": eudr_geo.geojson_of(geom)}
    vals, dates = [], []
    for f in feats:
        v = _vh_db(f["id"], feature)
        if v is not None:
            vals.append(v)
            dates.append((f["properties"].get("datetime") or "")[:10])
    return vals, orbit, dates


def change(plot: dict, today: date | None = None) -> dict:
    """So VH 60 ngày gần nhất với cùng kỳ năm trước trong ranh thửa."""
    today = today or date.today()
    geom = eudr_geo.shapely_geom(plot)
    key = cache_store.make_key("s1-change", 1, eudr_geo.geojson_of(geom), today.isoformat())
    hit = cache_store.get(key)
    if hit is not None:
        return _label(hit)
    start = today - timedelta(days=WINDOW_DAYS)
    now, orbit, d_now = _series(geom, start, today, None)
    before, _, d_before = _series(geom, start - timedelta(days=365), today - timedelta(days=365), orbit) if orbit else ([], None, [])
    if len(now) < 2 or len(before) < 2:
        raw = {"available": False, "orbit": orbit, "n_now": len(now), "n_before": len(before)}
    else:
        m_now = sorted(now)[len(now) // 2]
        m_before = sorted(before)[len(before) // 2]
        drop = m_before - m_now
        level = ("strong" if m_before >= FOREST_DB and drop >= STRONG_DROP_DB else
                 "weak" if m_before >= FOREST_DB and drop >= WEAK_DROP_DB else "none")
        raw = {"available": True, "orbit": orbit, "vh_db_now": round(m_now, 2), "vh_db_year_before": round(m_before, 2),
               "drop_db": round(drop, 2), "signal": level, "dates_now": d_now, "dates_before": d_before,
               "window_days": WINDOW_DAYS}
    cache_store.put(key, raw, ttl_seconds=_TTL)
    return _label(raw)


def _label(raw: dict) -> dict:
    out = dict(raw)
    if not raw.get("available"):
        out["label"] = tr("Chưa đủ cảnh radar để so (cần ≥2 cảnh mỗi kỳ, cùng hướng quỹ đạo).",
                          "Not enough radar scenes to compare (≥2 per period, same orbit direction).")
        return out
    s, d = raw["signal"], raw["drop_db"]
    out["label"] = {
        "strong": tr(f"Radar xuyên mây: tán xạ VH tụt {d:.1f} dB so với cùng kỳ năm trước — dấu hiệu MẠNH mất tán cây, cần sàng lọc lại.",
                     f"Cloud-piercing radar: VH backscatter fell {d:.1f} dB vs the same period last year — STRONG sign of canopy loss; re-screen."),
        "weak": tr(f"Radar xuyên mây: VH tụt {d:.1f} dB — dấu hiệu yếu, theo dõi thêm.",
                   f"Cloud-piercing radar: VH fell {d:.1f} dB — weak sign, keep watching."),
        "none": tr(f"Radar xuyên mây: không thấy tụt tán xạ (chênh {d:+.1f} dB so với cùng kỳ năm trước).",
                   f"Cloud-piercing radar: no backscatter drop ({d:+.1f} dB vs the same period last year)."),
    }[s]
    return out
