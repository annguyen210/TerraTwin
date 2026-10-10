"""CỔNG GĐ6 — nhật ký thửa có sinh "sự kiện rác" không? Chạy trên dữ liệu THẬT.

    cd backend && python ../ops/journal_gate.py --days 7                 # phát lại 7 ngày vừa qua
    python ../ops/journal_gate.py --days 1 --jsonl ../journal.jsonl      # lượt SỐNG hằng ngày (journal-live.yml)
    python ../ops/journal_gate.py --summary ../journal.jsonl             # tổng kết các lượt sống — cổng 7 ngày

Với mỗi thửa mẫu: lấy mưa ngày (Open-Meteo) và cảnh radar Sentinel-1 mới (Planetary Computer) đúng như nhật
ký làm khi người dùng mở, rồi in MỌI sự kiện được bật cờ "thay đổi thật" kèm số đo đứng sau nó. Rác = sự
kiện bật cờ mà số đo không vượt ngưỡng đã công bố (mưa ≥ 50 mm/ngày; radar: VV < −18 dB và thấp hơn nền
≥ 3 dB). Ngưỡng cố định trong mã, không chỉnh theo kết quả chạy.

Cổng kế hoạch: "nhật ký không sinh sự kiện rác trong 7 ngày chạy thử" → --summary đạt khi có ≥ 7 ngày sống
khác nhau, 0 sự kiện rác, và mỗi ngày đọc được nguồn mưa của ít nhất 5/6 thửa.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

PLOTS = [("Quảng Điền, Huế (lúa)", 16.5751, 107.4952), ("Phong Điền, Cần Thơ", 10.0452, 105.7469),
         ("Đông Anh, Hà Nội", 21.1405, 105.8468), ("Lâm Hà, Lâm Đồng (cà phê)", 11.7536, 108.2190),
         ("Trần Văn Thời, Cà Mau", 9.0820, 104.9690), ("Điện Bàn, Quảng Nam", 15.8890, 108.2500)]
LIVE_DAYS_MIN = 7


def run(days: int) -> dict:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
    from app.services import plot_journal as pj
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    rec = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "days": days, "plots": [], "total": 0, "junk": 0}
    for name, lat, lon in PLOTS:
        ext = pj._external(lat, lon, since)
        ev, ctx = pj._ext_events(ext, since)
        rain_ok, radar_ok = ext.get("rain") is not None, ext.get("radar") is not None
        sig = [e for e in ev if e["significant"]]
        print(f"\n{name} ({lat}, {lon}) — mưa: {'có' if rain_ok else 'KHÔNG LẤY ĐƯỢC'}, "
              f"radar: {'có' if radar_ok else 'KHÔNG LẤY ĐƯỢC'}"
              f"{' (có nền)' if (ext.get('radar') or {}).get('has_baseline') else ' (chưa có nền — chỉ báo cảnh mới)'}"
              f" · mưa tổng {ctx.get('rain_total_mm')} mm · {len(sig)} thay đổi thật / {len(ev)} sự kiện")
        junk = 0
        for e in ev:
            print(f"   [{'THẬT' if e['significant'] else 'bối cảnh':8}] {e['at'][:10]} {e['text']}")
            if e["significant"]:
                ok = (e["kind"] == "rain" and e.get("precip_mm", 0) >= pj.RAIN_HEAVY_MM) or e["kind"] == "water"
                junk += not ok
        rec["plots"].append({"name": name, "rain_ok": rain_ok, "radar_ok": radar_ok, "rain_total_mm": ctx.get("rain_total_mm"),
                             "significant": [{"at": e["at"][:10], "kind": e["kind"], "text": e["text"]} for e in sig],
                             "context": len(ev) - len(sig), "junk": junk})
        rec["total"] += len(sig)
        rec["junk"] += junk
    print(f"\nTỔNG: {rec['total']} sự kiện bật cờ trên {len(PLOTS)} thửa × {days} ngày; rác: {rec['junk']}")
    return rec


def summary(path: str) -> int:
    rows = [json.loads(ln) for ln in open(path, encoding="utf-8") if ln.strip()]
    live = [r for r in rows if r.get("days") == 1]
    dates = sorted({r["at"][:10] for r in live})
    junk = sum(r["junk"] for r in live)
    total = sum(r["total"] for r in live)
    weak = [r["at"][:10] for r in live if sum(p["rain_ok"] for p in r["plots"]) < 5]
    print(f"{len(dates)} ngày sống ({dates[0] if dates else '—'} → {dates[-1] if dates else '—'}): {total} sự kiện bật cờ, "
          f"{junk} rác; ngày thiếu nguồn mưa (<5/6 thửa): {weak or 'không'}")
    for r in live:
        for p in r["plots"]:
            for s in p["significant"]:
                print(f"   {r['at'][:10]} · {p['name']}: {s['text']}")
    passed = len(dates) >= LIVE_DAYS_MIN and junk == 0 and not weak
    print("CỔNG GĐ6 (7 ngày sống, 0 rác):", "ĐẠT" if passed else ("CHƯA ĐỦ NGÀY" if len(dates) < LIVE_DAYS_MIN else "TRƯỢT"))
    return 0 if passed else 2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--jsonl", help="ghi thêm một dòng kết quả vào tệp này")
    ap.add_argument("--summary", help="tổng kết các lượt sống trong tệp này")
    a = ap.parse_args()
    if a.summary:
        return summary(a.summary)
    rec = run(a.days)
    if a.jsonl:
        with open(a.jsonl, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return 1 if rec["junk"] else 0


if __name__ == "__main__":
    sys.exit(main())
