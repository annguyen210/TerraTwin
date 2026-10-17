"""MÙA LŨ CỦA TỪNG ĐIỂM — lớp DIỄN GIẢI cho lịch sử nước radar (17/10/2026). KHÔNG đổi bộ phát hiện (cổng GĐ2).

Vấn đề đo trên production: ruộng lúa/ao tôm được cho nước theo vụ cũng làm VV tụt như lũ, nên "đợt nước phủ" lẫn
nước tưới. Cà Mau 9.18, 105.09: 13 đợt, tháng bắt đầu 5,5,5,4,8,4,5,8,3,4,4,5,9 (mùa khô); Hà Nội 21.12, 105.89: 6 đợt
tháng 3,2,7,7,3,2 (cấy lúa xuân); Huế 16.52, 107.59: 6 đợt tháng 11,10,10,10,9,10 (đúng mùa lũ). Giám khảo thấy "13 đợt"
sẽ hiểu là ngập 13 lần; tin "không ngập" ở ruộng tôm/lúa bị chấm "mâu thuẫn" oan.

QUY TẮC v1 (đăng ký TRƯỚC khi chạy: backend/data/eval/flood_season_protocol.json):
  · Dữ liệu: lượng mưa ngày ERA5 (Open-Meteo Archive) 2016-01-01 → 2025-12-31 tại chính toạ độ điểm.
  · Mưa trung bình từng tháng dương lịch qua 10 năm.
  · LÕI = các tháng xếp theo mưa trung bình giảm dần, lấy dần tới khi cộng dồn ≥ 50% tổng mưa năm trung bình.
  · MÙA LŨ = LÕI ∪ {tháng liền sau mỗi tháng trong lõi} — lũ/ngập thường đến SAU đỉnh mưa.
  · Một đợt "trong mùa lũ" nếu tháng BẮT ĐẦU của đợt thuộc mùa lũ; ngược lại "ngoài mùa lũ".
  · Đợt ngoài mùa lũ trên khung đo là ruộng (WorldCover Trồng trọt ≥ 50%) hoặc có mặt nước nhỏ (nền p10 < −18 dB,
    hoặc WorldCover Mặt nước 10–50%) → "có thể là nước tưới / nuôi trồng theo vụ".
Lớp này chỉ BẬT khi cổng trong tệp kết quả (backend/data/eval/flood_season_result.json) đạt.
"""
from __future__ import annotations

import json
import os

from app.services import cache_store
from app.services.reqlang import tr

WINDOW = ("2016-01-01", "2025-12-31")
CORE_SHARE = 0.50
RULE_V = 1
_TTL = 365 * 86400
RESULT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "eval", "flood_season_result.json")


def monthly_mm(rows: list[dict]) -> list[float]:
    """Mưa trung bình của từng tháng 1..12 (mm/tháng) qua các năm có trong `rows` [{date, precip}]."""
    tot: dict[tuple[int, int], float] = {}
    for r in rows:
        y, m = int(r["date"][:4]), int(r["date"][5:7])
        tot[(y, m)] = tot.get((y, m), 0.0) + float(r.get("precip") or 0.0)
    out = []
    for m in range(1, 13):
        vals = [v for (y, mm), v in tot.items() if mm == m]
        out.append(round(sum(vals) / len(vals), 1) if vals else 0.0)
    return out


def season_from_monthly(mm: list[float]) -> dict:
    """Áp quy tắc v1 lên 12 giá trị mưa trung bình tháng — tách riêng để kiểm được không cần mạng."""
    annual = sum(mm)
    order = sorted(range(1, 13), key=lambda m: -mm[m - 1])
    core, acc = [], 0.0
    for m in order:
        core.append(m)
        acc += mm[m - 1]
        if annual > 0 and acc >= CORE_SHARE * annual:
            break
    months = sorted(set(core) | {m % 12 + 1 for m in core})
    return {"months": months, "core": sorted(core), "monthly_mm": mm, "annual_mm": round(annual, 1)}


