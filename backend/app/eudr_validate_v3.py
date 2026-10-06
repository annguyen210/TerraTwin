"""Kiểm định EUDR v3 — LẤY MẪU (trước khi gán nhãn) và CHẤM (một lần, sau khi khoá nhãn).

Giao thức: app/services/label_v3.py (PROTOCOL_DOC_V3), ghi ra data/eudr_validation_protocol_v3.json.

    python -m app.eudr_validate_v3 sample     # Hansen theo tầng, loại ô gần mẫu v1/v2 (cần rasterio)
    python -m app.eudr_validate_v3 imagery    # ngày chụp ảnh Wayback + cảnh Sentinel-2 2020/2026 cho từng ô
    python -m app.eudr_validate_v3 run labels.json   # SAU KHI KHOÁ NHÃN: chấm v1, v2, v3 trên nhóm sự thật
"""
from __future__ import annotations

import argparse
import json
import random
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone

from app.eudr_validate import HANSEN, SAMPLE, SAMPLE_V2, _km
from app.services import label_v3
from app.services.label_v3 import PROTOCOL_DOC_V3 as P


def write_protocol() -> None:
    with open(label_v3.PROTOCOL_V3, "w", encoding="utf-8") as f:
        json.dump(P, f, ensure_ascii=False, indent=1)


def _previous_points() -> list[tuple[float, float]]:
    pts = []
    for path in (SAMPLE, SAMPLE_V2):
        s = json.load(open(path, encoding="utf-8"))
        pts += [((c["lat0"] + c["lat1"]) / 2, (c["lon0"] + c["lon1"]) / 2) for lst in s["sets"].values() for c in lst]
    return pts


