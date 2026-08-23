"""Dòng thời gian rủi ro trên lưới — và ba cơ chế chống ba rủi ro của nó.

Hoạt hình trên bản đồ là "điểm cộng demo số 1" trong bản thiết kế, nhưng nó
mang ba rủi ro thật. Mỗi rủi ro ở đây có một CƠ CHẾ trong mã, không phải một
dòng chú thích — và mỗi cơ chế có test riêng:

  ① "Chỉ đẹp hơn, không chính xác hơn"
     → Trả THÊM thông tin mà bản đồ đỉnh đang vứt đi: NGÀY ĐẾN và SỐ NGÀY KÉO
       DÀI. "Ngập ngày mai" khác "ngập thứ Bảy"; "ngập một ngày" khác "ngập bốn
       ngày" — lúa chết vì cái sau.

  ② "Trông chắc chắn hơn thực tế"
     → Công bố độ phân giải HIỆU DỤNG theo từng mô-đun và cảnh báo khi ô hiển
       thị mịn hơn dữ liệu.

  ③ "Dễ thành trang trí"
     → Mọi thứ nhìn thấy khi chạy hoạt hình đều phải đọc được dưới dạng SỐ khi
       đứng yên (n_over_by_day, arrival_day, days_over).
"""
from __future__ import annotations

import pytest

from app.services import calibration, heatmap, realdata


def _rows(precips, start_day=0):
    return [{"day": start_day + i, "date": f"2026-08-{20 + i:02d}",
             "precip": p, "et0": 4.0, "tmax": 33.0}
            for i, p in enumerate(precips)]


@pytest.fixture
def offline(monkeypatch):
    """Lưới giả tất định — không chạm mạng, không phụ thuộc thời tiết thật."""
    monkeypatch.setattr(realdata, "elevation_m", lambda la, lo: 3.0)
    monkeypatch.setattr(realdata, "slope_deg",
                        lambda la, lo, step_m=500.0: 20.0)
    monkeypatch.setattr(realdata, "elevation_multi",
                        lambda pts: [3.0] * len(pts))
    monkeypatch.setattr(heatmap, "_grid_slopes", lambda pts: [20.0] * len(pts))
    monkeypatch.setattr("app.services.cache_store.get", lambda k: None)
    monkeypatch.setattr("app.services.cache_store.put", lambda k, v, t: None)
    # Khí hậu nền dựng theo PHÂN VỊ có chủ đích, không phải một công thức cho
    # tiện. Hiệu chuẩn ánh xạ P90→40 và P97→70, nên hình dạng phân bố quyết
    # định thẳng việc test có ý nghĩa hay không.
    #
    # Bản đầu tôi dùng (i/400)²×260: P90 rơi vào 210 mm, khiến một trận 130 mm
    # chỉ nằm ở phân vị 75 và không vượt ngưỡng nào. Test đỏ, mà lỗi nằm ở dữ
    # liệu giả chứ không ở mã — đúng loại bẫy đã gặp một lần ở test_advanced.
    dist = sorted(
        [i / 359 * 60.0 for i in range(360)]          # 90% số ngày: 0–60
        + [60.0 + i / 27 * 40.0 for i in range(28)]   # tới P97: 60–100
        + [100.0 + i / 11 * 100.0 for i in range(12)]  # đuôi hiếm: 100–200
    )
    monkeypatch.setattr(calibration, "climatology", lambda *a, **k: dist)


def _all_cells(monkeypatch, precips):
    monkeypatch.setattr(realdata, "weather_multi",
                        lambda pts: [_rows(precips) for _ in pts])


# ------------------------------------------------ ① thông tin MỚI, không chỉ đẹp

def test_tra_ve_ngay_den_va_so_ngay_keo_dai(offline, monkeypatch):
    """Hai con số bản đồ đỉnh đang vứt đi — và là thứ quyết định hành động."""
    # Khô 3 ngày, rồi mưa lớn 3 ngày, rồi tạnh.
    _all_cells(monkeypatch, [0, 0, 0, 120, 120, 120, 0])

    r = heatmap.timeline("flood", 15.36, 107.90, radius_km=8.0, side=3)
    base = r["scenarios"][0]
    c = base["cells"][0]

    assert c["values"] is not None and len(c["values"]) == 7
    assert c["arrival_day"] is not None and c["arrival_day"] >= 3, \
        "phải phát hiện rủi ro đến từ ngày thứ 4, không phải ngày đầu"
    assert c["days_over"] >= 2, "phải đếm được rủi ro kéo dài nhiều ngày"


