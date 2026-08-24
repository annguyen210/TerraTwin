"""Đối chứng ngưỡng chung vs hiệu chuẩn — và các cách nó có thể nói dối.

Khối này ra màn hình chính và là lý lẽ thuyết phục nhất của sản phẩm, nên nó
cũng là chỗ dễ gian nhất. Nhóm test cuối canh đúng việc đó: hằng số phải đo
được lại, và phải nêu cả trường hợp ngưỡng chung KHÔNG tệ.
"""
from __future__ import annotations

import pytest

from app.services import calibration as cal


def test_du_bon_hiem_hoa_co_nguong_chung():
    assert set(cal.NATIONAL_P97) == {"flood", "landslide", "drought", "wildfire"}
    for m, v in cal.NATIONAL_P97.items():
        assert v > 0, m


def test_nguong_chung_cung_bac_do_lon_voi_san_hiem_hoa():
    """Hằng số phải nằm trong khoảng hợp lý so với sàn tuyệt đối của cùng module.

    Đây là bẫy đã sập một lần: bản đầu tính hằng số trên chuỗi liền 10 năm thay
    vì trên đỉnh cửa sổ 7 ngày, làm ngưỡng hạn ra 3.623 — cao gấp trăm lần sàn,
    và không nơi nào trên cả nước chạm tới. Test này bắt đúng kiểu sai đó.
    """
    for m, v in cal.NATIONAL_P97.items():
        floor = cal._FLOOR.get(m, 0.0)
        assert floor < v < floor * 20, (
            f"{m}: ngưỡng chung {v} lệch bậc độ lớn so với sàn {floor} — "
            "nhiều khả năng tính trên sai phân bố")


def test_khong_co_module_thi_tra_none():
    assert cal.contrast("khong-ton-tai", 16.0, 107.0) is None


def test_thieu_lich_su_thi_tra_none_chu_khong_doan(monkeypatch):
    monkeypatch.setattr(cal, "climatology", lambda *a, **k: None)
    assert cal.contrast("flood", 16.46, 107.59) is None


def test_dem_dung_tren_phan_bo_gia_lap(monkeypatch):
    """Kiểm tra phép đếm, không phụ thuộc mạng."""
    # 100 cửa sổ: 10 cái vượt hẳn ngưỡng chung của lũ (95.23).
    dist = sorted([5.0] * 90 + [200.0] * 10)
    monkeypatch.setattr(cal, "climatology", lambda *a, **k: dist)
    c = cal.contrast("flood", 16.46, 107.59)
    assert c["fixed_alarms"] == 10
    assert c["windows"] == 100


def test_quy_ra_ngay_moi_nam_dung(monkeypatch):
    dist = sorted([5.0] * 365 + [200.0] * 365)   # 2 năm, nửa số ngày vượt
    monkeypatch.setattr(cal, "climatology", lambda *a, **k: dist)
    c = cal.contrast("flood", 16.0, 107.0)
    assert c["years"] == pytest.approx(2.0, abs=0.05)
    assert c["fixed_days_per_year"] == pytest.approx(182.5, abs=1.0)


def test_hai_ve_dung_cung_mot_phan_bo(monkeypatch):
    """Nếu hai vế đọc hai nguồn khác nhau thì so sánh vô nghĩa."""
    goi = []
    dist = sorted([float(i) for i in range(200)])

    def spy(*a, **k):
        goi.append(1)
        return dist

    monkeypatch.setattr(cal, "climatology", spy)
    cal.contrast("flood", 16.0, 107.0)
    assert len(goi) == 1, "phải dùng lại đúng một phân bố cho cả hai vế"


def test_khong_ton_them_luot_goi_mang(monkeypatch):
    """Khối này nằm trên màn hình chính nên không được kéo theo lượt gọi mới.

    Nó phải sống nhờ phân bố mà bước hiệu chuẩn trong lượt quét đã cache.
    """
    from app.services import realdata
    n = {"c": 0}
    monkeypatch.setattr(realdata, "_fetch",
                        lambda u, t: n.__setitem__("c", n["c"] + 1))
    monkeypatch.setattr(cal, "climatology", lambda *a, **k: [1.0, 2.0, 300.0] * 40)
    cal.contrast("flood", 16.0, 107.0)
    assert n["c"] == 0


def test_cong_bo_cach_tinh_de_kiem_lai(monkeypatch):
    monkeypatch.setattr(cal, "climatology", lambda *a, **k: [1.0, 200.0] * 60)
    c = cal.contrast("flood", 16.0, 107.0)
    assert "phân vị 97" in c["method"]
    assert "58.336" in c["method"], "phải nêu cỡ mẫu để người đọc kiểm lại được"


def test_khong_giau_truong_hop_nguong_chung_khong_te(monkeypatch):
    """Nếu ở một nơi ngưỡng chung tình cờ tốt ngang thì con số phải nói ra thế.

    Khối này chỉ đáng tin nếu nó CÓ THỂ cho ra kết quả bất lợi cho chính mình.
    """
    dist = sorted([50.0] * 100)          # không cái nào vượt 95.23
    monkeypatch.setattr(cal, "climatology", lambda *a, **k: dist)
    c = cal.contrast("flood", 16.0, 107.0)
    assert c["fixed_days_per_year"] == 0.0
