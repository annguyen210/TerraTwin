"""Hiệu chuẩn xác suất cảnh báo lũ / sạt lở trên dự báo LƯU TRỮ — giao thức backend/data/eval/alert_calibration_protocol.json
(đăng ký trước, chạy MỘT lần).

    python ops/alert_calibration.py fetch     # tải dữ liệu từng điểm vào D:/tt-scratch/alertcal (chạy tiếp được nếu gặp 429)
    python ops/alert_calibration.py run       # dựng cặp (dự báo, thực đo), hiệu chuẩn, chấm cổng → data/eval/alert_calibration_result.json

Dữ liệu: ERA5 (Open-Meteo Archive) một chuỗi dài mỗi điểm — dùng cho CẢ khí hậu nền của thang hiệu chuẩn (calibration.py,
10 năm) lẫn số thực đo; dự báo mưa theo độ trễ 0–6 ngày từ Open-Meteo Previous Runs. Ngày thứ k của cửa sổ 7 ngày dùng
dự báo phát hành trước k ngày — đúng tình thế lúc phát cảnh báo.
"""
from __future__ import annotations

import http.client
import json
import math
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
PROTO = ROOT / "backend" / "data" / "eval" / "alert_calibration_protocol.json"
OUT = ROOT / "backend" / "data" / "eval" / "alert_calibration_result.json"
TABLE = ROOT / "backend" / "data" / "alert_calibration.json"
CACHE = Path("D:/tt-scratch/alertcal")
UA = {"User-Agent": "TerraTwin/1.0 (alert calibration study; +https://terratwin-web.vercel.app)"}

# 38 điểm cố định TRƯỚC khi chạy (tỉnh lỵ/đô thị, đủ 7 vùng). Tập kiểm tra = i % 4 == 3.
POINTS = [
    ("ha_giang", 22.82, 104.98), ("lao_cai", 22.48, 103.97), ("dien_bien", 21.39, 103.02), ("son_la", 21.33, 103.91),
    ("lang_son", 21.85, 106.76), ("thai_nguyen", 21.59, 105.85), ("ha_noi", 21.03, 105.85), ("hai_phong", 20.86, 106.68),
    ("nam_dinh", 20.43, 106.17), ("thanh_hoa", 19.81, 105.78), ("vinh", 18.68, 105.68), ("ha_tinh", 18.34, 105.91),
    ("dong_hoi", 17.47, 106.62), ("dong_ha", 16.82, 107.10), ("hue", 16.46, 107.59), ("da_nang", 16.05, 108.20),
    ("tam_ky", 15.57, 108.47), ("quang_ngai", 15.12, 108.80), ("quy_nhon", 13.78, 109.22), ("tuy_hoa", 13.10, 109.30),
    ("nha_trang", 12.24, 109.19), ("phan_rang", 11.56, 108.99), ("phan_thiet", 10.93, 108.10), ("kon_tum", 14.35, 108.00),
    ("pleiku", 13.98, 108.00), ("buon_ma_thuot", 12.67, 108.04), ("da_lat", 11.94, 108.44), ("dong_xoai", 11.54, 106.89),
    ("tay_ninh", 11.31, 106.10), ("tp_hcm", 10.78, 106.70), ("tan_an", 10.54, 106.41), ("my_tho", 10.36, 106.36),
    ("ben_tre", 10.24, 106.38), ("can_tho", 10.03, 105.78), ("long_xuyen", 10.39, 105.44), ("rach_gia", 10.01, 105.08),
    ("soc_trang", 9.60, 105.97), ("ca_mau", 9.18, 105.15),
]
P0, P1 = date(2024, 2, 1), date(2025, 12, 31)       # giai đoạn đánh giá (giao thức)
ERA_START = date(2014, 1, 1)                         # đủ 10 năm khí hậu nền trước mọi cửa sổ
WARMUP, WINDOW, STEP = 30, 7, 3
HIT = 40.0                                           # verify.py: thực đo đỉnh ≥ SAFE (40) là "trúng"
RAW_ALERT = 70.0                                     # hazard.WARNING — quy tắc thô phát cảnh báo
BINS = [0, 20, 40, 55, 70, 101]
ALPHA = 0.1


