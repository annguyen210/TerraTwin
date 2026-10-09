"""Kiểm song ngữ VI/EN trên các màn chính (GĐ1 kế hoạch tổng) — chỉ đọc, không ghi gì.

    python ops/e2e_lang.py <web>

Mỗi trang mở hai lần (terratwin_lang=vi rồi =en), đợi tiêu đề đúng ngôn ngữ, ghi lỗi console/trang.
"""
from __future__ import annotations

import sys

from playwright.sync_api import sync_playwright

WEB = sys.argv[1].rstrip("/")
CHECKS = [
    ("/eudr", "h1", "Hồ sơ vườn chuẩn EUDR", "EUDR-ready plot dossier"),
    ("/thi-diem", "h1", "Bộ thí điểm cho hợp tác xã", "Pilot kit for co-operatives"),
    ("/pricing", "h1", "Bảng giá", "Pricing"),
    ("/help", "h1", "Trợ giúp", "Help"),
]

fails = 0
with sync_playwright() as p:
    br = p.chromium.launch(channel="chrome", headless=True)
    for lang in ("vi", "en"):
        ctx = br.new_context(viewport={"width": 390, "height": 844}, is_mobile=True)
        ctx.add_init_script(f"try{{localStorage.setItem('terratwin_lang','{lang}');"
                            "localStorage.setItem('terratwin_onboarded','1')}catch(e){}")
        for path, sel, vi, en in CHECKS:
            pg = ctx.new_page()
            errs = []
            pg.on("pageerror", lambda x, e=errs: e.append(str(x)[:140]))
            pg.on("console", lambda m, e=errs: m.type == "error" and e.append(m.text[:140]))
            want = vi if lang == "vi" else en
            try:
                pg.goto(WEB + path, wait_until="domcontentloaded", timeout=120_000)
                pg.wait_for_function("([s, w]) => (document.querySelector(s)?.innerText || '').includes(w)",
                                     arg=[sel, want], timeout=60_000)
                w = pg.evaluate("() => document.documentElement.scrollWidth")
                ok = not errs and w <= 392
                print(f"{'PASS' if ok else 'FAIL'} {lang} {path}: '{want}' · rộng {w}px" + (f" · lỗi {errs[:2]}" if errs else ""))
                fails += 0 if ok else 1
            except Exception as e:      # noqa: BLE001
                print(f"FAIL {lang} {path}: không thấy '{want}' ({type(e).__name__})")
                fails += 1
            pg.close()
        ctx.close()
    br.close()
print("KẾT QUẢ:", "ĐẠT" if fails == 0 else f"{fails} lỗi")
sys.exit(1 if fails else 0)