def test_ngay_den_khac_nhau_thi_phan_biet_duoc(offline, monkeypatch):
    """Cùng một đỉnh nhưng đến sớm hay muộn là hai quyết định khác nhau."""
    _all_cells(monkeypatch, [150, 0, 0, 0, 0, 0, 0])
    som = heatmap.timeline("flood", 15.36, 107.90, side=3)["scenarios"][0]

    _all_cells(monkeypatch, [0, 0, 0, 0, 0, 0, 150])
    muon = heatmap.timeline("flood", 15.36, 107.90, side=3)["scenarios"][0]

    assert som["first_arrival_day"] < muon["first_arrival_day"]


def test_dem_so_o_vuot_nguong_theo_tung_ngay(offline, monkeypatch):
    """Con số cho mỗi khung hình — để hoạt hình không phải thứ duy nhất đọc được."""
    _all_cells(monkeypatch, [0, 0, 130, 130, 0, 0, 0])

    r = heatmap.timeline("flood", 15.36, 107.90, side=3)
    n = r["scenarios"][0]["n_over_by_day"]
    assert len(n) == 7
    assert n[0] == 0 and n[1] == 0
    assert n[2] > 0, "ngày mưa lớn phải có ô vượt ngưỡng"


def test_bon_kich_ban_deu_co_va_khac_nhau(offline, monkeypatch):
    _all_cells(monkeypatch, [40, 40, 40, 40, 40, 40, 40])

    r = heatmap.timeline("flood", 15.36, 107.90, side=3)
    assert len(r["scenarios"]) == 4

    def dinh(s):
        return max(v for c in s["cells"] if c["values"] for v in c["values"])

    hien_tai = dinh(r["scenarios"][0])
    mua_doi = dinh(r["scenarios"][2])      # "Mưa gấp đôi"
    kho_han = dinh(r["scenarios"][3])      # "Khô hạn kéo dài"
    assert mua_doi > hien_tai > kho_han, (hien_tai, mua_doi, kho_han)


# ------------------------------------------------ ② trung thực độ phân giải

def test_canh_bao_khi_o_hien_thi_min_hon_du_lieu(offline, monkeypatch):
    """Hạn chỉ phụ thuộc thời tiết → độ phân giải thật là lưới khí tượng ~11 km.

    Vẽ ô 1,5 km cho dữ liệu 11 km là bịa ra chi tiết. Phần mềm phải nói ra.
    """
    _all_cells(monkeypatch, [0] * 7)

    r = heatmap.timeline("drought", 15.36, 107.90, radius_km=3.0, side=5)
    res = r["resolution"]
    assert res["oversampled"] is True
    assert res["effective_km"] == 11.0
    assert res["cells_per_data_pixel"] > 1
    assert "KHÔNG có nghĩa là biết chi tiết" in res["note"]


def test_khong_canh_bao_khi_o_khong_min_hon_du_lieu(offline, monkeypatch):
    _all_cells(monkeypatch, [0] * 7)

    r = heatmap.timeline("drought", 15.36, 107.90, radius_km=40.0, side=3)
    assert r["resolution"]["oversampled"] is False
    assert "không có chi tiết nào bị bịa ra" in r["resolution"]["note"]


def test_do_phan_giai_hieu_dung_khac_nhau_theo_mo_dun(offline, monkeypatch):
    """Lũ/sạt lở có địa hình tham gia nên mịn hơn hạn/cháy thuần thời tiết."""
    _all_cells(monkeypatch, [0] * 7)

    han = heatmap.timeline("drought", 15.36, 107.90, side=3)["resolution"]
    lu = heatmap.timeline("flood", 15.36, 107.90, side=3)["resolution"]
    sat_lo = heatmap.timeline("landslide", 15.36, 107.90, side=3)["resolution"]

    assert han["effective_km"] > lu["effective_km"] > sat_lo["effective_km"]
    assert "THỜI ĐIỂM thì vẫn bị khoá theo lưới thời tiết" in lu["why"]


