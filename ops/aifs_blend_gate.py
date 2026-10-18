"""CỔNG tổ hợp dự báo mưa best_match + ECMWF AIFS — đúng giao thức backend/data/eval/aifs_blend_protocol.json, MỘT lần.

    cd backend && python ../ops/aifs_blend_gate.py        # ghi data/eval/aifs_blend_result.json

Nguồn: Open-Meteo Previous Runs API (dự báo đã phát hành, theo số ngày trước) + Archive ERA5 (sự thật, ngưỡng P97).
Lỗi MẠNG ở bất kỳ điểm nào → dừng, không ghi kết quả (chạy lại sau); chỉ số null CÓ TRONG dữ liệu mới bị bỏ theo giao thức.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))

from app.db import init_db  # noqa: E402

init_db()
from app.services import flood_season as fs, realdata  # noqa: E402

EVAL = os.path.join(HERE, "..", "backend", "data", "eval")
PROTO = os.path.join(EVAL, "aifs_blend_protocol.json")
OUT = os.path.join(EVAL, "aifs_blend_result.json")
PREV = "https://previous-runs-api.open-meteo.com/v1/forecast"
MODELS = ("best_match", "ecmwf_aifs025_single")
D0, D1 = date(2025, 3, 1), date(2025, 12, 28)


def fetch(url: str, tries: int = 5):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "terratwin-gate/1 (research; github.com/annguyen210/TerraTwin)"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504):
                raise
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(10 * (i + 1))
    raise RuntimeError(f"không tải được sau {tries} lần: {url[:120]}")


def daily_forecast(lat: float, lon: float) -> dict:
    """{model: {ngày: {k: mm}}} — tổng theo giờ của precipitation_previous_dayk; ngày thiếu giờ nào → không có k đó."""
    q = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon, "timezone": "Asia/Bangkok",
        "hourly": "precipitation_previous_day1,precipitation_previous_day2,precipitation_previous_day3",
        "models": ",".join(MODELS),
        "start_date": (D0 + timedelta(days=1)).isoformat(), "end_date": (D1 + timedelta(days=3)).isoformat()})
    j = fetch(f"{PREV}?{q}")
    h = j["hourly"]
    out: dict = {m: {} for m in MODELS}
    for m in MODELS:
        for k in (1, 2, 3):
            vals = h.get(f"precipitation_previous_day{k}_{m}")
            if vals is None:
                raise RuntimeError(f"phản hồi thiếu biến previous_day{k} của {m}")
            acc: dict[str, list] = {}
            for t, v in zip(h["time"], vals):
                acc.setdefault(t[:10], []).append(v)
            for d, vs in acc.items():
                if len(vs) == 24 and all(v is not None for v in vs):
                    out[m].setdefault(d, {})[k] = round(sum(vs), 2)
    return out


def score(rows: list[dict], key: str) -> dict:
    ev = [r for r in rows if r["truth"] >= r["p97"]]
    al = [r for r in rows if r[key] >= r["p97"]]
    hit = sum(1 for r in ev if r[key] >= r["p97"])
    fa = sum(1 for r in al if r["truth"] < r["p97"])
    miss = len(ev) - hit
    return {"events": len(ev), "alarms": len(al), "hits": hit, "misses": miss, "false_alarms": fa,
            "POD": round(hit / len(ev), 3) if ev else None, "FAR": round(fa / len(al), 3) if al else None,
            "CSI": round(hit / (hit + miss + fa), 3) if (hit + miss + fa) else None,
            "MAE_mm": round(sum(abs(r[key] - r["truth"]) for r in rows) / len(rows), 2) if rows else None}


def main() -> int:
    if os.path.exists(OUT):
        print("Đã có", os.path.relpath(OUT), "— cổng chỉ chấm MỘT lần.")
        return 0
    proto = json.load(open(PROTO, encoding="utf-8"))
    rows, per_point = [], []
    for p in proto["points"]:
        la, lo = p["lat"], p["lon"]
        p97 = fs.threshold_p97(la, lo)
        era = realdata.historical_weather(la, lo, *fs.WINDOW)
        if p97 is None or not era:
            raise RuntimeError(f"không tải được ERA5 cho {p['name']} — chạy lại sau (không chấm trên tập thiếu)")
        rain = {r["date"]: float(r.get("precip") or 0.0) for r in era}
        fc = daily_forecast(la, lo)
        n0 = len(rows)
        d = D0
        while d <= D1:
            ds = [(d + timedelta(days=k)).isoformat() for k in (1, 2, 3)]
            f3 = {}
            for m in MODELS:
                parts = [fc[m].get(ds[k - 1], {}).get(k) for k in (1, 2, 3)]
                f3[m] = None if any(x is None for x in parts) else round(sum(parts), 2)
            if all(v is not None for v in f3.values()) and all(x in rain for x in ds):
                truth = round(sum(rain[x] for x in ds), 2)
                rows.append({"point": p["name"], "D": d.isoformat(), "p97": p97, "truth": truth,
                             "best": f3["best_match"], "aifs": f3["ecmwf_aifs025_single"],
                             "blend": round((f3["best_match"] + f3["ecmwf_aifs025_single"]) / 2, 2)})
            d += timedelta(days=1)
        mine = rows[n0:]
        per_point.append({"point": p["name"], "p97_mm": p97, "days": len(mine),
                          "events": sum(1 for r in mine if r["truth"] >= p97)})
        print(f"{p['name']}: P97 {p97} mm · {len(mine)} ngày · {per_point[-1]['events']} ngày-sự kiện", flush=True)
        time.sleep(3)
    res = {k: score(rows, k) for k in ("best", "blend", "aifs")}
    n_ev = res["best"]["events"]
    pts_ev = sum(1 for x in per_point if x["events"] > 0)
    enough = n_ev >= 30 and pts_ev >= 3
    b, c = res["best"], res["blend"]
    far_ok = c["FAR"] is not None and b["FAR"] is not None and c["FAR"] < b["FAR"]
    pod_ok = c["POD"] is not None and b["POD"] is not None and c["POD"] >= b["POD"]
    passed = enough and far_ok and pod_ok
    out = {"run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "protocol": "aifs_blend_protocol.json",
           "n_rows": len(rows), "per_point": per_point, "enough_sample": enough,
           "scores": res,
           "margins": {m: (None if c[m] is None or b[m] is None else round(c[m] - b[m], 3)) for m in ("FAR", "POD", "CSI", "MAE_mm")},
           "far_reduced": far_ok, "pod_kept": pod_ok, "passed": passed,
           "note": "AIFS đứng một mình chỉ để tham khảo (không phải ứng viên).", "rows": rows}
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for k, name in (("best", "best_match"), ("blend", "TỔ HỢP"), ("aifs", "AIFS (tham khảo)")):
        x = res[k]
        print(f"{name:18s} POD {x['POD']} · FAR {x['FAR']} · CSI {x['CSI']} · MAE {x['MAE_mm']} mm "
              f"(sự kiện {x['events']}, báo {x['alarms']}, trúng {x['hits']}, bừa {x['false_alarms']})")
    print("Đủ mẫu:", enough, f"({n_ev} ngày-sự kiện, {pts_ev} điểm)", "· FAR giảm:", far_ok, "· POD giữ:", pod_ok)
    print("CỔNG:", "ĐẠT — bật tổ hợp" if passed else "TRƯỢT — giữ best_match")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
