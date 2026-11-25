"""Nâng cấp 25/11/2026 — chỗ cao gần nhất: Dijkstra trên lưới độ cao, tránh vùng thấp hơn thửa."""
from __future__ import annotations

from app.services import high_ground as h, reqlang

N, C = h.N, h.N // 2


def _flat(v=2.0):
    return [v] * (N * N)


def test_tim_o_cao_gan_nhat():
    e = _flat()
    e[(C - 4) * N + C] = 6.0                 # ô cao cách 4 ô về phía BẮC
    e[(C + 2) * N + C] = 4.0                 # ô gần hơn nhưng chỉ cao hơn 2 m (< 3 m) → không tính
    r = h.route(e, 3.0)
    assert r["path"][-1] == (C - 4, C) and r["dist_m"] == 500 and r["low_steps"] == 0
    assert h._bearing_idx(C - 4, C) == 0      # Bắc


def test_tranh_vung_trung():
    e = _flat(2.0)
    e[C * N + C + 3] = 6.0                   # đích phía ĐÔNG, 3 ô
    for c in range(C + 1, C + 3):            # hai ô trũng ngay trên đường thẳng
        e[C * N + c] = 0.5
    r = h.route(e, 3.0)
    assert r["path"][-1] == (C, C + 3)
    assert r["low_steps"] == 0 and r["dist_m"] > 375   # vòng qua hàng bên cạnh, không lội ô trũng


def test_khong_co_cho_cao_va_thieu_du_lieu():
    assert h.route(_flat(), 3.0) is None
    e = _flat()
    e[C * N + C] = None
    assert h.route(e, 3.0) is None


def test_cau_chu_va_thieu_do_cao(monkeypatch):
    from app.services import cache_store, realdata
    monkeypatch.setattr(cache_store, "get", lambda k: None)
    monkeypatch.setattr(cache_store, "put", lambda *a, **k: None)
    reqlang.set_lang("vi")
    e = _flat()
    e[(C + 4) * N + C - 4] = 7.0             # Tây Nam
    monkeypatch.setattr(h, "terrarium_elev", lambda pts: list(e))
    r = h.find(16.5, 107.5)
    assert r["found"] and "Tây Nam" in r["text"] and "sơ tán" in r["caveat"] and len(r["path"]) >= 2
    monkeypatch.setattr(h, "terrarium_elev", lambda pts: [None] * len(pts))
    monkeypatch.setattr(realdata, "elevation_multi", lambda pts: [None] * len(pts))
    assert h.find(16.5, 107.5)["available"] is False
    monkeypatch.setattr(realdata, "elevation_multi", lambda pts: list(e))     # ô địa hình hỏng → Open-Meteo dự phòng
    assert h.find(16.5, 107.5)["found"]
