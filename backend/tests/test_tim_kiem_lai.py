"""Nâng cấp 25/11/2026 — kho kinh nghiệm của trợ lý: BM25 + Reciprocal Rank Fusion với thứ hạng gen đất."""
from __future__ import annotations

from types import SimpleNamespace as N

from app.services import copilot


def test_bm25_tu_hiem_nang_hon_va_khong_thuong_bai_dai():
    notes = [N(topic="mặn", title="Xử lý ruộng nhiễm mặn", body="Rửa mặn bằng nước ngọt đầu vụ."),
             N(topic="lúa", title="Gieo lúa", body="lúa lúa lúa ruộng ruộng ruộng nước nước " * 10),
             N(topic="cà phê", title="Tưới cà phê", body="Tưới cà phê mùa khô.")]
    s = copilot.bm25("Ruộng tôi bị mặn phải làm sao?", notes)
    assert s[0] > s[1] > 0 and s[2] == 0
    assert copilot.bm25("", notes) == [0.0, 0.0, 0.0]
    s2 = copilot.bm25("ruong bi man", notes)                      # gõ không dấu vẫn khớp
    assert s2[0] > 0


def test_rrf_gop_hai_thu_hang():
    f = copilot.rrf([0, 1, 2], [2, 1, 0])
    assert abs(f[0] - f[2]) < 1e-12 and f[1] == 2 / 62
    f = copilot.rrf([0, 1, 2], [0, 2, 1])
    assert max(f, key=f.get) == 0
