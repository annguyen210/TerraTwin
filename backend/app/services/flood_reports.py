"""SỔ LŨ CÔNG KHAI (data/flood_reports.json): đợt nước radar nào trùng với bài báo / tài liệu ghi NGẬP ở đúng huyện cũ
hoặc tỉnh của thửa. Việc 14/11/2026 — người dùng cần thấy bằng chứng độc lập, không chỉ "máy nói có nước".

Lớp DIỄN GIẢI như mùa lũ: không thêm/bớt đợt, không đổi phép đo, KHÔNG phải xác nhận thực địa (field_truth). Mỗi bài trong
sổ đã được mở để kiểm ngày đăng và địa danh; chỉ ghi nơi bài nói rõ là ngập. Ranh huyện + tỉnh cũ: geoBoundaries gbHumanitarian VNM
ADM2/ADM1 2020 (Chính phủ VN qua HDX; CC BY 3.0 IGO), giản lược ~100 m — thửa sát ranh huyện có thể bị xếp sang huyện bên cạnh.
Cửa sổ ngày như phép đối chiếu báo chí (water_press_protocol.json): khoảng ngập của bài giao với [S−12, S+3] ngày."""
from __future__ import annotations

import json
import os
import unicodedata
from datetime import date, timedelta
from functools import lru_cache

from app.services.reqlang import tr

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data")
BEFORE_DAYS, AFTER_DAYS = 12, 3
MAX_REPORTS = 3


