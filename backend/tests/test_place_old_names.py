"""Tìm địa danh theo tên cũ trước sáp nhập 1/7/2025 (góp ý dùng thử 7/11/2026: "Phú Khương, Bến Tre" → "Chưa tìm được").

Chạy OFFLINE: giả lập ba nguồn địa danh.
"""
import pytest

from app.services import place

_REAL_NOMINATIM = place._from_nominatim      # fixture `nguon` thay hàm này; giữ bản thật cho test lọc POI


@pytest.fixture
def nguon(monkeypatch):
    by_q = {
        "Phú Khương": {
            "om": [{"label": "Phú Khương · Huyện Hòa Thành · Tay Ninh", "lat": 11.3, "lon": 106.1, "kind": "", "source": "open-meteo"}],
            "ph": [{"label": "Phường Phú Khương · Vĩnh Long Province", "lat": 10.25, "lon": 106.38, "kind": "suburb", "source": "photon"},
                   {"label": "Phú Khương · Xã Ân Tường · Gia Lai province", "lat": 14.3, "lon": 108.9, "kind": "village", "source": "photon"}],
        },
    }
    om = lambda q: by_q.get(q, {}).get("om", [])        # noqa: E731
    ph = lambda q: by_q.get(q, {}).get("ph", [])        # noqa: E731
    nom = lambda q: []                                   # noqa: E731
    monkeypatch.setattr(place, "_from_open_meteo", om)
    monkeypatch.setattr(place, "_from_photon", ph)
    monkeypatch.setattr(place, "_from_nominatim", nom)
    monkeypatch.setattr(place, "_SOURCES", (om, ph, nom))     # vòng tìm chính giữ tham chiếu hàm gốc
    monkeypatch.setattr(place.cache_store, "get", lambda k: None)
    monkeypatch.setattr(place.cache_store, "put", lambda *a, **k: None)


def test_ten_tinh_cu_tim_ra_phuong_o_tinh_moi(nguon):
    r = place.search("Phú Khương, Bến Tre")
    assert [x["label"] for x in r["results"]] == ["Phường Phú Khương · Vĩnh Long Province"]


def test_khong_dau_cung_tim_duoc(nguon):
    r = place.search("Phú Khương, ben tre")
    assert r["results"] and "Vĩnh Long" in r["results"][0]["label"]


def test_noi_sau_dau_phay_khong_khop_thi_dua_moi_noi_trung_ten(nguon):
    r = place.search("Phú Khương, Hà Nội")
    assert len(r["results"]) == 3 and "chọn đúng nơi" in r["message"]


def test_chi_nominatim_biet_ten_thi_van_tim_ra(nguon, monkeypatch):
    """Review Qodo PR #7: hai nguồn nhanh không có "Tên" → phải hỏi Nominatim theo tên rồi mới lọc theo nơi."""
    calls = []

    def nom(q):
        calls.append(q)
        if q == "Phú Mỹ":
            return [{"label": "Phú Mỹ · Huyện Mỏ Cày Nam · Tỉnh Vĩnh Long", "lat": 10.1, "lon": 106.3,
                     "kind": "village", "source": "nominatim"},
                    {"label": "Phú Mỹ · Thị xã Phú Mỹ · Hồ Chí Minh", "lat": 10.6, "lon": 107.0,
                     "kind": "town", "source": "nominatim"}]
        return []                     # câu đầy đủ "Phú Mỹ, Bến Tre": chỉ có POI, đã bị lọc
    monkeypatch.setattr(place, "_from_nominatim", nom)
    monkeypatch.setattr(place, "_SOURCES", (place._from_open_meteo, place._from_photon, nom))
    r = place.search("Phú Mỹ, Bến Tre")
    assert [x["label"] for x in r["results"]] == ["Phú Mỹ · Huyện Mỏ Cày Nam · Tỉnh Vĩnh Long"]
    assert calls == ["Phú Mỹ, Bến Tre", "Phú Mỹ"]


def test_nguon_nhanh_da_khop_thi_khong_hoi_nominatim_theo_ten(nguon, monkeypatch):
    calls = []
    nom = lambda q: calls.append(q) or []        # noqa: E731
    monkeypatch.setattr(place, "_from_nominatim", nom)
    monkeypatch.setattr(place, "_SOURCES", (place._from_open_meteo, place._from_photon, nom))
    place.search("Phú Khương, Bến Tre")
    assert calls == ["Phú Khương, Bến Tre"]      # chỉ câu đầy đủ; tên riêng đã khớp ở Photon


