"""Huấn luyện + đánh giá mô hình bất thường. Chạy: python -m app.ml.train

QUY TẮC ĐÁNH GIÁ — viết ra trước khi biết kết quả, để không tự chỉnh cho đẹp:

① SO Ở CÙNG TỈ LỆ BÁO ĐỘNG GIẢ.
   Một mô hình báo nhiều hơn thì đương nhiên bắt được nhiều hơn. So sánh chỉ có
   nghĩa khi hai bên cùng báo đúng x% số ngày. Vì vậy ngưỡng của mỗi bên được
   đặt theo phân vị TRÊN TẬP KIỂM TRA sao cho tỉ lệ báo bằng nhau, rồi mới đếm
   xem bên nào bắt được nhiều sự kiện thật hơn.

② TẬP KIỂM TRA LÀ 5 NĂM SAU, VÀ CHỨA CẢ 4 THẢM HOẠ.
   Huấn luyện 2015–2019, kiểm tra 2020–2024. Cả bốn sự kiện có thật đều nằm
   ngoài tập huấn luyện. Nếu chia ngẫu nhiên thì ngày 12/10 vào tập học và ngày
   13/10 vào tập kiểm tra — hai ngày gần như giống hệt nhau, điểm sẽ đẹp giả tạo.

③ CÒN KIỂM TRA TRÊN ĐỊA ĐIỂM CHƯA TỪNG THẤY.
   Bỏ hẳn một tỉnh khỏi quá trình huấn luyện rồi chấm chính tỉnh đó. Đây mới là
   câu hỏi thật, vì sản phẩm phải chạy ở 63 tỉnh chứ không phải 16 điểm.

④ NẾU THUA BASELINE THÌ GHI LÀ THUA, và không bật mô hình lên.

BASELINE là cách hệ thống hiện tại đang làm: xét TỪNG biến một so với lịch sử
của chính nơi đó, lấy phân vị cao nhất. Đây là baseline mạnh và trung thực —
không phải hình nộm dựng lên cho dễ thắng.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date, timedelta

from app.ml import dataset, linalg, model

# Bốn thảm hoạ có thật, đều nằm trong 2020–2024 (ngoài tập huấn luyện).
# (mã điểm, ngày đỉnh, số ngày cửa sổ trước đó, nhãn, có nằm trong tầm mô hình không)
#
# BẾN TRE BỊ ĐÁNH DẤU NGOÀI TẦM — và đây là kết luận từ dữ liệu, không phải cách
# né một kết quả xấu. Cân bằng nước 60 ngày tại Bến Tre giữa tháng 3 các năm:
#     2015 −269 · 2016 −284 · 2019 −267 · 2020 −287 · 2024 −300
# Tháng 3/2020 chỉ khô thứ nhì trong mười năm, và năm 2024 còn khô hơn. Ngày khô
# nhất cả chuỗi là 03/05/2024, không phải 2020. Nói cách khác, thảm hoạ mặn 2020
# KHÔNG có dấu vết trong khí tượng tại chỗ: nó do dòng chảy thượng nguồn Mekong
# suy giảm đẩy mặn vào sâu. Một mô hình chỉ đọc thời tiết địa phương không thể
# và không nên bắt được nó — muốn bắt thì phải đọc lưu lượng sông, đúng như
# module xâm nhập mặn đang làm. Giữ sự kiện này trong báo cáo để thấy giới hạn,
# nhưng không tính vào điểm đối đầu.
EVENTS = [
    ("hue",     "2020-10-11",  7, "Lũ lịch sử Thừa Thiên Huế 10/2020", True),
    ("traleng", "2020-10-28",  7, "Sạt lở Trà Leng 28/10/2020", True),
    ("danang",  "2022-10-14",  7, "Lũ Quảng Nam – Đà Nẵng 10/2022", True),
    ("bentre",  "2020-03-15", 30, "Hạn – mặn Bến Tre mùa khô 2020", False),
]

IN_SCOPE = [e for e in EVENTS if e[4]]


def marginal_percentiles(train_rows: list[dict]) -> list[list[float]]:
    """Phân bố huấn luyện của từng đặc trưng, đã sắp xếp — nền cho baseline."""
    cols = []
    for i in range(len(dataset.FEATURES)):
        cols.append(sorted(dataset.vector(r)[i] for r in train_rows))
    return cols


REVERSED = {"wb_7d", "wb_60d"}      # với cân bằng nước thì THẤP mới nguy hiểm


def baseline_score(row: dict, cols: list[list[float]]) -> float:
    """Phân vị cao nhất trong các biến, mỗi biến so với lịch sử của chính nơi đó.

    Chú ý dấu: với cân bằng nước thì THẤP mới nguy hiểm — hạn. Những biến đó lấy
    phân vị ngược. Bỏ qua chi tiết này sẽ làm baseline mù với hạn và tạo ra một
    chiến thắng giả cho mô hình mới.

    NỚI TRÊN 100 ĐỂ BASELINE CHỈNH ĐƯỢC NGƯỠNG. Bản đầu dừng ở 100 nên mọi ngày
    vượt kỷ lục 5 năm ở bất kỳ biến nào đều bằng điểm nhau, và baseline kẹt ở
    mức báo 6,95% số ngày — không hạ xuống 1% được để so cho ngang. Ở đây điểm
    được kéo dài liên tục phía trên 100 theo mức vượt kỷ lục, đo bằng khoảng
    cách từ trung vị tới kỷ lục. Việc này làm baseline MẠNH LÊN, tức là khó hơn
    cho mô hình mới — cố ý như vậy.
    """
    x = dataset.vector(row)
    best = 0.0
    for i, name in enumerate(dataset.FEATURES):
        col = cols[i]
        v = -x[i] if name in REVERSED else x[i]
        c = [-u for u in reversed(col)] if name in REVERSED else col
        p = linalg.percentile_of(c, v)
        if v > c[-1]:
            med = linalg.quantile(c, 50.0)
            span = max(c[-1] - med, 1e-9)
            p = 100.0 + 10.0 * (v - c[-1]) / span
        best = max(best, p)
    return best


def _window(day: str, back: int) -> set[str]:
    d = date.fromisoformat(day)
    return {(d - timedelta(days=k)).isoformat() for k in range(back + 1)}


def evaluate(scores_by_site: dict[str, dict[str, float]],
             target_rate: float) -> dict:
    """Đặt ngưỡng sao cho đúng target_rate% số ngày bị báo, rồi đếm sự kiện bắt được."""
    allv = sorted(v for s in scores_by_site.values() for v in s.values())
    if not allv:
        return {"threshold": None, "rate": 0.0, "detected": 0, "events": []}
    thr = linalg.quantile(allv, 100.0 - target_rate)

    flagged = sum(1 for s in scores_by_site.values() for v in s.values() if v >= thr)
    rate = 100.0 * flagged / len(allv)

    out = []
    for code, day, back, label, scoped in EVENTS:
        series = scores_by_site.get(code, {})
        win = sorted(_window(day, back))
        hits = [(d, series[d]) for d in win if d in series and series[d] >= thr]
        peak = max((series[d] for d in win if d in series), default=None)
        lead = None
        if hits:
            lead = (date.fromisoformat(day) - date.fromisoformat(hits[0][0])).days
        out.append({"label": label, "site": code, "detected": bool(hits),
                    "in_scope": scoped, "lead_days": lead,
                    "peak_score": round(peak, 2) if peak else None})
    return {"threshold": round(thr, 3), "rate": round(rate, 2),
            "detected": sum(1 for e in out if e["detected"] and e["in_scope"]),
            "n_scope": sum(1 for e in out if e["in_scope"]),
            "events": out}


def build(data: dict, exclude: str | None = None) -> dict | None:
    """Huấn luyện toàn bộ đường ống trên tập train. `exclude` để kiểm tra bỏ-một-tỉnh."""
    codes = [c for c in data if c != exclude]
    if len(codes) < 4:
        return None

    sigs = {c: model.signature(data[c]["train"]) for c in codes}
    sig_rows = [sigs[c] for c in codes]
    sig_mu = linalg.mean(sig_rows)
    sig_sd = linalg.stdev(sig_rows, sig_mu)
    z_sigs = [[(s[i] - sig_mu[i]) / sig_sd[i] for i in range(len(s))] for s in sig_rows]

    centroids, labels = model.kmeans(z_sigs, model.K_REGIMES)

    pooled: dict[int, list[list[float]]] = {}
    members: dict[int, list[str]] = {}
    for idx, c in enumerate(codes):
        lab = labels[idx]
        mu, sd = model.local_stats(data[c]["train"])
        for r in data[c]["train"]:
            x = dataset.vector(r)
            pooled.setdefault(lab, []).append(
                [(x[i] - mu[i]) / sd[i] for i in range(len(x))])
        members.setdefault(lab, []).append(c)

    regimes = []
    keep = []
    for lab in sorted(pooled):
        fit = model.fit_regime(pooled[lab])
        if fit is None:
            continue
        fit["id"] = len(regimes)
        fit["centroid"] = centroids[lab]
        fit["sites"] = members[lab]
        regimes.append(fit)
        keep.append(lab)
    if not regimes:
        return None

    return {"version": 1, "features": dataset.FEATURES,
            "signature_mu": sig_mu, "signature_sd": sig_sd,
            "regimes": regimes,
            "train_period": [dataset.TRAIN_START, dataset.TRAIN_END],
            "test_period": [dataset.TEST_START, dataset.TEST_END]}


def score_site(m: model.Model, site: dict) -> dict[str, float]:
    mu, sd = model.local_stats(site["train"])
    reg = m.assign(model.signature(site["train"]))
    return {r["date"]: m.score(r, mu, sd, reg)["percentile"] for r in site["test"]}


def main() -> int:
    print("Nạp dữ liệu ERA5 (dùng cache nếu đã tải)...")
    data = dataset.load_all()
    if len(data) < 8:
        print(f"DỪNG: chỉ có {len(data)} điểm, không đủ để huấn luyện.")
        return 1

    n_tr = sum(len(v["train"]) for v in data.values())
    n_te = sum(len(v["test"]) for v in data.values())
    print(f"\n{len(data)} điểm · {n_tr:,} ngày huấn luyện · {n_te:,} ngày kiểm tra\n")

    t0 = time.time()
    blob = build(data)
    if blob is None:
        print("DỪNG: không khớp được mô hình.")
        return 1
    print(f"Huấn luyện xong trong {time.time() - t0:.1f}s · {len(blob['regimes'])} vùng khí hậu:")
    for r in blob["regimes"]:
        names = ", ".join(data[c]["name"] for c in r["sites"])
        print(f"  Vùng {r['id']}  ({r['n']:6,} ngày)  {names}")

    m = model.Model(blob)
    joint = {c: score_site(m, data[c]) for c in data}

    base = {}
    for c, site in data.items():
        cols = marginal_percentiles(site["train"])
        base[c] = {r["date"]: baseline_score(r, cols) for r in site["test"]}

    print("\n" + "=" * 74)
    print("ĐỐI ĐẦU TRÊN 5 NĂM CHƯA TỪNG THẤY (2020–2024), CÙNG TỈ LỆ BÁO ĐỘNG")
    print("=" * 74)

    table = []
    for rate in (1.0, 2.0, 3.0, 5.0):
        ej = evaluate(joint, rate)
        eb = evaluate(base, rate)
        table.append((rate, ej, eb))
        print(f"\nBáo {rate:.0f}% số ngày   "
              f"(thực đo: tổ hợp {ej['rate']:.2f}% · từng biến {eb['rate']:.2f}%)")
        print(f"  {'Sự kiện':<40} {'tổ hợp':>16} {'từng biến':>16}")
        for a, b in zip(ej["events"], eb["events"]):
            tag = "" if a["in_scope"] else "   ← ngoài tầm, không tính điểm"
            fa = f"bắt, sớm {a['lead_days']}n" if a["detected"] else "BỎ SÓT"
            fb = f"bắt, sớm {b['lead_days']}n" if b["detected"] else "BỎ SÓT"
            print(f"  {a['label'][:39]:<40} {fa:>16} {fb:>16}{tag}")
        print(f"  {'TỔNG (chỉ sự kiện trong tầm)':<40} "
              f"{ej['detected']:>13}/{ej['n_scope']} {eb['detected']:>13}/{eb['n_scope']}")

    print("\n" + "=" * 74)
    print("KIỂM TRA TRÊN ĐỊA ĐIỂM CHƯA TỪNG HUẤN LUYỆN (bỏ-một-tỉnh)")
    print("=" * 74)
    loo = []
    for code in [e[0] for e in IN_SCOPE]:
        if code not in data:
            continue
        b2 = build(data, exclude=code)
        if b2 is None:
            continue
        m2 = model.Model(b2)
        s2 = score_site(m2, data[code])
        allv = sorted(s2.values())
        thr = linalg.quantile(allv, 98.0)          # cùng 2% số ngày
        ev = next(e for e in IN_SCOPE if e[0] == code)
        win = sorted(_window(ev[1], ev[2]))
        hits = [d for d in win if d in s2 and s2[d] >= thr]
        lead = ((date.fromisoformat(ev[1]) - date.fromisoformat(hits[0])).days
                if hits else None)
        loo.append({"site": code, "label": ev[3], "detected": bool(hits), "lead": lead})
        mark = f"bắt được, sớm {lead} ngày" if hits else "BỎ SÓT"
        print(f"  {data[code]['name']:<22} {mark}")

    # MỨC QUYẾT ĐỊNH CHỐT TRƯỚC LÀ 2%, không phải mức nào có lợi nhất.
    # Lấy max trên các mức rồi tuyên bố thắng là tự chọn kết quả đẹp — đúng loại
    # thiên vị mà quy tắc ① ở đầu tệp cấm. 2% là điểm vận hành thật của sản phẩm.
    OPERATING = 2.0
    rate, ej, eb = next(t for t in table if t[0] == OPERATING)
    margin = ej["detected"] - eb["detected"]

    # Sớm hơn bao nhiêu ngày, cộng dồn trên các sự kiện cả hai đều bắt được.
    lead_gain = sum((a["lead_days"] or 0) - (b["lead_days"] or 0)
                    for a, b in zip(ej["events"], eb["events"])
                    if a["in_scope"] and a["detected"] and b["detected"])

    print("\n" + "=" * 74)
    n = ej["n_scope"]
    if margin > 0:
        verdict = (f"THẮNG ở mức vận hành {OPERATING:.0f}%: tổ hợp {ej['detected']}/{n}, "
                   f"từng biến {eb['detected']}/{n}")
        enabled = True
    elif margin == 0 and lead_gain > 0:
        verdict = (f"HOÀ số sự kiện ({ej['detected']}/{n}) nhưng tổ hợp báo sớm hơn "
                   f"tổng cộng {lead_gain} ngày — bật, vai trò bổ trợ")
        enabled = True
    elif margin == 0:
        verdict = (f"HOÀ ({ej['detected']}/{n}) và không sớm hơn — bật nhưng chỉ để "
                   f"đối chiếu, không thay baseline")
        enabled = True
    else:
        verdict = (f"THUA baseline ({ej['detected']}/{n} so với {eb['detected']}/{n}) "
                   f"— KHÔNG bật")
        enabled = False
    print("KẾT LUẬN:", verdict)
    print("Ghi chú: hạn–mặn Bến Tre 2020 nằm ngoài tầm mô hình thời tiết địa phương")
    print("         (bằng chứng ở chú thích EVENTS) nên không tính vào điểm.")
    print("=" * 74)

    blob["metrics"] = {
        "trained_at": time.strftime("%Y-%m-%d"),
        "sites": len(data), "train_days": n_tr, "test_days": n_te,
        "comparison": [
            {"alarm_rate": r,
             "joint_detected": a["detected"], "baseline_detected": b["detected"],
             "joint_events": a["events"], "baseline_events": b["events"]}
            for r, a, b in table],
        "leave_one_out": loo,
        "verdict": verdict,
        "enabled": enabled,
    }
    model.save(blob)
    size = len(json.dumps(blob, separators=(",", ":"))) / 1024
    print(f"\nĐã lưu {model.MODEL_PATH}  ({size:.0f} KB)")
    print(f"Bật trong sản phẩm: {'CÓ' if enabled else 'KHÔNG'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