def fold(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").replace("Đ", "D").replace("đ", "d"))
    return "".join(c for c in s if c.isalnum() and not unicodedata.combining(c)).lower()


def _load(name: str):
    try:
        with open(os.path.join(DATA, *name.split("/")), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


@lru_cache(maxsize=1)
def registry() -> tuple[dict, ...]:
    return tuple((_load("flood_reports.json") or {}).get("reports") or ())


@lru_cache(maxsize=1)
def _units() -> tuple:
    """(tên huyện đã gập, tên tỉnh, tỉnh đã gập, hộp bao, hình shapely) — dựng hình một lần, bỏ toạ độ thô."""
    from shapely.geometry import shape
    d = _load("admin/vnm_adm2_2020.json") or {}
    return tuple((fold(u["name"]), u["province"], fold(u["province"]), tuple(u["bbox"]),
                  shape({"type": u["type"], "coordinates": u["coordinates"]})) for u in d.get("units") or ())


@lru_cache(maxsize=4096)
def _locate(lat5: float, lon5: float) -> tuple | None:
    from shapely.geometry import Point
    p = Point(lon5, lat5)
    for dist, prov, provf, (x0, y0, x1, y1), geom in _units():
        if x0 <= lon5 <= x1 and y0 <= lat5 <= y1 and geom.covers(p):
            return dist, prov, provf
    return None


def locate(lat: float, lon: float) -> dict | None:
    """Huyện cũ (ranh 2020) + tỉnh cũ chứa điểm; None nếu ngoài Việt Nam / không đọc được ranh."""
    hit = _locate(round(float(lat), 5), round(float(lon), 5))
    return {"district_key": hit[0], "province": hit[1], "province_key": hit[2]} if hit else None


def _overlaps(rep: dict, start: str) -> bool:
    s = date.fromisoformat(start[:10])
    lo, hi = (s - timedelta(days=BEFORE_DAYS)).isoformat(), (s + timedelta(days=AFTER_DAYS)).isoformat()
    return rep["flood_from"] <= hi and rep["flood_to"] >= lo


def _vn(iso: str) -> str:
    y, m, d = iso[:10].split("-")
    return f"{int(d)}/{int(m)}/{y}"


def match_event(start: str, loc: dict) -> dict | None:
    """Mức khớp tốt nhất của MỘT đợt: "district" (bài nêu đúng huyện cũ) > "province" (chỉ nêu tỉnh). None = sổ chưa có."""
    district, province = [], []
    for rep in registry():
        if not _overlaps(rep, start):
            continue
        area = next((a for a in rep.get("areas") or () if a.get("level") == "district"
                     and fold(a["name"]) == loc["district_key"] and fold(a["province"]) == loc["province_key"]), None)
        if area:
            district.append((rep, area))
        elif loc["province_key"] in {fold(p) for p in rep.get("provinces") or ()}:
            province.append((rep, None))
    hits, level = (district, "district") if district else (province, "province")
    if not hits:
        return None
    hits.sort(key=lambda t: t[0]["published"], reverse=True)
    out = []
    for rep, area in hits[:MAX_REPORTS]:
        s = rep.get("summary") or {}
        out.append({"id": rep["id"], "publisher": rep["publisher"], "published": rep["published"], "url": rep["url"],
                    "summary": tr(s.get("vi", ""), s.get("en") or s.get("vi", "")),
                    "area": area["name"] if area else None, "via": (area or {}).get("via")})
    return {"level": level, "reports": out, "n_reports": len(hits)}


def annotate(r: dict, lat: float, lon: float) -> dict:
    """Gắn `press` vào từng đợt + tóm tắt. Trả {} khi không có đợt hoặc không định vị được (fail-open)."""
    ev = r.get("events") or []
    if not ev or not registry():
        return {}
    try:
        loc = locate(lat, lon)
    except Exception:
        return {}
    if not loc:
        return {}
    events, n_d, n_p = [], 0, 0
    for e in ev:
        m = match_event(e["start"], loc)
        events.append({**e, "press": m})
        n_d += bool(m and m["level"] == "district")
        n_p += bool(m and m["level"] == "province")
    n, prov = len(ev), loc["province"]
    if n_d:
        text = tr(f"Báo chí ghi ngập ở đúng huyện cũ của thửa trong {n_d}/{n} đợt radar.",
                  f"News reports flooding in the plot's former district for {n_d}/{n} radar events.")
        if n_p:
            text += tr(f" Thêm {n_p} đợt chỉ có tin {prov} ngập, chưa nêu huyện.",
                       f" {n_p} more event(s) only have reports of flooding in {prov}, without the district.")
    elif n_p:
        text = tr(f"{n_p}/{n} đợt có tin báo ghi {prov} ngập, nhưng chưa nêu đúng huyện của thửa.",
                  f"{n_p}/{n} events have news of flooding in {prov}, but not naming the plot's district.")
    else:
        text = tr(f"Sổ lũ công khai ({len(registry())} bài) chưa có tin báo trùng các đợt này — không có nghĩa là không ngập.",
                  f"The public flood register ({len(registry())} reports) has no news matching these events — that does not mean no flooding.")
    return {"events": events,
            "press": {"n_district": n_d, "n_province": n_p, "n_events": n, "province": prov, "registry_size": len(registry()),
                      "text": text,
                      "limits": tr("Tin báo nêu huyện hoặc xã, không chứng minh chính thửa này bị ngập; báo chỉ đưa tin trận lớn. "
                                   "Đây là bằng chứng công khai bổ sung, không phải xác nhận thực địa.",
                                   "News names a district or commune; it does not prove this exact plot flooded, and only big floods "
                                   "make the news. This is supporting public evidence, not a field confirmation.")}}


def evidence(events: list[dict], season_only: bool = False) -> str:
    """Một câu cho kiểm tin rao: bài mới nhất nêu đúng huyện cũ, ở đợt gần nhất có khớp. '' nếu không có."""
    for e in reversed(events or []):
        if season_only and e.get("season") == "out":
            continue
        m = e.get("press")
        if m and m["level"] == "district":
            rp = m["reports"][0]
            where = rp.get("via") or rp.get("area")
            return tr(f" Báo chí cũng ghi ngập ở đúng huyện cũ của thửa đợt {_vn(e['start'])}: {rp['publisher']} {_vn(rp['published'])}"
                      f"{f' ({where})' if where else ''}.",
                      f" News also reports flooding in the plot's former district for the {_vn(e['start'])} event: {rp['publisher']} "
                      f"{_vn(rp['published'])}{f' ({where})' if where else ''}.")
    return ""
