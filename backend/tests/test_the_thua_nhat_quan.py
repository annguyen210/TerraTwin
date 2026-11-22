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


# ---- Kiểm A–Z lần 2 (22/11/2026): thẻ + kế hoạch khi lũ thượng nguồn NGUY HIỂM, 5 hiểm hoạ thời tiết đều yên ----

def _scan_yen_upstream_pending():
    from app.schemas import ScanModule, ScanResult, TerraScoreResult
    mods = [ScanModule(id=h, name=h, icon="", group="B", risk_level="safe", headline="yên", recommendation="",
                       is_real=True, threat=True, status="ok", risk_dates=[]) for h in terrascore._HAZARDS]
    mods.append(ScanModule(id="upstream_flood", name="Lũ từ thượng nguồn", icon="", group="B", risk_level="unknown",
                           headline="Đang kiểm tra", recommendation="", is_real=False, threat=True, status="pending"))
    ts = TerraScoreResult(location=LOC, score=100, grade="A", summary="Hiểm hoạ thiên tai 7 ngày tới: thấp.")
    return ScanResult(location=LOC, terrascore=ts, modules=mods, alerts=[], real_data_ratio=1.0,
                      generated_at="2026-11-22T00:00:00")


def test_ke_hoach_khong_noi_moi_ngay_deu_thuan_khi_lu_thuong_nguon_nguy_hiem(monkeypatch):
    import json
    from app.services import advisor, landuse
    monkeypatch.setattr(scan, "scan", lambda loc, deadline=None: _scan_yen_upstream_pending())
    monkeypatch.setattr(landuse, "fetch_raw", lambda la, lo: None)
    up = registry.get_module("upstream_flood")
    monkeypatch.setattr(up, "assess", lambda loc: _a("upstream_flood", "danger",
                        head="Thượng nguồn đang mưa rất lớn và nước sẽ dồn về đây — mưa thượng nguồn 260 mm"))
    reqlang.set_lang("vi")
    p = advisor.build(LOC, crop="lua")
    txt = json.dumps(p, ensure_ascii=False)
    assert "mọi ngày đều thuận" not in txt
    assert p["safe_window"]["safe_dates"] == [] and all("Lũ từ thượng nguồn" in d["hazards"] for d in p["safe_window"]["days"])
    assert p["actions"][0]["id"] == "upstream_flood" and p["actions"][0]["risk_level"] == "danger"


def test_ke_hoach_chua_tinh_kip_lu_thuong_nguon_thi_khong_goi_ngay_nao_an_toan(monkeypatch):
    import json, time
    from app.services import advisor, landuse
    monkeypatch.setattr(scan, "scan", lambda loc, deadline=None: _scan_yen_upstream_pending())
    monkeypatch.setattr(landuse, "fetch_raw", lambda la, lo: None)
    monkeypatch.setattr(advisor, "UPSTREAM_TIMEOUT", 0.3)
    up = registry.get_module("upstream_flood")
    monkeypatch.setattr(up, "assess", lambda loc: time.sleep(2) or _a("upstream_flood", "safe"))
    reqlang.set_lang("vi")
    p = advisor.build(LOC, crop="lua")
    sw = p["safe_window"]
    assert "mọi ngày đều thuận" not in json.dumps(p, ensure_ascii=False)
    assert sw["safe_dates"] == [] and all(d["unknown"] for d in sw["days"])
    assert "chưa tính lũ từ thượng nguồn" in sw["headline"] and "đang kiểm" in sw["headline"]


def test_ke_hoach_lu_thuong_nguon_thieu_du_lieu_thi_khong_goi_ngay_nao_an_toan(monkeypatch):
    """Kiểm 22/11/2026 (sau PR #59): mô-đun chạy xong mà THIẾU DỮ LIỆU (is_real=False) trước đây bị coi là "không đe doạ"
    → vẫn "mọi ngày đều thuận". Nay là "chưa kết luận được"."""
    import json
    from app.services import advisor, landuse
    monkeypatch.setattr(scan, "scan", lambda loc, deadline=None: _scan_yen_upstream_pending())
    monkeypatch.setattr(landuse, "fetch_raw", lambda la, lo: None)
    up = registry.get_module("upstream_flood")
    monkeypatch.setattr(up, "assess", lambda loc: _a("upstream_flood", "unknown", real=False, head="Thiếu dữ liệu mưa"))
    reqlang.set_lang("vi")
    p = advisor.build(LOC, crop="lua")
    sw = p["safe_window"]
    assert "mọi ngày đều thuận" not in json.dumps(p, ensure_ascii=False)
    assert sw["safe_dates"] == [] and all(d["unknown"] for d in sw["days"])
    assert "chưa kết luận được" in sw["headline"]


def test_the_co_other_threats_co_cau_truc():
    alerts = [SimpleNamespace(id="upstream_flood", name="Lũ từ thượng nguồn", risk_level="danger")]
    ts = terrascore.with_other_threats(_ts(), alerts)
    assert ts.other_threats == [{"id": "upstream_flood", "name": "Lũ từ thượng nguồn", "risk_level": "danger", "kind": "forecast"}]
    assert ts.grade == "A"                              # điểm vẫn chỉ chấm 5 hiểm hoạ — chữ to do other_threats quyết


# ---- Kiểm A–Z lần 3 (22/11/2026): Huế 16.52,107.59 — chỉ mối DỰ BÁO vào "7 ngày tới" và lịch ngày an toàn ----

