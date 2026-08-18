"""S04 Twin Genome — tìm vùng có 'bộ gen' đất đai giống nhau.

Chạy offline: giả lập một Việt Nam thu nhỏ gồm ba kiểu địa lý (đồng bằng ven
biển, cao nguyên Nam, núi cao Bắc) rồi kiểm tra thuật toán xếp đúng nhóm.
"""
from __future__ import annotations

import math

import pytest

from app.services import cache_store, genome, realdata

# Ba cụm địa lý giả lập, mỗi cụm vài điểm.
#            (lat,   lon,    elev, rain, dry%, tmax, range)
_WORLD = {
    # Đồng bằng ven biển Nam — thấp, nóng đều, mưa nhiều
    (9.5, 105.5): (2.0, 2300, 10, 31.0, 4.0),
    (9.5, 106.2): (3.0, 2200, 11, 31.2, 4.2),
    (10.2, 105.5): (5.0, 2100, 10, 30.8, 4.5),
    # Cao nguyên Nam — cao vừa, mát, biên độ nhỏ
    (12.0, 108.0): (900.0, 1600, 11, 26.0, 5.5),
    (12.7, 108.0): (1000.0, 1500, 10, 25.5, 5.2),
    # Núi cao Bắc — cao, lạnh, biên độ LỚN (đặc trưng phân biệt Bắc/Nam)
    (22.0, 104.0): (1400.0, 1700, 16, 21.0, 11.0),
    (22.7, 104.0): (1500.0, 1600, 17, 20.5, 11.5),
}


