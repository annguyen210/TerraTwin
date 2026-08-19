"""Hạ tầng chạy song song (nguyên lý 02) và ba mũi nhọn nhóm D.

Phần song song test bằng việc GIẢ LẬP CÓ ĐỘ TRỄ: nếu mã chạy nối tiếp thì tổng
thời gian cộng dồn, chạy song song thì xấp xỉ thời gian việc lâu nhất. Đo thời
gian trong test thường mong manh, nên biên ở đây đặt rất rộng — mục tiêu là bắt
được "ai đó vô tình bỏ song song đi", không phải đo hiệu năng chính xác.

Phần nhóm D giả lập ở tầng `osm._query` (JSON Overpass thô) chứ không giả lập
`built_environment`, để mã tính diện tích đa giác, tách đường xe khỏi lối đi bộ
và chấm độ đầy đủ dữ liệu đều được chạy thật.
"""
from __future__ import annotations

import threading
import time

import pytest

from app.schemas import Location
from app.services import jobs, osm


# ================================================================ song song

def test_gather_chay_song_song_chu_khong_noi_tiep():
    def mk(_i):
        return lambda: (time.sleep(0.25), True)[1]

    t0 = time.time()
    r = jobs.gather([mk(i) for i in range(8)], limit=8)
    dt = time.time() - t0
    assert all(r)
    # Nối tiếp sẽ là ~2,0 s. Biên 1,0 s rất rộng nhưng vẫn bắt được hồi quy.
    assert dt < 1.0, f"có vẻ đang chạy nối tiếp: {dt:.2f}s"


def test_gather_giu_dung_thu_tu_ket_qua():
    def mk(i):
        # Việc sau cố tình xong TRƯỚC việc trước.
        return lambda: (time.sleep(0.2 - i * 0.03), i)[1]

    assert jobs.gather([mk(i) for i in range(6)], limit=6) == [0, 1, 2, 3, 4, 5]


def test_mot_viec_hong_khong_keo_do_ca_me():
    def boom():
        raise RuntimeError("hỏng có chủ đích")

    r = jobs.gather([lambda: 1, boom, lambda: 3])
    assert r == [1, None, 3]


def test_gather_rong_khong_no():
    assert jobs.gather([]) == []