def _get(url: str, tries: int = 6) -> dict:
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code in (429, 502, 503, 504) and k < tries - 1:
                wait = 65 * (k + 1)
                print(f"  {e.code} — chờ {wait} s", flush=True)
                time.sleep(wait)
                continue
            raise
        except (TimeoutError, urllib.error.URLError, OSError, http.client.HTTPException) as e:   # máy chủ chậm / đứt giữa chừng
            if k < tries - 1:
                print(f"  {type(e).__name__} — thử lại sau 30 s", flush=True)
                time.sleep(30)
                continue
            raise
    raise RuntimeError("hết lượt thử")


def fetch() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    geo()
    era_end = min(date.today() - timedelta(days=7), date(2026, 11, 15))
    for i, (pid, lat, lon) in enumerate(POINTS):
        f = CACHE / f"{pid}.json"
        if f.exists():
            continue
        print(f"[{i + 1}/{len(POINTS)}] {pid}", flush=True)
        era = _get("https://archive-api.open-meteo.com/v1/archive"
                   f"?latitude={lat}&longitude={lon}&start_date={ERA_START}&end_date={era_end}"
                   "&daily=precipitation_sum,et0_fao_evapotranspiration,temperature_2m_max&timezone=auto")
        time.sleep(8)
        hv = ",".join(["precipitation"] + [f"precipitation_previous_day{k}" for k in range(1, WINDOW)])
        prev = _get("https://previous-runs-api.open-meteo.com/v1/forecast"
                    f"?latitude={lat}&longitude={lon}&start_date={P0 - timedelta(days=1)}&end_date={P1 + timedelta(days=WINDOW)}"
                    f"&hourly={hv}&timezone=Asia%2FBangkok")
        f.write_text(json.dumps({"era": era["daily"], "prev": prev["hourly"], "era_end": str(era_end)}), encoding="utf-8")
        time.sleep(8)


def geo() -> None:
    """Độ cao + độ dốc từng điểm, MỘT lần (đúng URL và công thức của realdata.elevation_m / slope_deg — DEM Open-Meteo,
    4 hướng cách 500 m). Bước run dùng lại → không gọi mạng giữa chừng (25/11/2026: API độ cao bị bóp tốc làm treo)."""
    f = CACHE / "geo.json"
    got = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    for pid, lat, lon in POINTS:
        if pid in got:
            continue
        step = 500.0
        dlat = step / 111_320.0
        dlon = step / (111_320.0 * max(0.1, math.cos(math.radians(lat))))
        lats = [lat, lat + dlat, lat - dlat, lat, lat]
        lons = [lon, lon, lon, lon + dlon, lon - dlon]
        d = _get("https://api.open-meteo.com/v1/elevation?latitude=" + ",".join(f"{v:.5f}" for v in lats)
                 + "&longitude=" + ",".join(f"{v:.5f}" for v in lons))
        e = [float(x) for x in d["elevation"]]
        grad = math.hypot((e[1] - e[2]) / (2 * step), (e[3] - e[4]) / (2 * step))
        got[pid] = {"elev": round(e[0], 1), "slope": round(math.degrees(math.atan(grad)), 1)}
        f.write_text(json.dumps(got), encoding="utf-8")
        print(f"  geo {pid}: {got[pid]}", flush=True)
        time.sleep(2)


def _daily_prev(h: dict) -> dict[int, dict[str, float | None]]:
    """Mưa dự báo theo NGÀY cho từng độ trễ: {k: {ngày: mm hoặc None nếu thiếu giờ nào}}."""
    out: dict[int, dict[str, float | None]] = {}
    times = h["time"]
    for k in range(WINDOW):
        key = "precipitation" if k == 0 else f"precipitation_previous_day{k}"
        vals = h.get(key) or []
        day: dict[str, list] = {}
        for t, v in zip(times, vals):
            day.setdefault(t[:10], []).append(v)
        out[k] = {d: (None if len(v) < 24 or any(x is None for x in v) else round(sum(v), 2)) for d, v in day.items()}
    return out


