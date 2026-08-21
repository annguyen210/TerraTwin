"""Mưa ở THƯỢNG NGUỒN sắp chảy xuống đây.

VÌ SAO CẦN: cho tới file này, module Lũ và Sạt lở chỉ nhìn lượng mưa rơi trên
CHÍNH thửa đó. Nhưng lũ quét và lũ hạ nguồn đến từ nước rơi ở trên cao rồi dồn
xuống — Trà Leng 2020 không phải vì mưa tại chỗ, mà vì cả sườn núi phía trên
ngậm nước. Một mảnh đất có thể khô ráo suốt buổi sáng rồi ngập trong một giờ vì
chuyện xảy ra cách đó mười cây số về phía núi.

Bản thiết kế xếp việc này vào ô "Graph Neural Network — rủi ro lan truyền (lũ
hạ nguồn)". Xét theo MỤC ĐÍCH thì thứ người dùng cần không phải một mạng nơ-ron
đồ thị, mà là câu trả lời: "phía trên tôi có đang mưa không, và nước đó có chảy
về phía tôi không". Câu đó trả lời được bằng DEM và lưới mưa đã có.

CÁCH LÀM: lấy mẫu một nan quạt điểm quanh thửa, giữ lại những điểm CAO HƠN
(nước từ đó chảy xuống đây), rồi cân theo độ chênh cao và khoảng cách. Điểm cao
hơn 100 m cách 3 km đóng góp mạnh hơn điểm cao hơn 10 m cách 12 km.

GIỚI HẠN PHẢI NÓI THẲNG, VÌ NÓ QUYẾT ĐỊNH KHI NÀO ĐƯỢC TIN:
  · Đây KHÔNG phải lưu vực được phân định đúng cách. Nó là một nan quạt lấy mẫu
    theo hướng dốc lên, giả định nước chảy thẳng xuống dốc.
  · Bỏ qua lòng sông, đê bao, cống và hồ chứa — ở ĐBSCL thì chính mấy thứ đó
    mới quyết định nước đi đâu.
  · Ở đồng bằng, chênh lệch cao độ nhỏ hơn sai số đứng của DEM, nên tín hiệu là
    NHIỄU. Hàm này TỪ CHỐI trả kết quả khi địa hình quá phẳng, thay vì trả một
    con số trông có vẻ chính xác.

Vì vậy kết quả được trả về như một ĐỐI CHỨNG ĐỘC LẬP, giống lưu lượng sông
GloFAS — không cộng thẳng vào chỉ số đã hiệu chuẩn, để không đếm hai lần và
không làm hỏng phép hiệu chuẩn theo phân vị.
"""
from __future__ import annotations

import math

# Nan quạt lấy mẫu: 8 hướng × 3 vòng = 24 điểm, gọn trong một lượt gọi
# Open-Meteo (trần 100 toạ độ) cho cả cao độ lẫn mưa.
BEARINGS = 8
RADII_KM = (3.0, 7.0, 12.0)

# Dưới ngưỡng này thì chênh cao nằm trong sai số đứng của DEM toàn cầu —
# nói "thượng nguồn" ở đồng bằng là nói bừa.
MIN_RELIEF_M = 20.0

# Điểm phải cao hơn thửa ít nhất chừng này mới tính là thượng nguồn.
MIN_DROP_M = 5.0


def _offset(lat: float, lon: float, km: float, bearing_deg: float):
    d = km / 6371.0
    b = math.radians(bearing_deg)
    la1, lo1 = math.radians(lat), math.radians(lon)
    la2 = math.asin(math.sin(la1) * math.cos(d)
                    + math.cos(la1) * math.sin(d) * math.cos(b))
    lo2 = lo1 + math.atan2(math.sin(b) * math.sin(d) * math.cos(la1),
                           math.cos(d) - math.sin(la1) * math.sin(la2))
    return round(math.degrees(la2), 4), round(math.degrees(lo2), 4)


def _fan(lat: float, lon: float):
    pts = [(lat, lon)]
    for km in RADII_KM:
        for i in range(BEARINGS):
            pts.append(_offset(lat, lon, km, i * 360.0 / BEARINGS))
    return pts


