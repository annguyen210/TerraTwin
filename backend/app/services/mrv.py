"""C07 — Báo cáo MRV carbon & ESG: đo, báo cáo, xác minh được.

VÌ SAO LUỒNG NÀY TỪNG BỊ XẾP "BỊ CHẶN": một con số tCO₂ bịa có hệ quả tiền thật
và pháp lý thật. Đó vẫn đúng. Thứ đã thay đổi là bây giờ có ảnh Sentinel-2, nên
tách được rành mạch hai phần vốn hay bị trộn vào nhau:

  ĐO ĐƯỢC TỪ VỆ TINH (phần này là số liệu):
      độ che phủ tán cây, diện tích có rừng, biến động che phủ theo thời gian.
      Đây là quan trắc thật, lặp lại được, ai cũng kiểm chứng lại được.

  KHÔNG ĐO ĐƯỢC TỪ VỆ TINH (phần này là ƯỚC LƯỢNG có phương pháp luận):
      sinh khối trên mặt đất (t/ha) → carbon → tCO₂. Vệ tinh quang học nhìn
      thấy TÁN, không nhìn thấy THÂN. Rừng non tán kín và rừng già tán kín cho
      NDVI gần như nhau nhưng chênh nhau nhiều lần về sinh khối.

Cách xử lý: dùng hệ số mặc định IPCC Tier 1 — đây là phương pháp luận quốc tế
được thiết kế ĐÚNG cho tình huống chưa có số liệu địa phương, luôn công bố kèm
bậc và sai số. Kết quả được gắn nhãn rõ là ƯỚC LƯỢNG SƠ BỘ TIER 1, KHÔNG PHẢI
số liệu đủ chuẩn phát hành tín chỉ, và nêu đúng những bước còn thiếu để lên
chuẩn đó. Người dùng nhập được hệ số sinh khối địa phương thì phần mềm dùng hệ
số đó và nâng nhãn lên Tier 2.

NGUỒN HỆ SỐ (IPCC 2006 Guidelines, Vol.4 AFOLU):
  Ch.4 Bảng 4.7  — sinh khối trên mặt đất rừng nhiệt đới ẩm châu Á lục địa
  Ch.4 Bảng 4.4  — tỉ lệ rễ/thân (root-to-shoot) rừng nhiệt đới ẩm
  Ch.4 mục 4.2.1 — tỉ lệ carbon trong sinh khối khô
  Hệ số phân tử   44/12 để quy carbon sang CO₂ tương đương

PHẦN "CHỐNG GIẢ MẠO" trong bản thiết kế: mỗi báo cáo mang một mã băm SHA-256
tính trên đúng bộ dữ liệu đầu vào đã dùng. Sửa một con số trong báo cáo là mã
băm không khớp nữa. Đây là tính toàn vẹn (ai cũng tự kiểm lại được), không phải
chữ ký số của một bên thứ ba có thẩm quyền — nói rõ để không ai hiểu nhầm.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone

from app.services import sentinel

# Ngưỡng NDVI coi là có tán cây. 0,55 là mức thận trọng cho vùng nhiệt đới ẩm:
# đủ cao để loại lúa, cỏ và cây bụi thấp, đủ thấp để không bỏ sót rừng thưa.
CANOPY_NDVI = 0.55

# --- Hệ số mặc định IPCC Tier 1 (rừng nhiệt đới ẩm, châu Á lục địa) ---
AGB_T_HA = 180.0          # sinh khối trên mặt đất, tấn chất khô/ha
ROOT_SHOOT = 0.24         # sinh khối dưới mặt đất = 0,24 × trên mặt đất
CARBON_FRACTION = 0.47    # tỉ lệ carbon trong sinh khối khô
CO2_PER_C = 44.0 / 12.0   # quy carbon sang CO₂ tương đương

# Sai số Tier 1 theo chính hướng dẫn IPCC: hệ số mặc định vùng có thể lệch rất
# xa thực tế một lô cụ thể. Công bố dải này là bắt buộc, không phải tùy chọn.
TIER1_UNCERTAINTY = 0.50  # ±50%


def _round(x, n=2):
    return round(float(x), n)


def build(lat: float, lon: float, buffer_m: float = 600.0,
          agb_t_ha: float | None = None,
          project_name: str = "") -> dict:
    """Dựng báo cáo MRV cho một lô đất.

    `agb_t_ha` là hệ số sinh khối địa phương do người dùng cung cấp (từ khảo sát
    ô mẫu hoặc số liệu kiểm kê rừng của tỉnh). Có nó thì báo cáo lên Tier 2.
    """
    if not sentinel.configured():
        return {
            "available": False,
            "reason": "no_satellite",
            "message": (
                "Báo cáo carbon bắt buộc phải dựa trên quan trắc vệ tinh thật. "
                "Chưa cấu hình khóa Copernicus nên phần mềm KHÔNG lập báo cáo — "
                "một con số carbon không có nguồn còn tệ hơn không có báo cáo. "
                "Đăng ký miễn phí tại dataspace.copernicus.eu."),
        }

    dist = sentinel.index_distribution(lat, lon, "NDVI", days=60,
                                       buffer_m=buffer_m, bins=20)
    if dist is None:
        return {
            "available": False,
            "reason": "no_clear_image",
            "message": ("Chưa lấy được ảnh quang mây cho lô này trong 60 ngày "
                        "qua. Mùa mưa thường phải chờ vài tuần. Không lập báo "
                        "cáo từ ảnh có mây."),
        }

    canopy_frac = sentinel.fraction_above(dist, CANOPY_NDVI)
    if canopy_frac is None:
        return {"available": False, "reason": "no_histogram",
                "message": "Không dựng được phân bố NDVI cho lô này."}

    total_ha = dist["area_ha"]
    forest_ha = _round(total_ha * canopy_frac)

    tier = 2 if agb_t_ha else 1
    agb = float(agb_t_ha) if agb_t_ha else AGB_T_HA
    bgb = agb * ROOT_SHOOT
    total_biomass = agb + bgb
    c_t_ha = total_biomass * CARBON_FRACTION
    co2_t_ha = c_t_ha * CO2_PER_C
    stock_tco2 = forest_ha * co2_t_ha

    # Dải sai số. Tier 2 hẹp hơn nhưng vẫn KHÔNG được coi là chính xác tuyệt đối.
    unc = TIER1_UNCERTAINTY if tier == 1 else 0.25
    lo, hi = stock_tco2 * (1 - unc), stock_tco2 * (1 + unc)

    # Biến động che phủ so với cùng kỳ năm trước — phần "M" của MRV có ý nghĩa
    # nhất, vì tín chỉ trả cho THAY ĐỔI chứ không trả cho trữ lượng tĩnh.
    change = None
    try:
        today = date.today()
        prev = sentinel.index_distribution(
            lat, lon, "NDVI", days=60, buffer_m=buffer_m, bins=20,
            end=today.replace(year=today.year - 1))
        prev_frac = sentinel.fraction_above(prev, CANOPY_NDVI)
        if prev_frac is not None:
            d_ha = _round((canopy_frac - prev_frac) * total_ha)
            change = {
                "previous_canopy_pct": _round(prev_frac * 100, 1),
                "current_canopy_pct": _round(canopy_frac * 100, 1),
                "delta_ha": d_ha,
                "delta_tco2": _round(d_ha * co2_t_ha),
                "verdict": ("mất rừng" if d_ha < -0.2
                            else "tăng che phủ" if d_ha > 0.2
                            else "gần như không đổi"),
                "window": [prev["observed_window"][0], dist["observed_window"][1]],
            }
    except Exception:
        change = None

    measured = {
        "location": {"lat": lat, "lon": lon},
        "aoi_ha": total_ha,
        "canopy_threshold_ndvi": CANOPY_NDVI,
        "canopy_fraction": canopy_frac,
        "canopy_pct": _round(canopy_frac * 100, 1),
        "forest_ha": forest_ha,
        "ndvi_mean": dist["mean"],
        "ndvi_std": dist["std"],
        "cloud_free_pct": dist["coverage_pct"],
        "observed_window": dist["observed_window"],
        "pixel_m": dist["pixel_m"],
        "source": sentinel.source_note("NDVI"),
    }

    estimated = {
        "tier": tier,
        "tier_label": ("Tier 1 — hệ số mặc định IPCC cho vùng"
                       if tier == 1 else
                       "Tier 2 — hệ số sinh khối do người dùng cung cấp"),
        "agb_t_ha": _round(agb), "bgb_t_ha": _round(bgb),
        "root_shoot_ratio": ROOT_SHOOT,
        "carbon_fraction": CARBON_FRACTION,
        "tco2_per_ha": _round(co2_t_ha),
        "stock_tco2": _round(stock_tco2),
        "uncertainty_pct": _round(unc * 100, 0),
        "stock_tco2_low": _round(lo),
        "stock_tco2_high": _round(hi),
        "arithmetic": (
            f"{forest_ha} ha có tán × (({_round(agb)} + {_round(bgb)}) t sinh khối/ha "
            f"× {CARBON_FRACTION} carbon × {_round(CO2_PER_C, 3)} CO₂/C) "
            f"= {_round(stock_tco2)} tCO₂"),
    }

    report = {
        "available": True,
        "project_name": project_name or "Lô chưa đặt tên",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "measured": measured,
        "estimated": estimated,
        "change_vs_last_year": change,
        "headline": (
            f"Che phủ tán {measured['canopy_pct']}% trên {total_ha} ha "
            f"(≈{forest_ha} ha có rừng). Trữ lượng ước tính "
            f"{estimated['stock_tco2']} tCO₂ "
            f"(dải {estimated['stock_tco2_low']}–{estimated['stock_tco2_high']}, "
            f"{estimated['tier_label']})."),
        "methodology": {
            "measured_by": ("Sentinel-2 L2A, NDVI mỗi pixel 10 m, lọc mây bằng "
                            "băng SCL, lấy tổ hợp ít mây nhất trong cửa sổ 60 ngày. "
                            "Tỉ lệ che phủ nội suy tuyến tính từ histogram 20 bin."),
            "estimated_by": ("IPCC 2006 Guidelines Vol.4 (AFOLU) Ch.4: bảng 4.7 "
                             "sinh khối trên mặt đất, bảng 4.4 tỉ lệ rễ/thân, "
                             "mục 4.2.1 tỉ lệ carbon, hệ số 44/12 quy sang CO₂."),
            "not_measured": ("Vệ tinh quang học nhìn thấy TÁN, không thấy THÂN. "
                             "Rừng non tán kín và rừng già tán kín cho NDVI gần "
                             "như nhau nhưng chênh nhau nhiều lần về sinh khối. "
                             "Toàn bộ phần từ tán sang tấn là hệ số, không phải đo."),
        },
        "limitations": [
            "ĐÂY KHÔNG PHẢI SỐ LIỆU ĐỦ CHUẨN PHÁT HÀNH TÍN CHỈ. Đây là ước lượng "
            "sơ bộ để biết có đáng theo đuổi dự án carbon hay không.",
            f"Sai số Tier {tier}: ±{_round(unc * 100, 0)}%. Hệ số mặc định IPCC là "
            "trung bình cho cả một vùng sinh thái, có thể lệch rất xa một lô cụ thể.",
            "Chưa có đường cơ sở (baseline) và chứng minh tính bổ sung "
            "(additionality) — hai thứ bắt buộc của mọi tiêu chuẩn tín chỉ.",
            "Chưa trừ rò rỉ (leakage) và chưa lập vùng đệm rủi ro đảo ngược.",
            "NDVI bão hòa ở tán rậm: rừng rất giàu sinh khối không phân biệt được "
            "với rừng trung bình bằng chỉ số quang học đơn thuần.",
        ],
        "to_reach_credit_grade": [
            "Lập ô mẫu thực địa (thường 0,1 ha/ô, tối thiểu 3–5 ô) đo đường kính "
            "ngang ngực và chiều cao, áp phương trình sinh khối của loài.",
            "Nhập hệ số sinh khối địa phương thu được vào phần mềm để lên Tier 2.",
            "Chọn tiêu chuẩn (VCS, Gold Standard, hoặc cơ chế trong nước) và lập "
            "đường cơ sở theo đúng phương pháp luận của tiêu chuẩn đó.",
            "Thuê đơn vị thẩm định độc lập (VVB) xác minh — không tổ chức nào chấp "
            "nhận tín chỉ do chính chủ dự án tự đo.",
        ],
    }

    # --- Toàn vẹn: băm trên ĐÚNG dữ liệu đã dùng, không băm cả bản trình bày ---
    payload = json.dumps({"measured": measured, "estimated": estimated,
                          "change": change},
                         sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    report["integrity"] = {
        "algorithm": "SHA-256",
        "hash": digest,
        "short": digest[:16],
        "covers": ["measured", "estimated", "change_vs_last_year"],
        "note": ("Mã băm tính trên đúng bộ số liệu đo và ước lượng ở trên. Sửa "
                 "bất kỳ con số nào là mã băm khác đi, nên người nhận báo cáo "
                 "tự kiểm được bản mình cầm có bị chỉnh sửa hay không."),
        "not_a_signature": ("Đây là kiểm tra TOÀN VẸN, không phải chữ ký số của "
                            "một cơ quan có thẩm quyền. Nó chứng minh báo cáo "
                            "không bị sửa, KHÔNG chứng minh nội dung đã được ai "
                            "thẩm định."),
        "verify": ("Băm lại chuỗi JSON gọn (khóa sắp xếp, không khoảng trắng) của "
                   "ba khối measured/estimated/change bằng SHA-256."),
    }
    return report


def verify(report: dict) -> dict:
    """Kiểm tra một báo cáo có còn nguyên vẹn không."""
    integ = (report or {}).get("integrity") or {}
    claimed = integ.get("hash")
    if not claimed:
        return {"valid": False, "reason": "Báo cáo không có mã băm."}
    payload = json.dumps({"measured": report.get("measured"),
                          "estimated": report.get("estimated"),
                          "change": report.get("change_vs_last_year")},
                         sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"))
    actual = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    ok = actual == claimed
    return {
        "valid": ok, "expected": claimed, "actual": actual,
        "message": ("Báo cáo nguyên vẹn — số liệu khớp mã băm."
                    if ok else
                    "CẢNH BÁO: số liệu trong báo cáo KHÔNG khớp mã băm. Bản này "
                    "đã bị sửa sau khi lập."),
    }
