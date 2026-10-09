"""CỔNG GĐ6 — nhật ký thửa có sinh "sự kiện rác" không? Phát lại 7 ngày vừa qua trên dữ liệu THẬT.

    cd backend && python ../ops/journal_gate.py [số ngày=7]

Với mỗi thửa mẫu: lấy mưa ngày (Open-Meteo) và cảnh radar Sentinel-1 mới (Planetary Computer) đúng như nhật
ký làm khi người dùng mở, rồi in MỌI sự kiện được bật cờ "thay đổi thật" kèm số đo đứng sau nó. Rác = sự
kiện bật cờ mà số đo không vượt ngưỡng đã công bố (mưa ≥ 50 mm/ngày; radar: VV < −18 dB và thấp hơn nền
≥ 3 dB). Ngưỡng cố định trong mã, không chỉnh theo kết quả chạy này.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.services import plot_journal as pj  # noqa: E402

PLOTS = [("Quảng Điền, Huế (lúa)", 16.5751, 107.4952), ("Phong Điền, Cần Thơ", 10.0452, 105.7469),
         ("Đông Anh, Hà Nội", 21.1405, 105.8468), ("Lâm Hà, Lâm Đồng (cà phê)", 11.7536, 108.2190),
         ("Trần Văn Thời, Cà Mau", 9.0820, 104.9690), ("Điện Bàn, Quảng Nam", 15.8890, 108.2500)]

days = int(sys.argv[1]) if len(sys.argv) > 1 else 7
since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
junk = total = 0
for name, lat, lon in PLOTS:
    ext = pj._external(lat, lon, since)
    ev, ctx = pj._ext_events(ext, since)
    sig = [e for e in ev if e["significant"]]
    rain_ok, radar_ok = ext.get("rain") is not None, ext.get("radar") is not None
    print(f"\n{name} ({lat}, {lon}) — mưa: {'có' if rain_ok else 'KHÔNG LẤY ĐƯỢC'}, "
          f"radar: {'có' if radar_ok else 'KHÔNG LẤY ĐƯỢC'}"
          f"{' (có nền)' if (ext.get('radar') or {}).get('has_baseline') else ' (chưa có nền — chỉ báo cảnh mới)'}"
          f" · mưa tổng {ctx.get('rain_total_mm')} mm · {len(sig)} thay đổi thật / {len(ev)} sự kiện")
    for e in ev:
        flag = "THẬT" if e["significant"] else "bối cảnh"
        print(f"   [{flag:8}] {e['at'][:10]} {e['text']}")
        if e["significant"]:
            total += 1
            ok = (e["kind"] == "rain" and e.get("precip_mm", 0) >= pj.RAIN_HEAVY_MM) or e["kind"] == "water"
            junk += not ok
print(f"\nTỔNG: {total} sự kiện bật cờ trên {len(PLOTS)} thửa × {days} ngày; rác (bật cờ mà số đo không vượt ngưỡng): {junk}")
sys.exit(1 if junk else 0)
