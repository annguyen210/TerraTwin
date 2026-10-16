"""TerraScore chỉ tính hiểm họa có dữ liệu THẬT (loại mock/ước lượng)."""
from app.schemas import Assessment, Location
from app.services import terrascore


def _a(mid, risk, is_real):
    return Assessment(
        module_id=mid, module_name=mid, location=Location(lat=10, lon=106),
        status="ok", risk_level=risk, headline="", detail="", recommendation="",
        is_real=is_real,
    )


def test_mock_hazard_does_not_penalize():
    loc = Location(lat=10, lon=106)
    # salinity mock ở mức 'danger' KHÔNG được trừ điểm; các hiểm họa thật đều 'safe'.
    assessments = {
        "salinity": _a("salinity", "danger", is_real=False),
        "drought": _a("drought", "safe", is_real=True),
        "flood": _a("flood", "safe", is_real=True),
        "landslide": _a("landslide", "safe", is_real=True),
        "wildfire": _a("wildfire", "safe", is_real=True),
    }
    r = terrascore.compute(loc, assessments=assessments)
    assert r.score == 100 and r.grade == "A"
    assert "salinity" not in r.breakdown           # mock bị loại khỏi điểm
    assert r.real_data_ratio == 0.8                # 4/5 hiểm họa thật


def test_real_danger_penalizes():
    loc = Location(lat=10, lon=106)
    assessments = {
        "salinity": _a("salinity", "safe", is_real=False),
        "drought": _a("drought", "safe", is_real=True),
        "flood": _a("flood", "danger", is_real=True),
        "landslide": _a("landslide", "warning", is_real=True),
        "wildfire": _a("wildfire", "safe", is_real=True),
    }
    r = terrascore.compute(loc, assessments=assessments)
    assert r.score == 100 - 22 - 11                # flood danger + landslide warning
    assert r.breakdown["flood"] == 22


def test_no_real_data_no_fake_score():
    loc = Location(lat=10, lon=106)
    assessments = {h: _a(h, "safe", is_real=False)
                   for h in ["salinity", "drought", "flood", "landslide", "wildfire"]}
    r = terrascore.compute(loc, assessments=assessments)
    assert r.grade == "—" and r.real_data_ratio == 0.0


def test_hai_con_so_noi_ro_pham_vi_khong_cung_goi_la_an_toan(monkeypatch):
    """Kiểm toàn bộ 16/10/2026, việc 2: cùng toạ độ, TerraScore 100 "Đất an toàn" cạnh "Điểm an toàn đất 49/100".
    TerraScore = hiểm hoạ thiên tai 7 ngày tới; land_risk = nền đất khi mua, cố định theo địa hình."""
    loc = Location(lat=15.8712, lon=108.3381)
    safe = {h: _a(h, "safe", is_real=True) for h in ["salinity", "drought", "flood", "landslide", "wildfire"]}
    r = terrascore.compute(loc, assessments=safe)
    assert r.score == 100 and "an toàn" not in r.summary.lower() and "7 ngày" in r.summary
    assert "7 ngày" in r.scope and "nền đất khi mua" in r.scope

    from app.modules import group_b
    from app.services import datasources as ds
    monkeypatch.setattr(ds, "elevation_proxy", lambda la, lo: 1.0)
    monkeypatch.setattr(ds, "slope_context", lambda la, lo: (0.5, True))
    monkeypatch.setattr(ds, "distance_to_coast_km", lambda la, lo: 4.0)
    calls = {"rain": 0}
    monkeypatch.setattr(ds, "forecast_precip_7d_total", lambda la, lo: calls.__setitem__("rain", calls["rain"] + 1) or (300.0, True))
    a = group_b.LandRiskModule().assess(loc)
    assert a.headline.startswith("Điểm nền đất khi mua:") and "cố định" in a.headline and "Phạm vi" in a.detail
    assert calls["rain"] == 0, "điểm nền đất khi mua không được đổi theo mưa dự báo tuần này"
    assert a.score == 52                      # 100 − trũng 28,8 − dốc 0,6 − gần biển 18,4
