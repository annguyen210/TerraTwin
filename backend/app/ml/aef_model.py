"""ALPHAEARTH (Google DeepMind, 2025) phân biệt RỪNG với VƯỜN CÂY — giao thức đặt trước, rồi mới chạy.

VÌ SAO. Mô hình rừng-hay-vườn hiện tại (Sentinel-2 12 tháng, app/ml/forest_or_crop.py) đạt BA 0,892 /
độ nhạy rừng 0,909 — sát ngưỡng. AlphaEarth là mô hình NỀN TẢNG: nén cả năm dữ liệu đa nguồn của mỗi
điểm 10 m thành vectơ 64 chiều. Câu hỏi đo được: chỉ 64 con số đó, với một bộ phân loại tuyến tính đơn
giản nhất, có tách rừng với vườn cây tốt bằng hay hơn 34 đặc trưng tự thiết kế không?

KỶ LUẬT NHƯ MỌI LẦN: ghi giao thức (data/ml/aef_protocol.json) + commit TRƯỚC khi tải đặc trưng và
huấn luyện; chấm tập kiểm tra MỘT lần; trượt thì công bố, không chỉnh rồi chấm lại.

    python -m app.ml.aef_model protocol     # ghi giao thức
    python -m app.ml.aef_model extract      # tải vectơ AlphaEarth 2020 cho 3.179 ô (~10 phút, lưu dần)
    python -m app.ml.aef_model train        # huấn luyện + chấm một lần → aef_runs.json, aef_model.json
"""
from __future__ import annotations

import argparse
import json
import math
import os
import time
from datetime import date

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "..", "data", "ml")
PROTOCOL = os.path.join(OUT, "aef_protocol.json")
FEATURES = os.path.join(OUT, "aef_features.npz")
RUNS = os.path.join(OUT, "aef_runs.json")
MODEL = os.path.join(OUT, "aef_model.json")
YEAR = 2020
HALF_DEG = 0.00045           # ô 100 m quanh tâm (≈ 11×11 điểm ảnh AlphaEarth) — đúng cỡ ô của bộ dữ liệu cũ
LAMBDAS = (0.01, 0.1, 1.0, 10.0)

PROTOCOL_DOC = {
    "title": "AlphaEarth Foundations phân biệt rừng / vườn cây — giao thức đặt trước",
    "registered": "2026-10-08",
    "data": ("AlphaEarth Foundations Satellite Embedding v1 (Google DeepMind), năm 2020, bản GeoZarr công khai "
             "source.coop/tge-labs/aef-mosaic (CC-BY 4.0). Ghi công: 'The AlphaEarth Foundations Satellite "
             "Embedding dataset is produced by Google and Google DeepMind.'"),
    "h1_weak_labels": {
        "points": ("ĐÚNG 3.179 ô 100 m của bộ dữ liệu rừng-hay-vườn (data/ml/foc_dataset.npz): cùng nhãn yếu "
                   "(nơi ba bản đồ đồng ý), cùng chia theo vĩ độ (huấn luyện 12,0–14,2; kiểm định 14,2–15,0; "
                   "kiểm tra 11,3–12,0)."),
        "feature": ("chỉ vectơ AlphaEarth 2020: trung bình các vectơ đơn vị trên ô 100 m rồi chuẩn hoá lại — 64 "
                    "chiều, không thêm đặc trưng nào khác. Ô không có dữ liệu bị loại và đếm công khai."),
        "model": ("hồi quy logistic L2, trọng số cân bằng lớp; độ mạnh L2 chọn trong {0,01; 0,1; 1; 10} theo độ "
                  "chính xác cân bằng trên tập KIỂM ĐỊNH; ngưỡng 0,5."),
        "pass": {"balanced_accuracy_test": 0.85, "forest_recall_test": 0.90},
        "comparator": "mô hình Sentinel-2 hiện tại trên cùng tập kiểm tra: BA 0,892, độ nhạy rừng 0,909 (chỉ báo cáo)",
        "decision": ("Đạt cả hai → bật làm TÍN HIỆU THAM KHẢO THỨ HAI (không vào hồ sơ ký, không vào quy tắc sàng "
                     "lọc). Không đạt → không bật, công bố."),
    },
    "h2_human_labels": {
        "data": "các ô ĐỒNG THUẬN của kiểm định v3 (hai người giải đoán ảnh 2020, eudr_validation_protocol_v3.json)",
        "task": "rừng năm 2020 (tự nhiên + rừng trồng gỗ) so với không phải rừng (cây trồng lâu năm + không có cây)",
        "model": "ĐÚNG mô hình đã khoá ở H1 — không huấn luyện lại trên nhãn người",
        "pass": {"balanced_accuracy": 0.85, "forest_recall": 0.90, "min_n_each_class": 25},
        "decision": ("Chấm MỘT lần cùng lúc với v3. Đạt → ứng viên cho quy tắc sàng lọc v4 (phải đăng ký riêng). "
                     "Trượt → công bố. Báo cáo kèm mô hình Sentinel-2 trên cùng các ô."),
    },
    "limits": [
        "Tập kiểm tra H1 là nhãn yếu (ca bản đồ đồng ý = ca dễ) — H2 trên nhãn người mới là phép thử chính.",
        "AlphaEarth học từ nhiều nguồn vệ tinh công khai; có thể đã thấy dữ liệu tương tự các bản đồ làm nhãn yếu → "
        "H1 có thể lạc quan.",
        "Độ đổi vectơ 2020→2025 (cosin) hiện trên giao diện là THỬ NGHIỆM, chưa kiểm định ở giao thức này.",
    ],
}


