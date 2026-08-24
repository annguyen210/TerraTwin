"""Tìm địa điểm theo tên — và cách nó hỏng khi dịch vụ ngoài không phản hồi.

Nominatim là dịch vụ cộng đồng miễn phí và ĐÃ bị chặn khi thử từ máy phát
triển. Vì vậy nhóm test này quan tâm tới đường HỎNG nhiều hơn đường chạy: một ô
tìm kiếm im lặng không ra kết quả là lỗi tệ hơn một ô báo rõ "đang bận, bấm
thẳng bản đồ nhé".
"""
from __future__ import annotations

from app.services import place


def test_qua_ngan_thi_khong_goi_mang(monkeypatch):
    goi = {"n": 0}
    monkeypatch.setattr(place, "_query", lambda q: goi.__setitem__("n", goi["n"] + 1))
    r = place.search("a")
    assert r["results"] == [] and goi["n"] == 0
    assert "hai ký tự" in r["message"]


def test_dich_vu_hong_thi_noi_ro_va_chi_duong_khac(monkeypatch):
    """Không được im lặng. Người dùng phải biết là dịch vụ hỏng, không phải
    là xã của họ không tồn tại."""
    monkeypatch.setattr(place, "_query", lambda q: None)
    r = place.search("Ba Tri")
    assert r["results"] == []
    assert "bản đồ" in r["message"], "phải chỉ sang cách vào khác"


def test_khong_tim_thay_khac_voi_dich_vu_hong(monkeypatch):
    """Hai tình huống này phải cho ra hai thông báo khác nhau."""
    monkeypatch.setattr(place, "_query", lambda q: [])
    r = place.search("xyzzy khong co that")
    assert "Không tìm thấy" in r["message"]

    monkeypatch.setattr(place, "_query", lambda q: None)
    r2 = place.search("xyzzy khong co that")
    assert r["message"] != r2["message"]


def test_bo_duoi_thua_trong_ten(monkeypatch):
    monkeypatch.setattr(place, "_query", lambda q: [{
        "lat": "10.0", "lon": "106.0", "addresstype": "village",
        "display_name": "Xã An Đức, Huyện Ba Tri, Tỉnh Bến Tre, "
                        "Đồng bằng sông Cửu Long, 86000, Việt Nam",
    }])
    r = place.search("An Duc")
    lab = r["results"][0]["label"]
    assert "Việt Nam" not in lab and "86000" not in lab
    assert lab.count(",") <= 2, f"tên quá dài để đọc trên một dòng: {lab}"


def test_bo_qua_ban_ghi_hong_thay_vi_do_ca_lo(monkeypatch):
    monkeypatch.setattr(place, "_query", lambda q: [
        {"lat": "khong-phai-so", "lon": "106.0", "display_name": "X"},
        {"lat": "10.0", "lon": "106.0", "display_name": "Xã Tốt, Huyện Y"},
    ])
    r = place.search("thu")
    assert len(r["results"]) == 1 and r["results"][0]["label"] == "Xã Tốt, Huyện Y"


def test_user_agent_thuan_ascii():
    """Header HTTP mã hoá latin-1 — một chữ có dấu là hỏng cả lời gọi, im lặng."""
    place.USER_AGENT.encode("latin-1")
    assert place.USER_AGENT.isascii()


def test_chi_tim_trong_viet_nam():
    import inspect
    src = inspect.getsource(place._query)
    assert '"countrycodes": "vn"' in src, "phải giới hạn Việt Nam"


def test_ton_trong_gioi_han_mot_lan_moi_giay():
    assert place._MIN_GAP >= 1.0, "Nominatim cho tối đa 1 lời gọi/giây"
