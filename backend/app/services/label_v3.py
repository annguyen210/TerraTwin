"""GÁN NHÃN KIỂM ĐỊNH EUDR v3 — người giải đoán ảnh năm 2020 làm thước đo, không phải bản đồ.

VÌ SAO CÓ TỆP NÀY. Kiểm định v2 (6/10/2026) trượt, và khi xem lại thì 12/16 ô "không phải
rừng" bị chấm sai là nơi cây mọc/trồng SAU năm 2000: thước đo Hansen theo năm 2000 không
biết chúng, còn EUDR hỏi trạng thái 31/12/2020. Không quy tắc nào chấm đúng được trên một
thước đo lệch mốc. Nên lần này thước đo là NGƯỜI: hai người độc lập nhìn ảnh độ phân giải
cao cuối 2020 + ảnh Sentinel-2 có ngày, trả lời "năm 2020 ô này là gì" theo đúng định nghĩa
EUDR (Điều 2(4)–(6) Quy định 2023/1115: rừng trồng lấy gỗ LÀ rừng; cao su, cà phê, điều, cây
ăn quả, nông lâm kết hợp KHÔNG phải rừng).

MÙ: API gán nhãn chỉ trả toạ độ + ảnh. Không trả tầng lấy mẫu, kết quả ba bản đồ, mô hình
hay nhãn của người kia — người gán không được biết máy nghĩ gì.

Tệp này THUẦN (không gọi mạng): lớp nhãn, giao thức, đọc mẫu, dựng khung xem, tính độ
đồng thuận và nhóm sự thật. Lấy mẫu và chạy chấm (cần mạng) ở app/eudr_validate_v3.py.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
from functools import lru_cache

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "..", "data")
SAMPLE_V3 = os.path.join(DATA, "eudr_validation_sample_v3.json")
PROTOCOL_V3 = os.path.join(DATA, "eudr_validation_protocol_v3.json")

COVER = {
    "natural_forest": ("Rừng tự nhiên", "Natural forest"),
    "planted_forest": ("Rừng trồng lấy gỗ (keo, bạch đàn, thông…)", "Timber plantation (acacia, eucalyptus, pine…)"),
    "tree_crop": ("Cây trồng lâu năm: cà phê, cao su, điều, tiêu, cây ăn quả, nông lâm kết hợp",
                  "Tree crop: coffee, rubber, cashew, pepper, orchard, agroforestry"),
    "no_trees": ("Không có tán cây: lúa, hoa màu, cỏ, đất trống, nhà, mặt nước",
                 "No tree cover: rice, annual crops, grass, bare land, buildings, water"),
    "unclear": ("Không xác định được (ảnh mờ, mây, ảnh quá cũ)", "Cannot tell (blurry, cloud, image too old)"),
}
FOREST = frozenset({"natural_forest", "planted_forest"})        # là rừng theo EUDR
NOT_FOREST = frozenset({"tree_crop", "no_trees"})
LOSS = ("yes", "no", "unclear")

WAYBACK_TILE = ("https://wayback.maptiles.arcgis.com/arcgis/rest/services/World_Imagery/WMTS/1.0.0/"
                "default028mm/MapServer/tile/{release}/{z}/{y}/{x}")
WAYBACK = {
    "before": {"release": 29260, "release_date": "2020-12-16",
               "metadata": "https://metadata.maptiles.arcgis.com/arcgis/rest/services/World_Imagery_Metadata_2020_r16/MapServer"},
    "after": {"release": 26334, "release_date": "2026-08-05",
              "metadata": "https://metadata.maptiles.arcgis.com/arcgis/rest/services/World_Imagery_Metadata_2026_r07/MapServer"},
}
ZOOM = 17
S2_DATA = "https://planetarycomputer.microsoft.com/api/data/v1/item/bbox"
S2_TRUE = "assets=visual&asset_bidx=visual%7C1%2C2%2C3&nodata=0"

PROTOCOL_DOC_V3 = {
    "title": "Kiểm định sàng lọc EUDR v3 trên NHÃN NGƯỜI GIẢI ĐOÁN ẢNH NĂM 2020",
    "registered": "2026-10-06",
    "why": ("v2 trượt (M3 0,60 < 0,70) và chẩn đoán cho thấy thước đo Hansen theo năm 2000 lệch mốc EUDR "
            "31/12/2020: 12/16 ô sai là cây mọc/trồng sau 2000. Lần này sự thật là nhãn của người."),
    "rules": {
        "primary": "terratwin.eudr-screen/3",
        "secondary": "terratwin.eudr-screen/2",
        "baseline": "terratwin.eudr-screen/1 (đang chạy production — chỉ để so sánh)",
        "v3_change": ("Như v2, thêm MỘT nhánh: thửa KHÔNG có dấu hiệu mất cây mà ≥2 bản đồ thấy ≥50% tán cây "
                      "năm 2020 → hỏi mô hình 'rừng hay vườn cây' (nhịp sinh trưởng 12 tháng Sentinel-2, đã đạt "
                      "kiểm định riêng 4/10/2026); xác suất rừng ≤ 0,2 → ĐẠT, ngược lại → CẦN XEM LẠI như v2. "
                      "Không có mô hình → CẦN XEM LẠI (thận trọng). v3 không bao giờ nặng hơn v2 (có test)."),
        "foc_threshold": ("0,2 chọn trên tập KIỂM ĐỊNH (614 mẫu) của mô hình rừng-hay-vườn: 4,6% rừng bị gọi là "
                          "vườn, nhận ra 72,7% vườn. Không nhìn mẫu v3 khi chọn."),
    },
    "development_sets": ("Mẫu v1 (seed 20261003), mẫu v2 (seed 20261006), tập kiểm định của mô hình rừng-hay-vườn. "
                         "Không dùng để kết luận."),
    "region": {"boxes": [
        {"name": "Tây Nguyên", "lat": [11.3, 15.0], "lon": [107.2, 109.0], "commodity": "cà phê"},
        {"name": "Đông Nam Bộ", "lat": [10.8, 12.2], "lon": [106.2, 107.6], "commodity": "cao su"}]},
    "seed": 20261007,
    "windows": 240,
    "window_px": 160,
    "per_stratum": 60,
    "exclude_km_from_previous": 1.0,
    "plot": "ô vuông 4×4 điểm ảnh Hansen (~111 m × 109 m ≈ 1,2 ha), đúng ranh điểm ảnh",
    "strata": {
        "_note": ("Tầng CHỈ để lấy đủ ca khó (Hansen GFC v1.12). Sự thật là nhãn người; tầng không bao giờ "
                  "hiện cho người gán."),
        "S_loss": "≥50% điểm ảnh lossyear 21–24 VÀ treecover2000 TB ≥30%",
        "S_old_trees": "không mất cây 2001–2024 VÀ treecover2000 TB ≥70%",
        "S_new_trees": "không mất cây VÀ treecover2000 TB <10% VÀ ≥25% điểm ảnh có 'gain' 2000–2012",
        "S_open": "không mất cây VÀ treecover2000 TB <10% VÀ không điểm ảnh nào có 'gain'",
    },
    "labeling": {
        "imagery": ["Esri World Imagery Wayback bản 16/12/2020 (ảnh ≤0,5 m; hiện NGÀY CHỤP thật của từng ảnh)",
                    "Esri World Imagery Wayback bản 05/08/2026", "Sentinel-2 L2A mùa khô (1–4) năm 2020",
                    "Sentinel-2 L2A mùa khô (1–4) năm 2026"],
        "question_cover": "Ngày 31/12/2020, phần lớn ô (khung đỏ) là gì?",
        "classes": {k: v[0] for k, v in COVER.items()},
        "eudr_forest": sorted(FOREST),
        "not_forest": sorted(NOT_FOREST),
        "question_loss": "Sau 31/12/2020, ô có mất tán cây không (chặt, đốt, chuyển đổi — từ khoảng 1/4 ô trở lên)?",
        "labelers": ("≥2 người ĐỘC LẬP, đã đọc hướng dẫn; không xem nhãn người khác, không xem kết quả bản đồ, "
                     "mô hình hay Hansen; không mở tệp mẫu."),
        "agreement": ("Ô vào bộ chấm khi có ≥2 nhãn, không ai chọn 'không xác định', mọi người cùng rừng/không "
                      "rừng; với ô rừng thì cùng mất/không mất (không ai 'không rõ'). Công bố Cohen's kappa."),
    },
    "truth_sets": {
        "T_lost": "rừng năm 2020 VÀ mất tán cây sau mốc",
        "T_forest": "rừng năm 2020 VÀ không mất",
        "T_clean": "không phải rừng năm 2020 (cây trồng lâu năm hoặc không có cây), bất kể sau đó",
    },
    "metrics": {
        "M1_detect_lost": "tỉ lệ ô T_lost được gắn review/high",
        "M2_flag_forest": "tỉ lệ ô T_forest được gắn review/high",
        "M3_pass_clean": "tỉ lệ ô T_clean được gắn low",
    },
    "pass_thresholds": {"M1_detect_lost": 0.80, "M2_flag_forest": 0.80, "M3_pass_clean": 0.70},
    "min_n_per_set": 25,
    "unknown_policy": "'unknown' (thiếu dữ liệu) tính là SAI cho mọi nhóm",
    "decision": ("v3 đạt cả ba ngưỡng, mỗi nhóm ≥25 ô → bật v3. v3 trượt mà v2 đạt → bật v2. Cả hai trượt → "
                 "giữ v1, công bố. Nhóm nào <25 ô → CHƯA KẾT LUẬN; gán thêm theo đúng thứ tự mẫu, không chọn ô. "
                 "Chấm MỘT lần sau khi khoá nhãn; không chỉnh quy tắc rồi chấm lại trên mẫu này."),
}


# ------------------------------------------------------------------ mẫu

@lru_cache(maxsize=2)
def _sample_cached(path: str, mtime: float) -> dict | None:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_sample() -> dict | None:
    try:
        return _sample_cached(SAMPLE_V3, os.path.getmtime(SAMPLE_V3))
    except (OSError, ValueError):
        return None


def cells() -> list[dict]:
    s = load_sample()
    return (s or {}).get("cells") or []


def order_for(user_id: int, n: int) -> list[int]:
    """Thứ tự ô RIÊNG cho mỗi người (tất định): hai người không cùng mệt ở cùng một đoạn."""
    seed = int(hashlib.sha256(f"{PROTOCOL_DOC_V3['seed']}:{user_id}".encode()).hexdigest()[:12], 16)
    idx = list(range(n))
    random.Random(seed).shuffle(idx)
    return idx


def _tile_xy(lat: float, lon: float, z: int) -> tuple[float, float]:
    n = 2 ** z
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n
    return x, y


def mosaic(c: dict, z: int = ZOOM, size: int = 3) -> dict:
    """Lưới size×size ô ảnh quanh tâm ô + vị trí khung ô (theo % của lưới)."""
    lat, lon = (c["lat0"] + c["lat1"]) / 2, (c["lon0"] + c["lon1"]) / 2
    cx, cy = _tile_xy(lat, lon, z)
    x0, y0 = int(cx) - size // 2, int(cy) - size // 2
    ax, ay = _tile_xy(c["lat1"], c["lon0"], z)       # góc trên-trái (lat lớn, lon nhỏ)
    bx, by = _tile_xy(c["lat0"], c["lon1"], z)
    pct = lambda v, o: round((v - o) / size * 100, 3)  # noqa: E731
    return {"z": z, "x0": x0, "y0": y0, "size": size,
            "box": {"left": pct(ax, x0), "top": pct(ay, y0),
                    "width": round((bx - ax) / size * 100, 3), "height": round((by - ay) / size * 100, 3)}}


def _s2_url(item: str, bbox: list[float]) -> str:
    bb = ",".join(f"{v:.5f}" for v in bbox)
    return f"{S2_DATA}/{bb}.png?collection=sentinel-2-l2a&item={item}&width=384&height=384&{S2_TRUE}"


def view(k: int) -> dict | None:
    """Thứ người gán nhãn ĐƯỢC thấy về ô k — toạ độ và ảnh, KHÔNG có tầng hay kết quả máy."""
    cs = cells()
    if not 0 <= k < len(cs):
        return None
    c = cs[k]
    m = mosaic(c)
    img = c.get("imagery") or {}
    wb = {}
    for when, meta in WAYBACK.items():
        wb[when] = {"release_date": meta["release_date"],
                    "acquired": (img.get("wayback") or {}).get(when, {}).get("date"),
                    "resolution_m": (img.get("wayback") or {}).get(when, {}).get("res_m"),
                    "source": (img.get("wayback") or {}).get(when, {}).get("source"),
                    "tiles": [[WAYBACK_TILE.format(release=meta["release"], z=m["z"], y=m["y0"] + r, x=m["x0"] + col)
                               for col in range(m["size"])] for r in range(m["size"])]}
    s2 = {}
    for when, v in (img.get("s2") or {}).items():
        if v and v.get("item") and v.get("bbox"):
            bb = v["bbox"]
            s2[when] = {"date": v.get("date"), "cloud_pct": v.get("cloud_pct"), "url": _s2_url(v["item"], bb),
                        "box": {"left": round((c["lon0"] - bb[0]) / (bb[2] - bb[0]) * 100, 3),
                                "top": round((bb[3] - c["lat1"]) / (bb[3] - bb[1]) * 100, 3),
                                "width": round((c["lon1"] - c["lon0"]) / (bb[2] - bb[0]) * 100, 3),
                                "height": round((c["lat1"] - c["lat0"]) / (bb[3] - bb[1]) * 100, 3)}}
        else:
            s2[when] = None
    lat, lon = (c["lat0"] + c["lat1"]) / 2, (c["lon0"] + c["lon1"]) / 2
    return {"cell": k, "center": {"lat": round(lat, 6), "lon": round(lon, 6)},
            "bounds": [c["lon0"], c["lat0"], c["lon1"], c["lat1"]], "area_ha": 1.2,
            "mosaic_box": m["box"], "wayback": wb, "s2": s2}


# ------------------------------------------------------------------ đồng thuận & sự thật

def _binary_forest(cover: str) -> bool | None:
    return True if cover in FOREST else False if cover in NOT_FOREST else None


def kappa(pairs: list[tuple[bool, bool]]) -> float | None:
    """Cohen's kappa nhị phân. None khi không tính được (ít cặp, hoặc cả hai luôn cùng một đáp án)."""
    n = len(pairs)
    if n < 2:
        return None
    po = sum(1 for a, b in pairs if a == b) / n
    pa, pb = sum(1 for a, _ in pairs if a) / n, sum(1 for _, b in pairs if b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return None if pe >= 1 else round((po - pe) / (1 - pe), 3)


def truth(labels: list[dict]) -> dict:
    """labels: [{"cell", "user_id", "cover2020", "loss"}] → nhóm sự thật từng ô + độ đồng thuận.

    Một ô vào bộ chấm CHỈ khi ≥2 người gán, không ai chọn 'không xác định', mọi người cùng
    rừng/không rừng; ô rừng thì mọi người cùng mất/không mất (không ai 'không rõ')."""
    by: dict[int, list[dict]] = {}
    for r in labels:
        by.setdefault(int(r["cell"]), []).append(r)
    sets: dict[int, str] = {}
    excluded = {"one_label": 0, "unclear": 0, "disagree_forest": 0, "disagree_loss": 0}
    pairs: list[tuple[bool, bool]] = []
    for cell, rs in sorted(by.items()):
        if len(rs) < 2:
            excluded["one_label"] += 1
            continue
        fb = [_binary_forest(r["cover2020"]) for r in rs]
        if all(x is not None for x in fb[:2]):
            pairs.append((fb[0], fb[1]))
        if any(x is None for x in fb):
            excluded["unclear"] += 1
            continue
        if len(set(fb)) > 1:
            excluded["disagree_forest"] += 1
            continue
        if not fb[0]:
            sets[cell] = "T_clean"
            continue
        ls = {r["loss"] for r in rs}
        if "unclear" in ls or len(ls) > 1:
            excluded["disagree_loss"] += 1
            continue
        sets[cell] = "T_lost" if ls == {"yes"} else "T_forest"
    n2 = sum(1 for rs in by.values() if len(rs) >= 2)
    return {"sets": sets, "counts": {t: sum(1 for v in sets.values() if v == t) for t in ("T_lost", "T_forest", "T_clean")},
            "cells_labeled": len(by), "cells_2plus": n2, "excluded": excluded,
            "kappa_forest": kappa(pairs), "agree_forest": round(sum(1 for a, b in pairs if a == b) / len(pairs), 3)
            if pairs else None}


def metrics(levels: dict[int, str], sets: dict[int, str]) -> dict:
    """levels: {ô: mức của một quy tắc} → M1, M2, M3 trên nhóm sự thật."""
    def share(t, ok):
        cs = [c for c, s in sets.items() if s == t]
        return round(sum(1 for c in cs if levels.get(c) in ok) / len(cs), 3) if cs else None
    return {"M1_detect_lost": share("T_lost", ("review", "high")),
            "M2_flag_forest": share("T_forest", ("review", "high")),
            "M3_pass_clean": share("T_clean", ("low",))}


def decide(m: dict, counts: dict) -> str:
    th, nmin = PROTOCOL_DOC_V3["pass_thresholds"], PROTOCOL_DOC_V3["min_n_per_set"]
    if any(counts.get(t, 0) < nmin for t in ("T_lost", "T_forest", "T_clean")):
        return "insufficient"
    return "pass" if all(m.get(k) is not None and m[k] >= v for k, v in th.items()) else "fail"