def upstream(lat: float, lon: float) -> dict | None:
    """Mưa dự báo ở phần đất cao hơn quanh thửa, cân theo độ dốc về phía thửa.

    Trả None khi không lấy được dữ liệu. Trả dict với `available=False` khi lấy
    được nhưng địa hình quá phẳng để nói chuyện thượng nguồn — hai tình huống
    khác nhau, người gọi cần phân biệt.
    """
    from app.services import realdata

    pts = _fan(lat, lon)
    elevs = realdata.elevation_multi(pts)
    if not elevs or elevs[0] is None:
        return None

    here = elevs[0]
    ring = [(p, e) for p, e in zip(pts[1:], elevs[1:]) if e is not None]
    if len(ring) < BEARINGS:
        return None

    vals = [e for _, e in ring] + [here]
    relief = max(vals) - min(vals)
    if relief < MIN_RELIEF_M:
        return {
            "available": False,
            "reason": "flat",
            "here_m": here,
            "relief_m": round(relief, 1),
            "message": (
                f"Chênh cao quanh thửa chỉ {relief:.0f} m trong bán kính "
                f"{RADII_KM[-1]:.0f} km — nằm trong sai số đứng của DEM toàn cầu. "
                "Ở địa hình này nước đi đâu là do đê bao, cống và kênh quyết "
                "định, không do độ dốc; phần mềm không đoán thay."),
        }

    # Giữ lại phần đất CAO HƠN — nước từ đó chảy về phía thửa.
    up = []
    for (pla, plo), e in ring:
        drop = e - here
        if drop < MIN_DROP_M:
            continue
        km = _km(lat, lon, pla, plo)
        # Trọng số: dốc về phía thửa (m trên km). Gần và cao thì nặng ký hơn.
        up.append({"lat": pla, "lon": plo, "elev": e,
                   "drop_m": round(drop, 1), "km": round(km, 1),
                   "w": drop / max(1.0, km)})

    if not up:
        return {
            "available": False, "reason": "no_upslope",
            "here_m": here, "relief_m": round(relief, 1),
            "message": ("Thửa này nằm ở phần cao của khu vực — không có sườn "
                        "nào đáng kể đổ nước về đây. Đó là tin tốt cho nguy cơ "
                        "ngập từ thượng nguồn."),
        }

    rain = realdata.weather_multi([(u["lat"], u["lon"]) for u in up])
    tot_w = sum(u["w"] for u in up)
    acc = 0.0
    counted = 0
    for u, rows in zip(up, rain):
        if not rows:
            continue
        mm = sum(r["precip"] for r in rows)
        u["rain_7d_mm"] = round(mm, 1)
        acc += mm * u["w"]
        counted += 1
    if counted == 0:
        return None

    weighted = acc / tot_w if tot_w else 0.0

    # So với mưa tại chỗ: điều người dùng cần biết là "trên kia có mưa NHIỀU HƠN
    # ở đây không". Mưa thượng nguồn bằng mưa tại chỗ thì không thêm thông tin.
    local = realdata.weather_7d(lat, lon)
    local_mm = sum(r["precip"] for r in local) if local else None
    extra = (weighted - local_mm) if local_mm is not None else None

    if weighted >= 200 and (extra is None or extra > 20):
        level = "danger"
        verdict = "thượng nguồn đang mưa rất lớn và nước sẽ dồn về đây"
    elif weighted >= 100 and (extra is None or extra > 10):
        level = "warning"
        verdict = "thượng nguồn mưa đáng kể, cần tính tới nước từ trên xuống"
    elif extra is not None and extra < -20:
        level = "safe"
        verdict = "thượng nguồn khô hơn tại chỗ — nước dồn về ít"
    else:
        level = "safe"
        verdict = "thượng nguồn không mưa bất thường"

    up.sort(key=lambda u: u["w"], reverse=True)
    top = up[0]

    return {
        "available": True,
        "level": level,
        "verdict": verdict,
        "here_m": here,
        "relief_m": round(relief, 1),
        "upslope_points": counted,
        "total_points": len(ring),
        "upstream_rain_mm": round(weighted, 1),
        "local_rain_mm": round(local_mm, 1) if local_mm is not None else None,
        "extra_vs_local_mm": round(extra, 1) if extra is not None else None,
        "steepest": {"km": top["km"], "drop_m": top["drop_m"],
                     "rain_7d_mm": top.get("rain_7d_mm")},
        "method": (
            f"Lấy mẫu {BEARINGS} hướng × {len(RADII_KM)} vòng "
            f"({', '.join(f'{r:.0f}' for r in RADII_KM)} km), giữ lại điểm cao "
            f"hơn thửa ≥{MIN_DROP_M:.0f} m, cân theo độ dốc về phía thửa "
            "(mét chênh cao trên mỗi km)."),
        "caveat": (
            "KHÔNG phải lưu vực được phân định đúng cách — là nan quạt lấy mẫu "
            "theo hướng dốc lên, giả định nước chảy thẳng xuống dốc. Bỏ qua "
            "lòng sông, đê bao, cống và hồ chứa. Dùng như một đối chứng, không "
            "thay cho cảnh báo của cơ quan thuỷ văn."),
    }


def _km(la1: float, lo1: float, la2: float, lo2: float) -> float:
    from app.services import datasources as ds
    return ds._haversine_km(la1, lo1, la2, lo2)
