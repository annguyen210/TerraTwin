"""KIỂM ĐỊNH ĐỘC LẬP sàng lọc phá rừng EUDR — ngưỡng ĐẶT TRƯỚC, công bố kể cả khi thấp.

Cùng kỷ luật với U-Net (app/dl): chốt giao thức + mẫu + ngưỡng, COMMIT, rồi mới
chạy TerraTwin trên mẫu — một lần. Không đạt thì ghi "không đạt", không chỉnh quy
tắc rồi chấm lại trên cùng mẫu.

NGUỒN ĐỐI CHIẾU ĐỘC LẬP: Hansen/UMD/Google Global Forest Change v1.12 (2000–2024),
30 m — KHÔNG nằm trong bộ bản đồ TerraTwin dùng để sàng lọc (WorldCover, ALOS,
Impact Observatory, Sentinel-2). Hansen cũng là một mô hình có sai số và tính cả
khai thác rừng trồng là "mất cây" — nên đây là đối chiếu độc lập, không phải sự
thật mặt đất.

    python -m app.eudr_validate sample   # tạo mẫu (đọc Hansen qua HTTP, cần rasterio)
    python -m app.eudr_validate run      # chạy TerraTwin trên mẫu, ghi kết quả
"""
from __future__ import annotations

import argparse
import json
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
PROTOCOL = os.path.join(DATA, "eudr_validation_protocol.json")
SAMPLE = os.path.join(DATA, "eudr_validation_sample.json")
RESULT = os.path.join(DATA, "eudr_validation.json")

HANSEN = ("https://storage.googleapis.com/earthenginepartners-hansen/GFC-2024-v1.12/"
          "Hansen_GFC-2024-v1.12_{layer}_20N_100E.tif")

PROTOCOL_DOC = {
    "title": "Kiểm định độc lập sàng lọc phá rừng EUDR của TerraTwin",
    "registered": "2026-10-03",
    "rule_version": "terratwin.eudr-screen/1",
    "reference": "Hansen/UMD/Google Global Forest Change v1.12 (2000–2024), 30 m — tile 20N_100E",
    "region": {"lat": [11.3, 15.0], "lon": [107.2, 109.0],
               "note": "Tây Nguyên và vùng giáp ranh — vùng cà phê chính của Việt Nam"},
    "plot": "ô vuông 4×4 điểm ảnh Hansen (~111 m × 109 m ≈ 1,2 ha), đúng ranh điểm ảnh",
    "seed": 20261003,
    "windows": 160,
    "window_px": 160,
    "per_set": 40,
    "sets": {
        "lost_after_2020": {
            "criteria": "≥50% điểm ảnh trong ô có lossyear 21–24 (mất cây 2021–2024) VÀ treecover2000 TB ≥30%",
            "expected": "review hoặc high (KHÔNG được 'low')"},
        "stable_forest": {
            "criteria": "không điểm ảnh nào mất cây 2001–2024 VÀ treecover2000 TB ≥70%",
            "expected": "review hoặc high (rừng không được lọt qua sàng lọc)"},
        "never_forest": {
            "criteria": "không điểm ảnh nào mất cây 2001–2024 VÀ treecover2000 TB <10%",
            "expected": "low"},
    },
    "metrics": {
        "M1_detect_lost": "tỉ lệ ô lost_after_2020 được gắn review/high",
        "M2_flag_forest": "tỉ lệ ô stable_forest được gắn review/high",
        "M3_pass_clean": "tỉ lệ ô never_forest được gắn low",
        "info_high_share_lost": "tỉ lệ ô lost_after_2020 được gắn high (chỉ báo cáo)",
    },
    "pass_thresholds": {"M1_detect_lost": 0.80, "M2_flag_forest": 0.80, "M3_pass_clean": 0.70},
    "unknown_policy": "'unknown' (thiếu dữ liệu) tính là SAI cho mọi nhóm",
    "decision": "ĐẠT khi cả ba M1, M2, M3 ≥ ngưỡng. Không đạt → công bố, không chấm lại trên mẫu này.",
}


def write_protocol() -> None:
    with open(PROTOCOL, "w", encoding="utf-8") as f:
        json.dump(PROTOCOL_DOC, f, ensure_ascii=False, indent=1)


# ------------------------------------------------------------------ lấy mẫu