# ------------------------------------------------ ③ không thành trang trí

def test_moi_thu_nhin_thay_deu_doc_duoc_bang_so(offline, monkeypatch):
    """Chốt chặn cho rủi ro "đẹp mà rỗng".

    Nếu một thông tin chỉ hiện ra khi chạy hoạt hình thì người không xem hoạt
    hình sẽ mất nó — và hoạt hình trở thành trang trí bắt buộc.
    """
    _all_cells(monkeypatch, [0, 0, 130, 130, 0, 0, 0])

    r = heatmap.timeline("flood", 15.36, 107.90, side=3)
    s = r["scenarios"][0]
    for khoa in ("n_over_by_day", "first_arrival_day", "cells_affected",
                 "max_days_over"):
        assert khoa in s, khoa
    assert r["dates"] and len(r["dates"]) == 7
    assert r["headline"]


def test_tieu_de_noi_ro_khi_nao_va_bao_lau(offline, monkeypatch):
    _all_cells(monkeypatch, [0, 0, 0, 140, 140, 0, 0])

    r = heatmap.timeline("flood", 15.36, 107.90, side=3)
    assert "sớm nhất" in r["headline"]
    assert "kéo dài" in r["headline"]


# ------------------------------------------------ chi phí & an toàn

def test_khong_ton_them_luot_goi_so_voi_ban_do_nhiet():
    """Lời hứa cốt lõi: hoạt hình MIỄN PHÍ về mặt mạng.

    Dữ liệu 7 ngày vốn đã được tải cho mọi ô rồi bị vứt đi chỉ giữ đỉnh; bốn
    kịch bản chỉ là phép nhân trên cùng bộ đó.
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parent.parent / "app" / "services"
           / "heatmap.py").read_text(encoding="utf-8")
    tl = src[src.index("def timeline("):]
    # Trong timeline chỉ được lấy dữ liệu qua _prepare, không gọi mạng trực tiếp.
    for cam in ("realdata.weather_multi", "realdata.elevation_multi",
                "realdata.weather_7d", "ds.slope_context"):
        assert cam not in tl, f"timeline() không được gọi thẳng {cam}"
    assert "_prepare(" in tl


def test_tran_luoi_thap_hon_ban_do_nhiet_tinh(offline, monkeypatch):
    """Kích thước phản hồi nhân với 4 kịch bản × 7 ngày nên phải chặn."""
    _all_cells(monkeypatch, [0] * 7)

    r = heatmap.timeline("flood", 15.36, 107.90, side=99)
    assert r["side"] == heatmap._MAX_SIDE_TIMELINE
    assert heatmap._MAX_SIDE_TIMELINE < heatmap._MAX_SIDE


def test_o_thieu_du_lieu_khong_bi_coi_la_an_toan(offline, monkeypatch):
    """None phải giữ nguyên là None, không được hoá thành 0."""
    monkeypatch.setattr(realdata, "weather_multi",
                        lambda pts: [None] * len(pts))

    r = heatmap.timeline("flood", 15.36, 107.90, side=3)
    c = r["scenarios"][0]["cells"][0]
    assert c["values"] is None
    assert c["arrival_day"] is None


def test_mo_dun_khong_phai_hiem_hoa_thi_tra_none(offline):
    assert heatmap.timeline("solar", 15.36, 107.90) is None


def test_ban_do_nhiet_va_dong_thoi_gian_khop_nhau(offline, monkeypatch):
    """Hai màn hình PHẢI nói cùng một chuyện về cùng một ô.

    Cả hai đi qua _prepare/_cell_series chung. Nếu ai đó tách đôi logic thì
    test này đỏ — đúng loại lệch dự án đã mất một đợt để dẹp.
    """
    _all_cells(monkeypatch, [0, 0, 130, 130, 0, 0, 0])

    tinh = heatmap.build("flood", 15.36, 107.90, radius_km=8.0, side=3)
    dong = heatmap.timeline("flood", 15.36, 107.90, radius_km=8.0, side=3)

    for a, b in zip(tinh["cells"], dong["scenarios"][0]["cells"]):
        if a["value"] is None or b["values"] is None:
            continue
        assert abs(a["value"] - max(b["values"])) < 0.05, (a, b)
