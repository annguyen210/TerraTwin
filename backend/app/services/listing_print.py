"""DẤU VÂN TAY TIN RAO — phát hiện tin bị CHÉP / ĐĂNG LẠI cho nhiều thửa và tin KHÁC THƯỜNG (nâng cấp 25/11/2026).

Chiêu quen của cò đất: cùng một bài "đất cao ráo, không bao giờ ngập, sổ hồng riêng" dán cho nhiều mảnh ở nhiều nơi. Mỗi
tin người dùng dán để kiểm được lấy DẤU VÂN TAY:
  · MinHash 64 số trên cụm 4 từ liền nhau (đã bỏ dấu, đã che số điện thoại/email/CCCD) — ước lượng độ giống Jaccard giữa
    hai tin mà KHÔNG lưu chữ nào của tin (không đảo ngược được ra nội dung). Lưu kèm tỉnh và toạ độ làm tròn ~1 km.
  · Tin mới giống ≥ 80% một tin đã kiểm ở chỗ CÁCH > 5 km → "dấu hiệu tin chép / đăng cho nhiều thửa". Cùng chỗ (người
    dùng kiểm lại) thì bỏ qua.
  · Isolation Forest (tự cài bằng numpy, 100 cây) trên 8 đặc trưng SỐ của tin (số lời cam kết tuyệt đối, số câu mâu thuẫn
    với số đo, từ hối thúc, từ "nhất"…) — chỉ chạy khi kho có ≥ 50 tin; điểm ≥ 0,62 gọi là "KHÁC THƯỜNG so với N tin đã
    kiểm", KHÔNG gọi là lừa đảo.
Ngưỡng chốt trước khi có dữ liệu (25/11/2026), không chỉnh theo kết quả.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import re
import time

K = 64
SHINGLE = 4
DUP_SIM = 0.80
FAR_KM = 5.0
IF_MIN = 50
IF_SCORE = 0.62
_IF_CACHE: dict = {"at": 0.0, "n": 0, "model": None}

_ABS = ("khong bao gio", "tuyet doi", "cam ket", "100%", "chac chan", "dam bao", "vinh vien")
_URGENT = ("ban gap", "can tien", "gap gap", "chi trong", "hom nay", "cat lo", "duy nhat", "nhanh tay", "co 1 khong 2")
_SUPER = ("nhat", "dep nhat", "re nhat", "hiem")


def _fold(s: str) -> str:
    from app.services.ai_guard import mask_pii
    import unicodedata
    s = mask_pii(s or "")[0]
    s = unicodedata.normalize("NFD", s.replace("đ", "d").replace("Đ", "D"))
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn").lower()
    return " ".join(re.findall(r"[a-z0-9%]+", s))


def shingles(text: str) -> set[str]:
    w = _fold(text).split()
    n = SHINGLE if len(w) >= 8 else 2
    return {" ".join(w[i:i + n]) for i in range(max(1, len(w) - n + 1))} if w else set()


def minhash(sh: set[str]) -> list[int]:
    if not sh:
        return []
    sig = []
    for seed in range(K):
        salt = seed.to_bytes(4, "little")
        sig.append(min(int.from_bytes(hashlib.blake2b(s.encode(), digest_size=8, salt=salt).digest(), "little") for s in sh))
    return sig


def similarity(a: list[int], b: list[int]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x == y for x, y in zip(a, b)) / len(a)


def features(text: str, result: dict) -> list[float]:
    f = _fold(text)
    counts = (result or {}).get("counts") or {}
    return [float(sum(f.count(k) for k in _ABS)), float(counts.get("contradicted", 0)), float(counts.get("consistent", 0)),
            float(sum(f.count(k) for k in _URGENT)), float(sum(len(re.findall(rf"\b{k}\b", f)) for k in _SUPER)),
            math.log1p(len(f.split())), float((text or "").count("!")), float(len((result or {}).get("claims") or []))]


# ---------------------------------------------------------------- Isolation Forest (numpy, không cần scikit-learn)

def _c(n: float) -> float:
    return 2 * (math.log(n - 1) + 0.5772156649) - 2 * (n - 1) / n if n > 2 else (1.0 if n == 2 else 0.0)


def _tree(X, depth, limit, rnd):
    import numpy as np
    if depth >= limit or len(X) <= 1:
        return ("leaf", len(X))
    live = [j for j in range(X.shape[1]) if X[:, j].min() < X[:, j].max()]   # chỉ chia theo cột còn biến thiên
    if not live:
        return ("leaf", len(X))
    q = rnd.choice(live)
    lo, hi = float(X[:, q].min()), float(X[:, q].max())
    p = rnd.uniform(lo, hi)
    m = X[:, q] < p
    return ("node", q, p, _tree(X[m], depth + 1, limit, rnd), _tree(X[~m], depth + 1, limit, rnd))


def _path(t, x, d=0):
    while t[0] == "node":
        t = t[3] if x[t[1]] < t[2] else t[4]
        d += 1
    return d + _c(t[1])


def fit_iforest(X, n_trees: int = 100, sample: int = 128, seed: int = 20261125) -> dict:
    import numpy as np
    X = np.asarray(X, float)
    rnd = random.Random(seed)
    s = min(sample, len(X))
    limit = math.ceil(math.log2(max(2, s)))
    trees = [_tree(X[rnd.sample(range(len(X)), s)], 0, limit, rnd) for _ in range(n_trees)]
    return {"trees": trees, "c": _c(s)}


def iforest_score(model: dict, x) -> float:
    """Điểm bất thường 0–1 (≈ 0,5 bình thường; càng gần 1 càng khác thường) — Liu, Ting & Zhou 2008."""
    h = sum(_path(t, x) for t in model["trees"]) / len(model["trees"])
    return round(2 ** (-h / model["c"]), 3) if model["c"] else 0.5


# ---------------------------------------------------------------- lưu + so

def _km(a, b, c, d) -> float:
    from app.services import datasources as ds
    return ds._haversine_km(a, b, c, d)


def record_and_compare(text: str, lat: float, lon: float, result: dict) -> dict:
    """Lưu dấu vân tay tin (không lưu chữ) và so với kho. → {reuse: [...], anomaly: {...}|None, n_prints}."""
    from sqlalchemy import select

    from app import db as _db
    from app.db import ListingPrint
    sig = minhash(shingles(text))
    feat = features(text, result)
    out: dict = {"reuse": [], "anomaly": None}
    if not sig:
        return out
    try:
        from app.services import flood_reports
        prov = (flood_reports.locate(lat, lon) or {}).get("province") or ""
    except Exception:  # noqa: BLE001
        prov = ""
    with _db.SessionLocal() as s:
        rows = s.execute(select(ListingPrint).order_by(ListingPrint.id.desc()).limit(5000)).scalars().all()
        for r in rows:
            sim = similarity(sig, json.loads(r.sig_json))
            if sim >= DUP_SIM and _km(lat, lon, r.lat_r, r.lon_r) > FAR_KM:
                out["reuse"].append({"similarity": round(sim, 2), "province": r.province, "date": r.created_at.date().isoformat(),
                                     "km": round(_km(lat, lon, r.lat_r, r.lon_r))})
        out["reuse"] = sorted(out["reuse"], key=lambda x: -x["similarity"])[:5]
        out["n_prints"] = len(rows)
        if len(rows) >= IF_MIN:
            now = time.time()
            if _IF_CACHE["model"] is None or now - _IF_CACHE["at"] > 3600 or abs(_IF_CACHE["n"] - len(rows)) > 50:
                _IF_CACHE.update(model=fit_iforest([json.loads(r.feat_json) for r in rows]), at=now, n=len(rows))
            sc = iforest_score(_IF_CACHE["model"], feat)
            out["anomaly"] = {"score": sc, "unusual": sc >= IF_SCORE, "n": len(rows)}
        s.add(ListingPrint(sig_json=json.dumps(sig), feat_json=json.dumps(feat), province=prov,
                           lat_r=round(lat, 2), lon_r=round(lon, 2)))
        s.commit()
    return out
