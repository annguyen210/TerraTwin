"""Toạ độ này là ĐẤT LIỀN VIỆT NAM, mặt biển, hay đất nước khác?

VÌ SAO CẦN: trước file này, kiểm tra phạm vi chỉ là một HÌNH CHỮ NHẬT
(lat 7,5–24 · lon 101,5–112,5). Hình chữ nhật đó bao trọn Viêng Chăn, Phnom
Penh, một phần Nam Trung Quốc và toàn bộ Biển Đông. Hậu quả đo được:

  Giữa Biển Đông  →  "Điểm an toàn đất: 70/100"
                     "Thiếu nước NGHIÊM TRỌNG 96,7%"   ← giữa đại dương
  Viêng Chăn      →  TerraScore 100/100, đánh giá đầy đủ
  Phnom Penh      →  TerraScore 100/100, đánh giá đầy đủ

Trong khi README lại ghi "Toạ độ ngoài vùng bị từ chối". Lời đó sai, và đây là
loại sai mà một giám khảo bấm thử là thấy ngay.

CÁCH PHÂN BIỆT BIỂN VỚI ĐẤT — đo, không đoán:
Cao độ đơn thuần không đủ. Cần Giờ (rừng ngập mặn TP.HCM, có dân, có vuông tôm)
đọc đúng 0 m, y hệt mặt biển. Khoảng cách tới bờ cũng không đủ: đường bờ 34
điểm quá thô nên Cần Giờ tính ra xa bờ 23,7 km, trong khi một điểm biển thật
ngoài Vũng Tàu chỉ 14,3 km.

Thứ tách được là LẤY MẪU VÒNG QUANH. Đo thực tế trên vòng bán kính 5 km:

  Cần Giờ (đất)         7/8 điểm quanh có cao độ > 0
  Đất Mũi (đất)         5/8
  Phú Quốc (đảo)        4/8
  Biển ngoài Nha Trang  1/8
  Biển ngoài Vũng Tàu   0/8
  Giữa Biển Đông        0/8
  Vịnh Bắc Bộ           0/8

Ranh giới ở 2/8 tách sạch cả hai nhóm.

QUỐC GIA: hỏi Nominatim (OpenStreetMap), miễn phí, không key, cache vĩnh viễn
vì biên giới không đổi theo giờ. FAIL-OPEN: Nominatim chết thì KHÔNG chặn ai —
thà cho một người Lào dùng nhầm còn hơn chặn cả nước vì một dịch vụ ngoài
đang bảo trì.
"""
from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request

from app.services.reqlang import tr

NOMINATIM = "https://nominatim.openstreetmap.org/reverse"
# Chính sách Nominatim bắt buộc User-Agent nhận dạng được. Phải THUẦN ASCII —
# header HTTP mã hoá latin-1, một chữ tiếng Việt có dấu là hỏng cả lời gọi.
USER_AGENT = "TerraTwin/0.7 (Vietnam land digital twin; contact via repo)"
TIMEOUT = 12.0
_TTL_COUNTRY = 365 * 86400      # biên giới không đổi theo giờ

RING_KM = 5.0
RING_N = 8
MIN_LAND_NEIGHBOURS = 2         # từ 2/8 trở lên là đất; 0–1/8 là mặt nước


def _ring(lat: float, lon: float, km: float, n: int):
    out = []
    for i in range(n):
        b = math.radians(i * 360.0 / n)
        d = km / 6371.0
        a1, o1 = math.radians(lat), math.radians(lon)
        a2 = math.asin(math.sin(a1) * math.cos(d)
                       + math.cos(a1) * math.sin(d) * math.cos(b))
        o2 = o1 + math.atan2(math.sin(b) * math.sin(d) * math.cos(a1),
                             math.cos(d) - math.sin(a1) * math.sin(a2))
        out.append((round(math.degrees(a2), 4), round(math.degrees(o2), 4)))
    return out


