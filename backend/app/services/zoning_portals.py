"""Cổng TRA QUY HOẠCH chính thức theo tỉnh — bước tiếp theo khi câu "thổ cư / quy hoạch" ra "Không đủ dữ liệu".

Kiểm A–Z 21/11/2026, P2-2: người mua lo QUY HOẠCH trước tiên, mà TerraTwin không kiểm được phần đó (dữ liệu địa chính
không công khai). Thay vì dừng ở "Không đủ dữ liệu", chỉ đúng chỗ tra: cổng của CƠ QUAN NHÀ NƯỚC (tên miền .gov.vn), đã
tự mở kiểm từng link. KHÔNG dùng trang tư nhân. Tỉnh chưa có cổng đã kiểm thì hướng dẫn hỏi Văn phòng đăng ký đất đai.

Khoá là tên tỉnh CŨ (ranh 2020, data/admin/vnm_adm2_2020.json — cùng bộ với flood_reports.locate). Thêm tỉnh: tự mở link,
ghi ngày kiểm, chỉ nhận .gov.vn.
"""
from __future__ import annotations

from app.services.reqlang import tr

# Đã mở kiểm 22/11/2026 (trình duyệt thật):
#   · qhkhsdd.hanoi.gov.vn → "Ứng dụng công khai thông tin quy hoạch, kế hoạch sử dụng đất thành phố Hà Nội"
#   · thongtinquyhoach.hochiminhcity.gov.vn → "Thông tin quy hoạch TP.HCM"
#   · gis.khanhhoa.gov.vn/public/8192/ → "Cổng Thông Tin GIS - Tỉnh Khánh Hòa | Tra cứu thông tin quy hoạch" (UBND tỉnh,
#     mục "Tra cứu quy hoạch") — kiểm A–Z lần 2
# Đã kiểm 22/11/2026 và LOẠI (không mở được): qhkhsdd.binhduong.gov.vn (tên miền không còn — NXDOMAIN),
#   hph.mplis.gov.vn/og/KhaiThacBanDo (Hải Phòng — 404). Tỉnh khác: chưa kiểm → giữ câu hỏi Văn phòng đăng ký đất đai.
PORTALS: dict[str, dict] = {
    "Hà Nội": {"url": "https://qhkhsdd.hanoi.gov.vn",
               "name_vi": "Quy hoạch, kế hoạch sử dụng đất TP Hà Nội",
               "name_en": "Hanoi land-use planning portal", "checked": "2026-11-22"},
    "TP Hồ Chí Minh": {"url": "https://thongtinquyhoach.hochiminhcity.gov.vn",
                       "name_vi": "Thông tin quy hoạch TP.HCM",
                       "name_en": "Ho Chi Minh City planning information", "checked": "2026-11-22"},
    "Khánh Hòa": {"url": "https://gis.khanhhoa.gov.vn/public/8192/",
                  "name_vi": "Cổng thông tin GIS tỉnh Khánh Hòa — Tra cứu thông tin quy hoạch",
                  "name_en": "Khanh Hoa provincial GIS portal — planning lookup", "checked": "2026-11-22"},
}


def for_point(lat: float, lon: float) -> dict:
    """{province, portal: {url, name, checked} | None, note} — portal chỉ có khi tỉnh nằm trong danh sách đã kiểm."""
    from app.services import flood_reports
    loc = flood_reports.locate(lat, lon)
    prov = loc["province"] if loc else None
    p = PORTALS.get(prov or "")
    if p:
        return {"province": prov,
                "portal": {"url": p["url"], "name": tr(p["name_vi"], p["name_en"]), "checked": p["checked"]},
                "note": tr("TerraTwin không kiểm quy hoạch; đây là cổng chính thức của tỉnh/thành phố — tra theo vị trí "
                           "hoặc số thửa, rồi đối chiếu với sổ đỏ.",
                           "TerraTwin does not check zoning; this is the official provincial portal — look up by "
                           "location or parcel number, then compare with the land certificate.")}
    return {"province": prov, "portal": None,
            "note": tr("TerraTwin không kiểm quy hoạch và chưa có cổng tra trực tuyến đã kiểm cho tỉnh này. Hỏi Văn phòng "
                       "đăng ký đất đai (chi nhánh huyện) hoặc UBND xã nơi có thửa: xin thông tin quy hoạch, kế hoạch sử dụng "
                       "đất của đúng số thửa trước khi đặt cọc.",
                       "TerraTwin does not check zoning and has no verified online portal for this province yet. Ask the "
                       "Land Registration Office (district branch) or the commune People's Committee for the zoning and "
                       "land-use plan of that exact parcel before paying a deposit.")}