def season(lat: float, lon: float) -> dict | None:
    """Mùa lũ của điểm (cache 1 năm — khí hậu 2016–2025 không đổi). None nếu không lấy được ERA5."""
    from app.services import realdata
    key = cache_store.make_key("flood-season", RULE_V, round(lat, 2), round(lon, 2))
    hit = cache_store.get(key)
    if hit is not None:
        return hit or None
    rows = realdata.historical_weather(lat, lon, *WINDOW)
    if not rows or len(rows) < 365 * 8:
        return None
    out = season_from_monthly(monthly_mm(rows))
    out.update(window=f"{WINDOW[0][:4]}–{WINDOW[1][:4]}", source="ERA5 (ECMWF) — Open-Meteo Archive", rule_v=RULE_V)
    cache_store.put(key, out, ttl_seconds=_TTL)
    return out


def label(start: str, s: dict) -> str:
    """'in' nếu tháng bắt đầu của đợt thuộc mùa lũ, ngược lại 'out'."""
    return "in" if int(start[5:7]) in s["months"] else "out"


def months_text(months: list[int]) -> str:
    """[9, 10, 11, 12] → '9–12'; [1, 7, 8, 9, 12] → '12–1, 7–9' (khoảng liền nhau, vòng qua cuối năm)."""
    ms = sorted(months)
    if not ms:
        return "—"
    runs, cur = [], [ms[0]]
    for m in ms[1:]:
        if m == cur[-1] + 1:
            cur.append(m)
        else:
            runs.append(cur)
            cur = [m]
    runs.append(cur)
    if len(runs) > 1 and runs[0][0] == 1 and runs[-1][-1] == 12:
        runs[0] = runs.pop() + runs[0]
    return ", ".join(f"{r[0]}–{r[-1]}" if len(r) > 1 else f"{r[0]}" for r in runs)


def gate_passed() -> bool:
    """Lớp diễn giải chỉ bật khi cổng đăng ký trước đạt (tệp kết quả do ops/flood_season_gate.py ghi)."""
    try:
        with open(RESULT, encoding="utf-8") as f:
            return bool(json.load(f).get("passed"))
    except (OSError, ValueError):
        return False


def seasonal_note() -> str:
    return tr("thường là nước tưới / nuôi trồng theo vụ", "usually seasonal irrigation / aquaculture")


# ======================================================================================================================
# v2 (17/10/2026) — BẮT LŨ SỚM/MUỘN bằng dấu hiệu MƯA CỰC ĐOAN, KHÔNG nới mùa. v1 ở trên GIỮ NGUYÊN; hồ sơ cũ giữ câu v1.
# Đăng ký trước: backend/data/eval/flood_season_v2_protocol.json. Lý do: đợt 19/09/2024 ở ruộng lúa Huế 16,52; 107,59
# trùng ngày bão Soulik nhưng v1 xếp "ngoài mùa lũ".
#   · Với mỗi đợt NGOÀI mùa lũ v1: cửa sổ mưa = từ ngày SAU cảnh radar khô gần nhất trước đợt tới NGÀY cảnh ướt đầu tiên
#     (= ngày bắt đầu đợt), dài tối đa 12 ngày (chu kỳ chụp) — cảnh khô xa hơn thì cửa sổ bắt đầu từ start − 11 ngày.
#   · Tổng mưa 3 ngày kết thúc ở ngày d: mưa(d−2) + mưa(d−1) + mưa(d) (ERA5 ngày, Open-Meteo Archive, tại điểm).
#     Lấy giá trị LỚN NHẤT với d chạy trong cửa sổ.
#   · Ngưỡng = phân vị 97 (nội suy tuyến tính) của MỌI tổng 3 ngày liên tiếp tại điểm, ERA5 2016-01-01 → 2025-12-31.
#   · Lớn nhất ≥ ngưỡng → "extreme": ngoài mùa nhưng ngay sau mưa cực đoan — có thể là lũ sớm/muộn. Còn lại → "out".
#   · Kiểm tin đăng: đợt "extreme" tính như đợt trong mùa lũ khi đối chiếu "không ngập".
# ======================================================================================================================
RULE_V2 = 2
P_EXTREME = 97.0
WINDOW_DAYS = 12
RESULT_V2 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "eval", "flood_season_v2_result.json")