def write_protocol() -> None:
    with open(PROTOCOL, "w", encoding="utf-8") as f:
        json.dump(PROTOCOL_DOC, f, ensure_ascii=False, indent=1)


def extract(workers: int = 4) -> None:
    """Vectơ AlphaEarth 2020 cho từng ô của bộ dữ liệu cũ. Lưu dần (chạy lại tiếp được)."""
    from concurrent.futures import ThreadPoolExecutor

    from app.services import aef

    d = np.load(os.path.join(OUT, "foc_dataset.npz"))
    lat, lon = d["lat"].astype(float), d["lon"].astype(float)
    n = len(lat)
    emb = np.zeros((n, 64), "float32")
    npx = np.zeros(n, "int32")
    done = np.zeros(n, bool)
    if os.path.exists(FEATURES):
        old = np.load(FEATURES)
        emb[:], npx[:], done[:] = old["emb"], old["npx"], old["done"]
    # gom theo khối con 256 điểm ảnh để các luồng không tải trùng
    order = sorted(np.nonzero(~done)[0], key=lambda i: aef.pixel(lat[i], lon[i]))

    def one(i):
        v, k = aef.mean_embedding(lat[i] - HALF_DEG, lon[i] - HALF_DEG, lat[i] + HALF_DEG, lon[i] + HALF_DEG, YEAR)
        return i, v, k

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for c, (i, v, k) in enumerate(ex.map(one, order), 1):
            if v is not None:
                emb[i] = v
            npx[i], done[i] = k, True
            if c % 100 == 0 or c == len(order):
                np.savez_compressed(FEATURES, emb=emb, npx=npx, done=done)
                print(f"  {c}/{len(order)} · {time.time() - t0:.0f}s", flush=True)
    np.savez_compressed(FEATURES, emb=emb, npx=npx, done=done)
    print(f"xong: {int(done.sum())}/{n} ô, {int((npx == 0).sum())} ô không có dữ liệu")


def _fit(X: np.ndarray, y: np.ndarray, lam: float, iters: int = 50) -> tuple[np.ndarray, float]:
    """Logistic L2 bằng Newton (IRLS), trọng số cân bằng lớp. Không chuẩn hoá chặn (b)."""
    n, d = X.shape
    w_cls = np.where(y == 1, n / (2 * max(1, y.sum())), n / (2 * max(1, (1 - y).sum())))
    Xb = np.hstack([X, np.ones((n, 1))])
    beta = np.zeros(d + 1)
    R = lam * np.eye(d + 1)
    R[-1, -1] = 0.0
    for _ in range(iters):
        p = 1 / (1 + np.exp(-(Xb @ beta)))
        g = Xb.T @ (w_cls * (p - y)) + R @ beta
        H = (Xb * (w_cls * p * (1 - p))[:, None]).T @ Xb + R
        step = np.linalg.solve(H, g)
        beta -= step
        if np.abs(step).max() < 1e-8:
            break
    return beta[:-1], float(beta[-1])


