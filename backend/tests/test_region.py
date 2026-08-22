"""Toạ độ này là đất liền Việt Nam, mặt biển, hay nước khác?

BỐI CẢNH — lỗi thật đã sửa: kiểm tra phạm vi trước đây chỉ là một HÌNH CHỮ NHẬT
bao trọn Viêng Chăn, Phnom Penh, nam Trung Quốc và cả Biển Đông. Đo được:

    Giữa Biển Đông →  "Điểm an toàn đất: 70/100"
                      "Thiếu nước NGHIÊM TRỌNG 96,7%"
    Viêng Chăn     →  TerraScore 100/100, đánh giá đầy đủ

Trong khi README ghi "Toạ độ ngoài vùng bị từ chối". Lời đó sai, và một giám
khảo bấm thử là thấy ngay.
"""
from __future__ import annotations

import pytest

from app.services import realdata, region


def _elev(mapping, default=None):
    """Giả lập cao độ theo toạ độ tròn tới 2 chữ số."""
    def one(la, lo):
        return mapping.get((round(la, 2), round(lo, 2)), default)

    def multi(pts):
        return [one(la, lo) for la, lo in pts]

    return one, multi


@pytest.fixture
def no_country(monkeypatch):
    """Mặc định tắt tra cứu quốc gia — test biển/đất không được phụ thuộc mạng."""
    monkeypatch.setattr(region, "country_code", lambda la, lo: None)


# ---------------------------------------------------------------- đất/biển

def test_cao_do_duong_thi_la_dat_khoi_hoi_them(no_country, monkeypatch):
    """Gần như mọi truy vấn đi qua nhánh này, nên nó phải rẻ nhất."""
    called = {"ring": 0}
    one, _ = _elev({(10.24, 106.38): 5.0})
    monkeypatch.setattr(realdata, "elevation_m", one)
    monkeypatch.setattr(realdata, "elevation_multi",
                        lambda pts: called.__setitem__("ring", called["ring"] + 1) or [])

    r = region.classify(10.24, 106.38)
    assert r["kind"] == "land" and r["serviceable"] is True
    assert called["ring"] == 0, "cao độ > 0 thì không được gọi thêm vòng lấy mẫu"


def test_giua_bien_dong_bi_xep_la_mat_nuoc(no_country, monkeypatch):
    monkeypatch.setattr(realdata, "elevation_m", lambda la, lo: 0.0)
    monkeypatch.setattr(realdata, "elevation_multi",
                        lambda pts: [0.0] * len(pts))

    r = region.classify(14.0, 111.0)
    assert r["kind"] == "sea"
    assert r["serviceable"] is False
    assert "MẶT NƯỚC" in r["note"]


def test_can_gio_cao_do_0_nhung_van_la_DAT(no_country, monkeypatch):
    """Ca khó nhất, và là lý do không được dùng mỗi cao độ để phán.

    Cần Giờ là rừng ngập mặn TP.HCM — có dân, có vuông tôm — nhưng DEM đọc đúng
    0 m, y hệt mặt biển. Đo thực tế: 7/8 điểm quanh trong bán kính 5 km có cao
    độ > 0, còn điểm biển ngoài Vũng Tàu là 0/8.
    """
    monkeypatch.setattr(realdata, "elevation_m", lambda la, lo: 0.0)
    monkeypatch.setattr(realdata, "elevation_multi",
                        lambda pts: [3.0] * 7 + [0.0] * (len(pts) - 7))

    r = region.classify(10.52, 106.88)
    assert r["kind"] == "land"
    assert r["serviceable"] is True
    assert r["land_neighbours"] == 7


def test_bien_sat_bo_van_la_bien(no_country, monkeypatch):
    """Một điểm quanh có đất (bờ gần) KHÔNG đủ để gọi là đất liền."""
    monkeypatch.setattr(realdata, "elevation_m", lambda la, lo: 0.0)
    monkeypatch.setattr(realdata, "elevation_multi",
                        lambda pts: [278.0] + [0.0] * (len(pts) - 1))

    r = region.classify(12.24, 109.35)
    assert r["kind"] == "sea"
    assert r["land_neighbours"] == 1


def test_nguong_dat_bien_dung_o_hai_diem(no_country, monkeypatch):
    monkeypatch.setattr(realdata, "elevation_m", lambda la, lo: 0.0)
    for n_land, mong in ((1, "sea"), (2, "land"), (4, "land")):
        monkeypatch.setattr(
            realdata, "elevation_multi",
            lambda pts, k=n_land: [5.0] * k + [0.0] * (len(pts) - k))
        assert region.classify(10.0, 106.0)["kind"] == mong, n_land


