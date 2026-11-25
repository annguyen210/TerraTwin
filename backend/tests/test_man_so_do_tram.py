"""Nâng cấp 25/11/2026 — số đo mặn trạm Trà Vinh / Cầu Quan 1991–2016 làm bối cảnh dài hạn cho thửa ĐBSCL."""
from __future__ import annotations

import json
import math
from pathlib import Path

from app.modules import salinity
from app.services import reqlang

DATA = Path(__file__).resolve().parents[1] / "data" / "salinity_stations.json"


def _mk(v):
    n = len(v)
    s = sum((v[j] > v[i]) - (v[j] < v[i]) for i in range(n) for j in range(i + 1, n))
    z = (s - 1) / math.sqrt(n * (n - 1) * (2 * n + 5) / 18)
    return z


def test_xu_the_tinh_lai_duoc_tu_so_lieu_trong_tep():
    d = json.loads(DATA.read_text(encoding="utf-8"))
    for k in ("tra_vinh", "cau_quan"):
        st = d["stations"][k]
        ys = sorted(st["annual_max"], key=int)
        v = [st["annual_max"][y] for y in ys]
        assert len(v) == 26 and ys[0] == "1991" and ys[-1] == "2016"
        assert abs(_mk(v) - st["mann_kendall_z"]) < 0.01                    # ai cũng tính lại được
        sl = sorted((v[j] - v[i]) / (int(ys[j]) - int(ys[i])) for i in range(len(v)) for j in range(i + 1, len(v)))
        assert abs(10 * sl[len(sl) // 2] - st["sen_g_l_per_decade"]) < 0.01


def test_cau_boi_canh_co_nguon():
    reqlang.set_lang("vi")
    t = salinity._mekong_history()
    assert "Trà Vinh" in t and "2.28" in t and "CC BY 4.0" in t
