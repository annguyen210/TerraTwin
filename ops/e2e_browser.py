"""KIỂM THỬ ĐẦU-CUỐI BẰNG TRÌNH DUYỆT THẬT — bấm như người dùng, không gọi tắt API.

    python ops/e2e_browser.py <web> <api> [--headed]
    vd: python ops/e2e_browser.py http://localhost:1825 http://127.0.0.1:8000

Luồng: trang đầu → /eudr vẽ ranh trên bản đồ → kiểm chuẩn EU + sàng lọc → nhập sổ đỏ →
phát hành hồ sơ → trang hồ sơ (4 phép kiểm) → link đầy đủ (tên chủ hộ đã chứng minh,
đợt giao hàng) → tải JSON → /kiem kiểm offline → hỏi đáp → kiểm tệp cả lô → đăng nhập →
/lo ghép lô, phát hành chứng thư → kiểm vườn thuộc lô → ảnh chụp màn hình điện thoại.
Ghi lỗi console, lỗi trang, phản hồi HTTP ≥ 400; mỗi bước PASS/FAIL. Dùng Chrome có sẵn.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

WEB = sys.argv[1].rstrip("/")
API = sys.argv[2].rstrip("/")
HEADED = "--headed" in sys.argv
# --readonly: KHÔNG ghi gì (dùng cho production — sổ minh bạch chỉ thêm, không xoá được).
READONLY = "--readonly" in sys.argv
OUT = os.path.join(os.environ.get("TEMP", "."), "terratwin-e2e")
os.makedirs(OUT, exist_ok=True)
results: list[tuple[str, bool, str]] = []
console_errors: list[str] = []
bad_responses: list[str] = []


def step(name):
    def deco(fn):
        def run(*a, **k):
            t = time.time()
            try:
                info = fn(*a, **k) or ""
                results.append((name, True, f"{info} ({time.time() - t:.0f}s)"))
                print(f"PASS {name} {info} ({time.time() - t:.0f}s)", flush=True)
                return True
            except Exception as e:                       # noqa: BLE001
                results.append((name, False, repr(e)[:300]))
                print(f"FAIL {name}: {repr(e)[:300]}", flush=True)
                return False
        return run
    return deco


def api(method, path, body=None, tok=None):
    h = {"Content-Type": "application/json"}
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    r = urllib.request.Request(API + path, data=json.dumps(body).encode() if body is not None else None, headers=h, method=method)
    return json.load(urllib.request.urlopen(r, timeout=300))


def shot(page, name, full=True):
    page.screenshot(path=os.path.join(OUT, f"{name}.png"), full_page=full)


state: dict = {}

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=not HEADED)
    ctx = browser.new_context(viewport={"width": 1360, "height": 900}, accept_downloads=True,
                              geolocation={"latitude": 12.7530, "longitude": 108.1120}, permissions=["geolocation"])
    page = ctx.new_page()
    page.set_default_navigation_timeout(180_000)   # server dev biên dịch trang lần đầu có thể >30 giây
    page.on("console", lambda m: m.type == "error" and console_errors.append(f"{page.url} :: {m.text[:200]}"))
    page.on("pageerror", lambda e: console_errors.append(f"{page.url} :: PAGEERROR {str(e)[:200]}"))
    page.on("response", lambda r: r.status >= 400 and bad_responses.append(f"{r.status} {r.request.method} {r.url[:140]}"))

    @step("Trang đầu hiện EUDR")
    def landing():
        page.goto(WEB + "/", wait_until="networkidle", timeout=180_000)
        page.get_by_text("Chứng minh vườn không phá rừng").first.wait_for(timeout=60_000)
        page.get_by_role("link", name="Lấy ranh và kiểm một vườn").first.wait_for()
        assert page.locator(".tt-nav a").count() == 5, "thiếu thanh điều hướng"
        page.wait_for_timeout(4500)                       # để màn quét vệ tinh chạy xong
        shot(page, "01-landing", full=False)
        shot(page, "01b-landing-full")
    landing()

    @step("/eudr vẽ ranh trên bản đồ")
    def draw():
        page.goto(WEB + "/eudr", wait_until="networkidle", timeout=180_000)
        canvas = page.locator(".eu-map canvas").first
        canvas.wait_for(timeout=60_000)
        page.wait_for_timeout(2500)
        b = canvas.bounding_box()
        cx, cy = b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
        for dx, dy in ((-50, -50), (50, -50), (50, 50), (-50, 50)):
            page.mouse.click(cx + dx, cy + dy)
            page.wait_for_timeout(300)
        txt = page.locator(".eu-draw-status").inner_text()
        assert "4" in txt and "ha" in txt, txt
        return txt.strip()[-40:]
    draw()

    @step("Kiểm chuẩn EU + sàng lọc phá rừng")
    def screen():
        page.fill("input[placeholder*='Vườn rẫy']", "Vườn thử E2E")
        page.fill("input[placeholder='Họ tên chủ hộ']", "Nguyễn Văn Kiểm")
        page.get_by_role("button", name=re.compile("Kiểm chuẩn EU \\+ sàng lọc")).click()
        page.locator(".eu-verdict .eu-badge").wait_for(timeout=240_000)      # máy chủ miễn phí lạnh: ~1 phút
        lv = page.locator(".eu-verdict .eu-badge").inner_text()
        imgs = page.locator(".eu-img img").count()
        # Ảnh vệ tinh phải TẢI XONG thật (Planetary Computer dựng theo yêu cầu, mất vài giây).
        # (CSP production chặn eval → không dùng wait_for_function; hỏi lặp bằng evaluate.)
        for _ in range(90):
            if page.evaluate("() => [...document.querySelectorAll('.eu-img img')].every(i => i.complete && i.naturalWidth > 0)"):
                break
            page.wait_for_timeout(1000)
        else:
            raise AssertionError("ảnh vệ tinh không tải xong sau 90 giây")
        shot(page, "02-eudr-screen")
        return f"mức: {lv.strip()} · ảnh vệ tinh: {imgs}"
    screen()

    @step("Nhập sổ đỏ tay + đối chiếu")
    def landdoc():
        page.locator("label:has-text('Diện tích (m²)') input").fill("10.000")
        page.locator("label:has-text('Mục đích sử dụng') select").select_option("CLN")
        page.locator("label:has-text('Thời hạn') input").fill("lâu dài")
        page.locator("label:has-text('Tên người sử dụng đất') input").fill("Nguyễn Văn Kiểm")
        page.get_by_role("button", name="Đối chiếu với ranh đo").click()
        page.locator(".eu-landdoc .eu-badge").wait_for(timeout=30_000)
        return page.locator(".eu-landdoc .eu-badge").inner_text()
    if not READONLY:
        landdoc()

    @step("Phát hành hồ sơ vườn")
    def issue():
        page.get_by_role("button", name="Phát hành Hồ sơ vườn ký số").click()
        page.get_by_text("Đã phát hành hồ sơ số").wait_for(timeout=240_000)
        t = page.locator(".eu-issued b").first.inner_text()
        state["did"] = re.search(r"mã (\w+)", t).group(1)
        codes = page.locator(".eu-issued code").all_inner_texts()
        state["full"] = next(c for c in codes if "?d=" in c)
        shot(page, "03-issued")
        return state["did"]
    if not READONLY:
        issue()

    @step("Trang hồ sơ: 4 phép kiểm đạt, tên chủ hộ ẩn")
    def dossier_page():
        page.goto(f"{WEB}/h/{state['did']}", wait_until="networkidle", timeout=120_000)
        page.get_by_text("Bản gốc — đã kiểm chứng").wait_for(timeout=60_000)
        assert page.get_by_text("ẩn — chủ hồ sơ giữ đường link đầy đủ").count() == 1
        assert page.get_by_text("Giấy chứng nhận quyền sử dụng đất").count() >= 1
        assert page.get_by_text("Sổ minh bạch (RFC 6962)").count() == 1
        shot(page, "04-dossier")
    if not READONLY:
        dossier_page()

    @step("Link đầy đủ: chứng minh tên + mục giao hàng")
    def full_link():
        page.goto(state["full"].replace("http://localhost:3000", WEB), wait_until="networkidle", timeout=120_000)
        page.get_by_text("đã chứng minh").first.wait_for(timeout=60_000)
        page.get_by_text("Đợt giao hàng khai cho vườn của bạn").wait_for(timeout=30_000)
    if not READONLY:
        full_link()

    @step("Tải JSON đã ký → /kiem kiểm offline")
    def offline():
        with page.expect_download() as dl:
            page.get_by_role("button", name=re.compile("Tải (bản )?JSON đã ký")).click()
        path = os.path.join(OUT, "dossier.json")
        dl.value.save_as(path)
        page.goto(WEB + "/kiem", wait_until="networkidle")
        page.wait_for_timeout(1500)
        ctx.set_offline(True)                              # tắt mạng thật
        try:
            page.set_input_files("#verify-file", path)
            page.locator(".eu-checks li").first.wait_for(timeout=20_000)
            lines = page.locator(".eu-checks li").all_inner_texts()
        finally:
            ctx.set_offline(False)                         # luôn bật lại, kể cả khi bước này trượt
        shot(page, "05-kiem")
        assert all(l.startswith("✓") for l in lines), lines
        return f"{len(lines)} phép kiểm ✓ khi TẮT MẠNG"
    if not READONLY:
        offline()

    @step("Hỏi đáp EUDR")
    def ask():
        page.goto(WEB + "/eudr?tab=hoi-dap", wait_until="networkidle")
        page.get_by_role("button", name="Vi phạm EUDR bị phạt bao nhiêu?").click()
        page.locator(".eu-answer").wait_for(timeout=30_000)
        a = page.locator(".eu-answer p").inner_text()
        assert "4%" in a, a
        return a[:60]
    ask()

    @step("Kiểm tệp cả lô (không đăng nhập)")
    def setcheck():
        page.goto(WEB + "/eudr?tab=lo", wait_until="networkidle")
        page.fill("textarea.bat-csv", "ma,vi_do,kinh_do,dien_tich\nA,12.712345,108.061234,1.2\nB,108.061234,12.712345,2\nC,12.71,108.06,6\n")
        page.get_by_role("button", name="Kiểm chuẩn EU").click()
        page.locator(".bat-table").first.wait_for(timeout=30_000)
        head = page.locator(".bat-head").first.inner_text()
        shot(page, "06-set-validate")
        return head
    setcheck()

    @step("Đăng nhập → /lo ghép lô → phát hành chứng thư")
    def lots():
        tok = api("POST", "/api/auth/register", {"email": f"e2e{int(time.time())}@terratwin.vn", "password": "MatKhau123", "name": "E2E"})["access_token"]
        page.goto(WEB + "/")
        page.evaluate(f"localStorage.setItem('terratwin_token', '{tok}')")
        page.goto(WEB + "/lo", wait_until="networkidle")
        page.locator("input[placeholder='EX-2026-001']").fill("EX-E2E-001")
        page.locator("label:has-text('Doanh nghiệp') input").fill("Cty Kiểm thử")
        page.fill("textarea.bat-csv", f"{state['did']}, 3000, 2026-12-10")
        page.get_by_role("button", name="Thêm vào bảng").click()
        page.get_by_role("button", name="Lưu & kiểm cân bằng khối lượng").click()
        page.locator(".bat-head").first.wait_for(timeout=60_000)
        head = page.locator(".bat-head").first.inner_text()
        shot(page, "07-lot")
        if "đủ điều kiện" not in head:
            return f"lô không đủ điều kiện (đúng nếu vườn 'cần xem lại'): {head}"
        page.get_by_role("button", name="Phát hành chứng thư lô hàng").click()
        page.locator(".eu-badge", has_text="Đã có chứng thư").wait_for(timeout=60_000)
        page.get_by_role("link", name="Mở chứng thư").click()
        page.get_by_text("CHỨNG THƯ LÔ HÀNG").first.wait_for(timeout=60_000)
        page.fill("#lot-check-did", state["did"])
        page.get_by_role("button", name="Kiểm", exact=True).click()
        page.locator(".dos-verify-inline").wait_for(timeout=30_000)
        r = page.locator(".dos-verify-inline").inner_text()
        shot(page, "08-lot-cert")
        assert r.startswith("✓"), r
        return r[:80]
    if not READONLY:
        lots()

    @step("Trang Hôm nay")
    def today():
        page.goto(WEB + "/hom-nay", wait_until="networkidle", timeout=120_000)
        page.locator(".hn-ring").first.wait_for(timeout=60_000)
        page.wait_for_timeout(800)
        shot(page, "13-today")
        return f"{page.locator('.hn-item').count()} việc"
    today()

    @step("Khu làm việc thửa đất: bản đồ lớn + chương")
    def workspace():
        page.goto(WEB + "/", wait_until="networkidle", timeout=120_000)
        page.locator(".start-quick button").first.click()
        page.locator(".pw-tabs").wait_for(timeout=60_000)
        skip = page.get_by_role("button", name="Bỏ qua")          # màn hướng dẫn lần đầu
        if skip.count():
            skip.first.click()
        page.locator(".pw-map canvas").first.wait_for(timeout=60_000)
        page.wait_for_timeout(6000)
        shot(page, "14-workspace", full=False)
        page.get_by_role("tab", name=re.compile("Công cụ chuyên sâu")).click()
        page.locator(".pw-mod").first.wait_for(timeout=30_000)
        shot(page, "15-workspace-tools", full=False)
        return f"{page.locator('.pw-mod').count()} công cụ"
    workspace()

    @step("Ảnh điện thoại (390 px) không tràn ngang")
    def phone():
        m = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True)
        pg = m.new_page()
        over = []
        for path, name in (("/", "09-phone-landing"), ("/eudr", "10-phone-eudr"), *( [(f"/h/{state['did']}", "11-phone-dossier")] if state.get("did") else []), ("/kiem", "12-phone-kiem"), ("/hom-nay", "16-phone-today")):
            pg.goto(WEB + path, wait_until="networkidle", timeout=120_000)
            pg.wait_for_timeout(1500)
            w = pg.evaluate("document.documentElement.scrollWidth")
            if w > 392:
                over.append(f"{path}:{w}px")
            pg.screenshot(path=os.path.join(OUT, f"{name}.png"), full_page=False)
        m.close()
        assert not over, over
    phone()

    browser.close()

print("\n==== TÓM TẮT ====")
for n, ok, info in results:
    print(("PASS " if ok else "FAIL ") + n + " — " + info)
print(f"\nLỗi console/trang ({len(console_errors)}):")
for e in dict.fromkeys(console_errors):
    print("  ", e)
print(f"Phản hồi HTTP ≥400 ({len(bad_responses)}):")
for e in dict.fromkeys(bad_responses):
    print("  ", e)
print("Ảnh chụp:", OUT)
