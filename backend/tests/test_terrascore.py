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