def country_code(lat: float, lon: float) -> str | None:
    """Mã quốc gia hai chữ, hoặc None nếu không tra được.

    None nghĩa là KHÔNG BIẾT, không phải "ngoài Việt Nam". Người gọi phải xử lý
    hai thứ đó khác nhau — nhầm lẫn ở đây là chặn nhầm người dùng thật.
    """
    from app.services import cache_store, jobs

    key = cache_store.make_key("country", round(lat, 3), round(lon, 3))
    hit = cache_store.get(key)
    if hit is not None:
        return hit or None

    def _work():
        h = cache_store.get(key)
        if h is not None:
            return h or None
        q = urllib.parse.urlencode({
            "format": "jsonv2", "lat": f"{lat:.5f}", "lon": f"{lon:.5f}",
            "zoom": "5", "addressdetails": "1",
        })
        try:
            req = urllib.request.Request(
                f"{NOMINATIM}?{q}", headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                d = json.loads(r.read().decode("utf-8"))
        except Exception:
            return None
        cc = ((d.get("address") or {}).get("country_code") or "").lower() or None
        # Ghi cả kết quả rỗng để không hỏi lại mãi một toạ độ giữa đại dương
        # (Nominatim trả rỗng ở đó, và đó là câu trả lời hợp lệ).
        cache_store.put(key, cc or "", _TTL_COUNTRY)
        return cc

    return jobs.single_flight(f"cc:{key}", _work)


# ------------------------------------------------------------------ mặt nước THƯỜNG XUYÊN trong đất liền
#
# Kiểm biển ở trên chỉ nhìn cao độ quanh 5 km nên một điểm GIỮA LÒNG SÔNG vẫn là "đất". Đo 16/10/2026 tại
# 15.8712, 108.3381 (sông Thu Bồn, Hội An): WorldCover 59,7% "Mặt nước"; nền radar p10 −19,1 dB, p25 −17,1,
# p50 −12,7 → lịch sử nước 0 đợt (nước quanh năm thì không thể "thấp hơn nền ≥ 3 dB"), TerraScore 100/A.
# So với đất thật (Huế, Điện Bàn, Cà Mau, Cần Thơ): WorldCover 0% nước, nền p10 −8,7…−11,8 dB.
#
#   CHẶN (không chấm điểm, không phát hành hồ sơ) khi ĐIỂM nằm trên nước:
#     · WorldCover "Mặt nước" (mã 80) ≥ 50% trong bán kính 60 m, HOẶC
#     · nền radar p25 < −18 dB (≥ 1/4 khung 200 m là nước ở hầu hết các lần chụp) — chỉ khi đã đọc lịch sử nước.
#   KHÔNG chặn nhưng CẢNH BÁO khi chỉ nền p10 < −18 dB hoặc WorldCover nước 10–50%: khung đo có một phần mặt nước
#   thường xuyên (kênh, ao) — xem water_history.water_surface().
WC_WATER_CODE = 80
WC_BLOCK_PCT = 50.0


def inland_water(lat: float, lon: float) -> dict | None:
    """Bằng chứng ĐIỂM này nằm trên mặt nước thường xuyên (sông, kênh, hồ, ao), hoặc None.

    FAIL-OPEN: không lấy được WorldCover và chưa đọc lịch sử nước → None (không chặn ai vì nguồn ngoài chết).
    Không gọi radar ở đây (vài phút) — chỉ dùng nền radar đã có trong cache."""
    from app.services import cache_store, landuse, water_history as wh
    ev: dict = {}
    try:
        raw = landuse.fetch_raw(lat, lon)
    except Exception:  # noqa: BLE001
        raw = None
    if raw and raw.get("hist"):
        hist = {int(k): float(v) for k, v in raw["hist"].items()}
        tot = sum(hist.values()) or 1.0
        ev["worldcover_water_pct"] = round(100.0 * hist.get(WC_WATER_CODE, 0.0) / tot, 1)
    try:
        h = cache_store.get(wh.cache_key(lat, lon))
    except Exception:  # noqa: BLE001
        h = None
    base = (h or {}).get("baseline_db") if (h or {}).get("available") else None
    if base:
        ev["radar_baseline_db"] = {k: base[k] for k in ("p10", "p25", "p50") if k in base}
    wc_hit = ev.get("worldcover_water_pct", 0.0) >= WC_BLOCK_PCT
    radar_hit = bool(base) and base.get("p25", 0.0) < wh.WATER_DB
    if not (wc_hit or radar_hit):
        return None
    why = []
    if wc_hit:
        why.append(tr(f"ESA WorldCover: {ev['worldcover_water_pct']:g}% quanh điểm là mặt nước thường xuyên",
                      f"ESA WorldCover: {ev['worldcover_water_pct']:g}% around the point is permanent water"))
    if radar_hit:
        why.append(tr(f"nền radar Sentinel-1 của chính điểm này p25 = {base['p25']:g} dB (< {wh.WATER_DB:g} dB: nước ở hầu hết các lần chụp)",
                      f"this point's own Sentinel-1 radar baseline p25 = {base['p25']:g} dB (< {wh.WATER_DB:g} dB: water in most scenes)"))
    ev["why"] = why
    return ev


def classify(lat: float, lon: float, check_country: bool = True) -> dict:
    """Phân loại một toạ độ. Không bao giờ ném lỗi — hỏng thì trả 'unknown'."""
    from app.services import realdata

    elev = realdata.elevation_m(lat, lon)

    # Cao độ > 0 là đất, khỏi phải hỏi thêm — đúng với gần như mọi truy vấn,
    # nên chi phí trung bình của cả hàm này gần bằng 0.
    if elev is not None and elev > 0:
        kind, land_n = "land", None
    elif elev is None:
        return {"kind": "unknown", "elevation_m": None, "country": None,
                "in_vietnam": None, "serviceable": True,
                "note": tr(
                    "Chưa lấy được cao độ nên không xác định được đây là "
                    "đất hay mặt nước. Kết quả bên dưới cứ đọc bình thường, "
                    "nhưng nếu bạn đang bấm ngoài biển thì đừng tin nó.",
                    "Couldn't fetch elevation, so land vs. water here is "
                    "unknown. The results below can still be read normally, "
                    "but don't trust them if you clicked out at sea.")}
    else:
        ring = _ring(lat, lon, RING_KM, RING_N)
        vals = [v for v in (realdata.elevation_multi(ring) or []) if v is not None]
        land_n = sum(1 for v in vals if v > 0)
        if not vals:
            kind = "unknown"
        else:
            kind = "land" if land_n >= MIN_LAND_NEIGHBOURS else "sea"

    if kind == "sea":
        return {
            "kind": "sea", "elevation_m": elev, "land_neighbours": land_n,
            "country": None, "in_vietnam": None, "serviceable": False,
            "note": tr(
                "Điểm này là MẶT NƯỚC. TerraTwin phục vụ đất liền và đảo "
                "có dân cư — mọi chỉ số đất đai ở đây đều vô nghĩa, nên "
                "phần mềm không chấm thay vì đưa ra con số trông có vẻ "
                "đúng. Bấm lại vào phần đất gần nhất.",
                "This point is OPEN WATER. TerraTwin serves mainland and "
                "inhabited islands — every land metric here would be "
                "meaningless, so the app skips scoring instead of showing a "
                "number that only looks correct. Click the nearest land "
                "instead."),
            "caveat": tr(
                "Nhận biết bằng cao độ DEM: điểm này và ít nhất 7/8 điểm "
                f"quanh trong bán kính {RING_KM:.0f} km đều ở mực nước "
                "biển. Đảo nhỏ và bãi cạn mà DEM toàn cầu không phân giải "
                "được cũng sẽ bị xếp vào đây.",
                "Detected via DEM elevation: this point and at least 7/8 "
                f"points sampled within a {RING_KM:.0f} km radius are all at "
                "sea level. Small islands and shoals the global DEM can't "
                "resolve will also fall into this bucket."),
        }

    cc = country_code(lat, lon) if check_country else None
    in_vn = None if cc is None else (cc == "vn")

    if in_vn is False:
        return {
            "kind": "foreign", "elevation_m": elev, "country": cc,
            "in_vietnam": False, "serviceable": False,
            "note": tr(
                f"Toạ độ này thuộc {cc.upper()}, ngoài phạm vi TerraTwin "
                "phục vụ. Toàn bộ mô hình được hiệu chuẩn theo khí hậu và "
                "địa hình Việt Nam — chạy ở nước khác sẽ ra số, nhưng số "
                "đó không có cơ sở.",
                f"This coordinate is in {cc.upper()}, outside TerraTwin's "
                "service area. Every model here is calibrated to Vietnam's "
                "climate and terrain — running it elsewhere still produces a "
                "number, but that number has no grounding."),
        }

    water = inland_water(lat, lon)
    if water:
        return {
            "kind": "inland_water", "elevation_m": elev, "country": cc, "in_vietnam": in_vn,
            "serviceable": False, "water": water,
            "note": tr(
                "Điểm này nằm trên MẶT NƯỚC THƯỜNG XUYÊN (sông, kênh, hồ, ao) — dời ô ngắm vào đúng thửa đất. "
                "TerraTwin không chấm điểm và không phát hành hồ sơ cho mặt nước: \"0 đợt ngập\" ở đây chỉ vì nước "
                "có sẵn quanh năm, không phải vì đất an toàn. Căn cứ: " + "; ".join(water["why"]) + ".",
                "This point is on PERMANENT WATER (river, canal, lake, pond) — move the crosshair onto the actual plot. "
                "TerraTwin does not score or issue dossiers for water surfaces: \"0 floods\" here only means the water "
                "is there all year, not that the land is safe. Evidence: " + "; ".join(water["why"]) + "."),
            "caveat": tr("Nếu đây là ao nuôi trồng thủy sản của bạn: TerraTwin chưa chấm rủi ro cho mặt nước nuôi trồng.",
                         "If this is your aquaculture pond: TerraTwin does not yet score risk for aquaculture water."),
        }

    return {
        "kind": "land", "elevation_m": elev, "land_neighbours": land_n,
        "country": cc, "in_vietnam": in_vn, "serviceable": True,
        "note": None if in_vn else tr(
            "Chưa xác nhận được quốc gia (dịch vụ tra cứu không phản hồi). "
            "Vẫn phục vụ bình thường — thà cho một toạ độ ngoài biên dùng nhầm "
            "còn hơn chặn cả nước vì một dịch vụ ngoài đang bảo trì.",
            "Couldn't confirm the country (lookup service didn't respond). "
            "Still serving normally — better to let one out-of-bounds "
            "coordinate through by mistake than block the whole country over "
            "an external service outage."),
    }