def sample() -> None:
    import numpy as np
    import rasterio
    from rasterio.windows import Window

    P = PROTOCOL_DOC
    rng = random.Random(P["seed"])
    env = dict(GDAL_HTTP_TIMEOUT=60, GDAL_HTTP_MAX_RETRY=4, GDAL_HTTP_RETRY_DELAY=2,
               GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif")
    cands: dict[str, list] = {k: [] for k in P["sets"]}
    t0 = time.time()
    with rasterio.Env(**env):
        loss_ds = rasterio.open("/vsicurl/" + HANSEN.format(layer="lossyear"))
        tc_ds = rasterio.open("/vsicurl/" + HANSEN.format(layer="treecover2000"))
        tf = loss_ds.transform
        r0, c0 = ~tf * (P["region"]["lon"][0], P["region"]["lat"][1])
        r1, c1 = ~tf * (P["region"]["lon"][1], P["region"]["lat"][0])
        col_lo, row_lo, col_hi, row_hi = int(r0), int(c0), int(r1), int(c1)
        W = P["window_px"]
        for k in range(P["windows"]):
            col = rng.randrange(col_lo, col_hi - W)
            row = rng.randrange(row_lo, row_hi - W)
            win = Window(col, row, W, W)
            loss = loss_ds.read(1, window=win)
            tc = tc_ds.read(1, window=win)
            by_set: dict[str, list] = {s: [] for s in cands}
            for i in range(0, W, 4):
                for j in range(0, W, 4):
                    lb, tb = loss[i:i + 4, j:j + 4], tc[i:i + 4, j:j + 4]
                    frac_recent = float(((lb >= 21) & (lb <= 24)).mean())
                    any_loss = bool((lb > 0).any())
                    tcm = float(tb.mean())
                    if frac_recent >= 0.5 and tcm >= 30:
                        by_set["lost_after_2020"].append((i, j, tcm, frac_recent))
                    elif not any_loss and tcm >= 70:
                        by_set["stable_forest"].append((i, j, tcm, 0.0))
                    elif not any_loss and tcm < 10:
                        by_set["never_forest"].append((i, j, tcm, 0.0))
            for s, lst in by_set.items():
                if not lst:
                    continue
                i, j, tcm, fr = rng.choice(lst)     # tối đa 1 ô / cửa sổ / nhóm → trải đều
                x0, y0 = tf * (col + j, row + i)
                x1, y1 = tf * (col + j + 4, row + i + 4)
                cands[s].append({"lon0": round(x0, 6), "lat0": round(y1, 6), "lon1": round(x1, 6),
                                 "lat1": round(y0, 6), "treecover2000_mean": round(tcm, 1),
                                 "recent_loss_frac": round(fr, 2), "window": k})
            if (k + 1) % 20 == 0:
                print(f"  {k + 1}/{P['windows']} cửa sổ · " +
                      " · ".join(f"{s} {len(v)}" for s, v in cands.items()) + f" · {time.time() - t0:.0f}s",
                      flush=True)
    out = {"protocol": P, "created": datetime.now(timezone.utc).isoformat(timespec="seconds"), "sets": {}}
    for s, lst in cands.items():
        rng.shuffle(lst)
        out["sets"][s] = lst[:P["per_set"]]
        print(f"{s}: {len(lst)} ứng viên → lấy {len(out['sets'][s])}")
    with open(SAMPLE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)


# ------------------------------------------------------------------ chạy TerraTwin

def run(workers: int = 3) -> None:
    from app.services import eudr_forest, eudr_geo, reqlang

    reqlang.set_lang("vi")
    smp = json.load(open(SAMPLE, encoding="utf-8"))
    P = smp["protocol"]
    jobs = []
    for s, lst in smp["sets"].items():
        for k, c in enumerate(lst):
            jobs.append((s, k, c))

    def one(job):
        s, k, c = job
        geom = {"type": "Polygon", "coordinates": [[[c["lon0"], c["lat0"]], [c["lon1"], c["lat0"]],
                                                    [c["lon1"], c["lat1"]], [c["lon0"], c["lat1"]],
                                                    [c["lon0"], c["lat0"]]]]}
        plot = eudr_geo.validate_geometry(geom, ref=f"{s}-{k}")
        t = time.time()
        try:
            r = eudr_forest.screen(plot)
            lvl = r["level"]
            maps = {f["id"]: f.get("pct") for f in r["forest_2020"]}
            sig = r.get("signals") or {}
        except Exception as e:      # noqa: BLE001 — ghi lỗi, tính là unknown
            lvl, maps, sig = "unknown", {}, {"error": repr(e)}
        reqlang.set_lang("vi")
        return {"set": s, "k": k, "level": lvl, "maps_2020": maps, "loss_by": sig.get("loss_by"),
                "io_drop_pts": sig.get("io_drop_pts"), "ndvi_drop": sig.get("ndvi_drop"),
                "seconds": round(time.time() - t, 1), **c}

    t0 = time.time()
    rows = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for i, r in enumerate(ex.map(one, jobs), 1):
            rows.append(r)
            if i % 10 == 0:
                print(f"  {i}/{len(jobs)} · {time.time() - t0:.0f}s", flush=True)

    def share(s, ok):
        lst = [r for r in rows if r["set"] == s]
        return round(sum(1 for r in lst if r["level"] in ok) / len(lst), 3) if lst else None
    metrics = {
        "M1_detect_lost": share("lost_after_2020", ("review", "high")),
        "M2_flag_forest": share("stable_forest", ("review", "high")),
        "M3_pass_clean": share("never_forest", ("low",)),
        "info_high_share_lost": share("lost_after_2020", ("high",)),
    }
    th = P["pass_thresholds"]
    passed = all(metrics[k] is not None and metrics[k] >= v for k, v in th.items())
    counts = {s: {lv: sum(1 for r in rows if r["set"] == s and r["level"] == lv)
                  for lv in ("low", "review", "high", "unknown")} for s in smp["sets"]}
    out = {
        "protocol": P, "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule_version": eudr_forest.METHOD_VERSION, "n": len(rows),
        "metrics": metrics, "pass_thresholds": th, "passed": passed, "counts": counts,
        "seconds_total": round(time.time() - t0),
        "rows": sorted(rows, key=lambda r: (r["set"], r["k"])),
    }
    with open(RESULT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(json.dumps({"metrics": metrics, "passed": passed, "counts": counts}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["protocol", "sample", "run"])
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    if a.cmd == "protocol":
        write_protocol()
    elif a.cmd == "sample":
        write_protocol()
        sample()
    else:
        run(a.workers)