def test_mat_du_lieu_cao_do_thi_KHONG_chan_ai(no_country, monkeypatch):
    """Fail-open: nguồn cao độ chết không được biến thành cấm cửa người dùng."""
    monkeypatch.setattr(realdata, "elevation_m", lambda la, lo: None)

    r = region.classify(10.24, 106.38)
    assert r["kind"] == "unknown"
    assert r["serviceable"] is True


# ---------------------------------------------------------------- quốc gia

def test_dat_o_nuoc_khac_bi_tu_choi(monkeypatch):
    monkeypatch.setattr(realdata, "elevation_m", lambda la, lo: 174.0)
    monkeypatch.setattr(region, "country_code", lambda la, lo: "la")

    r = region.classify(17.97, 102.60)
    assert r["kind"] == "foreign"
    assert r["serviceable"] is False
    assert "LA" in r["note"]


def test_khong_tra_duoc_quoc_gia_thi_VAN_phuc_vu(monkeypatch):
    """Fail-open lần hai, và lần này quan trọng hơn.

    Nominatim là dịch vụ ngoài. Nó bảo trì mà ta chặn theo thì cả nước không
    dùng được phần mềm — thà cho một toạ độ ngoài biên lọt qua.
    """
    monkeypatch.setattr(realdata, "elevation_m", lambda la, lo: 5.0)
    monkeypatch.setattr(region, "country_code", lambda la, lo: None)

    r = region.classify(10.24, 106.38)
    assert r["kind"] == "land"
    assert r["serviceable"] is True
    assert r["in_vietnam"] is None
    assert "bảo trì" in r["note"]


def test_user_agent_thuan_ascii():
    """Header HTTP mã hoá latin-1 — đã dính lỗi này một lần ở Overpass."""
    region.USER_AGENT.encode("latin-1")


# ---------------------------------------------------------------- hộp toạ độ

def test_hop_toa_do_khong_con_tu_choi_truong_sa():
    """Mốc cũ 112,5 khiến Trường Sa bị từ chối kèm câu "ngoài lãnh thổ Việt Nam".

    Phần mềm không nên tự phát ngôn về chủ quyền, và càng không nên phát ngôn
    sai. Nay toạ độ đó đi qua cửa rồi được trả lời trung thực là mặt nước.
    """
    from app.schemas import Location

    Location(lat=11.43, lon=114.33)      # Song Tử Tây
    Location(lat=16.50, lon=112.00)      # Hoàng Sa


def test_hop_toa_do_van_chan_rac():
    from app.schemas import Location

    for la, lo in ((0.0, 0.0), (48.85, 2.35), (7.5, 130.0), (60.0, 105.0)):
        with pytest.raises(Exception):
            Location(lat=la, lon=lo)


def test_thong_bao_hop_toa_do_khong_noi_ve_chu_quyen():
    from app.schemas import Location

    try:
        Location(lat=11.43, lon=125.0)
    except Exception as e:
        assert "lãnh thổ" not in str(e)


# ---------------------------------------------------------------- endpoint

@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app
    return TestClient(app)


def test_endpoint_khong_cham_diem_mat_nuoc(client, monkeypatch):
    """Chốt chặn cho "Thiếu nước NGHIÊM TRỌNG 96,7%" giữa đại dương."""
    monkeypatch.setattr(region, "classify", lambda la, lo, check_country=True: {
        "kind": "sea", "serviceable": False, "elevation_m": 0.0,
        "note": "Điểm này là MẶT NƯỚC.", "country": None, "in_vietnam": None})

    d = client.post("/api/assess/land_risk", json={"lat": 14.0, "lon": 111.0}).json()
    assert d["status"] == "out_of_scope"
    assert d["risk_level"] == "unknown"
    assert "mặt nước" in d["headline"].lower()

    t = client.post("/api/terrascore", json={"lat": 14.0, "lon": 111.0}).json()
    assert t["score"] == 0 and t["grade"] == "—"

    s = client.post("/api/scan", json={"lat": 14.0, "lon": 111.0}).json()
    assert s["modules"] == [] and s["alerts"] == []
    assert s["region"]["kind"] == "sea"


def test_endpoint_van_chay_binh_thuong_tren_dat(client, monkeypatch):
    monkeypatch.setattr(region, "classify", lambda la, lo, check_country=True: {
        "kind": "land", "serviceable": True, "elevation_m": 5.0,
        "note": None, "country": "vn", "in_vietnam": True})

    d = client.post("/api/assess/land_risk",
                    json={"lat": 10.24, "lon": 106.38}).json()
    assert d["status"] == "ok"