def test_single_flight_gop_loi_goi_trung():
    calls = {"n": 0}

    def slow():
        calls["n"] += 1
        time.sleep(0.3)
        return "X"

    out = []
    ts = [threading.Thread(target=lambda: out.append(
        jobs.single_flight("test-key", slow))) for _ in range(6)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()

    assert calls["n"] == 1, "phải chỉ chạy MỘT lần cho 6 lời gọi trùng"
    assert out == ["X"] * 6


def test_single_flight_nem_loi_cho_moi_nguoi_cho():
    """Người chờ không được nhận âm thầm None trong khi thực tế là lỗi."""
    def boom():
        time.sleep(0.1)
        raise ValueError("hỏng")

    errs = []

    def call():
        try:
            jobs.single_flight("key-loi", boom)
        except Exception as e:
            errs.append(type(e).__name__)

    ts = [threading.Thread(target=call) for _ in range(3)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert errs == ["ValueError"] * 3


def test_single_flight_khong_ket_dinh_key_sau_khi_loi():
    """Lỗi xong phải dọn key, không thì key đó hỏng vĩnh viễn."""
    def boom():
        raise ValueError("x")

    with pytest.raises(ValueError):
        jobs.single_flight("key-don-dep", boom)
    # Lần sau cùng key đó phải chạy lại được bình thường.
    assert jobs.single_flight("key-don-dep", lambda: 42) == 42


def test_hang_doi_viec_chay_va_tra_ket_qua():
    jid = jobs.submit("test", lambda: (time.sleep(0.2), {"ok": True})[1], "thử")
    assert jobs.status(jid)["state"] in ("queued", "running")
    for _ in range(60):
        st = jobs.status(jid)
        if st["state"] == "done":
            break
        time.sleep(0.1)
    assert st["state"] == "done"
    assert st["result"] == {"ok": True}


def test_viec_hong_bao_loi_chu_khong_lo_chi_tiet_noi_bo():
    def boom():
        raise RuntimeError("/duong/dan/noi/bo/bi/mat.db")

    jid = jobs.submit("test", boom)
    for _ in range(60):
        st = jobs.status(jid)
        if st["state"] == "error":
            break
        time.sleep(0.1)
    assert st["state"] == "error"
    assert st["error"] == "RuntimeError"
    assert "/duong/dan" not in repr(st), "không được lộ chi tiết nội bộ ra API"


def test_ma_viec_khong_ton_tai_tra_none():
    assert jobs.status("khong-co-ma-nay") is None


def test_tran_goi_ra_ngoai_co_gioi_han():
    st = jobs.stats()
    assert st["upstream_concurrency_limit"] >= 1
    assert st["workers"] >= 1


def test_scan_va_chunk_deu_dung_gather():
    """Chốt chặn: không ai được lặng lẽ đưa vòng lặp nối tiếp trở lại."""
    from pathlib import Path
    app = Path(__file__).resolve().parent.parent / "app"
    assert "jobs.gather" in (app / "services" / "scan.py").read_text(encoding="utf-8")
    rd = (app / "services" / "realdata.py").read_text(encoding="utf-8")
    assert "_parallel_chunks" in rd
    assert "jobs.gather" in rd


# ================================================================ nhóm D

def _way(tags, geom):
    return {"type": "way", "tags": tags, "geometry": geom}


def _square(lat, lon, side_m):
    d = side_m / 111_320.0
    return [{"lat": lat, "lon": lon}, {"lat": lat + d, "lon": lon},
            {"lat": lat + d, "lon": lon + d}, {"lat": lat, "lon": lon + d},
            {"lat": lat, "lon": lon}]


@pytest.fixture
def fake_osm(monkeypatch):
    """Thay tầng HTTP của Overpass. Trả về hàm để mỗi test tự nạp dữ liệu."""
    box = {"elements": []}

    def _q(q):
        return dict(box)

    monkeypatch.setattr(osm, "_query", _q)
    return box


def test_osm_user_agent_phai_thuan_ascii():
    """Header HTTP mã hoá latin-1 — một chữ có dấu là hỏng cả lời gọi.

    Đã dính đúng lỗi này: User-Agent tiếng Việt làm mọi truy vấn OSM ném
    UnicodeEncodeError và im lặng trả None.
    """
    osm.USER_AGENT.encode("latin-1")


def test_osm_co_may_chu_du_phong():
    assert len(osm.ENDPOINTS) >= 2


def test_tach_duong_xe_khoi_loi_di_bo(fake_osm):
    fake_osm["elements"] = [
        _way({"highway": "residential"}, [{"lat": 10.0, "lon": 106.0},
                                          {"lat": 10.009, "lon": 106.0}]),
        _way({"highway": "footway"}, [{"lat": 10.0, "lon": 106.0},
                                      {"lat": 10.009, "lon": 106.0}]),
    ]
    env = osm.built_environment(10.0, 106.0, radius_m=1000.0)
    assert env["road_km"] == pytest.approx(1.0, abs=0.1)
    assert env["path_km"] == pytest.approx(1.0, abs=0.1)


def test_khong_co_nha_thi_khong_bao_gio_la_du_lieu_tot(fake_osm):
    """Nghịch lý đã gặp: 0 nhà nhưng 20 km đường vẫn bị xếp 'đầy đủ'.

    0 nhà chính là bằng chứng rõ nhất rằng chưa ai vẽ, nên không được để người
    đọc hiểu là thực địa trống.
    """
    fake_osm["elements"] = [
        _way({"highway": "primary"}, [{"lat": 10.0 + i * 0.002, "lon": 106.0},
                                      {"lat": 10.0 + (i + 1) * 0.002, "lon": 106.0}])
        for i in range(120)
    ]
    env = osm.built_environment(10.0, 106.0, radius_m=1000.0)
    assert env["buildings"] == 0
    assert env["completeness"] == "thưa"
    assert "CHƯA AI VẼ" in env["completeness_note"]


def test_dem_nha_va_dien_tich(fake_osm):
    fake_osm["elements"] = [_way({"building": "yes"}, _square(10.0, 106.0, 20))
                            for _ in range(50)]
    env = osm.built_environment(10.0, 106.0, radius_m=1000.0)
    assert env["buildings"] == 50
    assert env["building_area_m2"] > 0
    assert env["completeness"] == "vừa"


def test_overpass_hong_thi_tra_none(monkeypatch):
    monkeypatch.setattr(osm, "_query", lambda q: None)
    assert osm.built_environment(10.0, 106.0) is None
    assert osm.nearest(10.0, 106.0, '["landuse"="quarry"]') is None


# ---------------------------------------------------------------- URB-09

def test_duong_cong_dong_chay_scs():
    from app.modules.group_d import CN_IMPERVIOUS, CN_PERVIOUS, _runoff_mm

    # Bê tông cho dòng chảy lớn hơn hẳn đất thấm với cùng lượng mưa.
    assert _runoff_mm(100.0, CN_IMPERVIOUS) > _runoff_mm(100.0, CN_PERVIOUS)
    # Mưa nhỏ hơn lượng thấm ban đầu thì KHÔNG chảy tràn.
    assert _runoff_mm(2.0, CN_PERVIOUS) == 0.0
    assert _runoff_mm(0.0, CN_IMPERVIOUS) == 0.0
    # Đơn điệu tăng theo lượng mưa.
    assert _runoff_mm(50.0, 90.0) < _runoff_mm(150.0, 90.0)


def test_urban_do_duoc_be_tong_hoa(fake_osm, monkeypatch):
    from app.modules.registry import get_module
    from app.services import datasources as ds

    fake_osm["elements"] = [_way({"building": "yes"}, _square(10.0, 106.0, 60))
                            for _ in range(300)]
    monkeypatch.setattr(ds, "forecast_precip_7d_total", lambda la, lo: (120.0, True))
    monkeypatch.setattr(ds, "elevation_proxy", lambda la, lo: 2.0)

    a = get_module("urban").assess(Location(lat=10.0, lon=106.0))
    assert a.status == "ok" and a.is_real is True
    assert a.metrics["be_tong_hoa_pct"] > 0
    # Bê tông hoá phải làm dòng chảy LỚN HƠN nền tự nhiên.
    assert a.metrics["chay_tran_mm"] > a.metrics["chay_tran_tu_nhien_mm"]
    assert "SCS Curve Number" in a.detail


def test_urban_khong_co_osm_thi_noi_that(monkeypatch):
    from app.modules.registry import get_module

    monkeypatch.setattr(osm, "_query", lambda q: None)
    a = get_module("urban").assess(Location(lat=10.0, lon=106.0))
    assert a.status == "need_data"
    assert a.risk_level == "unknown"


# ---------------------------------------------------------------- INF-11

def test_mining_khong_co_mo_gan_thi_khong_bao_dong(monkeypatch):
    from app.modules.registry import get_module
    from app.services import datasources as ds

    monkeypatch.setattr(osm, "nearest", lambda *a, **k: [])
    monkeypatch.setattr(ds, "slope_context", lambda la, lo: (0.5, True))
    monkeypatch.setattr(ds, "forecast_precip_7d_total", lambda la, lo: (10.0, True))
    monkeypatch.setattr(ds, "elevation_proxy", lambda la, lo: 5.0)

    a = get_module("mining").assess(Location(lat=10.0, lon=106.0))
    assert a.risk_level == "safe"
    assert "Không thấy mỏ" in a.headline


def test_mining_doc_lon_mua_lon_gan_mo_thi_bao_dong(monkeypatch):
    from app.modules.registry import get_module
    from app.services import datasources as ds

    monkeypatch.setattr(osm, "nearest", lambda *a, **k: [
        {"lat": 21.0, "lon": 107.3, "km": 1.5, "name": "Mỏ thử", "tags": {}}])
    monkeypatch.setattr(ds, "slope_context", lambda la, lo: (18.0, True))
    monkeypatch.setattr(ds, "forecast_precip_7d_total", lambda la, lo: (400.0, True))
    monkeypatch.setattr(ds, "elevation_proxy", lambda la, lo: 120.0)

    a = get_module("mining").assess(Location(lat=21.0, lon=107.29))
    assert a.risk_level == "danger"
    assert "Mỏ thử" in a.headline


def test_mining_overpass_hong_thi_noi_that(monkeypatch):
    from app.modules.registry import get_module

    monkeypatch.setattr(osm, "nearest", lambda *a, **k: None)
    a = get_module("mining").assess(Location(lat=10.0, lon=106.0))
    assert a.status == "need_data"


# ---------------------------------------------------------------- SUP-12

def test_supply_chain_dem_ty_le_vung_rui_ro(monkeypatch):
    from app.modules.registry import get_module
    from app.services import hazard, realdata

    rows = [{"day": i, "date": f"2026-08-{19 + i:02d}", "precip": 90.0,
             "et0": 3.0, "tmax": 33.0} for i in range(7)]
    monkeypatch.setattr(realdata, "weather_multi", lambda pts: [rows] * len(pts))

    # Điều kiện XÁC ĐỊNH theo toạ độ, không dùng biến đếm dùng chung: các điểm
    # được chấm SONG SONG nên một biến đếm cho kết quả khác nhau mỗi lần chạy —
    # đúng loại test chập chờn mà chính bản test đầu tiên của tệp này đã mắc.
    # Lưới 5×5 quanh vĩ độ 10,0 ⇒ 15/25 điểm có la >= 10,0 ⇒ đúng 60%.
    def fake_series(mid, la, lo, r):
        risky = (mid == "flood") and la >= 10.0
        return [(0, "2026-08-19", 80.0 if risky else 10.0)], True

    monkeypatch.setattr(hazard, "index_series_calibrated", fake_series)
    monkeypatch.setattr(osm, "nearest", lambda *a, **k: None)

    a = get_module("supply_chain").assess(Location(lat=10.0, lon=106.0))
    assert a.status == "ok" and a.is_real is True
    assert a.metrics["diem_kiem_tra"] == 25
    assert a.metrics["ty_le_rui_ro_pct"] == 60.0
    assert a.metrics["diem_canh_bao_lu"] == 15
    assert a.metrics["diem_canh_bao_han"] == 0
    assert a.risk_level == "danger"


def test_supply_chain_khong_co_thoi_tiet_thi_noi_that(monkeypatch):
    from app.modules.registry import get_module
    from app.services import realdata

    monkeypatch.setattr(realdata, "weather_multi", lambda pts: [None] * len(pts))
    a = get_module("supply_chain").assess(Location(lat=10.0, lon=106.0))
    assert a.status == "need_data"


# ---------------------------------------------------------------- truy xuất

def test_truy_xuat_tra_ho_so_co_ma_bam(monkeypatch):
    from app.modules.group_d import provenance
    from app.services import realdata

    rows = [{"day": i, "date": f"2025-11-{i + 1:02d}", "precip": 5.0 * (i % 4),
             "et0": 3.0, "tmax": 31.0 + (i % 3)} for i in range(30)]
    monkeypatch.setattr(realdata, "historical_weather_multi",
                        lambda pts, s, e: [rows])

    r = provenance(Location(lat=10.24, lon=106.38), "2025-11-01", "2025-11-30",
                   "Gạo ST25", "HTX thử")
    assert r["available"] is True
    assert r["measured"]["rain_total_mm"] > 0
    assert len(r["integrity"]["hash"]) == 64
    # Phải nói rõ hồ sơ KHÔNG chứng minh nguồn gốc vật lý.
    assert "KHÔNG chứng minh" in r["scope"]


def test_truy_xuat_doi_ma_bam_khi_so_lieu_doi(monkeypatch):
    from app.modules.group_d import provenance
    from app.services import realdata

    def rows(mm):
        return [{"day": i, "date": f"2025-11-{i + 1:02d}", "precip": mm,
                 "et0": 3.0, "tmax": 31.0} for i in range(30)]

    monkeypatch.setattr(realdata, "historical_weather_multi",
                        lambda pts, s, e: [rows(5.0)])
    h1 = provenance(Location(lat=10.24, lon=106.38), "2025-11-01",
                    "2025-11-30")["integrity"]["hash"]
    monkeypatch.setattr(realdata, "historical_weather_multi",
                        lambda pts, s, e: [rows(6.0)])
    h2 = provenance(Location(lat=10.24, lon=106.38), "2025-11-01",
                    "2025-11-30")["integrity"]["hash"]
    assert h1 != h2, "sửa số liệu mà mã băm không đổi thì mã băm vô dụng"


def test_truy_xuat_tu_choi_khoang_thoi_gian_vo_ly():
    from app.modules.group_d import provenance

    loc = Location(lat=10.24, lon=106.38)
    assert provenance(loc, "khong-phai-ngay", "2025-11-30")["available"] is False
    assert provenance(loc, "2025-11-30", "2025-11-01")["available"] is False
    # ERA5 công bố chậm ~5–7 ngày: xin dữ liệu hôm nay là phải từ chối.
    from datetime import date
    assert provenance(loc, "2026-01-01",
                      date.today().isoformat())["available"] is False


# ---------------------------------------------------------------- 12 ngành

def test_phu_du_12_nganh():
    """Bản thiết kế hứa 12 ngành. Test này giữ lời hứa đó."""
    from app.modules.registry import list_modules

    ids = {m.id for m in list_modules()}
    can_thiet = {
        "salinity", "drought", "pest", "yield",        # AGR-01
        "carbon", "wildfire",                          # FOR-02
        "flood",                                       # ENV-03 / DIS-05
        "land_risk",                                   # RES-04
        "storm_damage", "landslide",                   # DIS-05
        "parametric_insurance",                        # INS-06
        "solar",                                       # ENG-08
        "urban",                                       # URB-09
        "aquaculture",                                 # AQU-10
        "mining",                                      # INF-11
        "supply_chain",                                # SUP-12
    }
    thieu = can_thiet - ids
    assert not thieu, f"thiếu mũi nhọn cho ngành: {thieu}"


def test_moi_mui_nhon_deu_khai_bao_day_du():
    from app.modules.registry import list_modules

    for m in list_modules():
        assert m.name and m.icon and m.group
        assert m.data_sources, f"{m.id} không khai nguồn dữ liệu"
        assert m.users, f"{m.id} không khai ai dùng"
        assert m.description, f"{m.id} không có mô tả"