def test_sau_benh_quan_sat_khong_vao_7_ngay_toi():
    alerts = [SimpleNamespace(id="pest", name="Phát hiện sâu bệnh sớm", risk_level="danger",
                              headline="Sức sống cây giảm mạnh bất thường — NDVI 0.1849, ảnh ngày 2026-11-15"),
              SimpleNamespace(id="mining", name="An toàn mỏ & công trường", risk_level="warning", headline="mỏ cách 3 km")]
    ts = terrascore.with_other_threats(_ts(), alerts)
    assert ts.other_threats == []                                    # không lên chữ to "7 ngày tới"
    assert ts.summary.startswith("Hiểm hoạ thiên tai 7 ngày tới: thấp.")
    kinds = {o["id"]: o["kind"] for o in ts.observed_threats}
    assert kinds == {"pest": "observed", "mining": "fixed"}
    assert "ảnh ngày 2026-11-15" in ts.observed_threats[0]["headline"]


def test_lu_thuong_nguon_van_la_du_bao():
    alerts = [SimpleNamespace(id="upstream_flood", name="Lũ từ thượng nguồn", risk_level="danger", headline="x"),
              SimpleNamespace(id="pest", name="Phát hiện sâu bệnh sớm", risk_level="danger", headline="y")]
    ts = terrascore.with_other_threats(_ts(), alerts)
    assert [o["id"] for o in ts.other_threats] == ["upstream_flood"] and ts.other_threats[0]["kind"] == "forecast"
    assert "sâu bệnh" not in ts.summary


def test_hang_a_co_hiem_hoa_canh_bao_thi_khong_noi_thap(monkeypatch):
    """Huế: lũ CẢNH BÁO mà hạng A 89 → "thấp". Điểm giữ nguyên, câu chữ đổi, có hazard_alerts cho giao diện."""
    reqlang.set_lang("vi")
    ass = {h: _a(h, "safe") for h in terrascore._HAZARDS}
    ass["flood"] = _a("flood", "warning")
    ts = terrascore.compute(LOC, assessments=ass, reassess=False)
    assert ts.grade == "A" and ts.score >= 80
    assert "thấp" not in ts.summary and "cần để ý" in ts.summary
    assert ts.hazard_alerts == [{"id": "flood", "name": registry.get_module("flood").disp_name(), "risk_level": "warning"}]
    ts2 = terrascore.compute(LOC, assessments={h: _a(h, "safe") for h in terrascore._HAZARDS}, reassess=False)
    assert ts2.hazard_alerts == [] and "thấp" in ts2.summary


def test_ke_hoach_moi_co_dinh_khong_chan_ngay_lam_dong(monkeypatch):
    """Huế: 'An toàn mỏ & công trường' (nhà máy cách 3,1 km) chặn CẢ 7 ngày làm đồng. Mối cố định/quan sát không vào lịch."""
    from app.schemas import ScanModule
    from app.services import advisor, landuse
    sc = _scan_yen_upstream_pending()
    sc.modules = [m for m in sc.modules if m.id != "upstream_flood"]
    mine = ScanModule(id="mining", name="An toàn mỏ & công trường", icon="", group="D", risk_level="warning",
                      headline="Gần nhất mỏ cách 3,1 km", recommendation="r", is_real=True, threat=True, status="ok")
    pest = ScanModule(id="pest", name="Phát hiện sâu bệnh sớm", icon="", group="A", risk_level="danger",
                      headline="ảnh ngày 2026-11-15", recommendation="r", is_real=True, threat=True, status="ok")
    sc.alerts = [pest, mine]
    monkeypatch.setattr(scan, "scan", lambda loc, deadline=None: sc)
    monkeypatch.setattr(landuse, "fetch_raw", lambda la, lo: None)
    reqlang.set_lang("vi")
    p = advisor.build(LOC, crop="lua")
    sw = p["safe_window"]
    assert len(sw["safe_dates"]) == 7 and all(d["hazards"] == [] for d in sw["days"])
    assert {a["id"] for a in p["actions"]} == {"pest", "mining"}     # vẫn nằm trong việc cần làm


def test_mo_chi_tinh_mo_va_bai_khai_thac_khong_tinh_khu_cong_nghiep():
    sel = registry.get_module("mining")._SELECTOR
    assert sel == '[~"^(landuse|industrial)$"~"^(quarry|mine)$"]'        # khoá: landuse=industrial không còn khớp
    assert '"industrial"' not in sel and "quarry|industrial" not in sel


def test_tom_tat_khong_lap_hiem_hoa_7_ngay_toi():
    """Huế sau PR #66: "Hiểm hoạ 7 ngày tới: còn 1 mối … Hiểm hoạ 7 ngày tới: có mối cần để ý — …" — lặp cụm mở đầu."""
    reqlang.set_lang("vi")
    ass = {h: _a(h, "safe") for h in terrascore._HAZARDS}
    ass["flood"] = _a("flood", "warning")
    ts = terrascore.compute(LOC, assessments=ass, reassess=False)
    ts = terrascore.with_other_threats(ts, [SimpleNamespace(id="upstream_flood", name="Lũ từ thượng nguồn",
                                                            risk_level="warning", headline="x")])
    assert ts.summary.count("Hiểm hoạ 7 ngày tới") == 1
    assert ts.summary.startswith("Hiểm hoạ 7 ngày tới: còn 1 mối cần theo dõi — lũ từ thượng nguồn (cảnh báo).")
    assert "Trong 5 hiểm hoạ thời tiết: cần để ý — " in ts.summary