def pairs_for(pid: str, lat: float, lon: float) -> dict[str, list[tuple[float, float]]]:
    from app.services import hazard, realdata

    d = json.loads((CACHE / f"{pid}.json").read_text(encoding="utf-8"))
    era = d["era"]
    rows_all = [{"day": i, "date": t, "precip": p or 0.0, "et0": e or 0.0, "tmax": x if x is not None else 30.0}
                for i, (t, p, e, x) in enumerate(zip(era["time"], era["precipitation_sum"],
                                                     era["et0_fao_evapotranspiration"], era["temperature_2m_max"]))]
    by_date = {r["date"]: r for r in rows_all}

    def hist(la, lo, start, end):              # khí hậu nền của calibration.py lấy từ chuỗi đã tải — không gọi mạng
        return [dict(r) for r in rows_all if start <= r["date"] <= end] or None
    realdata.historical_weather = hist
    g = json.loads((CACHE / "geo.json").read_text(encoding="utf-8"))[pid]
    realdata.elevation_m = lambda la, lo: g["elev"]
    realdata.slope_deg = lambda la, lo, step_m=500.0: g["slope"]
    from app.services import datasources as dsrc
    assert dsrc.elevation_context(lat, lon) == (g["elev"], True) and dsrc.slope_context(lat, lon) == (g["slope"], True)
    prev = _daily_prev(d["prev"])
    out: dict[str, list[tuple[float, float]]] = {"flood": [], "landslide": []}
    day = P0 + timedelta(days=WARMUP)
    while day + timedelta(days=WINDOW - 1) <= P1:
        ds = [(day + timedelta(days=j)).isoformat() for j in range(-WARMUP, WINDOW)]
        if all(x in by_date for x in ds):
            obs = [dict(by_date[x]) for x in ds]
            fc = [dict(r) for r in obs]
            ok = True
            for k in range(WINDOW):
                v = prev[k].get(ds[WARMUP + k])
                if v is None:
                    ok = False
                    break
                fc[WARMUP + k]["precip"] = v
            if ok:
                for m in out:
                    so, sf = hazard.index_series(m, lat, lon, obs), hazard.index_series(m, lat, lon, fc)
                    if len(so) == len(obs) and len(sf) == len(fc):
                        out[m].append((max(float(s[2]) for s in sf[WARMUP:]), max(float(s[2]) for s in so[WARMUP:])))
        day += timedelta(days=STEP)
    return out


def isotonic(x: list[float], y: list[float]) -> list[tuple[float, float]]:
    """Hồi quy đẳng trương tăng (pool-adjacent-violators). → bậc [(x_max của khối, p)]."""
    pts = sorted(zip(x, y))
    blocks: list[list[float]] = []                   # [tổng y, số mẫu, x lớn nhất]
    for xi, yi in pts:
        blocks.append([yi, 1.0, xi])
        while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] > blocks[-1][0] / blocks[-1][1]:
            s, n, xm = blocks.pop()
            blocks[-1][0] += s
            blocks[-1][1] += n
            blocks[-1][2] = xm
    return [(b[2], b[0] / b[1]) for b in blocks]


def prob(steps: list[tuple[float, float]], x: float) -> float:
    for xm, p in steps:
        if x <= xm:
            return p
    return steps[-1][1]


def _bin(x: float) -> int:
    for i in range(len(BINS) - 1):
        if BINS[i] <= x < BINS[i + 1]:
            return i
    return len(BINS) - 2


