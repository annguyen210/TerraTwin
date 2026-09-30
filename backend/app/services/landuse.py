"""Loại đất THẬT tại thửa — ESA WorldCover 10 m, qua Microsoft Planetary Computer.

VÌ SAO CÓ TỆP NÀY. "Kế hoạch thửa" từng tính "giá trị đang chịu rủi ro" theo cây
lúa cho MỌI điểm, kể cả giữa thành phố Huế: ~20 triệu/ha lúa trên nền bê tông.
Với người thẩm định (ngân hàng, bảo hiểm, người mua đất) đó là con số sai hiển
nhiên — và một con số sai hiển nhiên làm mất tin mọi con số còn lại. Cần biết
thửa là đất gì TRƯỚC khi quy ra tiền theo cây trồng.

NGUỒN. ESA WorldCover 2021 v200: bản đồ lớp phủ toàn cầu 10 m, 11 lớp, do Cơ quan
Vũ trụ châu Âu phát hành, độ chính xác tổng thể công bố ~76,7%. Planetary
Computer tính sẵn biểu đồ lớp (categorical) trên máy chủ của họ — không cần
khoá, không cần rasterio trên máy chủ này. Cùng nguồn nhãn với lớp học sâu A1
(app/dl), nên hai lớp nói cùng một "ngôn ngữ" 11 lớp.

GIỚI HẠN, nói thẳng: bản đồ năm 2021 — đất mới xây sau đó chưa có; độ phân giải
10 m nên thửa nhỏ hơn ~3 điểm ảnh bị lẫn với xung quanh. Kết quả luôn kèm năm,
nguồn và tỉ lệ từng lớp để người đọc tự đánh giá, không chỉ một nhãn.

ĐÃ KIỂM CHỨNG (29/9/2026): giữa phố Huế (16,46; 107,59) → 100% bề mặt xây dựng.
"""
from __future__ import annotations

import urllib.parse

from app.services import cache_store, mpc
from app.services.reqlang import tr

COLLECTION = "esa-worldcover"
SOURCE = "ESA WorldCover 2021 v200 (10 m)"
RADIUS_M = 60.0            # ô ~120 m × 120 m ≈ 144 điểm ảnh quanh tâm thửa
_TTL = 90 * 86400          # bản đồ 2021 không đổi — cache lâu
_CACHE_V = 1               # đổi cách tính → tăng số này (cache bền, xem cache_store)

# Mã WorldCover → (tên VI, tên EN, nhóm dùng cho kế hoạch thửa)
CLASSES: dict[int, tuple[str, str, str]] = {
    10: ("Tán cây", "Tree cover", "tree"),
    20: ("Cây bụi", "Shrubland", "open"),
    30: ("Đồng cỏ", "Grassland", "open"),
    40: ("Đất trồng trọt", "Cropland", "crop"),
    50: ("Bề mặt xây dựng", "Built-up", "built"),
    60: ("Đất trống", "Bare / sparse vegetation", "open"),
    70: ("Băng tuyết", "Snow and ice", "open"),
    80: ("Mặt nước", "Permanent water", "water"),
    90: ("Đất ngập nước", "Herbaceous wetland", "water"),
    95: ("Rừng ngập mặn", "Mangroves", "tree"),
    100: ("Rêu, địa y", "Moss and lichen", "open"),
}

# Một nhóm chiếm từ mức này trở lên thì coi là loại đất CHÍNH của thửa.
DOMINANT_PCT = 50.0


def _item_id(box: list[float]) -> str | None:
    """Tấm WorldCover MỚI NHẤT phủ vùng này (2021 v200 thay 2020 v100)."""
    r = mpc._call(mpc.STAC, {"collections": [COLLECTION], "bbox": box, "limit": 5})
    if not r or not r.get("features"):
        return None
    feats = sorted(r["features"],
                   key=lambda f: f.get("properties", {}).get("start_datetime", ""))
    return feats[-1].get("id")


def _histogram(item_id: str, box: list[float]) -> dict[int, float] | None:
    q = urllib.parse.urlencode({"collection": COLLECTION, "item": item_id,
                                "assets": "map", "categorical": "true"})
    r = mpc._call(f"{mpc.DATA}?{q}", mpc._poly(box))
    if not r:
        return None
    try:
        st = list(r["properties"]["statistics"].values())[0]
        counts, codes = st["histogram"][0], st["histogram"][1]
    except (KeyError, IndexError, TypeError):
        return None
    out: dict[int, float] = {}
    for n, c in zip(counts, codes):
        try:
            code = int(round(float(c)))
        except (TypeError, ValueError):
            continue
        if code in CLASSES and n:
            out[code] = out.get(code, 0.0) + float(n)
    return out or None


def fetch_raw(lat: float, lon: float, radius_m: float = RADIUS_M) -> dict | None:
    """Biểu đồ lớp thô {item, hist} — KHÔNG phụ thuộc ngôn ngữ, gọi được từ
    luồng khác (advisor chạy song song với lượt quét). None nếu không gọi được."""
    key = cache_store.make_key("landuse", _CACHE_V, round(lat, 4), round(lon, 4),
                               int(radius_m))
    raw = cache_store.get(key)
    if raw is None:
        box = mpc.bbox_around(lat, lon, radius_m)
        item = _item_id(box)
        hist = _histogram(item, box) if item else None
        if not hist:
            return None
        raw = {"item": item, "hist": {str(k): v for k, v in hist.items()}}
        cache_store.put(key, raw, ttl_seconds=_TTL)
    return raw


