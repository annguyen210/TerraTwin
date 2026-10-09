"""ĐẤT CÓ ĐỔI KHÁC SAU 2021? — bằng AlphaEarth Foundations + bộ phân loại ĐÃ QUA KIỂM ĐỊNH (GĐ5).

Kiểm định đăng ký trước (data/ml/aef_landcover_protocol.json, commit 0f1997d): mIoU 0,420 trên 4 tỉnh mô hình
chưa từng thấy (ngưỡng 0,35; U-Net hai lần trước 0,232 và 0,314). Kết quả từng lớp: data/landcover_runs.json.

Cách dùng: vectơ AlphaEarth của ô 120 m quanh thửa cho NĂM 2021 và NĂM MỚI NHẤT có dữ liệu → bộ phân loại
tuyến tính → tỉ lệ từng nhóm (cây, trồng trọt, xây dựng, nước, đất trống). Hai năm cùng một mô hình nên chênh
lệch phản ánh thay đổi của mặt đất hơn là lệch giữa hai nguồn khác nhau.

NÓI THẲNG GIỚI HẠN: đây là DỰ ĐOÁN của mô hình (mIoU 0,42 — đúng khoảng 84% điểm ảnh trên tỉnh giữ lại), nên
KHÔNG vào hồ sơ ký số (quy tắc tin cậy: hồ sơ chỉ chứa số đo và số tính lại được). Lớp yếu: cây bụi, đất ngập
nước (IoU 0), rừng ngập mặn (0,11). Một nhóm đổi ≥ 25 điểm % mới gọi là "có đổi khác".
"""
from __future__ import annotations

import json
import os

import numpy as np

from app.services import cache_store
from app.services.reqlang import tr

MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "ml", "aef_landcover_model.json")
RADIUS_M = 60.0
CHANGE_PTS = 25.0
BASE_YEAR = 2021
GROUPS = ["tree", "open", "open", "crop", "built", "open", "open", "water", "water", "tree", "open"]   # theo WC_CODES
_TTL = 60 * 86400
_model: dict | None = None


def model() -> dict | None:
    global _model
    if _model is None and os.path.exists(MODEL):
        with open(MODEL, encoding="utf-8") as f:
            m = json.load(f)
        _model = {**m, "W": np.array(m["W"]), "b": np.array(m["b"])}
    return _model


def _composition(vecs: np.ndarray, m: dict) -> dict:
    pred = (vecs.astype("float64") @ m["W"] + m["b"]).argmax(1)
    n = len(pred)
    cls = np.bincount(pred, minlength=len(m["classes"])) / n * 100
    groups: dict[str, float] = {}
    for i, g in enumerate(GROUPS):
        groups[g] = round(groups.get(g, 0.0) + float(cls[i]), 1)
    top = [{"name": m["classes"][i], "pct": round(float(cls[i]), 1)} for i in np.argsort(-cls) if cls[i] >= 1.0]
    return {"pixels": n, "groups_pct": groups, "classes": top}


def change(lat: float, lon: float) -> dict:
    from app.services import aef
    m = model()
    if m is None:
        return {"available": False, "message": tr("Mô hình loại đất chưa qua kiểm định nên chưa bật.",
                                                  "The land-cover model has not passed validation, so it is off.")}
    key = cache_store.make_key("aef-lc", round(lat, 5), round(lon, 5), m.get("miou_test"))
    hit = cache_store.get(key)
    if hit is not None:
        return hit
    d = RADIUS_M / 111_320.0
    dl = RADIUS_M / (111_320.0 * max(0.2, float(np.cos(np.radians(lat)))))
    latest = aef.YEARS[-1]
    years = {}
    for y in (BASE_YEAR, latest):
        v = aef.window(lat - d, lon - dl, lat + d, lon + dl, y)
        if len(v) < 20:
            out = {"available": False, "message": tr("AlphaEarth không có đủ điểm ảnh ở vị trí này.",
                                                     "AlphaEarth has too few pixels at this location.")}
            return out
        years[str(y)] = _composition(v, m)
    a, b = years[str(BASE_YEAR)]["groups_pct"], years[str(latest)]["groups_pct"]
    delta = {g: round(b.get(g, 0.0) - a.get(g, 0.0), 1) for g in ("tree", "crop", "built", "water", "open")}
    big = max(delta, key=lambda g: abs(delta[g]))
    changed = abs(delta[big]) >= CHANGE_PTS
    name = {"tree": tr("cây xanh", "trees"), "crop": tr("trồng trọt", "cropland"), "built": tr("xây dựng", "built-up"),
            "water": tr("mặt nước", "water"), "open": tr("đất trống / cỏ", "open land")}
    moved = sorted((g for g in delta if abs(delta[g]) >= CHANGE_PTS), key=lambda g: -abs(delta[g]))
    head = (tr("Có đổi khác từ " + str(BASE_YEAR) + " tới " + str(latest) + ": " + ", ".join(
                   f"{name[g]} {'tăng' if delta[g] > 0 else 'giảm'} {abs(delta[g]):g} điểm %" for g in moved) + ".",
               f"Changed from {BASE_YEAR} to {latest}: " + ", ".join(
                   f"{name[g]} {'up' if delta[g] > 0 else 'down'} {abs(delta[g]):g} points" for g in moved) + ".")
            if changed else
            tr(f"Chưa thấy đổi khác lớn từ {BASE_YEAR} tới {latest} (không nhóm nào đổi ≥ {CHANGE_PTS:g} điểm %).",
               f"No large change from {BASE_YEAR} to {latest} (no group moved ≥ {CHANGE_PTS:g} points)."))
    out = {
        "available": True, "evidence_class": "predicted", "changed": changed, "headline": head,
        "base_year": BASE_YEAR, "latest_year": latest, "years": years, "delta_pts": delta,
        "model": {"miou_holdout": m.get("miou_test"), "protocol": m.get("protocol"),
                  "holdout": "Cần Giờ, Cần Thơ, Hà Giang, Đà Nẵng"},
        "caveat": tr("DỰ ĐOÁN của mô hình (mIoU 0,42 trên 4 tỉnh mô hình chưa thấy, ~84% điểm ảnh đúng) — tham khảo, "
                     "không vào hồ sơ ký số. Yếu với cây bụi, đất ngập nước, rừng ngập mặn.",
                     "MODEL PREDICTION (mIoU 0.42 on 4 unseen provinces, ~84% of pixels correct) — for reference, not "
                     "part of the signed dossier. Weak on shrubland, wetland and mangroves."),
        "attribution": "The AlphaEarth Foundations Satellite Embedding dataset is produced by Google and Google DeepMind.",
    }
    cache_store.put(key, out, _TTL)
    return out