def run() -> None:
    proto = json.loads(PROTO.read_text(encoding="utf-8"))
    g = proto["gate"]
    calib: dict[str, list] = {"flood": [], "landslide": []}
    test: dict[str, list] = {"flood": [], "landslide": []}
    missing = [pid for pid, _, _ in POINTS if not (CACHE / f"{pid}.json").exists()]
    if missing:
        sys.exit(f"DỪNG — còn thiếu dữ liệu {len(missing)} điểm ({', '.join(missing[:5])}…); chạy fetch trước.")
    for i, (pid, lat, lon) in enumerate(POINTS):
        got = pairs_for(pid, lat, lon)
        for m, ps in got.items():
            (test if i % 4 == 3 else calib)[m] += ps
        print(f"{pid:<14} " + " ".join(f"{m}={len(ps)}" for m, ps in got.items()), flush=True)
    result = {"protocol": PROTO.name, "ran_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(), "modules": {}}
    table = {"source": "ops/alert_calibration.py — " + PROTO.name, "built_at": result["ran_at"], "modules": {}}
    for m in calib:
        cx = [f for f, _ in calib[m]]
        cy = [1.0 if o >= HIT else 0.0 for _, o in calib[m]]
        steps = isotonic(cx, cy)
        # split-conformal theo khoảng dự báo
        res_by: dict[int, list[float]] = {}
        for f, o in calib[m]:
            res_by.setdefault(_bin(f), []).append(abs(o - f))
        qs = {}
        for b, r in res_by.items():
            r.sort()
            k = min(len(r) - 1, math.ceil((1 - ALPHA) * (len(r) + 1)) - 1)
            qs[b] = r[k]
        tx = [f for f, _ in test[m]]
        ty = [1.0 if o >= HIT else 0.0 for _, o in test[m]]
        n = len(ty)
        base = sum(cy) / len(cy) if cy else 0.0
        pc = [prob(steps, f) for f in tx]
        brier = sum((p - y) ** 2 for p, y in zip(pc, ty)) / n if n else None
        brier_clim = sum((base - y) ** 2 for y in ty) / n if n else None
        brier_raw = sum(((1.0 if f >= RAW_ALERT else 0.0) - y) ** 2 for f, y in zip(tx, ty)) / n if n else None
        bss = (1 - brier / brier_clim) if n and brier_clim else None
        # ECE: 10 khoảng xác suất bằng nhau
        ece = 0.0
        for j in range(10):
            idx = [t for t, p in enumerate(pc) if j / 10 <= p < (j + 1) / 10 or (j == 9 and p == 1.0)]
            if idx:
                ece += len(idx) / n * abs(sum(pc[t] for t in idx) / len(idx) - sum(ty[t] for t in idx) / len(idx))
        cover = (sum(1 for f, o in test[m] if abs(o - f) <= qs.get(_bin(f), max(qs.values()))) / n) if n else None
        checks = {
            "min_test_windows": n >= g["min_test_windows"],
            "brier_skill_vs_climatology": bss is not None and bss > g["brier_skill_vs_climatology_min"],
            "brier_vs_raw_rule": brier is not None and brier < brier_raw,
            "reliability_ece": ece <= g["reliability_ece_max"],
            "conformal_coverage": cover is not None and cover >= g["conformal_coverage_min"],
        }
        passed = all(checks.values())
        result["modules"][m] = {
            "n_calib": len(cy), "n_test": n, "base_rate_calib": round(base, 4),
            "brier": None if brier is None else round(brier, 4), "brier_climatology": None if brier_clim is None else round(brier_clim, 4),
            "brier_raw_rule": None if brier_raw is None else round(brier_raw, 4), "brier_skill": None if bss is None else round(bss, 4),
            "ece": round(ece, 4), "conformal_coverage": None if cover is None else round(cover, 4),
            "conformal_halfwidth_by_bin": {f"{BINS[b]}-{BINS[b + 1]}": round(q, 1) for b, q in sorted(qs.items())},
            "raw_rule_alert_rate_test": round(sum(1 for f in tx if f >= RAW_ALERT) / n, 4) if n else None,
            "p_hit_when_raw_alert_test": (round(sum(y for f, y in zip(tx, ty) if f >= RAW_ALERT) /
                                                max(1, sum(1 for f in tx if f >= RAW_ALERT)), 4) if n else None),
            "checks": checks, "passed": passed,
        }
        if passed:
            table["modules"][m] = {"steps": [[round(x, 2), round(p, 4)] for x, p in steps],
                                   "halfwidth_by_bin": {str(b): round(q, 1) for b, q in qs.items()}, "bins": BINS,
                                   "hit_threshold": HIT, "n_calib": len(cy), "n_test": n, "brier_skill": round(bss, 4),
                                   "ece": round(ece, 4), "coverage": round(cover, 4)}
        print(f"\n{m}: test n={n} BSS={bss} ECE={ece:.3f} phủ={cover} Brier {brier} vs thô {brier_raw} → "
              f"{'ĐẠT' if passed else 'TRƯỢT'} {checks}")
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    TABLE.write_text(json.dumps(table, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n→ {OUT}\n→ {TABLE} (chỉ chứa module ĐẠT)")


if __name__ == "__main__":
    {"fetch": fetch, "geo": geo, "run": run}[sys.argv[1] if len(sys.argv) > 1 else "run"]()
