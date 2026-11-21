"""Kiểm A–Z 21/11/2026, P1-1 — thẻ thửa phải nhất quán với các mô-đun.

Quảng Điền (16.5751, 107.4952): /api/scan ghi "TerraScore 100/A — Hiểm hoạ thiên tai 7 ngày tới: thấp" trong khi
/api/assess/upstream_flood báo NGUY HIỂM (210,1 mm thượng nguồn so với 168,7 mm); nhãn chờ của lũ thượng nguồn và vùng
nguyên liệu ghi "cần ảnh vệ tinh" dù không dùng ảnh; điện mặt trời "danger" kèm chữ "Trung bình"."""
from __future__ import annotations

from types import SimpleNamespace

from app.modules import registry
from app.schemas import Assessment, Location
from app.services import reqlang, scan, terrascore

LOC = Location(lat=16.5751, lon=107.4952)


def _a(mid: str, level: str, real: bool = True, head: str = "x") -> Assessment:
    return Assessment(module_id=mid, module_name=registry.get_module(mid).disp_name(), location=LOC, status="ok",
                      risk_level=level, headline=head, detail="", recommendation="r", confidence=0.7, is_real=real,
                      data_sources=[])


def _ts(score=100, grade="A"):
    reqlang.set_lang("vi")
    return terrascore.TerraScoreResult(location=LOC, score=score, grade=grade,
                                       summary="Hiểm hoạ thiên tai 7 ngày tới: thấp. (chấm từ 5/5 hiểm họa có dữ liệu thật)",
                                       breakdown={}, real_data_ratio=1.0, scope="")


def test_co_moi_nguy_hiem_ngoai_5_hiem_hoa_thi_khong_ghi_thap():
    alerts = [SimpleNamespace(id="upstream_flood", name="Lũ từ thượng nguồn", risk_level="danger")]
    ts = terrascore.with_other_threats(_ts(), alerts)
    assert "thấp" not in ts.summary
    assert ts.summary.startswith("Hiểm hoạ 7 ngày tới: có mối NGUY HIỂM — lũ từ thượng nguồn (nguy hiểm).")
    assert "5 hiểm hoạ thời tiết chính" in ts.summary and "(chấm từ 5/5" in ts.summary


def test_chi_canh_bao_thi_noi_can_theo_doi():
    alerts = [SimpleNamespace(id="upstream_flood", name="Lũ từ thượng nguồn", risk_level="warning")]
    ts = terrascore.with_other_threats(_ts(), alerts)
    assert ts.summary.startswith("Hiểm hoạ 7 ngày tới: còn 1 mối cần theo dõi — lũ từ thượng nguồn (cảnh báo).")
    assert "thấp" not in ts.summary


def test_khong_co_moi_khac_thi_giu_nguyen():
    # mối nằm TRONG 5 hiểm hoạ đã được tính vào điểm — không nhắc lại
    ts = terrascore.with_other_threats(_ts(78, "B"), [SimpleNamespace(id="flood", name="Lũ", risk_level="danger")])
    assert ts.summary.startswith("Hiểm hoạ thiên tai 7 ngày tới: thấp.")


def test_quet_sau_quang_dien_the_noi_ro_lu_thuong_nguon(monkeypatch):
    """Lượt quét sâu giả: 5 hiểm hoạ thời tiết an toàn (dữ liệu thật) + lũ thượng nguồn NGUY HIỂM → câu tóm tắt nói nó."""
    from app.services import jobs
    infos = [i for i in registry.list_modules() if registry.get_module(i.id) is not None]
    by = {h: _a(h, "safe") for h in terrascore._HAZARDS}
    by["upstream_flood"] = _a("upstream_flood", "danger", head="Thượng nguồn đang mưa rất lớn")
    monkeypatch.setattr(jobs, "gather", lambda tasks, **kw: [by.get(i.id) for i in infos][:len(tasks)])
    r = scan.scan(LOC, include_heavy=True, deadline=5.0)
    assert any(a.id == "upstream_flood" and a.risk_level == "danger" for a in r.alerts)
    assert r.terrascore.grade == "A" and "thấp" not in r.terrascore.summary
    assert "lũ từ thượng nguồn (nguy hiểm)" in r.terrascore.summary


def test_nhan_cho_dung_ly_do(monkeypatch):
    from app.services import jobs
    monkeypatch.setattr(jobs, "gather", lambda tasks, **kw: [None] * len(tasks))
    reqlang.set_lang("vi")
    r = scan.scan(LOC, include_heavy=False, deadline=1.0)
    pend = {m.id: m.headline for m in r.modules if m.status == "pending"}
    assert "ảnh vệ tinh" not in pend["upstream_flood"] and "24 điểm" in pend["upstream_flood"]
    assert "ảnh vệ tinh" not in pend["supply_chain"] and "khí hậu 10 năm" in pend["supply_chain"]
    for mid in ("pest", "yield", "carbon", "storm_damage", "illegal_build"):
        assert "cần ảnh vệ tinh" in pend[mid], (mid, pend[mid])


def test_dien_mat_troi_chu_khop_thang_thong_tin(monkeypatch):
    from app.services import datasources as ds
    reqlang.set_lang("vi")
    m = registry.get_module("solar")
    assert m.threat is False                        # không bao giờ thành cảnh báo / tô đỏ
    for rad, lvl, chu in ((4.22, "danger", "Kém"), (4.5, "warning", "Trung bình"), (5.1, "safe", "Phù hợp")):
        monkeypatch.setattr(ds, "solar_radiation", lambda la, lo, r=rad: (r, True))
        a = m.assess(LOC)
        assert a.risk_level == lvl and a.headline.startswith(chu), (rad, a.headline)
