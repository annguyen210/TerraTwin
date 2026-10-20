"""Phép kiểm đăng ký trước: U-Net radar làm ý kiến thứ hai cho đợt nước — backend/data/ml/s1_unet_confirm_protocol.json.

    python ops/s1_unet_gate.py        # cần backend/data/ml/s1_water_unet.onnx + onnxruntime; chạy thật trên Planetary Computer

Dương tính: đợt (phương pháp ngưỡng) của Quảng Điền chồng lên 06–20/10/2020 và 25/10–10/11/2025 → U-Net ≥ 10% khung thửa.
Âm tính: 24 ngày cảnh (hạt giống 20261020) ở Đà Lạt và đồi thông Thiên An → U-Net < 10% trên CẢ 48 cảnh.
Ghi backend/data/ml/s1_unet_confirm_result.json.
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
from datetime import date

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "backend"))
from app.services import s1_unet, water_history as wh  # noqa: E402

POS = ("Đồng lúa Quảng Điền, Huế", 16.575, 107.495,
       [("lũ Huế 10/2020", date(2020, 10, 6), date(2020, 10, 20)), ("lũ miền Trung 10/2025", date(2025, 10, 25), date(2025, 11, 10))])
NEG = [("Đất cao Đà Lạt", 11.9404, 108.4583), ("Đồi thông Thiên An, Huế", 16.4283, 107.5628)]
SEED, N_NEG = 20261020, 24


def overlaps(ev: dict, a: date, b: date) -> bool:
    return date.fromisoformat(ev["start"]) <= b and date.fromisoformat(ev["end"]) >= a


def share(lat, lon, day):
    for k in range(3):                                   # lỗi mạng: thử lại, không đổi phép chấm
        r = s1_unet.water_share(lat, lon, day, force=True)
        if r is not None:
            return r
        time.sleep(3 * (k + 1))
    return None


def main() -> None:
    t0 = time.time()
    name, lat, lon, floods = POS
    h = wh.history(lat, lon)
    assert h.get("available"), h
    pos_checks, all_events = [], []
    for e in h["events"]:
        r = share(lat, lon, e["flag_date"])
        all_events.append({"start": e["start"], "end": e["end"], "flag_date": e["flag_date"], "threshold_cover": e["peak_cover"],
                           "unet_share": None if r is None else r["share"], "unet_item": None if r is None else r["item"]})
        print("  đợt", all_events[-1], flush=True)
    for label, a, b in floods:
        hit = [x for x in all_events if overlaps(x, a, b)]
        ok = bool(hit) and all(x["unet_share"] is not None and x["unet_share"] >= s1_unet.CONFIRM_SHARE for x in hit)
        pos_checks.append({"label": label, "events": hit, "pass": ok})
        print(("ĐẠT " if ok else "TRƯỢT ") + label, flush=True)
    neg = []
    for nm, la, lo in NEG:
        hh = wh.history(la, lo)
        assert hh.get("available"), hh
        days = sorted(d for d, *_ in hh["series"])
        pick = sorted(random.Random(SEED).sample(days, N_NEG))
        rows = []
        for d in pick:
            r = share(la, lo, d)
            rows.append({"date": d, "unet_share": None if r is None else r["share"]})
        bad = [x for x in rows if x["unet_share"] is None or x["unet_share"] >= s1_unet.CONFIRM_SHARE]
        neg.append({"case": nm, "n": len(rows), "n_confirmed_wrongly_or_unread": len(bad), "scenes": rows, "pass": not bad})
        print(("ĐẠT " if not bad else "TRƯỢT ") + f"{nm}: {len(bad)}/{len(rows)} cảnh bị xác nhận nhầm hoặc không đọc được", flush=True)
    res = {"protocol": "terratwin.s1_unet_confirm/1", "confirm_share": s1_unet.CONFIRM_SHARE,
           "context_m": 2 * s1_unet.CONTEXT_M, "px": s1_unet.PX, "center_px": 2 * s1_unet.center_px(),
           "positive": pos_checks, "negative": neg, "all_events_quang_dien": all_events,
           "passed": all(c["pass"] for c in pos_checks) and all(c["pass"] for c in neg),
           "seconds": round(time.time() - t0, 1)}
    json.dump(res, open(s1_unet.RESULT_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: res[k] for k in ("passed", "seconds")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