def sample() -> None:
    import rasterio
    from rasterio.windows import Window

    write_protocol()
    rng = random.Random(P["seed"])
    prev = _previous_points()
    env = dict(GDAL_HTTP_TIMEOUT=60, GDAL_HTTP_MAX_RETRY=4, GDAL_HTTP_RETRY_DELAY=2,
               GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif")
    strata = [k for k in P["strata"] if not k.startswith("_")]
    cands = {k: [] for k in strata}
    boxes = P["region"]["boxes"]
    per_box = P["windows"] // len(boxes)
    W = P["window_px"]
    skipped, k, t0 = 0, 0, time.time()
    with rasterio.Env(**env):
        loss_ds = rasterio.open("/vsicurl/" + HANSEN.format(layer="lossyear"))
        tc_ds = rasterio.open("/vsicurl/" + HANSEN.format(layer="treecover2000"))
        gain_ds = rasterio.open("/vsicurl/" + HANSEN.format(layer="gain"))
        tf = loss_ds.transform
        for box in boxes:
            c0, r0 = ~tf * (box["lon"][0], box["lat"][1])
            c1, r1 = ~tf * (box["lon"][1], box["lat"][0])
            for _ in range(per_box):
                col = rng.randrange(int(c0), int(c1) - W)
                row = rng.randrange(int(r0), int(r1) - W)
                win = Window(col, row, W, W)
                loss, tc, gain = (ds.read(1, window=win) for ds in (loss_ds, tc_ds, gain_ds))
                by = {x: [] for x in strata}
                for i in range(0, W, 4):
                    for j in range(0, W, 4):
                        lb, tb, gb = loss[i:i + 4, j:j + 4], tc[i:i + 4, j:j + 4], gain[i:i + 4, j:j + 4]
                        recent = float(((lb >= 21) & (lb <= 24)).mean())
                        any_loss = bool((lb > 0).any())
                        tcm, gfrac = float(tb.mean()), float((gb > 0).mean())
                        if recent >= 0.5 and tcm >= 30:
                            by["S_loss"].append((i, j))
                        elif not any_loss and tcm >= 70:
                            by["S_old_trees"].append((i, j))
                        elif not any_loss and tcm < 10 and gfrac >= 0.25:
                            by["S_new_trees"].append((i, j))
                        elif not any_loss and tcm < 10 and gfrac == 0:
                            by["S_open"].append((i, j))
                for x, lst in by.items():
                    rng.shuffle(lst)
                    for i, j in lst:            # ô đầu tiên không gần mẫu cũ, mỗi cửa sổ tối đa 1 ô/tầng
                        x0, y0 = tf * (col + j, row + i)
                        x1, y1 = tf * (col + j + 4, row + i + 4)
                        ctr = ((y0 + y1) / 2, (x0 + x1) / 2)
                        if any(_km(ctr, q) < P["exclude_km_from_previous"] for q in prev):
                            skipped += 1
                            continue
                        cands[x].append({"lon0": round(x0, 6), "lat0": round(y1, 6), "lon1": round(x1, 6),
                                         "lat1": round(y0, 6), "stratum": x, "region": box["name"], "window": k})
                        break
                k += 1
                if k % 20 == 0:
                    print(f"  {k}/{P['windows']} cửa sổ · " + " · ".join(f"{x} {len(v)}" for x, v in cands.items())
                          + f" · {time.time() - t0:.0f}s", flush=True)
    chosen = []
    for x, lst in cands.items():
        rng.shuffle(lst)
        chosen += lst[:P["per_stratum"]]
        print(f"{x}: {len(lst)} ứng viên → lấy {min(len(lst), P['per_stratum'])}")
    rng.shuffle(chosen)                 # trộn tầng: thứ tự ô không lộ tầng
    out = {"protocol": "eudr_validation_protocol_v3.json", "seed": P["seed"],
           "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "skipped_near_previous": skipped, "cells": chosen}
    with open(label_v3.SAMPLE_V3, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)


def _get_json(url: str, timeout: float = 40.0) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "TerraTwin-validation/3"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def wayback_date(meta_url: str, lat: float, lon: float) -> dict | None:
    """Ngày chụp THẬT của ảnh Wayback tại điểm (ảnh bản 2020 có thể chụp từ năm 2017)."""
    for layer in (5, 6, 7, 8, 4, 9):
        q = (f"{meta_url}/{layer}/query?geometry={lon},{lat}&geometryType=esriGeometryPoint&inSR=4326"
             "&spatialRel=esriSpatialRelIntersects&outFields=SRC_DATE,SRC_RES,NICE_DESC,MaxMapLevel"
             "&returnGeometry=false&f=json")
        for attempt in range(2):
            try:
                feats = _get_json(q).get("features") or []
                break
            except Exception:           # noqa: BLE001 — nguồn chậm: thử lại một lần rồi bỏ lớp này
                feats = []
                time.sleep(2)
        for f in feats:
            a = f.get("attributes") or {}
            d = a.get("SRC_DATE")
            if d and (a.get("MaxMapLevel") or 0) >= label_v3.ZOOM:
                d = str(d)
                return {"date": f"{d[:4]}-{d[4:6]}-{d[6:8]}", "res_m": a.get("SRC_RES"), "source": a.get("NICE_DESC")}
    return None


def _s2(lat: float, lon: float, year: int) -> dict | None:
    from app.services import imagery, mpc
    bbox = mpc.bbox_around(lat, lon, 600.0)
    try:
        it = imagery._pick(bbox, date(year, 1, 1), date(year, 4, 30))
    except Exception:                   # noqa: BLE001
        it = None
    return None if not it else {"item": it["item"], "date": it["date"], "cloud_pct": it["cloud_scene_pct"],
                                "bbox": [round(v, 6) for v in bbox]}


def imagery(workers: int = 4) -> None:
    s = json.load(open(label_v3.SAMPLE_V3, encoding="utf-8"))
    cs = s["cells"]

    def one(i):
        c = cs[i]
        if c.get("imagery", {}).get("complete"):
            return i, c["imagery"]
        lat, lon = (c["lat0"] + c["lat1"]) / 2, (c["lon0"] + c["lon1"]) / 2
        wb = {w: wayback_date(m["metadata"], lat, lon) for w, m in label_v3.WAYBACK.items()}
        s2 = {"2020": _s2(lat, lon, 2020), "2026": _s2(lat, lon, 2026)}
        return i, {"wayback": wb, "s2": s2, "complete": all(wb.values()) and all(s2.values())}

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for n, (i, img) in enumerate(ex.map(one, range(len(cs))), 1):
            cs[i]["imagery"] = img
            if n % 20 == 0:
                print(f"  {n}/{len(cs)} · {time.time() - t0:.0f}s", flush=True)
                with open(label_v3.SAMPLE_V3, "w", encoding="utf-8") as f:     # lưu dần, chạy lại được
                    json.dump(s, f, ensure_ascii=False, indent=1)
    s["imagery_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with open(label_v3.SAMPLE_V3, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=1)
    ok = sum(1 for c in cs if c["imagery"].get("complete"))
    print(f"ảnh đủ cho {ok}/{len(cs)} ô")


def run(labels_path: str, workers: int = 3) -> None:
    """CHẤM MỘT LẦN trên nhãn đã khoá. Quyết định theo đúng PROTOCOL_DOC_V3['decision']."""
    from app.services import eudr_forest, eudr_geo, forest_or_crop, reqlang

    reqlang.set_lang("vi")
    labels = json.load(open(labels_path, encoding="utf-8"))["labels"]
    for r in labels:
        r["user_id"] = r.get("user_id", r.get("labeler"))
    t = label_v3.truth(labels)
    cs = label_v3.cells()

    def one(cell):
        c = cs[cell]
        geom = {"type": "Polygon", "coordinates": [[[c["lon0"], c["lat0"]], [c["lon1"], c["lat0"]],
                                                    [c["lon1"], c["lat1"]], [c["lon0"], c["lat1"]],
                                                    [c["lon0"], c["lat0"]]]]}
        plot = eudr_geo.validate_geometry(geom, ref=f"v3-{cell}")
        try:
            raw = eudr_forest.screen(plot)
            lv = {r: eudr_forest._localize(raw, rule=r)["level"] for r in (1, 2)}
            sig = eudr_forest._localize(raw, rule=2)["signals"]
            p = None
            if len(sig.get("majority") or []) >= 2 and not sig.get("loss"):
                p = forest_or_crop.predict(plot).get("probability_forest")
            lv[3] = eudr_forest._localize(raw, rule=3, p_forest=p)["level"]
        except Exception as e:          # noqa: BLE001
            lv, sig, p = {1: "unknown", 2: "unknown", 3: "unknown"}, {"error": repr(e)}, None
        reqlang.set_lang("vi")
        return cell, lv, p, sig

    rows = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for cell, lv, p, sig in ex.map(one, sorted(t["sets"])):
            rows[cell] = {"truth": t["sets"][cell], "levels": lv, "p_forest": p, "stratum": cs[cell].get("stratum"),
                          "region": cs[cell].get("region"), "maps_2020": sig.get("votes"), "loss_by": sig.get("loss_by")}
    res = {}
    for r in (1, 2, 3):
        m = label_v3.metrics({c: v["levels"][r] for c, v in rows.items()}, t["sets"])
        res[eudr_forest.RULES[r]] = {"metrics": m, "decision": label_v3.decide(m, t["counts"])}
    v3, v2 = res[eudr_forest.RULES[3]]["decision"], res[eudr_forest.RULES[2]]["decision"]
    enable = (3 if v3 == "pass" else 2 if v3 == "fail" and v2 == "pass" else None)
    out = {"protocol": "eudr_validation_protocol_v3.json", "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "agreement": {k: t[k] for k in ("cells_labeled", "cells_2plus", "excluded", "kappa_forest", "agree_forest")},
           "truth_counts": t["counts"], "results": res,
           "enable_rule": None if enable is None else eudr_forest.RULES[enable],
           "decision": ("CHƯA KẾT LUẬN — có nhóm dưới 25 ô" if v3 == "insufficient" else
                        f"bật {eudr_forest.RULES[enable]}" if enable else "cả v3 lẫn v2 trượt — giữ v1, công bố"),
           "rows": {str(k): v for k, v in sorted(rows.items())}}
    with open(label_v3.SAMPLE_V3.replace("sample_v3", "v3"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: out[k] for k in ("agreement", "truth_counts", "results", "decision")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["protocol", "sample", "imagery", "run"])
    ap.add_argument("labels", nargs="?")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    if a.cmd == "protocol":
        write_protocol()
    elif a.cmd == "sample":
        sample()
    elif a.cmd == "imagery":
        imagery(a.workers)
    else:
        if not a.labels:
            ap.error("cần đường dẫn tệp nhãn đã xuất (GET /api/admin/label/v3/export)")
        run(a.labels, a.workers)
