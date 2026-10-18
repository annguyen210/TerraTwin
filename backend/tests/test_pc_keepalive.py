"""Planetary Computer: trần đồng thời RIÊNG (không chung trần 6 của Open-Meteo) + kết nối giữ mở (18/10/2026)."""
from __future__ import annotations

import json


class _Resp:
    def __init__(self, status, body):
        self.status, self._b = status, body

    def read(self):
        return self._b


def test_ket_noi_hong_thi_mo_lai_mot_lan(monkeypatch):
    from app.services import mpc
    made = []

    class Conn:
        def __init__(self, host, timeout=None):
            self.n = len(made)
            made.append(self)
            self.timeout = timeout

        def request(self, method, path, body=None, headers=None):
            self.method, self.path = method, path
            if self.n == 0:
                raise ConnectionResetError("máy chủ đóng kết nối cũ")

        def getresponse(self):
            return _Resp(200, json.dumps({"ok": 1}).encode())

        def close(self):
            pass
    monkeypatch.setattr(mpc.http.client, "HTTPSConnection", Conn)
    monkeypatch.setattr(mpc._tls, "conn", None, raising=False)
    out = mpc._pc_request(mpc.DATA + "?collection=x&item=y", {"type": "Feature"}, 30)
    assert out == {"ok": 1} and len(made) == 2 and made[1].method == "POST" and made[1].path.startswith("/api/data/v1/item/statistics?")
    # lượt sau dùng lại kết nối đang mở (không tạo thêm)
    assert mpc._pc_request(mpc.DATA + "?a=1", None, 30) == {"ok": 1} and len(made) == 2


def test_loi_http_tra_none(monkeypatch):
    from app.services import mpc

    class Conn:
        def __init__(self, host, timeout=None):
            self.timeout = timeout

        def request(self, *a, **k):
            pass

        def getresponse(self):
            return _Resp(503, b"busy")

        def close(self):
            pass
    monkeypatch.setattr(mpc.http.client, "HTTPSConnection", Conn)
    monkeypatch.setattr(mpc._tls, "conn", None, raising=False)
    assert mpc._pc_request(mpc.DATA + "?a=1", None, 30) is None


def test_tran_rieng_cho_planetary_computer():
    from app.services import jobs
    assert jobs._PC_LIMIT > jobs._UPSTREAM_LIMIT
    pc, other = jobs.upstream("pc"), jobs.upstream()
    assert pc._sem is jobs._upstream_pc and other._sem is jobs._upstream
