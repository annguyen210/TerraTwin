"""Kiểm 20/11/2026 (ann953201, tab Canh đất): cảnh báo CŨ lưu "cách 1.99 km ((không tên))" — sửa lúc đọc ra."""
from app.services.textfix import alert_text


def test_canh_bao_cu_hien_dung():
    s = ("Hội An, Đà Nẵng — ven sông Thu Bồn: Có khu khai thác/công nghiệp cách 1.99 km ((không tên)) — "
         "độ dốc 0.4°, mưa dự báo 7 ngày tới 146.8 mm")
    out = alert_text(s)
    assert "cách 1,99 km (chưa có tên)" in out and "((" not in out
    assert "độ dốc 0.4°" in out and "146.8 mm" in out          # chỉ đổi đúng đoạn "cách … km"


def test_khong_dung_cau_khac():
    for s in (None, "", "Cảnh báo hạn: chỉ số 72.5", "Gần nhất khu công nghiệp cách 3,2 km (KCN Đình Vũ)"):
        assert alert_text(s) == s
