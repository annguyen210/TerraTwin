"""Tìm địa danh theo tên cũ trước sáp nhập 1/7/2025 (góp ý dùng thử 7/11/2026: "Phú Khương, Bến Tre" → "Chưa tìm được").

Chạy OFFLINE: giả lập ba nguồn địa danh.
"""
import pytest

from app.services import place


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


def test_context_terms_bo_tien_to_va_map_tinh_moi():
    assert place._context_terms("Tỉnh Bến Tre") == ["ben tre", "vinh long"]
    assert place._context_terms("TP Châu Đốc") == ["chau doc"]