def _metrics(p: np.ndarray, y: np.ndarray, thr: float = 0.5) -> dict:
    pred = p >= thr
    tp = int((pred & (y == 1)).sum()); fn = int((~pred & (y == 1)).sum())
    tn = int((~pred & (y == 0)).sum()); fp = int((pred & (y == 0)).sum())
    rec_f = tp / max(1, tp + fn); rec_c = tn / max(1, tn + fp)
    return {"balanced_accuracy": round((rec_f + rec_c) / 2, 4), "forest_recall": round(rec_f, 4),
            "tree_crop_recall": round(rec_c, 4), "accuracy": round((tp + tn) / max(1, len(y)), 4),
            "n": int(len(y)), "confusion": {"tp": tp, "tn": tn, "fp": fp, "fn": fn}}


def train() -> dict:
    from app.ml import forest_or_crop as foc

    d = np.load(os.path.join(OUT, "foc_dataset.npz"))
    f = np.load(FEATURES)
    y, lat = d["y"].astype(int), d["lat"].astype(float)
    ok = f["done"] & (f["npx"] > 0)
    sp = np.array([foc.split_of(float(a)) for a in lat])
    X = f["emb"].astype("float64")
    tr, va, te = (sp == "train") & ok, (sp == "val") & ok, (sp == "test") & ok
    best = None
    for lam in LAMBDAS:
        w, b = _fit(X[tr], y[tr], lam)
        m = _metrics(1 / (1 + np.exp(-(X[va] @ w + b))), y[va])
        if best is None or m["balanced_accuracy"] > best[0]["balanced_accuracy"]:
            best = (m, lam, w, b)
    mval, lam, w, b = best
    test = _metrics(1 / (1 + np.exp(-(X[te] @ w + b))), y[te])
    P = PROTOCOL_DOC["h1_weak_labels"]["pass"]
    passed = test["balanced_accuracy"] >= P["balanced_accuracy_test"] and test["forest_recall"] >= P["forest_recall_test"]
    run = {"date": date.today().isoformat(), "year": YEAR, "lambda": lam, "val": mval, "test": test,
           "n": {"train": int(tr.sum()), "val": int(va.sum()), "test": int(te.sum()),
                 "no_data": int((~ok).sum())},
           "pass_thresholds": P, "passed": passed, "status": "accepted" if passed else "rejected",
           "comparator_s2_test": {"balanced_accuracy": 0.8917, "forest_recall": 0.9093}}
    runs = json.load(open(RUNS, encoding="utf-8")) if os.path.exists(RUNS) else []
    runs.append(run)
    with open(RUNS, "w", encoding="utf-8") as fh:
        json.dump(runs, fh, ensure_ascii=False, indent=1)
    if passed:
        with open(MODEL, "w", encoding="utf-8") as fh:
            json.dump({"kind": "aef-logreg", "year": YEAR, "w": [round(float(v), 6) for v in w], "b": round(b, 6),
                       "run": run}, fh, ensure_ascii=False, indent=1)
    print(json.dumps(run, ensure_ascii=False, indent=1))
    return run


# ------------------------------------------------------------------ dùng trong ứng dụng

