"""Gói cước, hạn mức và bảng kê sử dụng.

Test quan trọng nhất ở đây không phải "bảng giá hiện ra đúng" mà là "hạn mức
THI HÀNH thật". Một bảng giá không chặn được ai chỉ là trang trí, và tệ hơn
trang trí: nó làm người đọc tưởng phần thương mại đã xong.

Nhóm cuối kiểm tra sản phẩm KHÔNG nói dối về tình trạng thanh toán.
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import plans

client = TestClient(app)


def _dang_ky(email: str) -> str:
    r = client.post("/api/auth/register",
                    json={"email": email, "password": "matkhaudaidu123", "name": "Test"})
    if r.status_code >= 400:
        r = client.post("/api/auth/login",
                        json={"email": email, "password": "matkhaudaidu123"})
    return r.json()["access_token"]


# ─────────────────────────────── bảng giá ───────────────────────────────

def test_ba_goi_tang_dan_ve_han_muc():
    q = [plans.PLANS[k]["quota"] for k in ("free", "pro", "enterprise")]
    assert q == sorted(q) and len(set(q)) == 3


def test_gia_tang_dan_theo_han_muc():
    p = [plans.PLANS[k]["price_vnd"] for k in ("free", "pro", "enterprise")]
    assert p == sorted(p)
    assert plans.PLANS["free"]["price_vnd"] == 0


def test_bang_gia_luon_noi_ro_chua_thu_tien():
    """Không được để ai đọc bảng giá rồi tưởng đã có doanh thu."""
    c = plans.catalogue()
    assert c["status"] == "đề xuất"
    assert "chưa" in c["disclaimer"].lower()
    assert "thanh toán" in c["disclaimer"].lower()


def test_endpoint_bang_gia_mo_cho_moi_nguoi():
    """Xem giá thì không cần đăng nhập — bắt đăng nhập mới cho xem giá là vô lý."""
    r = client.get("/api/plans")
    assert r.status_code == 200
    assert len(r.json()["plans"]) == 3


# ─────────────────────────── hạn mức theo gói ───────────────────────────

def test_quota_for_tra_dung_tung_goi(monkeypatch):
    monkeypatch.delenv("TERRATWIN_KEY_MONTHLY_QUOTA", raising=False)
    assert plans.quota_for("free") == 500
    assert plans.quota_for("pro") == 5000
    assert plans.quota_for("enterprise") == 50000


def test_goi_khong_biet_thi_ve_muc_thap_nhat(monkeypatch):
    """Gói lạ phải rơi về mức THẤP nhất, không phải mức cao nhất.

    Sai chiều ở đây là lỗ hổng: đặt plan='vip' rồi được hạn mức doanh nghiệp.
    """
    monkeypatch.delenv("TERRATWIN_KEY_MONTHLY_QUOTA", raising=False)
    assert plans.quota_for("vip") == plans.PLANS["free"]["quota"]
    assert plans.quota_for(None) == plans.PLANS["free"]["quota"]
    assert plans.quota_for("") == plans.PLANS["free"]["quota"]


def test_bien_moi_truong_ghi_de_duoc(monkeypatch):
    monkeypatch.setenv("TERRATWIN_KEY_MONTHLY_QUOTA", "7")
    assert plans.quota_for("enterprise") == 7


def test_tu_choi_goi_khong_hop_le_khi_tao_khoa():
    tok = _dang_ky("goi-la@test.vn")
    h = {"Authorization": f"Bearer {tok}"}
    r = client.post("/api/keys?label=thu&plan=sieu-vip", headers=h)
    assert r.status_code == 400
    assert "không hợp lệ" in r.json()["detail"].lower()


def test_khoa_tao_ra_mang_dung_goi_va_han_muc(monkeypatch):
    monkeypatch.delenv("TERRATWIN_KEY_MONTHLY_QUOTA", raising=False)
    tok = _dang_ky("goi-pro@test.vn")
    h = {"Authorization": f"Bearer {tok}"}
    r = client.post("/api/keys?label=chinh&plan=pro", headers=h)
    assert r.status_code == 201
    body = r.json()
    assert body["plan"] == "pro"
    assert body["monthly_quota"] == 5000


def test_han_muc_duoc_THI_HANH_that_chu_khong_chi_hien_thi(monkeypatch):
    """Test then chốt của cả tệp: vượt hạn mức phải bị CHẶN bằng 429.

    Nếu test này hỏng thì bảng giá vô nghĩa — ai cũng dùng được không giới hạn
    dù đăng ký gói nào.
    """
    monkeypatch.setenv("TERRATWIN_KEY_MONTHLY_QUOTA", "3")
    tok = _dang_ky("han-muc@test.vn")
    h = {"Authorization": f"Bearer {tok}"}
    raw = client.post("/api/keys?label=cham&plan=free", headers=h).json()["key"]

    # PHẢI dùng endpoint CÓ xác thực. /api/modules là công khai nên không đi
    # qua tầng đếm — chọn nhầm nó thì test xanh mà hạn mức chẳng chặn ai.
    hk = {"X-API-Key": raw}
    ma = [client.get("/api/plots", headers=hk).status_code for _ in range(6)]
    assert 429 in ma, f"hạn mức không được thi hành: {ma}"
    assert ma.index(429) <= 4, f"chặn quá muộn: {ma}"


def test_thong_bao_vuot_han_muc_chi_duong_di_tiep(monkeypatch):
    monkeypatch.setenv("TERRATWIN_KEY_MONTHLY_QUOTA", "1")
    tok = _dang_ky("vuot-han@test.vn")
    h = {"Authorization": f"Bearer {tok}"}
    raw = client.post("/api/keys?label=x&plan=free", headers=h).json()["key"]
    hk = {"X-API-Key": raw}
    for _ in range(4):
        r = client.get("/api/plots", headers=hk)
        if r.status_code == 429:
            d = r.json()["detail"]
            assert "/api/plans" in d, "báo lỗi phải chỉ chỗ xem mức cao hơn"
            return
    pytest.fail("không chặn được")


# ────────────────────────────── bảng kê ──────────────────────────────

class _Khoa:
    prefix = "tt_abc"
    calls_total = 120
    calls_period = 40
    created_at = None
    last_used_at = None
    plan = "pro"

    def __init__(self, period: str):
        self.period = period


def test_bang_ke_tinh_dung_phan_con_lai(monkeypatch):
    monkeypatch.delenv("TERRATWIN_KEY_MONTHLY_QUOTA", raising=False)
    from datetime import datetime, timezone
    k = _Khoa(datetime.now(timezone.utc).strftime("%Y-%m"))
    s = plans.statement(k)
    assert s["used"] == 40
    assert s["quota"] == 5000
    assert s["remaining"] == 4960
    assert s["over_quota"] == 0


def test_bang_ke_khong_giau_phan_vuot(monkeypatch):
    """Đã vượt thì nói vượt bao nhiêu, không làm tròn thành 'gần hết'."""
    monkeypatch.setenv("TERRATWIN_KEY_MONTHLY_QUOTA", "10")
    from datetime import datetime, timezone
    k = _Khoa(datetime.now(timezone.utc).strftime("%Y-%m"))
    s = plans.statement(k)
    assert s["over_quota"] == 30
    assert s["remaining"] == 0


def test_bang_ke_dat_lai_khi_sang_thang_moi(monkeypatch):
    monkeypatch.delenv("TERRATWIN_KEY_MONTHLY_QUOTA", raising=False)
    s = plans.statement(_Khoa("2019-01"))
    assert s["used"] == 0, "kỳ cũ không được tính vào kỳ này"


def test_endpoint_usage_can_dang_nhap():
    assert client.get("/api/usage").status_code in (401, 403)


def test_endpoint_usage_liet_ke_tung_khoa(monkeypatch):
    monkeypatch.delenv("TERRATWIN_KEY_MONTHLY_QUOTA", raising=False)
    tok = _dang_ky("bang-ke@test.vn")
    h = {"Authorization": f"Bearer {tok}"}
    client.post("/api/keys?label=a&plan=free", headers=h)
    client.post("/api/keys?label=b&plan=enterprise", headers=h)
    d = client.get("/api/usage", headers=h).json()
    assert len(d["keys"]) >= 2
    assert {k["plan"] for k in d["keys"]} >= {"free", "enterprise"}


# ──────────── KHÔNG NÓI DỐI VỀ TÌNH TRẠNG THANH TOÁN ────────────

def test_khong_dung_cong_thanh_toan_gia():
    """Không được có adapter thanh toán rỗng đóng vai đã tích hợp.

    Một 'PaymentGateway' không nhận được đồng nào nhưng làm người đọc mã tưởng
    phần thu tiền đã xong — tệ hơn là không có gì.
    """
    import app.services.plans as m
    src = open(m.__file__, encoding="utf-8").read().lower()
    for tu in ("class paymentgateway", "def charge(", "def capture_payment",
               "stripe", "def process_payment"):
        assert tu not in src, f"có {tu} — cổng thanh toán giả"


def test_moi_dau_ra_ve_tien_deu_noi_ro_chua_thu():
    from datetime import datetime, timezone
    s = plans.statement(_Khoa(datetime.now(timezone.utc).strftime("%Y-%m")))
    assert s["cash_cost_vnd"] == 0
    assert "chưa thu tiền" in s["billing_status"]
    assert plans.catalogue()["status"] == "đề xuất"
