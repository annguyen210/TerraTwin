"""Kiểm A–Z 24/11/2026 (thị trấn Ba Tri): thẻ đầu "7 ngày tới: yên · TerraScore 100" ngay trên ô "Mặn mức CẢNH BÁO — đỉnh
~2.42 g/L". Mặn ở đó chỉ có ƯỚC LƯỢNG chưa hiệu chỉnh nên đúng là không vào điểm — nhưng phải được ghi riêng để thẻ không
nói "yên"/"thấp". Chưa kết luận (need_data) thì KHÔNG tính là ước lượng cảnh báo."""
from __future__ import annotations

from app.schemas import Assessment, Location
from app.services import reqlang, terrascore

LOC = Location(lat=10.04427, lon=106.5902)


def _a(mid, lvl, real=True, status="ok"):
    return Assessment(module_id=mid, module_name={"salinity": "Cảnh báo xâm nhập mặn"}.get(mid, mid), location=LOC,
                      status=status, risk_level=lvl, headline="x", detail="", recommendation="", is_real=real)


def _all_safe(**over):
    got = {h: _a(h, "safe") for h in ("salinity", "drought", "flood", "landslide", "wildfire")}
    got.update(over)
    return got


def test_uoc_luong_man_canh_bao_duoc_ghi_rieng_khong_vao_diem():
    reqlang.set_lang("vi")
    t = terrascore.compute(LOC, _all_safe(salinity=_a("salinity", "warning", real=False)), reassess=False)
    assert t.score == 100 and t.grade == "A"                       # điểm giữ nguyên định nghĩa
    assert t.estimate_alerts == [{"id": "salinity", "name": "Cảnh báo xâm nhập mặn", "risk_level": "warning"}]
    assert t.hazard_alerts == []
    assert "thấp; ước lượng mô hình (chưa hiệu chỉnh) báo cần để ý — cảnh báo xâm nhập mặn" in t.summary


def test_chua_ket_luan_khong_phai_uoc_luong_canh_bao():
    t = terrascore.compute(LOC, _all_safe(salinity=_a("salinity", "unknown", real=False, status="need_data")), reassess=False)
    assert t.estimate_alerts == [] and "ước lượng" not in t.summary