def _model() -> dict | None:
    try:
        with open(MODEL, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def runs() -> list:
    try:
        with open(RUNS, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def status() -> dict:
    """Trạng thái + MỌI lần chạy (kể cả trượt) — để không ai chỉ thấy lần đẹp nhất."""
    from app.services import aef
    from app.services.reqlang import tr
    m, rs = _model(), runs()
    out = {"available": m is not None, "runs": rs, "protocol": PROTOCOL_DOC, "attribution": aef.ATTRIBUTION,
           "source": "source.coop/tge-labs/aef-mosaic (CC-BY 4.0)"}
    if m is None:
        last = rs[-1] if rs else None
        out["message"] = tr(
            "AI nền tảng AlphaEarth chưa bật: " + (
                f"lần chạy {last['date']} không đạt ngưỡng đặt trước (độ chính xác cân bằng "
                f"{last['test']['balanced_accuracy']}, độ nhạy rừng {last['test']['forest_recall']})." if last
                else "đang chờ huấn luyện theo giao thức đặt trước."),
            "AlphaEarth foundation-model signal not enabled: " + (
                f"the {last['date']} run missed the pre-set bar (balanced accuracy {last['test']['balanced_accuracy']}, "
                f"forest recall {last['test']['forest_recall']})." if last else "waiting for the pre-registered training run."))
    else:
        out["run"] = m["run"]
    return out


def predict(geometry_plot: dict) -> dict:
    """Xác suất 'rừng năm 2020' từ vectơ AlphaEarth trên thửa + độ đổi vectơ 2020→2025 (THỬ NGHIỆM)."""
    from app.services import aef
    from app.services.reqlang import tr
    m = _model()
    if m is None:
        return {**status(), "probability_forest": None}
    box = plot_box(geometry_plot)
    v20, n = aef.mean_embedding(*box, m["year"])
    if v20 is None:
        return {"available": True, "probability_forest": None, "attribution": aef.ATTRIBUTION, "message": tr(
            "AlphaEarth không có dữ liệu năm 2020 trên thửa này (mây, biển hoặc ngoài vùng phủ).",
            "AlphaEarth has no 2020 data over this plot (cloud, sea or outside coverage).")}
    z = float(np.dot(v20, np.array(m["w"])) + m["b"])
    p = 1 / (1 + math.exp(-z))
    change = None
    v25, _ = aef.mean_embedding(*box, 2025)
    if v25 is not None:
        cos = float(np.clip(np.dot(v20, v25), -1, 1))
        change = {"cosine_2020_2025": round(cos, 3), "status": "experimental", "label": tr(
            f"Thử nghiệm, chưa kiểm định: độ giống nhau giữa năm 2020 và 2025 là {cos:.2f} (1 = như cũ). "
            "Số thấp gợi ý thửa đã đổi nhiều — cần người xem ảnh, không dùng để kết luận.",
            f"Experimental, not validated: 2020-vs-2025 similarity {cos:.2f} (1 = unchanged). A low value suggests "
            "the plot changed a lot — needs a human look, not a conclusion.")}
    return {"available": True, "probability_forest": round(p, 3), "pixels": n, "evidence_class": "predicted",
            "model": {"kind": m["kind"], "date": m["run"]["date"], "test": m["run"]["test"]},
            "change": change, "attribution": aef.ATTRIBUTION,
            "label": tr(f"AI nền tảng AlphaEarth: {p * 100:.0f}% khả năng là rừng năm 2020, {100 - p * 100:.0f}% là vườn cây/không rừng.",
                        f"AlphaEarth foundation model: {p * 100:.0f}% likely forest in 2020, {100 - p * 100:.0f}% tree crop / non-forest.")}


def plot_box(geometry_plot: dict) -> tuple[float, float, float, float]:
    """Hộp đọc cho một thửa — trần ~1 km quanh tâm để một lượt chỉ chạm 1–4 khối con."""
    from app.services import eudr_geo
    g = eudr_geo.shapely_geom(geometry_plot)
    x0, y0, x1, y1 = g.bounds
    cy, cx = (y0 + y1) / 2, (x0 + x1) / 2
    hy = min((y1 - y0) / 2, 0.0045)
    hx = min((x1 - x0) / 2, 0.0045 / max(0.2, math.cos(math.radians(cy))))
    hy, hx = max(hy, HALF_DEG), max(hx, HALF_DEG)
    return cy - hy, cx - hx, cy + hy, cx + hx


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["protocol", "extract", "train"])
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    if a.cmd == "protocol":
        write_protocol()
    elif a.cmd == "extract":
        extract(a.workers)
    else:
        train()