def composition(lat: float, lon: float, radius_m: float = RADIUS_M) -> dict | None:
    """Tỉ lệ từng lớp WorldCover quanh thửa. None nếu không gọi được (KHÁC rỗng).

    Trả: source, year, pixels, classes [{code, name, pct}] (giảm dần),
    group_pct {tree, open, crop, built, water}, dominant_group (hoặc 'mixed').
    Tên lớp dịch lúc GỌI, không lưu trong cache — cache dùng chung hai ngôn ngữ.
    """
    raw = fetch_raw(lat, lon, radius_m)
    return describe(raw) if raw else None


def describe(raw: dict) -> dict:
    hist = {int(k): float(v) for k, v in raw["hist"].items()}
    total = sum(hist.values())
    classes = [
        {"code": code, "name": tr(CLASSES[code][0], CLASSES[code][1]),
         "group": CLASSES[code][2], "pct": round(100.0 * n / total, 1)}
        for code, n in sorted(hist.items(), key=lambda kv: -kv[1])
    ]
    groups: dict[str, float] = {}
    for c in classes:
        groups[c["group"]] = round(groups.get(c["group"], 0.0) + c["pct"], 1)
    top_group, top_pct = max(groups.items(), key=lambda kv: kv[1])
    dominant = top_group if top_pct >= DOMINANT_PCT else "mixed"
    year = "2021" if "2021" in (raw.get("item") or "") else (
        "2020" if "2020" in (raw.get("item") or "") else None)
    return {
        "source": SOURCE if year != "2020" else "ESA WorldCover 2020 v100 (10 m)",
        "year": year, "item": raw.get("item"), "pixels": int(total),
        "classes": classes, "group_pct": groups,
        "dominant_group": dominant, "dominant_pct": top_pct,
        "label": _label(dominant, classes),
    }


def _label(dominant: str, classes: list[dict]) -> str:
    if dominant == "mixed":
        parts = ", ".join(f"{c['name']} {c['pct']:.0f}%" for c in classes[:3])
        return tr(f"Đất hỗn hợp ({parts})", f"Mixed land ({parts})")
    top = next(c for c in classes if c["group"] == dominant)
    return f"{top['name']} {top['pct']:.0f}%" if len(classes) > 1 else top["name"]


# Loại canh tác gợi ý mặc định theo nhóm đất. None = không đoán: hỏi người dùng.
DEFAULT_CROP_BY_GROUP = {"crop": "lua"}


def crop_applicability(lu: dict | None) -> dict:
    """Quy ra tiền theo cây trồng có nghĩa ở thửa này không?

    applicable  — có tính giá trị vụ theo cây trồng hay không
    default_crop — cây giả định mặc định (chỉ khi là đất trồng trọt), hoặc None
    reason      — câu giải thích khi không tính / cần người dùng chọn
    """
    if lu is None:
        return {"applicable": True, "default_crop": "lua", "reason": tr(
            "Chưa xác định được loại đất (không gọi được ESA WorldCover) — tạm giả "
            "định lúa; đổi loại canh tác nếu sai.",
            "Could not determine the land type (ESA WorldCover unreachable) — "
            "assuming rice for now; change the crop type if wrong.")}
    g, pct = lu["dominant_group"], lu["dominant_pct"]
    if g == "built":
        return {"applicable": False, "default_crop": None, "reason": tr(
            f"Thửa là bề mặt xây dựng ({pct:.0f}% theo {lu['source']}) — không có "
            "vụ mùa để quy ra tiền. Nếu đây thật là đất canh tác, chọn loại cây ở "
            "dưới để tính.",
            f"This plot is built-up land ({pct:.0f}% per {lu['source']}) — there is "
            "no crop to value. If it really is farmland, pick a crop below.")}
    if g == "water":
        return {"applicable": False, "default_crop": None, "reason": tr(
            f"Thửa chủ yếu là mặt nước / đất ngập nước ({pct:.0f}% theo "
            f"{lu['source']}). Nếu là ao nuôi, chọn \"Tôm / thuỷ sản\" để tính.",
            f"This plot is mostly water / wetland ({pct:.0f}% per {lu['source']}). "
            "If it is an aquaculture pond, pick \"Shrimp / aquaculture\".")}
    if g in DEFAULT_CROP_BY_GROUP:
        return {"applicable": True, "default_crop": DEFAULT_CROP_BY_GROUP[g],
                "reason": None}
    return {"applicable": False, "default_crop": None, "reason": tr(
        f"Loại đất: {lu['label']} (theo {lu['source']}) — không đoán được đang "
        "trồng gì. Chọn loại canh tác ở dưới để quy ra tiền.",
        f"Land type: {lu['label']} (per {lu['source']}) — the crop can't be "
        "inferred. Pick a crop type below to value it.")}
