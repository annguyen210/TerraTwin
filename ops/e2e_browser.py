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
    def watch(pg):
        """Ghi lỗi console, lỗi trang, phản hồi ≥ 400 và yêu cầu HỎNG MẠNG — cả với trang của ngữ cảnh riêng (23/10/2026:
        hai bước ở ngữ cảnh riêng trượt vì API không trả lời mà báo cáo ghi '0 lỗi')."""
        pg.on("console", lambda m: m.type == "error" and console_errors.append(f"{pg.url} :: {m.text[:200]}"))
        pg.on("pageerror", lambda e: console_errors.append(f"{pg.url} :: PAGEERROR {str(e)[:200]}"))
        pg.on("response", lambda r: r.status >= 400 and bad_responses.append(f"{r.status} {r.request.method} {r.url[:140]}"))
        # ERR_ABORTED = yêu cầu bị HUỶ khi chuyển trang / đóng ngữ cảnh (ô bản đồ đang tải dở) — không phải lỗi; lượt
        # 25/10/2026 ghi 385 dòng loại này làm chìm 18 dòng API hỏng thật.
        pg.on("requestfailed", lambda r: "ERR_ABORTED" not in (r.failure or "")
              and bad_responses.append(f"FAILED {r.failure} {r.method} {r.url[:140]}"))
        return pg

    watch(page)

    @step("Trang đầu: sự thật về một mảnh đất + chương EUDR")
    def landing():
        page.goto(WEB + "/", wait_until="networkidle", timeout=180_000)
        page.get_by_text("Sự thật về một mảnh đất").first.wait_for(timeout=60_000)
        assert page.locator(".lp4-cap").count() == 8, "thiếu 8 năng lực"
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
        ph = page.locator(".wv-ph button")          # bản đồ hoãn nạp tới thao tác đầu tiên
        if ph.count():
            ph.first.click()
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

    @step("Trang Hôm nay: đất trước — nhật ký sống các thửa mẫu (khách), EUDR chỉ là lối tắt Doanh nghiệp")
    def today():
        # Báo cáo 12/10/2026, mục 9: vòng đếm ngược EUDR (.hn-ring) chỉ hiện cho doanh nghiệp đã có bộ vườn / lô hàng.
        # Chế độ GHI (19/10/2026): bước lô hàng đã đăng nhập một doanh nghiệp CÓ lô → token còn trong trình duyệt. Kiểm
        # cả hai phía: doanh nghiệp có lô THẤY vòng đếm ngược; xoá token rồi kiểm phía khách như cũ.
        page.goto(WEB + "/")
        biz_tok = page.evaluate("localStorage.getItem('terratwin_token')")
        biz = ""
        if biz_tok:
            page.goto(WEB + "/hom-nay", wait_until="networkidle", timeout=120_000)
            page.locator(".hn-ring").first.wait_for(timeout=60_000)
            biz = " · doanh nghiệp có lô thấy vòng đếm ngược"
            page.evaluate("localStorage.removeItem('terratwin_token')")
        page.goto(WEB + "/hom-nay", wait_until="networkidle", timeout=120_000)
        page.locator(".hn-quick").first.wait_for(timeout=60_000)
        page.locator(".wh-samples li").first.wait_for(timeout=60_000)
        n = page.locator(".wh-samples li").count()
        rings = page.locator(".hn-ring").count()
        page.wait_for_timeout(800)
        shot(page, "13-today")
        assert n >= 6, f"{n} thửa mẫu"
        assert rings == 0, "khách thấy vòng đếm ngược EUDR"
        # Kiểm 24/10/2026 việc 3: câu mở đầu ghi "6 thửa mẫu" trong khi tiêu đề ghi 8 — một nguồn số cho cả ba chỗ.
        lede, h2 = page.locator(".hn-hero .doc-lede").first.inner_text(), page.locator(".hn-plots h2").first.inner_text()
        assert f"{n} thửa mẫu" in lede and h2.startswith(f"{n} thửa mẫu"), f"lệch số thửa mẫu: {n} dòng · '{lede[-40:]}' · '{h2[:40]}'"
        return f"{n} thửa mẫu sống · {page.locator('.hn-biz .hn-tile').count()} lối tắt Doanh nghiệp{biz}"
    today()

    @step("Trang đầu → 'Kiểm một tin đăng' mở thửa mẫu đúng tab Kiểm chứng, tab không bị ép")
    def try_now():
        page.goto(WEB + "/", wait_until="networkidle", timeout=120_000)
        page.get_by_role("button", name=re.compile("Kiểm một tin đăng")).first.click()
        page.locator(".pw-tabs").wait_for(timeout=60_000)
        skip = page.get_by_role("button", name="Bỏ qua")
        if skip.count():
            skip.first.click()
        page.wait_for_timeout(1500)
        sel = page.get_by_role("tab", selected=True).inner_text()
        hgt = page.evaluate("Math.round(document.querySelector('.pw-tabs').getBoundingClientRect().height)")
        offsite = page.locator(".offsite").count()
        assert "Kiểm chứng" in sel, sel
        assert hgt >= 40, f"thanh tab bị ép còn {hgt}px"
        page.locator(".lc textarea").wait_for(timeout=30_000)
        # Kịch bản demo: dán tin ở Kiểm chứng → sang Hồ sơ xem radar → QUAY LẠI Kiểm chứng. Thẻ dựng lại theo tab từng làm
        # mất trắng chữ đã dán (26/10/2026).
        page.locator(".lc textarea").fill("Đất cao ráo, không bao giờ ngập.")
        page.get_by_role("tab", name=re.compile("Hồ sơ")).click()
        page.get_by_role("tab", name=re.compile("Kiểm chứng")).click()
        kept = page.locator(".lc textarea").input_value(timeout=30_000)
        assert "không bao giờ ngập" in kept, f"đổi tab mất chữ tin đã dán: '{kept}'"
        return f"tab {sel.strip()} · cao {hgt}px · khung 'ngoài phạm vi': {offsite} · đổi tab giữ chữ tin"
    try_now()

    @step("Trang đầu → 'Xem ngay: Huế': không lớp phủ nào chặn bấm, lịch sử nước TỰ đọc (không phải bấm nút)")
    def try_hue():
        # Báo cáo kiểm toàn bộ 12/10/2026, mục 3–4: hộp hướng dẫn từng che cả màn sau khi đã chọn thửa; lịch sử
        # nước bắt bấm nút rồi chờ ~150 s. Ngữ cảnh mới = lần đầu vào (chưa có cờ đã xem hướng dẫn).
        ctx = browser.new_context(viewport={"width": 1366, "height": 860})
        pg = watch(ctx.new_page())
        pg.goto(WEB + "/", wait_until="networkidle", timeout=120_000)
        pg.get_by_role("button", name=re.compile("Xem ngay")).first.click()
        pg.locator(".pw-tabs").wait_for(timeout=60_000)
        pg.wait_for_timeout(2500)
        covered = pg.evaluate("""(() => { const pts = ['.pw-tabs', '.pw-map canvas'].map((s) => document.querySelector(s)).filter(Boolean);
            return pts.filter((el) => { const r = el.getBoundingClientRect(); const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
              return !el.contains(hit) && !(hit && hit.closest('.maplibregl-map')); }).length; })()""")
        assert covered == 0, f"{covered} vùng bị lớp phủ che"
        pg.get_by_role("tab", name=re.compile("Canh đất")).click()     # bấm được ngay → không bị chặn
        pg.locator(".wh-here").wait_for(timeout=30_000)
        pg.get_by_role("tab", name=re.compile("Hồ sơ")).click()
        pg.locator(".wh").first.wait_for(timeout=60_000)
        button = pg.get_by_role("button", name=re.compile("Xem lịch sử nước")).count()
        assert button == 0, "vẫn còn nút bắt bấm 'Xem lịch sử nước'"
        assert pg.get_by_role("button", name=re.compile("Xem đất có đổi khác")).count() == 0, "ô loại đất vẫn bắt bấm"
        pg.locator(".lc2 .wh-sum, .lc2 .doc-note").first.wait_for(timeout=90_000)   # loại đất tự chạy xong
        pg.locator(".wh-sum, .wh-prog").first.wait_for(timeout=60_000)
        pg.wait_for_timeout(1500)
        pg.screenshot(path=os.path.join(OUT, "18-xem-ngay-hue.png"), full_page=False)
        state_txt = "đã có kết quả" if pg.locator(".wh-sum").count() else "đang tự đọc (có thanh tiến độ)"
        if pg.locator("section.wh .wh-list li").count():            # có đợt nước → có lời mời xác nhận từng đợt (17/10/2026)
            assert pg.locator("section.wh p.wh-cf-note").count() == 1, "thiếu lời mời 'ruộng có ngập đợt này không'"
            state_txt += " · có lời mời xác nhận từng đợt"
        ctx.close()
        return f"không lớp phủ che · lịch sử nước {state_txt}"
    try_hue()

    @step("Thửa Quảng Điền: lịch sử nước có đợt + lời mời xác nhận (khách không thấy nút); ô tìm kiếm đọc link Google Maps")
    def confirm_and_maplink():
        # 17–18/10/2026: xác nhận từng đợt nước (chỉ người đăng nhập bấm được) + đọc link "địa điểm" Google Maps (lỗi cũ ra
        # toạ độ (1, 1)). CHỈ ĐỌC: không bấm xác nhận, không chọn thửa.
        ctx = browser.new_context(viewport={"width": 1366, "height": 860})
        pg = watch(ctx.new_page())
        pg.goto(WEB + "/plot/16.57510,107.49520", wait_until="domcontentloaded", timeout=120_000)
        pg.locator("section.wh .wh-list li").first.wait_for(timeout=180_000)      # thửa mẫu đã hâm nóng (warm-demo)
        n = pg.locator("section.wh .wh-list li").count()
        assert pg.locator("section.wh p.wh-cf-note").count() == 1, "thiếu lời mời xác nhận từng đợt"
        assert pg.locator("section.wh .wh-cf").count() == 0, "khách chưa đăng nhập không được thấy nút xác nhận"
        assert pg.get_by_role("button", name=re.compile("Mời người ở đó xác nhận")).count() == 1, "thiếu nút mời xác nhận"
        pg.goto(WEB + "/", wait_until="domcontentloaded", timeout=120_000)
        q = pg.locator("input.start-q").first
        q.wait_for(timeout=60_000)
        pg.wait_for_timeout(2500)                                                  # chờ React gắn sự kiện
        q.click()
        q.fill("https://www.google.com/maps/place/Hu%E1%BA%BF/@16.4637,107.5909,15z/data=!3m1!4b1!8m2!3d16.4498!4d107.5623")
        hit = pg.locator(".start-hits button").first
        hit.wait_for(timeout=10_000)
        label = hit.inner_text()
        assert "16.4498" in label and "107.5623" in label, f"đọc sai link Google Maps: {label}"
        ctx.close()
        return f"{n} đợt nước · lời mời có, nút ẩn với khách · link Google Maps → {label}"
    confirm_and_maplink()

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
        page.get_by_role("tab", name=re.compile("Chuyên sâu")).click()
        page.locator(".pw-mod").first.wait_for(timeout=30_000)
        shot(page, "15-workspace-tools", full=False)
        return f"{page.locator('.pw-mod').count()} công cụ"
    workspace()

    @step("Canh đất → 'Xem độ ẩm tán lá 10 m' (S10 ①): ảnh 20 m đo gốc cạnh ảnh 10 m làm sắc, hoặc nói rõ vì sao chưa có")
    def moisture():
        # 20/10/2026: NDMI 10 m bật sau phép kiểm Wald đăng ký trước (s2_sharpen_result.json). CHỈ ĐỌC (GET).
        ctx = browser.new_context(viewport={"width": 1366, "height": 860})
        pg = watch(ctx.new_page())
        pg.goto(WEB + "/", wait_until="networkidle", timeout=120_000)     # /plot/… là Sổ tay thửa, không có khu làm việc
        pg.get_by_role("button", name=re.compile("Xem ngay")).first.click()
        pg.locator(".pw-tabs").wait_for(timeout=120_000)
        skip = pg.get_by_role("button", name="Bỏ qua")
        if skip.count():
            skip.first.click()
        # Ảnh nền độ phân giải cao thật phải nói ngày chụp (21/10/2026). Mềm: dịch vụ Esri hỏng thì dòng này không hiện.
        try:
            pg.locator(".pw-basemap").first.wait_for(timeout=30_000)
            basemap = pg.locator(".pw-basemap").first.inner_text()
            assert "Ảnh nền" in basemap, basemap
        except Exception:  # noqa: BLE001
            basemap = "(không đọc được dòng ảnh nền)"
        pg.get_by_role("tab", name=re.compile("Canh đất")).click()
        pg.get_by_role("button", name=re.compile("Xem độ ẩm tán lá 10 m")).click()
        pg.locator("section.mm .mm-pair, section.mm .doc-note, section.mm .bat-err").first.wait_for(timeout=180_000)
        retried = ""
        err_txt = pg.locator("section.mm .bat-err").first.inner_text() if pg.locator("section.mm .bat-err").count() else ""
        if "request/phút" in err_txt or "Không kết nối được máy chủ" in err_txt:
            # Bộ giới hạn 120 lượt/phút/IP — hoặc (23/10 và 25/10/2026) lớp proxy của Render trả lỗi KHÔNG kèm CORS khi
            # một IP vừa dội ~20 yêu cầu ở bước khu làm việc (cả bộ E2E chạy từ MỘT IP). Làm như người dùng: chờ rồi bấm
            # Thử lại MỘT lần; vẫn hỏng thì trượt thật. Ghi rõ vào kết quả để không che chuyện đã phải thử lại.
            pg.wait_for_timeout(65_000)
            pg.locator("section.mm").get_by_role("button", name="Thử lại").click()
            pg.locator("section.mm .mm-pair, section.mm .doc-note, section.mm .bat-err").first.wait_for(timeout=180_000)
            retried = f" · ĐÃ THỬ LẠI 1 lần sau lỗi: {err_txt[:60]}"
        pg.wait_for_timeout(800)
        pg.screenshot(path=os.path.join(OUT, "19-do-am-10m.png"), full_page=False)
        if pg.locator("section.mm .mm-pair").count():
            sizes = pg.evaluate("Array.from(document.querySelectorAll('section.mm canvas')).map((c) => c.width)")
            assert sizes == [32, 64], f"lưới sai: {sizes}"
            ctx.close()
            return f"ảnh 20 m (32 ô) cạnh ảnh 10 m (64 ô) · {basemap[:90]}{retried}"
        assert not pg.locator("section.mm .bat-err").count(), pg.locator("section.mm .bat-err").inner_text()
        msg = pg.locator("section.mm .doc-note").first.inner_text()
        ctx.close()
        return f"không có ảnh quang mây — nói rõ: {msg[:80]}{retried}"
    moisture()

    @step("Khu làm việc trên điện thoại: tấm trượt 3 nấc, không tràn ngang")
    def phone_workspace():
        m = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
        pg = watch(m.new_page())
        pg.goto(WEB + "/", wait_until="networkidle", timeout=120_000)
        pg.locator(".start-quick button").first.click()
        pg.locator(".pw-tabs").wait_for(timeout=60_000)
        skip = pg.get_by_role("button", name="Bỏ qua")
        if skip.count():
            skip.first.click()
        pg.wait_for_timeout(1500)
        h = lambda: pg.evaluate("Math.round(document.querySelector('.pw-panel').getBoundingClientRect().height)")  # noqa: E731
        half = h()
        pg.locator(".pw-grip").click()                 # nửa màn → toàn màn
        pg.wait_for_timeout(500)
        full = h()
        pg.locator(".pw-grip").click()                 # toàn màn → thu gọn
        pg.wait_for_timeout(500)
        peek = h()
        pg.get_by_role("tab", name=re.compile("Kiểm chứng")).click()   # bấm tab khi thu gọn → mở nửa màn
        pg.wait_for_timeout(500)
        back = h()
        w = pg.evaluate("document.documentElement.scrollWidth")
        pg.screenshot(path=os.path.join(OUT, "17-phone-workspace.png"), full_page=False)
        m.close()
        assert peek < 220 < half < full, (peek, half, full)
        assert abs(back - half) < 8, (back, half)
        assert w <= 392, w
        return f"thu gọn {peek}px · nửa {half}px · toàn {full}px"
    phone_workspace()

    @step("Ảnh điện thoại (390 px) không tràn ngang")
    def phone():
        m = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True)
        pg = watch(m.new_page())
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
print(f"Phản hồi HTTP ≥400 + yêu cầu hỏng mạng ({len(bad_responses)}):")
for e in dict.fromkeys(bad_responses):
    print("  ", e)
print("Ảnh chụp:", OUT)
# Bước nào trượt thì CI phải ĐỎ — trước đây script chỉ in FAIL rồi thoát mã 0, CI luôn "xanh" (sửa 10/10/2026).
failed = [n for n, ok, _ in results if not ok]
if failed:
    print(f"\n{len(failed)} bước TRƯỢT: {', '.join(failed)}")
    sys.exit(1)
