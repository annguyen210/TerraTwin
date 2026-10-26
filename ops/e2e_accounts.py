"""KIỂM THỬ ĐẦU-CUỐI CÓ TÀI KHOẢN — người dùng + quản trị, bấm giao diện thật, CHỈ chạy trên stack cục bộ (CI).

    python ops/e2e_accounts.py <web> <api>
    vd: python ops/e2e_accounts.py http://127.0.0.1:3000 http://127.0.0.1:8000

Máy chủ phải chạy với: TERRATWIN_ADMIN_EMAILS chứa E2E_ADMIN (mặc định e2e-admin@terratwin.vn),
TERRATWIN_SEPAY_API_KEY = E2E_SEPAY_KEY, TERRATWIN_VIETQR_BIN/ACCOUNT/NAME là giá trị THỬ (không phải tài khoản thật).
KHÔNG chạy vào production: script ghi dữ liệu (đăng ký, yêu cầu nâng gói, giao dịch giả lập, tin đăng vàng).

Luồng: người dùng xin nâng gói → thấy mã VietQR đúng nội dung → giả lập SePay báo tiền về → trang Tài khoản TỰ cập nhật
gói → quản trị thấy giao dịch "đã cấp gói" → quản trị thêm/xoá tin đăng vàng (số điện thoại bị xoá trước khi lưu) →
các tab quản trị mở được → thẻ mô hình → tải dữ liệu của tôi → bật hai lớp + tải mã khôi phục → người thường bị chặn khỏi
tab quản trị → quản trị xoá tài khoản thử (gõ lại email).
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

WEB = sys.argv[1].rstrip("/")
API = sys.argv[2].rstrip("/")
ADMIN = os.environ.get("E2E_ADMIN", "e2e-admin@terratwin.vn")
SEPAY_KEY = os.environ.get("E2E_SEPAY_KEY", "e2e-sepay-khoa-thu")
OUT = os.path.join(os.environ.get("TEMP", "."), "terratwin-e2e-accounts")
os.makedirs(OUT, exist_ok=True)
results: list[tuple[str, bool, str]] = []
console_errors: list[str] = []


def step(name):
    def deco(fn):
        t = time.time()
        try:
            info = fn() or ""
            results.append((name, True, f"{info} ({time.time() - t:.0f}s)"))
            print(f"PASS {name} {info} ({time.time() - t:.0f}s)", flush=True)
        except Exception as e:                       # noqa: BLE001
            results.append((name, False, repr(e)[:300]))
            print(f"FAIL {name}: {repr(e)[:300]}", flush=True)
        return fn
    return deco


def api(method, path, body=None, tok=None, headers=None):
    h = {"Content-Type": "application/json", **(headers or {})}
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    r = urllib.request.Request(API + path, data=json.dumps(body).encode() if body is not None else None, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def totp_now(secret_b32: str) -> str:
    """Mã TOTP 6 số hiện tại (RFC 6238, SHA-1, 30 giây) — như ứng dụng Authenticator tính từ khoá trên màn hình."""
    import base64
    import hashlib
    import hmac
    import struct
    s = secret_b32.replace(" ", "").upper()
    key = base64.b32decode(s + "=" * (-len(s) % 8))
    h = hmac.new(key, struct.pack(">Q", int(time.time()) // 30), hashlib.sha1).digest()
    o = h[-1] & 0x0F
    return f"{(struct.unpack('>I', h[o:o + 4])[0] & 0x7FFFFFFF) % 1_000_000:06d}"


def register(email):
    st, j = api("POST", "/api/auth/register", {"email": email, "password": "MatKhauE2E-123", "name": "E2E"})
    assert st == 201, (st, j)
    return j["access_token"]


stamp = int(time.time())
USER = f"e2e-user-{stamp}@terratwin.vn"
state: dict = {}

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    ctx = browser.new_context(viewport={"width": 1360, "height": 900}, accept_downloads=True)
    page = ctx.new_page()
    page.set_default_navigation_timeout(120_000)
    page.on("console", lambda m: m.type == "error" and console_errors.append(f"{page.url} :: {m.text[:200]}"))
    page.on("pageerror", lambda e: console_errors.append(f"{page.url} :: PAGEERROR {str(e)[:200]}"))

    def login(tok):
        page.goto(WEB + "/")
        page.evaluate(f"localStorage.setItem('terratwin_token', '{tok}')")

    @step("Người dùng: xin nâng gói → thấy mã VietQR đúng nội dung chuyển khoản")
    def upgrade():
        state["user_tok"] = register(USER)
        login(state["user_tok"])
        page.goto(WEB + "/tai-khoan", wait_until="networkidle")
        page.get_by_text(USER).first.wait_for(timeout=60_000)
        page.get_by_label("Gói muốn xin").select_option("pro")
        page.get_by_placeholder("Vì sao cần thêm hạn mức? (vd HTX 40 hộ)").fill("E2E: HTX 40 hộ")
        page.get_by_role("button", name="Xin nâng hạn mức").click()
        page.locator(".tk-pay code").first.wait_for(timeout=60_000)
        memo = page.locator(".tk-pay code").first.inner_text()
        assert memo.startswith("TT") and memo.endswith("PRO"), memo
        page.get_by_alt_text("Mã VietQR chuyển khoản").wait_for(timeout=10_000)
        state["req_id"] = int(memo[2:].split()[0])
        page.screenshot(path=os.path.join(OUT, "01-vietqr.png"), full_page=True)
        return memo

    @step("SePay báo tiền về (giả lập) → gói tự kích hoạt, trang Tài khoản tự cập nhật")
    def sepay():
        rid = state["req_id"]
        txn = {"id": f"e2e-{stamp}", "transferType": "in", "transferAmount": 299000,
               "content": f"MBVCB.{stamp}.TT{rid}PRO.CT", "referenceCode": "FTE2E"}
        st, _ = api("POST", "/api/payments/sepay", txn, headers={"Authorization": "Apikey sai-khoa"})
        assert st == 401, f"sai khoá phải 401, được {st}"
        st, j = api("POST", "/api/payments/sepay", txn, headers={"Authorization": f"Apikey {SEPAY_KEY}"})
        assert st == 200 and j.get("status") == "matched", (st, j)
        st, j = api("POST", "/api/payments/sepay", txn, headers={"Authorization": f"Apikey {SEPAY_KEY}"})
        assert j.get("duplicate") is True, j                                    # SePay gửi lại → không cấp hai lần
        page.locator(".tk-pay").first.wait_for(state="detached", timeout=60_000)  # trang tự hỏi lại mỗi 15 giây
        st, me = api("GET", "/api/account/plan", tok=state["user_tok"])
        assert me["plan"] == "pro" and me["requests"][0]["status"] == "approved", me
        page.screenshot(path=os.path.join(OUT, "02-plan-active.png"), full_page=True)
        return f"gói {me['plan']} đến {me.get('until')}"

    @step("Người dùng: tải toàn bộ dữ liệu của tôi (JSON)")
    def export():
        with page.expect_download(timeout=60_000) as d:
            page.get_by_role("button", name="Tải toàn bộ dữ liệu của tôi (JSON)").click()
        path = os.path.join(OUT, "my-data.json")
        d.value.save_as(path)
        data = json.load(open(path, encoding="utf-8"))
        assert USER in json.dumps(data, ensure_ascii=False), "tệp xuất không có email của mình"
        return f"{os.path.getsize(path)} byte"

    @step("Người dùng: bật xác thực hai lớp bằng mã 6 số → tải tệp 8 mã khôi phục")
    def two_factor():
        page.goto(WEB + "/tai-khoan#hai-lop", wait_until="networkidle")
        page.get_by_role("button", name="Bật xác thực hai lớp").click()
        sec = page.locator(".tf-secret").first
        sec.wait_for(timeout=30_000)
        href = page.get_by_role("link", name="Đang dùng điện thoại? Mở thẳng ứng dụng Authenticator").get_attribute("href") or ""
        assert href.startswith("otpauth://totp/"), href
        page.get_by_label("2. Nhập mã 6 số đang hiện").fill(totp_now(sec.inner_text()))
        page.get_by_role("button", name="Xác nhận và bật").click()
        page.get_by_text("Mã khôi phục — lưu ngay").first.wait_for(timeout=30_000)
        with page.expect_download(timeout=30_000) as d:
            page.get_by_role("button", name="Tải tệp .txt").click()
        path = os.path.join(OUT, "ma-khoi-phuc.txt")
        d.value.save_as(path)
        codes = [ln for ln in open(path, encoding="utf-8").read().splitlines()[1:] if ln.strip()]
        assert len(codes) == 8, codes
        st, me = api("GET", "/api/auth/me", tok=state["user_tok"])
        assert st == 200 and me["totp_enabled"] is True, (st, me)
        page.screenshot(path=os.path.join(OUT, "02b-2fa-on.png"), full_page=True)
        return "đã bật, tệp 8 mã"

    @step("Người thường KHÔNG thấy dữ liệu quản trị")
    def not_admin():
        st, _ = api("GET", "/api/admin/payments", tok=state["user_tok"])
        assert st == 403, st
        page.goto(WEB + "/admin", wait_until="networkidle")
        assert page.get_by_role("button", name="Tin đăng GĐ3").count() == 0
        return "403 + không có tab quản trị"

    @step("Quản trị: thấy giao dịch SePay 'đã cấp gói' trong Yêu cầu nâng cấp")
    def admin_pay():
        state["admin_tok"] = register(ADMIN)
        login(state["admin_tok"])
        page.goto(WEB + "/admin", wait_until="networkidle")
        page.get_by_role("button", name="Yêu cầu nâng cấp").click()
        page.get_by_text("Chuyển khoản SePay").first.wait_for(timeout=30_000)
        page.get_by_text("đã cấp gói").first.wait_for(timeout=30_000)
        page.screenshot(path=os.path.join(OUT, "03-admin-payments.png"), full_page=True)

    @step("Quản trị: thêm tin đăng vàng → số điện thoại bị xoá trước khi lưu → xoá tin")
    def admin_gold():
        page.get_by_role("button", name="Tin đăng GĐ3").click()
        page.get_by_placeholder("Dán nội dung tin đăng…").fill("E2E bán đất thổ cư cao ráo, không ngập, LH 0905 123 456")
        page.get_by_label("Đất ở / thổ cư").check()
        page.get_by_label("Đất cao ráo").check()
        page.get_by_role("button", name="Thêm tin").click()
        item = page.locator("li", has_text="E2E bán đất thổ cư").first
        item.wait_for(timeout=30_000)
        txt = item.inner_text()
        assert "0905" not in txt and "[số điện thoại]" in txt, txt
        page.screenshot(path=os.path.join(OUT, "04-admin-gold.png"), full_page=True)
        item.get_by_role("button", name="xoá").click()
        item.wait_for(state="detached", timeout=30_000)
        return "ẩn danh đúng, xoá được"

    @step("Quản trị: mọi tab mở được, không lỗi")
    def admin_tabs():
        opened = []
        for name in ("Người dùng", "Sức khoẻ", "Phễu người dùng", "Góp ý thí điểm", "Gán nhãn v3", "Xác nhận thực địa",
                     "Sao lưu", "Trôi mô hình"):
            b = page.get_by_role("button", name=name)
            if b.count() == 0:
                continue
            b.first.click()
            page.wait_for_timeout(1500)
            assert page.locator(".ws-err").count() == 0, f"tab {name}: {page.locator('.ws-err').first.inner_text()}"
            opened.append(name)
        page.get_by_role("button", name="Người dùng").first.click()
        page.get_by_text(USER).first.wait_for(timeout=30_000)
        return f"{len(opened)} tab"

    @step("Thẻ mô hình: có nước ảnh thực địa + kiểm tin đăng (kết quả thật)")
    def cards():
        page.goto(WEB + "/mo-hinh", wait_until="networkidle")
        page.get_by_text("Nước trong ảnh thực địa").first.wait_for(timeout=30_000)
        page.get_by_text("Tách câu khẳng định trong tin đăng bán đất").first.wait_for(timeout=30_000)
        page.get_by_text("KHÔNG phải nhãn người").first.wait_for(timeout=30_000)

    @step("Quản trị: xoá tài khoản thử (gõ lại email) → biến khỏi danh sách, không đăng nhập được nữa")
    def admin_delete():
        page.goto(WEB + "/admin", wait_until="networkidle")
        page.get_by_role("button", name="Người dùng").first.click()
        row = page.locator("tr", has_text=USER).first
        row.wait_for(timeout=30_000)
        page.once("dialog", lambda dlg: dlg.accept("sai-" + USER))          # gõ sai email → máy chủ từ chối, không xoá
        row.get_by_role("button", name="Xoá tài khoản…").click()
        page.get_by_text("Email gõ lại không khớp").first.wait_for(timeout=30_000)
        page.once("dialog", lambda dlg: dlg.accept(USER))
        row.get_by_role("button", name="Xoá tài khoản…").click()
        page.get_by_text(f"Đã xoá {USER}").first.wait_for(timeout=30_000)
        page.locator("tr", has_text=USER).first.wait_for(state="detached", timeout=30_000)
        st, _ = api("POST", "/api/auth/login", {"email": USER, "password": "MatKhauE2E-123"})
        assert st == 401, st
        page.screenshot(path=os.path.join(OUT, "05-admin-delete.png"), full_page=True)
        return "sai email bị từ chối; đúng email → xoá, đăng nhập 401"

    browser.close()

print("\n==== TÓM TẮT ====")
for n, ok, info in results:
    print(("PASS " if ok else "FAIL ") + n + " — " + info)
print(f"\nLỗi console/trang ({len(console_errors)}):")
for e in dict.fromkeys(console_errors):
    print("  ", e)
failed = [n for n, ok, _ in results if not ok]
if failed:
    print(f"\n{len(failed)} bước TRƯỢT: {', '.join(failed)}")
    sys.exit(1)
