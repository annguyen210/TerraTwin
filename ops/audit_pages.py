"""RÀ SOÁT MỌI TRANG — chạy trước mỗi lần ra mắt, thay cho việc người đi bấm từng trang.

    python ops/audit_pages.py <web> [dossier_id]

Với MỖI trang, ở máy tính (1360 px) và điện thoại (390 px): lỗi console / lỗi trang,
phản hồi HTTP ≥ 400, tràn ngang, có khung điều hướng chung không, tiêu đề trang; gom
mọi đường link nội bộ rồi kiểm từng link trả 200. Chụp ảnh từng trang để soi bằng mắt.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from urllib.parse import urljoin, urlparse

from playwright.sync_api import sync_playwright

WEB = sys.argv[1].rstrip("/")
DID = sys.argv[2] if len(sys.argv) > 2 else ""
OUT = os.path.join(os.environ.get("TEMP", "."), "terratwin-audit")
os.makedirs(OUT, exist_ok=True)
ROUTES = ["/", "/hom-nay", "/eudr", "/eudr?tab=lo", "/eudr?tab=tong-quan", "/eudr?tab=hoi-dap", "/eudr?tab=phuong-phap",
          "/lo", "/kiem", "/about", "/pricing", "/help", "/thi-diem", "/privacy", "/terms", "/status", "/buyer", "/batch",
          "/forgot", "/thiet-bi", "/plot/12.7530,108.1120", "/embed/12.7530,108.1120", "/admin"]
if DID:
    ROUTES.append(f"/h/{DID}")

report = []
links: set[str] = set()
with sync_playwright() as p:
    br = p.chromium.launch(channel="chrome", headless=True)
    for vw, tag in (({"width": 1360, "height": 900}, "pc"), ({"width": 390, "height": 844}, "dt")):
        ctx = br.new_context(viewport=vw, is_mobile=(tag == "dt"), device_scale_factor=1)
        ctx.add_init_script("try{localStorage.setItem('terratwin_onboarded','1')}catch(e){}")
        for r in ROUTES:
            page = ctx.new_page()
            errs, bad = [], []
            page.on("console", lambda m, e=errs: m.type == "error" and e.append(m.text[:160]))
            page.on("pageerror", lambda x, e=errs: e.append("PAGEERROR " + str(x)[:160]))
            page.on("response", lambda resp, b=bad: resp.status >= 400 and b.append(f"{resp.status} {resp.url[:110]}"))
            try:
                if r.startswith("/embed/"):
                    # Widget gọi lượt quét (có thể kèm lượt sâu) — đo thời gian tới khi có thẻ
                    # thay vì chờ mạng im hẳn.
                    t0 = time.time()
                    page.goto(WEB + r, wait_until="domcontentloaded", timeout=120_000)
                    page.wait_for_function("() => !document.body.innerText.includes('Đang kiểm rủi ro')",
                                           timeout=180_000)
                    print(f"     embed có thẻ sau {time.time() - t0:.0f}s")
                else:
                    page.goto(WEB + r, wait_until="networkidle", timeout=120_000)
                page.wait_for_timeout(1500)
                w = page.evaluate("() => document.documentElement.scrollWidth")
                shell = page.locator(".tt-top").count() > 0
                title = page.title()
                if tag == "pc":
                    for h in page.evaluate("() => [...document.querySelectorAll('a[href]')].map(a => a.getAttribute('href'))"):
                        if h and (h.startswith("/") and not h.startswith("//")):
                            links.add(urlparse(h).path or "/")
                name = (r.strip("/").replace("/", "_").replace("?", "_").replace("=", "-").replace(",", "_") or "home")
                page.screenshot(path=os.path.join(OUT, f"{tag}-{name}.png"), full_page=False)
                report.append({"route": r, "view": tag, "overflow": w > vw["width"] + 2, "width": w, "shell": shell,
                               "title": title, "errors": errs, "bad": bad})
            except Exception as e:                   # noqa: BLE001
                report.append({"route": r, "view": tag, "fatal": repr(e)[:200]})
            page.close()
        ctx.close()
    br.close()

broken = []
for l in sorted(links):
    try:
        req = urllib.request.Request(urljoin(WEB, l), headers={"User-Agent": "terratwin-audit"})
        code = urllib.request.urlopen(req, timeout=120).status
    except urllib.error.HTTPError as e:
        code = e.code
    except Exception as e:                           # noqa: BLE001
        code = repr(e)[:60]
    if code != 200:
        broken.append((l, code))

print("==== RÀ SOÁT ====")
for x in report:
    if "fatal" in x:
        print(f"FATAL {x['view']} {x['route']}: {x['fatal']}")
        continue
    flags = []
    # Có chủ đích: widget nhúng (iframe trên trang khác) không có khung điều hướng; trang
    # quản trị khi chưa đăng nhập không có khung và /api/auth/me trả 401.
    no_shell_ok = x["route"].startswith(("/embed/", "/admin"))
    bad = [b for b in x["bad"] if not (x["route"] == "/admin" and b.startswith("401 ") and "/api/auth/me" in b)]
    errs = [e for e in x["errors"] if not (x["route"] == "/admin" and "401" in e)]
    if x["overflow"]:
        flags.append(f"TRÀN {x['width']}px")
    if not x["shell"] and not no_shell_ok:
        flags.append("KHÔNG CÓ KHUNG ĐIỀU HƯỚNG")
    if errs:
        flags.append(f"{len(errs)} lỗi console")
    if bad:
        flags.append(f"{len(bad)} HTTP≥400")
    print(f"{'OK  ' if not flags else 'LỖI '} {x['view']} {x['route']:28} [{x['title'][:40]}] {' · '.join(flags)}")
    for e in errs[:3]:
        print("        console:", e)
    for b in bad[:3]:
        print("        http:", b)
print(f"\nLink nội bộ: {len(links)} · hỏng: {len(broken)}")
for l, c in broken:
    print("   ", c, l)
json.dump({"report": report, "broken": broken}, open(os.path.join(OUT, "audit.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("Ảnh:", OUT)