def three_day_sums(rows: list[dict]) -> dict[str, float]:
    """{ngày d: mưa(d−2)+mưa(d−1)+mưa(d)} cho mọi d có đủ 3 ngày liên tiếp trong `rows` [{date, precip}]."""
    from datetime import date as _d, timedelta as _td
    rain = {r["date"]: float(r.get("precip") or 0.0) for r in rows}
    out = {}
    for ds in rain:
        d = _d.fromisoformat(ds)
        a, b = (d - _td(days=2)).isoformat(), (d - _td(days=1)).isoformat()
        if a in rain and b in rain:
            out[ds] = rain[a] + rain[b] + rain[ds]
    return out


def percentile(vals: list[float], p: float) -> float:
    """Phân vị p (0–100), nội suy tuyến tính — cùng cách numpy.percentile mặc định."""
    xs = sorted(vals)
    if not xs:
        raise ValueError("rỗng")
    k = (len(xs) - 1) * p / 100.0
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def window(start: str, prev_scene: str | None) -> tuple[str, str]:
    """Cửa sổ mưa [từ, tới] của một đợt: (cảnh khô trước + 1 ngày) → ngày bắt đầu, tối đa WINDOW_DAYS ngày."""
    from datetime import date as _d, timedelta as _td
    s = _d.fromisoformat(start)
    lo = s - _td(days=WINDOW_DAYS - 1)
    if prev_scene:
        lo = max(lo, _d.fromisoformat(prev_scene) + _td(days=1))
    return lo.isoformat(), s.isoformat()


def max3_in_window(sums: dict[str, float], frm: str, to: str) -> tuple[float, str] | None:
    """(tổng 3 ngày lớn nhất, ngày kết thúc) với d trong [frm, to]; None nếu thiếu dữ liệu mưa cho cả cửa sổ."""
    from datetime import date as _d, timedelta as _td
    d, end, best = _d.fromisoformat(frm), _d.fromisoformat(to), None
    while d <= end:
        v = sums.get(d.isoformat())
        if v is not None and (best is None or v > best[0]):
            best = (round(v, 1), d.isoformat())
        d += _td(days=1)
    return best


def _rain_rows(lat: float, lon: float) -> list[dict] | None:
    """Mưa ngày ERA5 tại điểm: 2016–2025 (cố định, dùng cho ngưỡng) + 2026 tới 6 ngày trước (đợt gần đây)."""
    from datetime import date as _d, timedelta as _td
    from app.services import realdata
    base = realdata.historical_weather(lat, lon, *WINDOW)
    if not base:
        return None
    end = _d.today() - _td(days=6)
    recent = realdata.historical_weather(lat, lon, "2026-01-01", end.isoformat()) if end.year >= 2026 else []
    return base + (recent or [])


def threshold_p97(lat: float, lon: float) -> float | None:
    """Ngưỡng P97 của tổng mưa 3 ngày tại điểm, ERA5 2016–2025 (cache 1 năm)."""
    from app.services import realdata
    key = cache_store.make_key("flood-p97", RULE_V2, round(lat, 2), round(lon, 2))
    hit = cache_store.get(key)
    if hit is not None:
        return hit.get("p97") if hit else None
    rows = realdata.historical_weather(lat, lon, *WINDOW)
    if not rows or len(rows) < 365 * 8:
        return None
    p = round(percentile(list(three_day_sums(rows).values()), P_EXTREME), 1)
    cache_store.put(key, {"p97": p}, ttl_seconds=_TTL)
    return p


def label_v2(events: list[dict], scene_dates: list[str], s: dict, lat: float, lon: float) -> list[dict]:
    """Gắn nhãn v2 cho từng đợt: 'in' (như v1) | 'extreme' | 'out', kèm bằng chứng mưa cho đợt ngoài mùa v1."""
    p97 = threshold_p97(lat, lon)
    rows = _rain_rows(lat, lon) if p97 is not None else None
    sums = three_day_sums(rows) if rows else {}
    idx = {d: i for i, d in enumerate(scene_dates)}
    out = []
    for e in events:
        lab = label(e["start"], s)
        rec = {**e, "season": lab}
        if lab == "out" and p97 is not None:
            i = idx.get(e["start"])
            prev = scene_dates[i - 1] if i else None
            frm, to = window(e["start"], prev)
            m = max3_in_window(sums, frm, to)
            rec.update(rain_window=[frm, to], p97_mm=p97)
            if m is not None:
                rec.update(rain3d_mm=m[0], rain3d_end=m[1])
                if m[0] >= p97:
                    rec["season"] = "extreme"
        out.append(rec)
    return out


