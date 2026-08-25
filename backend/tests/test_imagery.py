"""Ảnh thửa đất — và những chỗ nó có thể lừa người xem.

Ảnh thuyết phục hơn con số rất nhiều, nên nó cũng nguy hiểm hơn khi sai. Nhóm
test này canh hai điều: ảnh phải luôn đi kèm NGÀY CHỤP và ĐỘ MÂY, và cặp ảnh
đối chiếu phải CÙNG MÙA.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.services import imagery


@pytest.fixture(autouse=True)
def _cache_sach(monkeypatch):
    """Mỗi test một cache riêng.

    plot_view() cache cả trường hợp KHÔNG có ảnh (đúng trong sản phẩm: trong
    6 giờ Sentinel-2 không bay qua lần nữa nên câu trả lời không đổi). Nhưng
    trong test thì test đầu tiên lưu "không có ảnh" cho một toạ độ, và mọi test
    sau ở cùng toạ độ nhận lại đúng câu đó — dính nhau mà nhìn như lỗi mã.
    """
    from app.services import cache_store
    kho: dict = {}
    monkeypatch.setattr(cache_store, "get", lambda k: kho.get(k))
    monkeypatch.setattr(cache_store, "put",
                        lambda k, v, ttl_seconds=None: kho.__setitem__(k, v))


def _fake_item(day: str, cloud: float):
    return {"id": f"S2_{day}", "properties": {"datetime": day + "T03:00:00Z",
                                              "eo:cloud_cover": cloud}}


def test_khong_co_anh_thi_noi_ro_vi_sao(monkeypatch):
    monkeypatch.setattr(imagery.mpc, "search", lambda *a, **k: [])
    d = imagery.plot_view(10.0, 106.0)
    assert d["available"] is False
    assert "mây" in d["message"].lower(), "phải nói rõ nguyên nhân là mây"


def test_chon_anh_it_may_nhat(monkeypatch):
    monkeypatch.setattr(imagery.mpc, "search", lambda *a, **k: [
        _fake_item("2026-06-01", 80.0),
        _fake_item("2026-06-11", 5.0),
        _fake_item("2026-06-21", 40.0)])
    d = imagery.plot_view(10.0, 106.0)
    assert d["now"]["date"] == "2026-06-11"


def test_moi_anh_deu_kem_ngay_va_do_may(monkeypatch):
    """Thiếu hai thứ này thì người xem tưởng đang nhìn hiện tại, và tưởng ảnh sạch."""
    monkeypatch.setattr(imagery.mpc, "search", lambda *a, **k: [_fake_item("2026-06-11", 12.0)])
    d = imagery.plot_view(10.0, 106.0)
    assert d["now"]["date"] and d["now"]["cloud_scene_pct"] == 12.0
    assert "2026-06-11" in d["caveat"] and "12.0" in d["caveat"]
    assert "không phải hôm nay" in d["caveat"]


def test_doi_chieu_phai_cung_mua(monkeypatch):
    """Ảnh tháng 3 đặt cạnh ảnh tháng 9 thì khác biệt chủ yếu là MÙA VỤ.

    Người xem sẽ kết luận "đất bị phá" trong khi thực ra chỉ là lúa chưa cấy.
    """
    goi = []

    def spy(box, start, end, **k):
        goi.append((start, end))
        return [_fake_item(start.isoformat(), 10.0)]

    monkeypatch.setattr(imagery.mpc, "search", spy)
    imagery.plot_view(10.0, 106.0)
    assert len(goi) == 2, "phải tìm hai cửa sổ: nay và năm ngoái"
    (_, end_nay), (start_xua, end_xua) = goi
    # Cửa sổ năm ngoái phải bao quanh cùng tháng, cách đúng một năm.
    assert end_xua.year == end_nay.year - 1 or start_xua.year == end_nay.year - 1
    assert abs(start_xua.month - end_nay.month) <= 2 or \
        abs(end_xua.month - end_nay.month) <= 2


def test_khong_co_anh_cung_mua_thi_KHONG_lay_bua_thang_khac(monkeypatch):
    lan = {"n": 0}

    def spy(box, start, end, **k):
        lan["n"] += 1
        return [_fake_item("2026-06-11", 10.0)] if lan["n"] == 1 else []

    monkeypatch.setattr(imagery.mpc, "search", spy)
    d = imagery.plot_view(10.0, 106.0)
    assert "then" not in d, "không được thay bằng ảnh mùa khác cho đủ cặp"
    assert "mùa vụ" in d["compare_note"]


def test_duong_dan_anh_tro_dung_vung_va_co_kich_thuoc(monkeypatch):
    monkeypatch.setattr(imagery.mpc, "search", lambda *a, **k: [_fake_item("2026-06-11", 8.0)])
    d = imagery.plot_view(15.33, 108.05, buffer_m=400)
    u = d["now"]["true_color"]
    assert u.startswith("https://planetarycomputer.microsoft.com/")
    assert "width=512" in u and "height=512" in u
    assert "108.0" in u and "15.3" in u
    assert d["span_m"] == 800


def test_ndvi_va_mau_that_la_hai_duong_khac_nhau(monkeypatch):
    monkeypatch.setattr(imagery.mpc, "search", lambda *a, **k: [_fake_item("2026-06-11", 8.0)])
    d = imagery.plot_view(10.0, 106.0)
    assert d["now"]["true_color"] != d["now"]["ndvi"]
    assert "visual" in d["now"]["true_color"]
    assert "B08" in d["now"]["ndvi"]


def test_khong_tai_anh_qua_may_chu_nay():
    """Mỗi ảnh nửa megabyte — đẩy qua máy chủ gói free là tự bóp cổ mình."""
    import inspect
    src = inspect.getsource(imagery)
    assert "urlopen" not in src, "chỉ trả ĐƯỜNG DẪN, không tải ảnh về"
