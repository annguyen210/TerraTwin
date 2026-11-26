"""26/11/2026 — HyperLogLog (số người khác nhau, không IP) + Count-Min Sketch (nơi được tìm nhiều nhất)."""
from __future__ import annotations

from datetime import date

from app.services import sketches as s


def test_hll_sai_so_nho_va_khong_dem_lap():
    r = s.hll_new()
    for _ in range(3):
        for i in range(5000):
            s.hll_add(r, f"u{i}".encode())
    assert abs(s.hll_count(r) - 5000) / 5000 < 0.05
    a, b = s.hll_new(), s.hll_new()
    for i in range(3000):
        s.hll_add(a, f"u{i}".encode())
    for i in range(2000, 5000):
        s.hll_add(b, f"u{i}".encode())
    assert abs(s.hll_count(s.hll_merge([a, b])) - 5000) / 5000 < 0.05     # gộp ngày = hợp, không cộng dồn


def test_visit_khong_luu_ip(monkeypatch):
    store = {}
    from app.services import cache_store
    monkeypatch.setattr(cache_store, "get", lambda k: store.get(k))
    monkeypatch.setattr(cache_store, "put", lambda k, v, ttl_seconds=0: store.__setitem__(k, v))
    d = date(2026, 11, 26)
    for i in range(40):
        s.visit(f"10.0.0.{i}", "Mozilla", d)
        s.visit(f"10.0.0.{i}", "Mozilla", d)
    blob = str(store)
    assert "10.0.0" not in blob and "Mozilla" not in blob
    v = s.visitors(7, today=d)
    assert 37 <= v["daily"][0]["unique"] <= 43 and v["std_error_pct"] == 1.6


def test_cms_top_va_khong_uoc_thap():
    st = {}
    for p, n in (("hue", 40), ("ben tre", 25), ("ca mau", 10)):
        for _ in range(n):
            s.cms_add(st, p)
    assert [x for x, _ in sorted(st["top"].items(), key=lambda x: -x[1])][:3] == ["hue", "ben tre", "ca mau"]
    assert s.cms_estimate(st, "hue") >= 40 and s.cms_estimate(st, "khong co") == 0