def gate_v2_passed() -> bool:
    try:
        with open(RESULT_V2, encoding="utf-8") as f:
            return bool(json.load(f).get("passed"))
    except (OSError, ValueError):
        return False


# ======================================================================================================================
# v3 (17/10/2026) — bắt lũ sớm/muộn bằng LƯU LƯỢNG SÔNG GloFAS, tín hiệu độc lập với mưa. Bộ phát hiện + v1 GIỮ NGUYÊN,
# v2 đã trượt (không bật). Đăng ký trước: backend/data/eval/flood_season_v3_protocol.json.
#   · Ô sông: trong các ô lưới GloFAS 0,05° có tâm cách thửa ≤ 5 km, lấy ô có lưu lượng TRUNG BÌNH 2016–2025 lớn nhất.
#   · Phạm vi: chỉ áp dụng khi lưu lượng trung bình của ô đó ≥ 10 m³/s. Ngoài phạm vi → giữ nhãn v1 ("không áp dụng v3").
#   · Cửa sổ: như v2 (sau cảnh khô liền trước → ngày bắt đầu đợt, tối đa 12 ngày).
#   · R-a: lưu lượng ngày LỚN NHẤT trong cửa sổ ≥ P97 (2016–2025) của chính ô sông.
#   · R-b: lưu lượng lớn nhất ≥ P90 của ô sông VÀ tổng mưa 3 ngày ERA5 lớn nhất trong cửa sổ ≥ P97 của điểm (như v2).
#   · Đợt NGOÀI mùa v1 thoả quy tắc → "river": ngoài mùa nhưng sông lên mức hiếm — có thể là lũ sớm/muộn.
# ======================================================================================================================
RULE_V3 = 3
GLOFAS = "https://flood-api.open-meteo.com/v1/flood"
GLOFAS_CELL = 0.05
RIVER_KM = 5.0
RIVER_MIN_MEAN = 10.0
P_RIVER_A = 97.0
P_RIVER_B = 90.0
RESULT_V3 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "eval", "flood_season_v3_result.json")


