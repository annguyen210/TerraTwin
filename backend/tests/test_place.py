"""Tìm địa điểm — ba nguồn nối tiếp, và cách nó hỏng khi cả ba im lặng.

VÌ SAO CÓ BA NGUỒN. Bản đầu chỉ dùng Nominatim. Nó bị chặn hẳn từ máy phát
triển, nên ô tìm kiếm trả rỗng cho MỌI truy vấn — người dùng gõ tên xã của mình,
không ra gì, và kết luận phần mềm chỉ chạy được ở tám nơi trong danh sách chọn
nhanh. Họ kết luận đúng với thứ họ trải nghiệm.

Một dịch vụ cộng đồng miễn phí có thể chặn bất kỳ ai bất kỳ lúc nào. Cho đường
vào chính của sản phẩm phụ thuộc vào đúng một dịch vụ như thế là lỗi thiết kế,
không phải rủi ro vận hành.
"""
from __future__ import annotations

import pytest

from app.services import cache_store, place


@pytest.fixture(autouse=True)
def _cache_rieng(monkeypatch):
    kho: dict = {}
    monkeypatch.setattr(cache_store, "get", lambda k: kho.get(k))
    monkeypatch.setattr(cache_store, "put",
                        lambda k, v, ttl_seconds=None: kho.__setitem__(k, v))


def _nguon(monkeypatch, *ket_qua):
    """Thay cả ba nguồn bằng kết quả cho sẵn, theo đúng thứ tự ưu tiên."""
    monkeypatch.setattr(place, "_SOURCES",
                        tuple((lambda r: (lambda q: r))(r) for r in ket_qua))


def test_qua_ngan_thi_khong_goi_mang(monkeypatch):
    goi = {"n": 0}
    monkeypatch.setattr(place, "_SOURCES",
                        (lambda q: goi.__setitem__("n", goi["n"] + 1),))
    r = place.search("a")
    assert r["results"] == [] and goi["n"] == 0
    assert "hai ký tự" in r["message"]


def test_dung_o_nguon_dau_tien_co_ket_qua(monkeypatch):
    """Không gộp kết quả nhiều nguồn: chúng đặt tên khác nhau nên gộp lại sinh
    ra danh sách trùng lặp trông như lỗi."""
    a = [{"label": "A", "lat": 1.0, "lon": 2.0, "kind": "", "source": "mot"}]
    b = [{"label": "B", "lat": 3.0, "lon": 4.0, "kind": "", "source": "hai"}]
    _nguon(monkeypatch, a, b)
    r = place.search("Ba Tri")
    assert len(r["results"]) == 1 and r["results"][0]["label"] == "A"


def test_nguon_dau_hong_thi_chuyen_sang_nguon_sau(monkeypatch):
    b = [{"label": "B", "lat": 3.0, "lon": 4.0, "kind": "", "source": "hai"}]
    _nguon(monkeypatch, None, b)
    r = place.search("Tra Leng")
    assert r["results"] and r["results"][0]["label"] == "B"


def test_nguon_dau_rong_van_thu_nguon_sau(monkeypatch):
    """Rỗng KHÁC hỏng, nhưng cả hai đều phải để nguồn sau có cơ hội.

    Chính tình huống Trà Leng: Open-Meteo không có, Photon thì có.
    """
    b = [{"label": "Tra Leng", "lat": 15.2, "lon": 108.0, "kind": "town",
          "source": "photon"}]
    _nguon(monkeypatch, [], b)
    assert place.search("Tra Leng")["results"][0]["label"] == "Tra Leng"


def test_ca_ba_nguon_hong_thi_noi_ro_va_chi_duong_khac(monkeypatch):
    """Không được im lặng. Người dùng phải biết là dịch vụ hỏng, không phải là
    xã của họ không tồn tại."""
    _nguon(monkeypatch, None, None, None)
    r = place.search("Ba Tri")
    assert r["results"] == []
    assert "bản đồ" in r["message"] and "định vị" in r["message"]


def test_khong_tim_thay_khac_han_voi_dich_vu_hong(monkeypatch):
    _nguon(monkeypatch, [], [], [])
    khong_co = place.search("xyzzy khong ton tai")
    _nguon(monkeypatch, None, None, None)
    hong = place.search("xyzzy khong ton tai 2")
    assert "Không tìm thấy" in khong_co["message"]
    assert khong_co["message"] != hong["message"]


def test_khong_cache_ket_qua_rong(monkeypatch):
    """Cache 30 ngày một câu 'không tìm thấy' nghĩa là người dùng gõ đúng tên xã
    của mình vẫn bị từ chối suốt một tháng, không cách nào tự sửa."""
    _nguon(monkeypatch, [])
    place.search("Ba Tri")
    b = [{"label": "Ba Tri", "lat": 10.0, "lon": 106.0, "kind": "", "source": "x"}]
    _nguon(monkeypatch, b)
    assert place.search("Ba Tri")["results"], "ket qua rong khong duoc cache"


def test_photon_loc_bo_quan_an_nha_hat():
    """Không lọc thì truy vấn 'Ba Tri' trả về 'Bánh Bao Bến Tre' — đã gặp thật."""
    for xau in ("fast_food", "restaurant", "theatre", "cafe"):
        assert xau not in place._PHOTON_OK
    for tot in ("village", "town", "district", "administrative"):
        assert tot in place._PHOTON_OK


def test_chi_tim_trong_viet_nam():
    import inspect
    for fn in (place._from_open_meteo, place._from_photon, place._from_nominatim):
        src = inspect.getsource(fn)
        assert '"VN"' in src or '"vn"' in src, f"{fn.__name__} khong gioi han VN"


def test_user_agent_thuan_ascii():
    """Header HTTP mã hoá latin-1 — một chữ có dấu là hỏng cả lời gọi, im lặng."""
    place.USER_AGENT.encode("latin-1")
    assert place.USER_AGENT.isascii()


def test_ton_trong_gioi_han_mot_lan_moi_giay():
    assert place._MIN_GAP >= 1.0, "Nominatim cho toi da 1 loi goi/giay"


def test_moi_ket_qua_deu_du_truong_giao_dien_can(monkeypatch):
    b = [{"label": "X", "lat": 1.0, "lon": 2.0, "kind": "town", "source": "y"}]
    _nguon(monkeypatch, b)
    for it in place.search("X")["results"]:
        assert {"label", "lat", "lon", "kind"} <= set(it)
        assert isinstance(it["lat"], float) and isinstance(it["lon"], float)
