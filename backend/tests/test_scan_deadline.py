"""Lượt quét nhanh có hạn chót: một nguồn chậm không được bắt cả bảng chờ theo.

Lỗi thật trên Render (10/2026): /api/scan mất ~120 giây mỗi lần vì Overpass từ
máy chủ đám mây hết giờ hai lần (2 × 60 giây), còn jobs.gather thoát khối `with`
là chờ mọi luồng — tham số timeout không cắt được gì.
"""
import time

from app.modules import registry
from app.schemas import Location
from app.services import jobs, scan


def test_gather_tra_ve_khi_het_han_chot():
    late = object()
    t = time.time()
    out = jobs.gather([lambda: 1, lambda: time.sleep(3) or 2], deadline=0.5, late=late)
    assert time.time() - t < 2.0
    assert out[0] == 1 and out[1] is late


def test_gather_khong_han_chot_van_cho_du():
    assert jobs.gather([lambda: time.sleep(0.2) or 7]) == [7]


def test_quet_nhanh_khong_cho_mo_dun_cham(monkeypatch):
    slow = registry.get_module("mining")
    orig = slow.assess
    monkeypatch.setattr(slow, "assess", lambda loc: time.sleep(4) or orig(loc))
    t = time.time()
    r = scan.scan(Location(lat=10.03, lon=105.78), deadline=2.0)
    assert time.time() - t < 3.5
    m = next(m for m in r.modules if m.id == "mining")
    assert m.status == "pending" and m.risk_level == "unknown"
    assert "mining" not in [a.id for a in r.alerts]