def test_khop_nguyen_tu_khong_khop_chuoi_con():
    """"Quận 1" không được khớp "Quận 11" (góp ý review PR #5)."""
    assert place._matches_component("1", "Bến Thành · Quận 1 · Hồ Chí Minh")
    assert not place._matches_component("1", "Phường 2 · Quận 11 · Hồ Chí Minh")
    assert place._matches_component("vinh long", "Phường Phú Khương · Vĩnh Long Province")


def test_nominatim_co_nhan_khong_loi(monkeypatch):
    """8/11/2026: _from_nominatim gọi _label() chưa được định nghĩa → lỗi 500 trên Render (nơi Nominatim không bị chặn)."""
    sample = [{"lat": "10.24", "lon": "106.38", "name": "Phú Khương", "category": "boundary", "addresstype": "suburb",
               "address": {"suburb": "Phú Khương", "city": "Bến Tre", "state": "Vĩnh Long"}}]
    monkeypatch.setattr(place, "_get", lambda url, timeout=None: sample)
    out = place._from_nominatim("Phú Khương, Bến Tre")
    assert out[0]["label"] == "Phú Khương · Bến Tre · Vĩnh Long" and out[0]["source"] == "nominatim"


def test_nominatim_bo_cua_hang_ngan_hang(monkeypatch):
    """8/11/2026 production: "Phú Khương, Bến Tre" ra toàn ngân hàng ACB, cửa hàng Honda… — chỉ giữ địa danh/ranh hành chính."""
    sample = [
        {"lat": "10.244", "lon": "106.375", "name": "Ngân Hàng Á Châu - ACB CN Bến Tre", "category": "amenity",
         "addresstype": "amenity", "address": {"suburb": "Phường Phú Khương", "state": "Tỉnh Vĩnh Long"}},
        {"lat": "10.246", "lon": "106.374", "name": "Honda Huỳnh Thành 1", "category": "shop",
         "addresstype": "shop", "address": {"suburb": "Phường Phú Khương", "state": "Tỉnh Vĩnh Long"}},
        {"lat": "10.237", "lon": "106.381", "name": "Thành phố Bến Tre", "category": "historic",
         "addresstype": "historic", "address": {"suburb": "Phường An Hội", "state": "Tỉnh Vĩnh Long"}},
        {"lat": "10.245", "lon": "106.376", "name": "Phường Phú Khương", "category": "boundary",
         "addresstype": "suburb", "address": {"suburb": "Phường Phú Khương", "state": "Tỉnh Vĩnh Long"}},
    ]
    urls = []
    monkeypatch.setattr(place, "_get", lambda url, timeout=None: urls.append(url) or sample)
    out = place._from_nominatim("Phú Khương, Bến Tre")
    assert [x["label"] for x in out] == ["Phường Phú Khương · Tỉnh Vĩnh Long"]
    assert "featureType=settlement" in urls[0]


def test_nominatim_chi_co_cua_hang_thi_tim_theo_ten_va_noi(nguon, monkeypatch):
    """Nominatim chỉ trả POI → coi như rỗng, rơi xuống tìm "Tên" rồi lọc theo "Nơi" (cả tên tỉnh mới)."""
    poi = [{"lat": "10.244", "lon": "106.375", "name": "ACB Bến Tre", "category": "amenity", "addresstype": "amenity",
            "address": {"state": "Tỉnh Vĩnh Long"}}]
    monkeypatch.setattr(place, "_get", lambda url, timeout=None: poi)
    monkeypatch.setattr(place, "_MIN_GAP", 0)
    monkeypatch.setattr(place, "_SOURCES", (place._from_open_meteo, place._from_photon, _REAL_NOMINATIM))
    r = place.search("Phú Khương, Bến Tre")
    assert [x["label"] for x in r["results"]] == ["Phường Phú Khương · Vĩnh Long Province"]


def test_nominatim_nhieu_cap_van_giu_tinh():
    """Review #6: có nhiều cấp địa phương thì nhãn vẫn phải giữ TỈNH (phân biệt nơi trùng tên)."""
    it = {"name": "Phú Khương", "address": {"quarter": "Khu phố 3", "suburb": "Phú Khương", "city_district": "TP Bến Tre",
                                            "county": "Bến Tre", "city": "Bến Tre", "state": "Vĩnh Long"}}
    assert place._label(it) == "Phú Khương · Khu phố 3 · Vĩnh Long"


def test_context_terms_bo_tien_to_va_map_tinh_moi():
    assert place._context_terms("Tỉnh Bến Tre") == ["ben tre", "vinh long"]
    assert place._context_terms("TP Châu Đốc") == ["chau doc"]
