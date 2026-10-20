"""Lệch 1000 của Sentinel-2 L2A từ phiên bản xử lý 04.00 (25/01/2022): chỉ số phải tính trên phản xạ thật.

Đo 20/10/2026 cùng một cảnh An Giang 04/2024: NDVI tính thẳng trên DN 0,232, trừ lệch 0,392.
"""
from __future__ import annotations

import urllib.parse


def _it(pb=None, d="2024-03-20"):
    p = {"datetime": f"{d}T03:15:19Z"}
    if pb is not None:
        p["s2:processing_baseline"] = pb
    return {"id": "S2X", "properties": p}


def test_nhan_biet_canh_co_lech():
    from app.services import mpc
    assert mpc.has_offset(_it("05.10")) and mpc.has_offset(_it("04.00"))
    assert not mpc.has_offset(_it("02.12", "2021-03-31")) and not mpc.has_offset(_it("03.01", "2021-12-01"))
    assert mpc.has_offset(_it(None, "2022-02-01")) and not mpc.has_offset(_it(None, "2021-06-01"))   # thiếu thuộc tính → theo ngày
    assert not mpc.has_offset(None)


def test_bieu_thuc_tru_lech_dung_tung_bang():
    import numpy as np
    from app.services import mpc
    assert mpc.index_expr("NDVI", False) == mpc.EXPR["NDVI"]
    e = mpc.index_expr("NDMI", True)
    assert "where(B08>1000,B08-1000,1)" in e and "where(B11>1000,B11-1000,1)" in e
    # tính lại bằng numpy đúng như máy chủ: DN 1300/4000 → phản xạ 0,03/0,30 → NDVI 0,818 (không trừ: 0,509)
    B04, B08 = np.array([1300.0]), np.array([4000.0])
    v = eval(mpc.index_expr("NDVI", True), {"where": np.where, "B04": B04, "B08": B08})
    assert abs(float(v[0]) - 0.27 / 0.33) < 1e-9
    assert abs(float(eval(mpc.EXPR["NDVI"], {"B04": B04, "B08": B08})[0]) - 2700 / 5300) < 1e-9
    # mặt nước tối (DN ≤ 1000) không làm mẫu số về 0 hay đổi dấu
    w = eval(mpc.index_expr("NDVI", True), {"where": np.where, "B04": np.array([990.0]), "B08": np.array([1000.0])})
    assert np.isfinite(w).all() and abs(float(w[0])) <= 1


def test_thong_ke_gui_bieu_thuc_da_tru_lech(monkeypatch):
    from app.services import mpc
    seen = []
    bands = [{"mean": 0.3, "count": 100.0}, {"mean": 0.6, "count": 100.0}, {"mean": 0.15, "count": 100.0},
             {"min": 0.5}, {"max": 0.5}]

    def call(url, payload=None, timeout=None):
        seen.append(urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["expression"][0])
        return {"properties": {"statistics": {str(i): b for i, b in enumerate(bands)}}}
    monkeypatch.setattr(mpc, "_call", call)
    mpc.masked_stats("x", [0, 0, 1, 1], "NDVI", offset=True)
    mpc.masked_stats("x", [0, 0, 1, 1], "NDVI")
    assert "B08-1000" in seen[0] and "B08-1000" not in seen[1]


def test_chuoi_chi_so_tru_lech_theo_tung_canh(monkeypatch):
    """Chuỗi trộn cảnh 2021 (không lệch) với 2024 (có lệch): mỗi cảnh nhận đúng biểu thức của nó."""
    from datetime import date
    from app.services import cache_store, mpc
    monkeypatch.setattr(cache_store, "get", lambda k: None)
    monkeypatch.setattr(cache_store, "put", lambda *a, **k: None)
    items = [_it("05.10", "2024-03-20") | {"id": "moi"}, _it("02.12", "2021-03-31") | {"id": "cu"}]
    monkeypatch.setattr(mpc, "search", lambda *a, **k: items)
    got = {}

    def ms(item_id, box, index, offset=False):
        got[item_id] = offset
        return {"mean": 0.5, "std": 0.0, "min": 0.5, "max": 0.5, "count": 3000, "clear_pct": 90.0}
    monkeypatch.setattr(mpc, "masked_stats", ms)
    rows = mpc.index_series(10.45, 105.25, "NDVI", days=2000, end=date(2024, 4, 1))
    assert got == {"moi": True, "cu": False} and len(rows) == 2