def _km(a1: float, o1: float, a2: float, o2: float) -> float:
    import math
    p1, p2 = math.radians(a1), math.radians(a2)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(o2 - o1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def cells_within(lat: float, lon: float, km: float = RIVER_KM) -> list[tuple[float, float]]:
    """Tâm các ô GloFAS 0,05° (tâm ở x,x25 / x,x75) cách điểm ≤ km."""
    import math
    la0 = math.floor(lat / GLOFAS_CELL) * GLOFAS_CELL + GLOFAS_CELL / 2
    lo0 = math.floor(lon / GLOFAS_CELL) * GLOFAS_CELL + GLOFAS_CELL / 2
    out = []
    for i in range(-2, 3):
        for j in range(-2, 3):
            c = (round(la0 + i * GLOFAS_CELL, 3), round(lo0 + j * GLOFAS_CELL, 3))
            if _km(lat, lon, *c) <= km:
                out.append(c)
    return out


def _glofas_fetch(cells: list[tuple[float, float]], start: str, end: str) -> list[dict[str, float]] | None:
    """Lưu lượng ngày (m³/s) của nhiều ô trong MỘT lần gọi Open-Meteo Flood API. None nếu lỗi."""
    import urllib.parse
    import urllib.request
    q = urllib.parse.urlencode({"latitude": ",".join(f"{c[0]:.3f}" for c in cells),
                                "longitude": ",".join(f"{c[1]:.3f}" for c in cells),
                                "daily": "river_discharge", "start_date": start, "end_date": end})
    try:
        req = urllib.request.Request(f"{GLOFAS}?{q}", headers={"User-Agent": "TerraTwin/0.7 (Vietnam land digital twin)"})
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None
    d = d if isinstance(d, list) else [d]
    out = []
    for x in d:
        t, v = x["daily"]["time"], x["daily"]["river_discharge"]
        out.append({t[i]: float(v[i]) for i in range(len(t)) if v[i] is not None})
    return out


def river_cell(lat: float, lon: float) -> dict | None:
    """Ô sông của thửa + ngưỡng P97/P90 (2016–2025), cache 1 năm. None nếu GloFAS lỗi. Có trường in_scope."""
    key = cache_store.make_key("glofas-cell", RULE_V3, round(lat, 4), round(lon, 4))
    hit = cache_store.get(key)
    if hit is not None:
        return hit or None
    cells = cells_within(lat, lon)
    if not cells:
        return None
    series = _glofas_fetch(cells, *WINDOW)
    if not series:
        return None
    best = None
    for c, s in zip(cells, series):
        if len(s) < 365 * 8:
            continue
        mean = sum(s.values()) / len(s)
        if best is None or mean > best["mean_m3s"]:
            best = {"lat": c[0], "lon": c[1], "km": round(_km(lat, lon, *c), 2), "mean_m3s": round(mean, 2), "_s": s}
    if best is None:
        return None
    vals = list(best.pop("_s").values())
    best.update(p97_m3s=round(percentile(vals, P_RIVER_A), 2), p90_m3s=round(percentile(vals, P_RIVER_B), 2),
                in_scope=best["mean_m3s"] >= RIVER_MIN_MEAN, window=f"{WINDOW[0][:4]}–{WINDOW[1][:4]}",
                source="GloFAS v4 (Copernicus EMS) — Open-Meteo Flood API", rule_v=RULE_V3)
    cache_store.put(key, best, ttl_seconds=_TTL)
    return best


def discharge(cell: dict, frm: str, to: str) -> dict[str, float] | None:
    """Lưu lượng ngày của ô sông trong [frm, to] (cache 30 ngày theo cửa sổ)."""
    key = cache_store.make_key("glofas-win", round(cell["lat"], 3), round(cell["lon"], 3), frm, to)
    hit = cache_store.get(key)
    if hit is not None:
        return hit or None
    s = _glofas_fetch([(cell["lat"], cell["lon"])], frm, to)
    if not s:
        return None
    cache_store.put(key, s[0], ttl_seconds=30 * 86400)
    return s[0]


def label_v3(events: list[dict], scene_dates: list[str], s: dict, lat: float, lon: float, rule: str) -> list[dict]:
    """Nhãn v3 theo quy tắc `rule` ('a' | 'b'): 'in' (như v1) | 'river' | 'out', kèm bằng chứng lưu lượng / mưa.

    Ngoài phạm vi (không có ô sông ≥ 10 m³/s trong 5 km) → giữ nhãn v1 và ghi v3_scope = False."""
    cell = river_cell(lat, lon)
    scope = bool(cell and cell.get("in_scope"))
    p97_rain = threshold_p97(lat, lon) if (scope and rule == "b") else None
    sums = three_day_sums(_rain_rows(lat, lon) or []) if p97_rain is not None else {}
    idx = {d: i for i, d in enumerate(scene_dates)}
    out = []
    for e in events:
        rec = {**e, "season": label(e["start"], s), "v3_scope": scope}
        if rec["season"] == "out" and scope:
            i = idx.get(e["start"])
            frm, to = window(e["start"], scene_dates[i - 1] if i else None)
            q = discharge(cell, frm, to) or {}
            if q:
                day, qmax = max(q.items(), key=lambda kv: kv[1])
                rec.update(q_max_m3s=round(qmax, 2), q_date=day, p97_m3s=cell["p97_m3s"], p90_m3s=cell["p90_m3s"],
                           river_cell=[cell["lat"], cell["lon"]], river_km=cell["km"], rain_window=[frm, to])
                if rule == "a":
                    hit = qmax >= cell["p97_m3s"]
                else:
                    m = max3_in_window(sums, frm, to)
                    if m is not None:
                        rec.update(rain3d_mm=m[0], rain3d_end=m[1], p97_mm=p97_rain)
                    hit = qmax >= cell["p90_m3s"] and m is not None and m[0] >= p97_rain
                if hit:
                    rec["season"] = "river"
        out.append(rec)
    return out


def gate_v3() -> dict | None:
    """Kết quả cổng v3: {'passed', 'enabled_rule': 'a'|'b'|None, ...} hoặc None nếu chưa chạy."""
    try:
        with open(RESULT_V3, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None