@pytest.fixture
def fake_vietnam(monkeypatch, tmp_path):
    """Thay lưới thật bằng thế giới thu nhỏ, và dùng DB tạm cho cache."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app import db as dbmod

    engine = create_engine(f"sqlite:///{tmp_path/'g.db'}",
                           connect_args={"check_same_thread": False})
    dbmod.Base.metadata.create_all(engine)
    monkeypatch.setattr(dbmod, "engine", engine)
    monkeypatch.setattr(dbmod, "SessionLocal",
                        sessionmaker(bind=engine, autoflush=False,
                                     expire_on_commit=False))

    pts = list(_WORLD)
    monkeypatch.setattr(genome, "_grid", lambda: pts)
    monkeypatch.setattr(realdata, "elevation_m", lambda la, lo: _nearest(la, lo)[0])
    monkeypatch.setattr(realdata, "slope_deg", lambda la, lo, step_m=500.0: 1.0)
    monkeypatch.setattr(realdata, "elevation_multi",
                        lambda ps: [_nearest(la, lo)[0] for la, lo in ps])
    monkeypatch.setattr(realdata, "historical_weather_multi",
                        lambda ps, s, e: [_year(la, lo) for la, lo in ps])


def _nearest(lat, lon):
    return min(_WORLD.items(),
               key=lambda kv: (kv[0][0] - lat) ** 2 + (kv[0][1] - lon) ** 2)[1]


def _year(lat, lon):
    """Dựng một năm dữ liệu khớp với chỉ tiêu khí hậu của điểm gần nhất."""
    _, rain, dry_pct, tmax, trange = _nearest(lat, lon)
    dry_total = rain * dry_pct / 100.0
    wet_total = rain - dry_total
    dry_days = 31 + 31 + 28 + 31 + 30          # 12,1,2,3,4
    wet_days = 365 - dry_days
    rows = []
    for m in range(1, 13):
        days = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
        is_dry = m in genome._DRY_MONTHS
        per_day = (dry_total / dry_days) if is_dry else (wet_total / wet_days)
        # Nhiệt dao động theo mùa với biên độ đúng bằng `trange`
        t = tmax + (trange / 2.0) * math.cos((m - 7) / 12.0 * 2 * math.pi) * -1
        for d in range(days):
            rows.append({"day": 0, "date": f"2023-{m:02d}-{d+1:02d}",
                         "precip": per_day, "et0": 3.0, "tmax": round(t, 1)})
    return rows


# ---------- Dựng lưới tham chiếu ----------

def test_reference_keeps_only_land(fake_vietnam):
    ref = genome.build_reference(force=True)
    assert ref["land_cells"] == len(_WORLD)
    assert all(c["elev"] > 0 for c in ref["cells"])


def test_reference_is_cached(fake_vietnam):
    a = genome.build_reference(force=True)
    b = genome.build_reference()
    assert a["cached"] is False and b["cached"] is True


def test_climate_features_extracted_correctly(fake_vietnam):
    g = genome.genome_of(9.5, 105.5)
    assert g["rain_annual"] == pytest.approx(2300, rel=0.02)
    assert g["dry_share"] == pytest.approx(10, abs=1.5)
    assert g["tmax_range"] == pytest.approx(4.0, abs=0.6)


# ---------- Tìm song sinh ----------

def test_delta_matches_delta_not_mountain(fake_vietnam):
    genome.build_reference(force=True)
    r = genome.find_twins(9.5, 105.5, k=2)
    assert r["available"]
    for t in r["twins"]:
        assert t["genome"]["elev"] < 100, "đồng bằng không được khớp với núi"


def test_northern_mountain_prefers_northern_mountain(fake_vietnam):
    """Sa Pa và Đà Lạt cao gần bằng nhau — BIÊN ĐỘ NHIỆT mới phân biệt được."""
    genome.build_reference(force=True)
    top = genome.find_twins(22.0, 104.0, k=1)["twins"][0]
    assert top["genome"]["tmax_range"] > 8.0     # phải là núi Bắc, không phải cao nguyên Nam


def test_highland_matches_highland(fake_vietnam):
    genome.build_reference(force=True)
    top = genome.find_twins(12.0, 108.0, k=1)["twins"][0]
    assert 500 < top["genome"]["elev"] < 1300


def test_excludes_itself(fake_vietnam):
    """Ô chứa chính mình bị loại — 'song sinh với chính mình' là vô nghĩa."""
    genome.build_reference(force=True)
    for t in genome.find_twins(9.5, 105.5, k=5)["twins"]:
        assert t["distance_km"] > 1.0


def test_similarity_is_ordered_and_bounded(fake_vietnam):
    genome.build_reference(force=True)
    sims = [t["similarity_pct"] for t in genome.find_twins(9.5, 105.5, k=4)["twins"]]
    assert sims == sorted(sims, reverse=True)
    assert all(0 < s <= 100 for s in sims)


def test_k_is_clamped(fake_vietnam):
    genome.build_reference(force=True)
    assert len(genome.find_twins(9.5, 105.5, k=9999)["twins"]) <= 20


def test_comparison_covers_every_feature(fake_vietnam):
    genome.build_reference(force=True)
    comp = genome.find_twins(9.5, 105.5, k=1)["twins"][0]["comparison"]
    assert {c["feature"] for c in comp} == set(genome._FEATURES)
    assert all(c["label"] and c["unit"] is not None for c in comp)


def test_result_states_its_limits(fake_vietnam):
    """Kết quả trông thuyết phục nên PHẢI nói rõ giới hạn."""
    genome.build_reference(force=True)
    cav = genome.find_twins(9.5, 105.5, k=1)["caveat"]
    assert "MỘT năm" in cav and "VÙNG" in cav


# ---------- Log-hoá đặc trưng lệch ----------

def test_log_scaling_protects_lowland_differences():
    """HỒI QUY: z-score thẳng trên thang 0–3000 m khiến 6 m và 52 m gần như
    bằng nhau, nên Bến Tre từng khớp hạng 1 với một điểm cao 52 m."""
    stats = {f: {"mean": 0.0, "std": 1.0} for f in genome._FEATURES}
    base = {f: 0.0 for f in genome._FEATURES}

    lowland = {**base, "elev": 6.0}
    near = {**base, "elev": 12.0}      # cũng đồng bằng
    far = {**base, "elev": 52.0}       # gò cao, khác hẳn về ngập

    d_near = genome._distance(lowland, near, stats)
    d_far = genome._distance(lowland, far, stats)
    assert d_far > d_near * 2, "log-hoá phải giữ được khác biệt ở vùng thấp"


def test_log_scaling_compresses_mountain_range():
    """Ngược lại, 2000 m với 2100 m thì gần như không khác nhau."""
    stats = {f: {"mean": 0.0, "std": 1.0} for f in genome._FEATURES}
    base = {f: 0.0 for f in genome._FEATURES}
    a = genome._distance({**base, "elev": 2000.0}, {**base, "elev": 2100.0}, stats)
    b = genome._distance({**base, "elev": 6.0}, {**base, "elev": 106.0}, stats)
    assert b > a * 5


# ---------- Chia lô API (bug đã sửa) ----------

def test_multi_point_helpers_chunk_at_100(monkeypatch):
    """HỒI QUY: Open-Meteo chỉ nhận 100 toạ độ. Gửi 330 điểm một lần khiến API
    lỗi và TOÀN BỘ lô mất trắng — lưới genome từng trả về 0 ô đất liền."""
    calls = []

    def fake_get(url, timeout=None):
        n = url.split("latitude=")[1].split("&")[0].count(",") + 1
        calls.append(n)
        return {"elevation": [10.0] * n}

    monkeypatch.setattr(realdata, "_get", fake_get)
    out = realdata.elevation_multi([(10.0 + i * 0.01, 106.0) for i in range(250)])
    assert len(out) == 250
    assert calls == [100, 100, 50]
    assert all(v == 10.0 for v in out)
