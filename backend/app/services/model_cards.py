"""GĐ5 — THẺ MÔ HÌNH cho mọi mô hình / quy tắc AI của TerraTwin, kể cả cái đã TRƯỢT.

Kế hoạch tổng: "thẻ mô hình (dữ liệu, cách chia tập, điểm trên tập giữ lại, giới hạn đã biết, trường hợp không nên
dùng)". Con số KHÔNG gõ tay ở đây: đọc thẳng từ tệp kết quả kiểm định đã commit (landcover_runs.json,
data/ml/*_runs.json, eudr_validation*.json, water_gate.json) — tệp đổi thì thẻ đổi theo. Phần chữ (giới hạn, không
nên dùng) là mô tả cố định, viết theo kết quả đã công bố.
"""
from __future__ import annotations

import json
import os

from app.services.reqlang import tr

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data")
REPO = "https://github.com/annguyen210/TerraTwin/blob/main"


def _load(*parts):
    try:
        with open(os.path.join(DATA, *parts), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _r(v, n=3):
    return None if v is None else round(float(v), n)


def _field_metric() -> dict:
    """Kiểm thực địa bằng xác nhận người dùng (giao thức water_field_protocol.json): kết quả đã chấm, hoặc tiến độ."""
    fr = _load("eval", "water_field_result.json")
    label = tr("Kiểm thực địa: người dùng xác nhận đợt có ngập", "Field check: users confirm events really flooded")
    if fr:
        lo, hi = fr.get("wilson95") or [None, None]
        return {"label": label, "value": tr(f"P = {fr.get('precision')} (95%: {lo}–{hi}) trên {fr['sample']['labelled_events']} đợt",
                                            f"P = {fr.get('precision')} (95%: {lo}–{hi}) over {fr['sample']['labelled_events']} events"),
                "threshold": tr("cận dưới ≥ 0,60", "lower bound ≥ 0.60"), "passed": fr.get("outcome") == "confirmed"}
    have = None
    try:
        from app.db import SessionLocal
        from app.services import field_truth
        with SessionLocal() as db:
            have = field_truth.status(db)["have"]
    except Exception:
        pass
    n = have["labelled_events"] if have else "?"
    return {"label": label, "value": tr(f"chờ dữ liệu — {n}/30 đợt có nhãn", f"awaiting data — {n}/30 labelled events"),
            "threshold": tr("≥ 30 đợt, ≥ 10 người, ≥ 3 ô 1°; cận dưới Wilson ≥ 0,60", "≥ 30 events, ≥ 10 people, ≥ 3 1° cells; Wilson lower ≥ 0.60"),
            "passed": None}


def cards() -> list[dict]:
    out: list[dict] = []

    # 1 — Sàng lọc phá rừng EUDR (quy tắc)
    v1, v2 = _load("eudr_validation.json"), _load("eudr_validation_v2.json")
    if v1:
        m1, m2 = v1.get("metrics") or {}, (v2 or {}).get("metrics") or {}
        out.append({
            "id": "eudr_screen", "kind": tr("quy tắc", "rule"),
            "name": tr("Sàng lọc phá rừng sau 31/12/2020 (EUDR)", "Deforestation screening after 31/12/2020 (EUDR)"),
            "status": "active_v1",
            "status_label": tr("v1 đang chạy · v2 trượt · v3 chờ nhãn người", "v1 live · v2 failed · v3 awaiting human labels"),
            "task": tr("Ba bản đồ rừng 2020 bỏ phiếu + quỹ đạo tán cây + NDVI cùng mùa → Đạt / Cần xem lại / Rủi ro",
                       "Three 2020 forest maps vote + canopy trajectory + same-season NDVI → Pass / Review / Risk"),
            "data": tr("v1: 120 thửa Tây Nguyên · v2: 120 ô mới Tây Nguyên + Đông Nam Bộ (seed 20261006); thước đo Hansen GFC v1.12",
                       "v1: 120 Central Highlands plots · v2: 120 new cells (seed 20261006); reference Hansen GFC v1.12"),
            "split": tr("mẫu kiểm định riêng, giao thức commit trước khi chạy", "separate validation sample, protocol committed before running"),
            "metrics": [
                {"label": tr("v1 bắt rừng mất / giữ rừng / cho qua đất sạch", "v1 loss caught / forest kept / clean land passed"),
                 "value": " / ".join(str(_r(m1.get(k))) for k in ("M1_detect_lost", "M2_flag_forest", "M3_pass_clean")) if m1 else None, "threshold": "0,80 / 0,80 / 0,70",
                 "passed": v1.get("passed")},
                {"label": tr("v2 (mẫu mới), cùng ba chỉ số", "v2 (new sample), same three metrics"),
                 "value": " / ".join(str(_r(m2.get(k))) for k in ("M1_detect_lost", "M2_flag_forest", "M3_pass_clean")) if m2 else None, "threshold": "0,80 / 0,80 / 0,70",
                 "passed": (v2 or {}).get("passed")},
            ],
            "limits": tr("Cho qua đất sạch dưới ngưỡng (gắn cờ nhầm vườn cây lâu năm); thước đo năm 2000 không biết cây trồng sau 2000.",
                         "Clean-land pass rate below threshold (flags perennial orchards); the 2000 reference misses trees planted after 2000."),
            "not_for": tr("Không phải chứng nhận tuân thủ EUDR; không thay khảo sát thực địa.", "Not an EUDR compliance certificate; no substitute for field survey."),
            "code": f"{REPO}/backend/app/services/eudr_forest.py",
        })

    # 2 — Rừng hay vườn cây (FOC) và AlphaEarth
    foc = (_load("ml", "foc_runs.json") or [None])[-1]
    if foc:
        t = foc.get("test") or {}
        out.append({
            "id": "forest_or_crop", "kind": tr("mô hình", "model"),
            "name": tr("Rừng hay vườn cây (Sentinel-2 mùa)", "Forest or tree crop (seasonal Sentinel-2)"),
            "status": foc.get("status"), "status_label": tr("đạt · đã bật (tham khảo)", "passed · on (reference)"),
            "task": tr("Phân biệt rừng tự nhiên với vườn cà phê/cao su/cây ăn quả", "Tell natural forest from coffee/rubber/fruit orchards"),
            "data": tr(f"{foc.get('n', {}).get('train')} huấn luyện · {foc.get('n', {}).get('val')} kiểm định · {t.get('n')} kiểm tra, nhãn yếu",
                       f"{foc.get('n', {}).get('train')} train · {foc.get('n', {}).get('val')} val · {t.get('n')} test, weak labels"),
            "split": tr("chia theo vĩ độ (tránh rò rỉ không gian)", "split by latitude band (no spatial leakage)"),
            "metrics": [{"label": tr("BA / bắt rừng / bắt vườn (kiểm tra)", "BA / forest recall / orchard recall (test)"),
                         "value": f"{_r(t.get('balanced_accuracy'))} / {_r(t.get('forest_recall'))} / {_r(t.get('tree_crop_recall'))}",
                         "threshold": "0,85 / 0,90 / —", "passed": foc.get("passed")}],
            "limits": tr("Nhãn yếu; xác suất chưa hiệu chuẩn.", "Weak labels; probabilities not calibrated."),
            "not_for": tr("Không đưa vào hồ sơ ký, không thay quy tắc sàng lọc.", "Not in signed dossiers; does not replace the screening rule."),
            "code": f"{REPO}/backend/app/services/forest_or_crop.py",
        })
    aef = (_load("ml", "aef_runs.json") or [None])[-1]
    if aef:
        t = aef.get("test") or {}
        out.append({
            "id": "aef_forest", "kind": tr("mô hình nền + phân loại", "foundation model + classifier"),
            "name": tr("Rừng hay vườn — AlphaEarth (Google DeepMind)", "Forest or orchard — AlphaEarth (Google DeepMind)"),
            "status": aef.get("status", "accepted"), "status_label": tr("đạt · đã bật (tham khảo)", "passed · on (reference)"),
            "task": tr("Như trên, trên vectơ AlphaEarth 64 chiều + hồi quy logistic", "As above, on 64-d AlphaEarth vectors + logistic regression"),
            "data": tr(f"đúng {t.get('n')} mẫu kiểm tra của mô hình trên", f"the same {t.get('n')} test samples as above"),
            "split": tr("như trên; giao thức commit fd9c927 trước khi tải", "as above; protocol committed fd9c927 before download"),
            "metrics": [{"label": tr("BA / bắt rừng / bắt vườn (kiểm tra)", "BA / forest recall / orchard recall (test)"),
                         "value": f"{_r(t.get('balanced_accuracy'))} / {_r(t.get('forest_recall'))} / {_r(t.get('tree_crop_recall'))}",
                         "threshold": "0,85 / 0,90 / —", "passed": True}],
            "limits": tr("Xác suất rất \"gắt\" (gần 0/1), chưa hiệu chuẩn; phép thử chính tiếp theo là nhãn người v3.",
                         "Very sharp (near 0/1) probabilities, uncalibrated; next key test is v3 human labels."),
            "not_for": tr("Không vào hồ sơ ký.", "Not in signed dossiers."),
            "code": f"{REPO}/backend/app/ml/aef_model.py",
        })

    # 3 — Loại đất: U-Net (trượt) và AlphaEarth (đạt)
    for r in _load("landcover_runs.json") or []:
        is_aef = str(r.get("model", "")).startswith("AlphaEarth")
        out.append({
            "id": "landcover_" + ("aef" if is_aef else f"unet_{r.get('date')}"),
            "kind": tr("mô hình nền + phân loại", "foundation model + classifier") if is_aef else tr("học sâu", "deep learning"),
            "name": (tr("Loại đất — AlphaEarth", "Land cover — AlphaEarth") if is_aef else tr(f"Loại đất — U-Net ({r.get('date')})", f"Land cover — U-Net ({r.get('date')})")),
            "status": r.get("status"),
            "status_label": tr("đạt · đã bật (dự đoán, tham khảo)", "passed · on (prediction, reference)") if r.get("status") == "accepted"
                            else tr("trượt · không bật", "failed · off"),
            "task": tr("11 lớp ESA WorldCover; trả lời \"đất có đổi khác sau 2021\"", "11 ESA WorldCover classes; answers \"has the land changed since 2021\""),
            "data": r.get("data"),
            "split": tr(f"tỉnh giữ lại: {', '.join(r.get('test_provinces') or [])} · kiểm định: {', '.join(r.get('val_provinces') or [])}",
                        f"held-out provinces: {', '.join(r.get('test_provinces') or [])} · validation: {', '.join(r.get('val_provinces') or [])}"),
            "metrics": [{"label": tr("mIoU tỉnh giữ lại", "held-out mIoU"), "value": str(r.get("miou_test")), "threshold": "0,35",
                         "passed": r.get("status") == "accepted"},
                        {"label": tr("IoU đất trồng trọt", "cropland IoU"), "value": str((r.get("iou_per_class_test") or {}).get("Đất trồng trọt")),
                         "threshold": tr("báo riêng", "reported separately"), "passed": None}],
            "limits": r.get("diagnosis") or (tr("Yếu với cây bụi, đất ngập nước, rừng ngập mặn.", "Weak on shrubland, wetland, mangroves.") if is_aef else None),
            "not_for": tr("Không vào hồ sơ ký; không thay bản đồ quy hoạch.", "Not in signed dossiers; not a zoning map."),
            "code": f"{REPO}/backend/app/" + ("ml/aef_landcover.py" if is_aef else "dl/train.py"),
        })

    # 4 — Lịch sử nước radar (quy tắc)
    g = _load("water_gate.json")
    if g:
        out.append({
            "id": "water_radar", "kind": tr("quy tắc đo", "measurement rule"),
            "name": tr("Lịch sử nước nhìn xuyên mây (Sentinel-1)", "Water history through clouds (Sentinel-1)"),
            "status": "accepted" if g.get("passed") else "rejected",
            "status_label": tr("cổng đạt · đã bật (đo thật)", "gate passed · on (measured)") if g.get("passed") else tr("trượt", "failed"),
            "task": tr("Đợt nước phủ trên đúng thửa, 2017 → nay", "Water events over the exact plot, 2017 → now"),
            "data": tr("ảnh Sentinel-1 RTC một quỹ đạo, phân vị VV trong khung thửa", "one-track Sentinel-1 RTC, VV percentiles in the plot window"),
            "split": tr("cổng đặt trước: lũ Huế 10/2020, miền Trung 10/2025 đúng tuần; đất cao 0 đợt", "pre-set gate: Huế 10/2020 and central floods 10/2025 in the right week; high ground 0 events"),
            "metrics": [{"label": c.get("case"), "value": tr(f"{c.get('n_events')} đợt", f"{c.get('n_events')} events"),
                         "threshold": ", ".join(x.get("label", "") for x in c.get("checks") or []) or tr("0 đợt", "0 events"),
                         "passed": all(x.get("pass") for x in c.get("checks") or []) if c.get("checks") else c.get("n_events") == 0}
                        for c in g.get("cases", [])] + [_field_metric()],
            "limits": tr("Đô thị, rừng rậm, sườn dốc, mặt rất phẳng có thể sai; chu kỳ 6–12 ngày lọt đợt ngập ngắn.",
                         "Urban areas, dense forest, steep slopes, very smooth surfaces mislead; the 6–12 day revisit misses short floods."),
            "not_for": tr("Không phải số liệu ngập chính thức.", "Not official flood records."),
            "code": f"{REPO}/backend/app/services/water_history.py",
        })

    # 3c — Tổ hợp dự báo mưa best_match + ECMWF AIFS (GĐ5 mục 3) — 18/10/2026
    ab = _load("eval", "aifs_blend_result.json")
    if ab:
        sc, mg = ab["scores"], ab.get("margins") or {}

        def _m(key, label, better_low):
            b, c = sc["best"][key], sc["blend"][key]
            return {"label": label, "value": f"{b} → {c}", "threshold": tr("giảm", "lower") if better_low else tr("không giảm", "not lower"),
                    "passed": (c < b) if better_low else (c >= b)}
        out.append({
            "id": "aifs_blend", "kind": tr("tổ hợp dự báo", "forecast blend"),
            "name": tr("Mưa dự báo 7 ngày: trung bình best_match + ECMWF AIFS", "7-day rain forecast: mean of best_match + ECMWF AIFS"),
            "status": "accepted" if ab.get("passed") else "rejected",
            "status_label": tr("cổng đạt · đã bật", "gate passed · on") if ab.get("passed") else tr("trượt · giữ best_match", "failed · best_match kept"),
            "task": tr("Bắt mưa 3 ngày cực đoan (≥ P97 của điểm) trước 1–3 ngày", "Catch extreme 3-day rain (≥ the point's P97) 1–3 days ahead"),
            "data": tr("Open-Meteo Previous Runs (dự báo đã phát hành) so với ERA5; 9 điểm, ngày phát hành 01/03–28/12/2025",
                       "Open-Meteo Previous Runs (issued forecasts) vs ERA5; 9 points, issue days 1 Mar – 28 Dec 2025"),
            "split": tr(f"đăng ký trước (a6950c1), script trước khi chạy (ff0aa9e), chấm một lần: {sc['best']['events']} ngày-sự kiện",
                        f"pre-registered (a6950c1), script before running (ff0aa9e), scored once: {sc['best']['events']} event-days"),
            "metrics": [_m("POD", tr("Bắt trúng (POD) best_match → tổ hợp", "Hit rate (POD) best_match → blend"), False),
                        _m("FAR", tr("Báo bừa (FAR) best_match → tổ hợp", "False alarms (FAR) best_match → blend"), True),
                        _m("CSI", "CSI", False),
                        {"label": tr("AIFS một mình (tham khảo, không phải ứng viên)", "AIFS alone (reference, not a candidate)"),
                         "value": f"POD {sc['aifs']['POD']} · FAR {sc['aifs']['FAR']}", "threshold": "—", "passed": None}],
            "limits": tr("Sự thật là ERA5 (tái phân tích ~25 km), không phải trạm đo mưa; chấm ở mức mưa, chưa chấm mức cảnh báo vì chưa có "
                         "sự thật mặt đất. Ngày-sự kiện liền nhau không độc lập: gộp thành 50 đợt riêng biệt thì best_match bắt được 17, tổ hợp 22 "
                         "— cả hai vẫn bắt chưa tới một nửa số đợt mưa cực đoan. Chỉ một năm (2025).",
                         "Truth is ERA5 (~25 km reanalysis), not rain gauges; scored at rain level, not alert level, since there is no ground "
                         "truth yet. Consecutive event-days are not independent: merged into 50 distinct episodes, best_match caught 17 and the "
                         "blend 22 — both still catch fewer than half of the extreme-rain episodes. One year only (2025)."),
            "not_for": tr("Không phải dự báo chính thức của cơ quan khí tượng; ET0 và nhiệt độ vẫn theo best_match.",
                          "Not an official met-service forecast; ET0 and temperature still follow best_match."),
            "code": f"{REPO}/backend/app/services/realdata.py",
        })

    # 4a — Mô hình nước trên radar (U-Net, Sen1Floods11) — GĐ5 mục 2, giao thức đăng ký 09/10/2026 (6d9cfb4)
    s1 = _load("ml", "s1_water_result.json")
    s1c = _load("ml", "s1_unet_confirm_result.json")     # phép kiểm "ý kiến thứ hai" trên thửa GĐ2 (s1_unet_confirm_protocol.json)
    names = {"test": tr("tập test (90 ô)", "test set (90 chips)"), "bolivia": tr("Bolivia (sự kiện giữ lại)", "Bolivia (held-out event)"),
             "mekong": tr("Mekong (6 ô, gần Việt Nam nhất)", "Mekong (6 chips, closest to Viet Nam)")}
    if s1 and not s1.get("limit"):
        res = s1.get("results") or {}
        out.append({
            "id": "s1_water_unet", "kind": tr("học sâu", "deep learning"),
            "name": tr("Nước trên ảnh radar Sentinel-1 — U-Net (Sen1Floods11)", "Water on Sentinel-1 radar — U-Net (Sen1Floods11)"),
            "status": "accepted" if (s1.get("passed") and (s1c or {}).get("passed") is not False) else "rejected",
            "status_label": ((tr("cổng mô hình đạt · đạt phép kiểm trên thửa GĐ2 · đang chạy như Ý KIẾN THỨ HAI cho từng đợt (tham khảo)",
                                 "model gate passed · passed the GĐ2-plot check · live as a SECOND OPINION per event (reference)")
                              if (s1c or {}).get("passed") else
                              tr("cổng mô hình đạt · TRƯỢT phép kiểm trên thửa GĐ2 · không bật", "model gate passed · FAILED the GĐ2-plot check · not on")
                              if s1c else
                              tr("cổng mô hình đạt · CHƯA bật (phải qua phép kiểm trên thửa GĐ2)",
                                 "model gate passed · NOT on (must pass the check on GĐ2 plots)")) if s1.get("passed")
                             else tr("trượt · lịch sử nước giữ phương pháp ngưỡng −18 dB", "failed · water history keeps the −18 dB threshold")),
            "task": tr("Phân đoạn nước từng điểm ảnh trên ảnh radar VV/VH", "Per-pixel water segmentation on VV/VH radar"),
            "data": tr("Sen1Floods11 v1.1, nhãn tay 446 ô 512×512; chia tập chính thức train 252 · valid 89 · test 90 · Bolivia 15",
                       "Sen1Floods11 v1.1, 446 hand-labelled 512×512 chips; official split train 252 · valid 89 · test 90 · Bolivia 15"),
            "split": tr(f"đăng ký trước 09/10/2026 (6d9cfb4); chọn mô hình chỉ bằng valid (IoU tốt nhất {s1.get('best_valid_iou')}); "
                        f"chấm một lần; {s1.get('device', '?')}, {s1.get('epochs')} vòng",
                        f"pre-registered 09/10/2026 (6d9cfb4); model chosen on valid only (best IoU {s1.get('best_valid_iou')}); "
                        f"scored once; {s1.get('device', '?')}, {s1.get('epochs')} epochs"),
            "metrics": [{"label": tr(f"IoU nước — {names.get(k, k)}: mô hình / ngưỡng −18 dB / Otsu",
                                     f"Water IoU — {names.get(k, k)}: model / −18 dB threshold / Otsu"),
                         "value": f"{v.get('model')} / {v.get('threshold_-18dB')} / {v.get('otsu_per_chip')}",
                         "threshold": tr("mô hình > ngưỡng −18 dB", "model > −18 dB threshold"),
                         "passed": (v.get("model") is not None and v.get("threshold_-18dB") is not None
                                    and v["model"] > v["threshold_-18dB"])}
                        for k, v in res.items() if isinstance(v, dict)]
                       + ([{"label": tr(f"Thửa GĐ2 — {c['label']}: U-Net xác nhận đợt (≥ 10% khung thửa)",
                                        f"GĐ2 plot — {c['label']}: U-Net confirms the event (≥ 10% of plot window)"),
                            "value": ", ".join(f"{e['flag_date']}: {e['unet_share']}" for e in c["events"]) or "—",
                            "threshold": "≥ 0.10", "passed": c["pass"]} for c in s1c.get("positive", [])]
                          + [{"label": tr(f"Thửa GĐ2 — {c['case']}: cảnh bị xác nhận nhầm", f"GĐ2 plot — {c['case']}: scenes wrongly confirmed"),
                              "value": f"{c['n_confirmed_wrongly_or_unread']}/{c['n']}", "threshold": "0", "passed": c["pass"]}
                             for c in s1c.get("negative", [])] if s1c else []),
            "limits": tr("Học trên ô 512×512 điểm ảnh của 11 trận lũ ngoài Việt Nam (trừ Mekong). Lịch sử nước của TerraTwin hiện đọc "
                         "THỐNG KÊ phân vị từng cảnh trên khung thửa, không đọc ảnh điểm ảnh — muốn dùng mô hình phải đổi cách đọc và qua lại "
                         "cổng GĐ2 (lũ Huế 10/2020, miền Trung 10/2025, đất cao 0 đợt).",
                         "Trained on 512×512-pixel chips of 11 floods outside Viet Nam (except Mekong). TerraTwin's water history reads "
                         "per-scene PERCENTILE statistics over the plot window, not pixel images — using the model needs a different read "
                         "and must re-pass the GĐ2 gate (Huế 10/2020, central floods 10/2025, high ground 0 events)."),
            "not_for": tr("Không thay số đo radar trong hồ sơ ký.", "Does not replace radar measurements in signed dossiers."),
            "code": f"{REPO}/ml/kaggle/s1_water_seg.py",
        })
    else:
        out.append({
            "id": "s1_water_unet", "kind": tr("học sâu", "deep learning"),
            "name": tr("Nước trên ảnh radar Sentinel-1 — U-Net (Sen1Floods11)", "Water on Sentinel-1 radar — U-Net (Sen1Floods11)"),
            "status": "pending", "status_label": tr("đang huấn luyện trên GPU Kaggle · chấm một lần", "training on Kaggle GPU · scored once"),
            "task": tr("Phân đoạn nước từng điểm ảnh trên ảnh radar VV/VH", "Per-pixel water segmentation on VV/VH radar"),
            "data": tr("Sen1Floods11 v1.1, nhãn tay", "Sen1Floods11 v1.1, hand-labelled"),
            "split": tr("đăng ký trước 09/10/2026 (6d9cfb4): mô hình > ngưỡng −18 dB trên cả test, Bolivia, Mekong",
                        "pre-registered 09/10/2026 (6d9cfb4): model > −18 dB threshold on test, Bolivia and Mekong"),
            "metrics": [], "limits": tr("Chưa có kết quả.", "No result yet."),
            "not_for": tr("Chưa dùng ở đâu.", "Not used anywhere yet."),
            "code": f"{REPO}/ml/kaggle/s1_water_seg.py",
        })

    # 4a' — Nước trong ẢNH THỰC ĐỊA (SegFormer-b0, Flood Area Segmentation CC0) — đăng ký trước 18/10/2026 (2e44cb0)
    fw = _load("ml", "field_water_result.json")
    fw_base = {
        "id": "field_water_segformer", "kind": tr("học sâu", "deep learning"),
        "name": tr("Nước trong ảnh thực địa — SegFormer-b0", "Water in field photos — SegFormer-b0"),
        "task": tr("Tỉ lệ điểm ảnh là nước trong ảnh người dùng chụp tại thửa", "Share of water pixels in a photo the user takes at the plot"),
        "data": tr("Kaggle Flood Area Segmentation (CC0), 290 ảnh lũ + mặt nạ nhãn tay; chia cố định 70/15/15 theo hạt giống 20261018",
                   "Kaggle Flood Area Segmentation (CC0), 290 flood photos + hand-drawn masks; fixed 70/15/15 split, seed 20261018"),
        "code": f"{REPO}/ml/kaggle/field_water_seg.py",
    }
    # Bản 2 (19/10/2026): học thêm ảnh đồng ruộng khô SUN397 — có kết quả thì thẻ là của bản 2 (bản 1 vẫn ghi trong "split")
    fw2 = _load("ml", "field_water_v2_result.json")
    if fw2 and (fw2.get("test") or {}).get("model_iou") is not None:
        t2, d2 = fw2["test"], fw2.get("dry_test") or {}
        live2 = __import__("app.services.field_water", fromlist=["available"]).available()
        out.append({**fw_base,
            "name": tr("Nước trong ảnh thực địa — SegFormer-b0 bản 2 (học thêm ảnh ruộng khô)",
                       "Water in field photos — SegFormer-b0 v2 (also trained on dry fields)"),
            "status": "accepted" if fw2.get("passed") else "rejected",
            "status_label": (tr("đạt cả ảnh lũ lẫn đối chứng ảnh khô · đang chạy — chỉ tham khảo ở nhật ký thửa",
                                "passed flood photos AND dry-field control · live — reference only in the plot journal") if fw2.get("passed") and live2 else
                             tr("đạt cả ảnh lũ lẫn đối chứng ảnh khô · máy chủ chưa có tệp .onnx bản 2",
                                "passed flood photos AND dry-field control · server lacks the v2 .onnx") if fw2.get("passed") else
                             tr("bản 2 TRƯỢT · không bật — ảnh thực địa vẫn chỉ là bằng chứng người dùng",
                                "v2 FAILED · not on — field photos stay user evidence only")),
            "data": tr(f"ảnh lũ như bản 1 (204/43/43) + ảnh đồng ruộng KHÔ SUN397 phần train ({fw2['n']['dry_train']} học, "
                       f"{fw2['n']['dry_valid']} chọn mô hình) với mặt nạ rỗng; đối chứng trên {fw2['n']['dry_test']} ảnh khô phần test",
                       f"flood photos as v1 (204/43/43) + DRY SUN397 field photos from the train split ({fw2['n']['dry_train']} train, "
                       f"{fw2['n']['dry_valid']} selection) with empty masks; control on {fw2['n']['dry_test']} dry test-split photos"),
            "split": tr(f"đăng ký trước 19/10/2026 (c62362d) sau khi bản 1 (IoU 0,816) trượt đối chứng ảnh khô; chọn vòng theo valid; chấm test một lần",
                        f"pre-registered 19/10/2026 (c62362d) after v1 (IoU 0.816) failed the dry-field control; epoch chosen on valid; test scored once"),
            "metrics": [{"label": tr("IoU nước trên test ảnh lũ — mô hình / đường cơ sở màu", "Water IoU on flood test — model / colour baseline"),
                         "value": f"{t2['model_iou']} / {t2.get('color_baseline_iou')}", "threshold": "≥ 0.70, > màu",
                         "passed": fw2.get("passed_flood")},
                        {"label": tr("Đối chứng ảnh đồng ruộng KHÔ (test): trung vị tỉ lệ 'nước' / ảnh > 0,5",
                                     "DRY-field control (test): median 'water' share / images > 0.5"),
                         "value": f"{d2.get('median')} / {d2.get('share_over_0_5')}", "threshold": "≤ 0.10 / ≤ 0.10",
                         "passed": fw2.get("passed_dry")}]
                       + [{"label": f"  · {k}", "value": f"{v['median']} / {v['share_over_0_5']}", "threshold": "≤ 0.10 / ≤ 0.10",
                           "passed": v["median"] <= 0.10 and v["share_over_0_5"] <= 0.10}
                          for k, v in (d2.get("per_class") or {}).items()],
            "limits": tr("Ảnh lũ nhiều nước trên thế giới, ảnh khô SUN397 chủ yếu ngoài Việt Nam; ruộng lúa nước (vốn có nước) không nằm trong "
                         "đối chứng. Đạt KHÔNG chứng minh đúng trên ruộng Việt Nam — cần ảnh thực địa có nhãn của người dùng.",
                         "Flood photos from many countries, dry SUN397 photos mostly outside Viet Nam; paddy (normally watered) is not in "
                         "the control. Passing does NOT prove it works on Vietnamese fields — that needs labelled user field photos."),
            "not_for": tr("Không vào nội dung ký của hồ sơ, không thay câu trả lời 'có nước / không' của người dùng.",
                          "Not in signed dossier content; does not replace the user's own 'water / no water' answer."),
            "code": f"{REPO}/ml/kaggle/field_water_seg_v2.py",
        })
    elif fw and (fw.get("test") or {}).get("model_iou") is not None:
        t = fw["test"]
        nc1, nc2 = _load("ml", "field_water_negctrl_result.json"), _load("ml", "field_water_negctrl_1b_result.json")
        ctrl_fail = any(c is not None and c.get("passed") is False for c in (nc1, nc2))
        live = __import__("app.services.field_water", fromlist=["available"]).available()
        out.append({**fw_base,
            "status": "accepted" if (fw.get("passed") and not ctrl_fail) else "rejected",
            "status_label": (tr("cổng ảnh lũ đạt · TRƯỢT đối chứng ảnh đồng ruộng KHÔ (lúa mì vàng, cỏ khô bị nhìn thành nước) · KHÔNG bật",
                                "flood-photo gate passed · FAILED the DRY-field control (golden wheat, dry hay seen as water) · NOT on")
                             if fw.get("passed") and ctrl_fail else
                             tr("cổng mô hình đạt · đang chạy — chỉ tham khảo ở nhật ký thửa, không vào hồ sơ ký",
                                "model gate passed · live — reference only in the plot journal, not in signed dossiers") if fw.get("passed") and live else
                             tr("cổng mô hình đạt · CHƯA bật (máy chủ chưa có tệp .onnx; khi bật chỉ là tín hiệu tham khảo)",
                                "model gate passed · NOT on (server lacks the .onnx file; reference signal only once on)") if fw.get("passed") else
                             tr("trượt · ảnh thực địa vẫn chỉ là bằng chứng người dùng", "failed · field photos stay user evidence only")),
            "split": tr(f"đăng ký trước 18/10/2026 (2e44cb0); chọn mô hình chỉ bằng valid (IoU tốt nhất {fw.get('best_valid_iou')}); "
                        f"chấm một lần; {fw.get('device', '?')}, {fw.get('epochs')} vòng; train {fw['n']['train']} · valid {fw['n']['valid']} · test {fw['n']['test']}",
                        f"pre-registered 18/10/2026 (2e44cb0); model chosen on valid only (best IoU {fw.get('best_valid_iou')}); "
                        f"scored once; {fw.get('device', '?')}, {fw.get('epochs')} epochs; train {fw['n']['train']} · valid {fw['n']['valid']} · test {fw['n']['test']}"),
            "metrics": [{"label": tr("IoU nước trên test — mô hình", "Water IoU on test — model"), "value": t["model_iou"],
                         "threshold": "≥ 0.70", "passed": t["model_iou"] >= 0.70},
                        {"label": tr("IoU nước trên test — đường cơ sở màu HSV (không học)", "Water IoU on test — HSV colour baseline (no learning)"),
                         "value": t.get("color_baseline_iou"), "threshold": tr("mô hình phải hơn", "model must beat it"),
                         "passed": t.get("color_baseline_iou") is not None and t["model_iou"] > t["color_baseline_iou"]}]
                       + [{"label": tr(f"Đối chứng ảnh đồng ruộng KHÔ — {nm}: trung vị tỉ lệ 'nước' / ảnh > 0,5",
                                       f"DRY-field control — {nm}: median 'water' share / images > 0.5"),
                           "value": f"{c.get('median')} / {c.get('share_over_0_5')} ({c.get('n')} ảnh)",
                           "threshold": "≤ 0.10 / ≤ 0.10", "passed": c.get("passed")}
                          for nm, c in ((tr("ruộng ngô (SUN397)", "corn field (SUN397)"), nc1),
                                        (tr("8 lớp khác (SUN397)", "8 other classes (SUN397)"), nc2)) if c]
                       + [{"label": tr(f"  · {k}", f"  · {k}"), "value": f"{v['median']} / {v['share_over_0_5']}", "threshold": "≤ 0.10 / ≤ 0.10",
                           "passed": v["median"] <= 0.10 and v["share_over_0_5"] <= 0.10}
                          for k, v in ((nc2 or {}).get("per_class") or {}).items()],
            "limits": tr("Ảnh lũ nhiều nước trên thế giới, nhiều ảnh chụp từ trên cao/drone; ruộng lúa ngập nông và mặt ruộng ướt ở Việt Nam có "
                         "thể khác. Đạt cổng KHÔNG chứng minh đúng trên ruộng Việt Nam — muốn tin hơn cần ảnh thực địa có nhãn của người dùng.",
                         "Flood photos from many countries, many taken from above/drones; shallow-flooded rice and wet fields in Viet Nam may "
                         "differ. Passing does NOT prove it works on Vietnamese fields — that needs labelled field photos from users."),
            "not_for": tr("Không vào nội dung ký của hồ sơ, không thay câu trả lời 'có nước / không' của người dùng.",
                          "Not in signed dossier content; does not replace the user's own 'water / no water' answer."),
        })
    else:
        out.append({**fw_base, "status": "pending",
            "status_label": tr("đang huấn luyện trên GPU Kaggle · chấm một lần", "training on Kaggle GPU · scored once"),
            "split": tr("đăng ký trước 18/10/2026 (2e44cb0): IoU nước trên test ≥ 0,70 và hơn đường cơ sở màu",
                        "pre-registered 18/10/2026 (2e44cb0): test water IoU ≥ 0.70 and better than the colour baseline"),
            "metrics": [], "limits": tr("Chưa có kết quả.", "No result yet."),
            "not_for": tr("Chưa dùng ở đâu.", "Not used anywhere yet.")})

    # 4b — Lớp diễn giải mùa lũ (trong/ngoài mùa) — 17/10/2026
    fsr = _load("eval", "flood_season_result.json")
    if fsr:
        out.append({
            "id": "flood_season", "kind": tr("quy tắc diễn giải", "interpretation rule"),
            "name": tr("Mùa lũ của từng điểm (trong / ngoài mùa)", "Per-point flood season (in / out of season)"),
            "status": "accepted" if fsr.get("passed") else "rejected",
            "status_label": tr("cổng đạt · đã bật", "gate passed · on") if fsr.get("passed") else tr("trượt · không bật", "failed · off"),
            "task": tr("Tách đợt nước trong mùa lũ khỏi nước tưới / nuôi trồng theo vụ — không thêm/bớt đợt",
                       "Separate flood-season water events from seasonal irrigation / aquaculture — no events added or removed"),
            "data": tr("mưa ngày ERA5 2016–2025 tại điểm; lõi = tháng mưa nhiều nhất tới ≥ 50% năm, + tháng liền sau",
                       "daily ERA5 rain 2016–2025 at the point; core = wettest months up to ≥ 50% of the year, + the following month"),
            "split": tr("đăng ký trước 4 ca: Huế 10–11/2020 và 11/2025 phải trong mùa; Cà Mau tháng 3–5, Hà Nội tháng 2–3 phải ngoài mùa",
                        "4 pre-registered cases: Huế 10–11/2020 and 11/2025 must be in season; Cà Mau Mar–May, Hà Nội Feb–Mar must be out"),
            "metrics": [{"label": c.get("case"), "value": ", ".join(f"{e['start']}={e['label']}" for e in c.get("events") or []) or "—",
                         "threshold": tr("trong mùa", "in season") if c.get("must") == "in" else tr("ngoài mùa", "out of season"),
                         "passed": c.get("pass")} for c in fsr.get("cases", [])],
            "limits": tr("Lũ sớm đầu mùa bị xếp ngoài mùa (vd 19/09/2024, bão Soulik, đồng lúa Huế 16,52; 107,59). Mưa ERA5 là lưới thô ~25 km.",
                         "Early-season floods are labelled out of season (e.g. 19/09/2024, Typhoon Soulik, Huế paddy 16.52, 107.59). ERA5 rain is a coarse ~25 km grid."),
            "not_for": tr("Không chứng minh một đợt là nước tưới — chỉ nói đợt đó ngoài các tháng mưa lớn nhất của điểm.",
                          "Does not prove an event is irrigation — only that it falls outside the point's wettest months."),
            "code": f"{REPO}/backend/app/services/flood_season.py",
        })

    # 4c — Lớp mùa lũ v2 (mưa cực đoan bắt lũ sớm/muộn) — 17/10/2026, công bố cả khi trượt
    f2 = _load("eval", "flood_season_v2_result.json")
    if f2:
        def _m2(c):
            evs = c.get("events") or []
            if not evs:
                return tr("không có đợt nào trong cửa sổ — không đánh giá được", "no event in the window — not evaluable")
            return "; ".join(f"{e['start']}={e['season']}" + (f" ({e['rain3d_mm']:g}/{e['p97_mm']:g} mm)" if "rain3d_mm" in e else "") for e in evs)
        out.append({
            "id": "flood_season_v2", "kind": tr("quy tắc diễn giải", "interpretation rule"),
            "name": tr("Mùa lũ v2 — bắt lũ sớm/muộn bằng mưa cực đoan", "Flood season v2 — catch early/late floods via extreme rain"),
            "status": "accepted" if f2.get("passed") else "rejected",
            "status_label": tr("cổng đạt · đã bật", "gate passed · on") if f2.get("passed") else tr("trượt · không bật (giữ v1)", "failed · off (v1 kept)"),
            "task": tr("Đợt ngoài mùa lũ v1 mà ngay sau mưa cực đoan → 'có thể là lũ sớm/muộn'",
                       "Out-of-season (v1) events right after extreme rain → 'possibly early/late flood'"),
            "data": tr("tổng mưa 3 ngày ERA5 lớn nhất trong ≤ 12 ngày trước cảnh ướt đầu tiên, so với P97 của điểm (2016–2025)",
                       "max ERA5 3-day rain within ≤ 12 days before the first wet scene, vs the point's P97 (2016–2025)"),
            "split": tr("đăng ký trước 6 ca, hai chiều: bão Soulik 19/9/2024, bão Noru 28/9/2022 (dương tính); Cà Mau tháng 3–5, Hà Nội tháng 2–3 (âm tính); 2 ca giữ v1",
                        "6 pre-registered cases, both directions: Typhoon Soulik 19/9/2024, Typhoon Noru 28/9/2022 (positive); Cà Mau Mar–May, Hà Nội Feb–Mar (negative); 2 v1 cases"),
            "metrics": [{"label": f"[{c.get('direction')}] {c.get('case')}", "value": _m2(c),
                         "threshold": c.get("must"), "passed": c.get("pass")} for c in f2.get("cases", [])],
            "limits": tr("Trượt chiều âm: Cà Mau 05/04/2025 mưa 3 ngày 70,4 mm vượt P97 69,6 mm (đợt cho nước theo vụ bị bắt nhầm). "
                         "Ca Noru không đánh giá được: năm 2022 chỉ còn Sentinel-1A (12 ngày/lần), cảnh 25/9 và 07/10, ruộng không có đợt nước. "
                         "Soulik đạt sát nút (125,7 / 125,2 mm) — mưa ERA5 lưới thô ~25 km phân biệt kém.",
                         "Negative direction failed: Cà Mau 05/04/2025 3-day rain 70.4 mm above P97 69.6 mm (a seasonal-watering event caught by mistake). "
                         "Noru case not evaluable: in 2022 only Sentinel-1A flew (12-day revisit), scenes 25/9 and 07/10, no water event on the paddies. "
                         "Soulik passed by a hair (125.7 / 125.2 mm) — coarse ~25 km ERA5 rain separates poorly."),
            "not_for": tr("Không bật: mọi đợt ngoài mùa vẫn diễn giải theo v1.", "Not enabled: all out-of-season events keep the v1 interpretation."),
            "code": f"{REPO}/backend/app/services/flood_season.py",
        })

    # 4d — Lớp mùa lũ v3 (lưu lượng sông GloFAS, R-a / R-b) — 17/10/2026, công bố cả khi trượt
    f3 = _load("eval", "flood_season_v3_result.json")
    if f3:
        def _pos3(p):
            if not p.get("event"):
                return tr("radar không thấy nước quanh ngày lũ", "radar saw no water around the flood date")
            e, m = p["event"], p.get("margins") or {}
            bits = [f"{k} {v:+.1%}" for k, v in m.items() if isinstance(v, float)]
            return f"{e['start']}={e['season']} · q {e.get('q_max_m3s')} m³/s" + (f" · {', '.join(bits)}" if bits else "") + (" · biên mỏng" if m.get("thin") else "")
        metrics = []
        for rk in ("a", "b"):
            x = f3["rules"][rk]
            metrics += [{"label": f"R-{rk} · [dương tính] {p['id']} {p['name']} {p['date']}", "value": _pos3(p),
                         "threshold": "≥ P97 lưu lượng" if rk == "a" else "≥ P90 lưu lượng VÀ ≥ P97 mưa 3 ngày", "passed": p["caught"]}
                        for p in x["positives"]]
            metrics.append({"label": f"R-{rk} · [âm tính] {x['n_neg']} đợt (Cà Mau, Hà Nội NGOÀI phạm vi — giữ v1; Phan Rang trong phạm vi)",
                            "value": f"bắt nhầm {x['false_positives']} · biên an toàn nhỏ nhất {x['neg_min_safety']:.0%}" if x["neg_min_safety"] is not None else f"bắt nhầm {x['false_positives']}",
                            "threshold": "0 bắt nhầm", "passed": x["neg_pass"]})
            metrics.append({"label": f"R-{rk} · [giữ v1] Huế 10–11/2020, 11/2025", "value": "giữ nguyên" if x["v1_pass"] else "ĐỔI",
                            "threshold": "không đổi", "passed": x["v1_pass"]})
        out.append({
            "id": "flood_season_v3", "kind": tr("quy tắc diễn giải", "interpretation rule"),
            "name": tr("Mùa lũ v3 — lũ sớm/muộn theo lưu lượng sông GloFAS (R-a, R-b)", "Flood season v3 — early/late floods via GloFAS river discharge (R-a, R-b)"),
            "status": "accepted" if f3.get("passed") else "rejected",
            "status_label": (tr(f"cổng đạt · bật R-{f3['enabled_rule']}", f"gate passed · R-{f3['enabled_rule']} on") if f3.get("passed")
                             else tr("trượt cả R-a và R-b · không bật (giữ v1)", "R-a and R-b both failed · off (v1 kept)")),
            "task": tr("Đợt ngoài mùa v1 mà sông lên mức hiếm → 'có thể là lũ sớm/muộn'", "Out-of-season (v1) events while the river ran unusually high → 'possibly early/late flood'"),
            "data": tr("ô GloFAS 0,05° có lưu lượng TB lớn nhất trong 5 km (chỉ khi TB ≥ 10 m³/s); P97/P90 2016–2025 của chính ô đó; cửa sổ ≤ 12 ngày trước cảnh ướt đầu tiên",
                       "the 0.05° GloFAS cell with the largest mean discharge within 5 km (only if mean ≥ 10 m³/s); that cell's 2016–2025 P97/P90; window ≤ 12 days before the first wet scene"),
            "split": tr("đăng ký trước (59837ec, sửa đổi A2 e80bd09, danh sách ca 3a812f6): 12 trận bão có ngày công khai → 3 đủ điều kiện ở 2 vùng (cần ≥ 4)",
                        "pre-registered (59837ec, amendment A2 e80bd09, case list 3a812f6): 12 dated storms → 3 eligible in 2 regions (≥ 4 required)"),
            "metrics": metrics,
            "limits": tr("Soulik: ô sông chỉ 45 m³/s (P97 248) — ruộng ngập do mưa tại chỗ, sông không lên mức hiếm. Conson, Bualoi: radar không thấy nước ở điểm ruộng. "
                         "Âm tính mỏng: Cà Mau và Hà Nội không có ô sông ≥ 10 m³/s trong 5 km, chỉ 3 đợt ở Phan Rang được xét. Bão tháng 8–9 ở Hà Tĩnh – Nghệ An đã TRONG mùa v1.",
                         "Soulik: the river cell reached only 45 m³/s (P97 248) — the paddy flooded from local rain, the river did not run rare. Conson, Bualoi: radar saw no water on the paddies. "
                         "Thin negatives: Cà Mau and Hà Nội have no river cell ≥ 10 m³/s within 5 km; only 3 Phan Rang events were tested. Aug–Sep storms in Hà Tĩnh – Nghệ An are already IN the v1 season."),
            "not_for": tr("Không bật. Ca thật cho v4: câu trả lời 'ruộng có ngập thật' rơi vào đợt ngoài mùa (bảng season_cases) — "
                          "từ trả lời một chạm, quan sát lũ, và nút 'Ruộng có ngập đợt này không?' dưới từng đợt nước.",
                          "Not enabled. Real cases for v4: 'my field really flooded' answers that fall on out-of-season events (season_cases table) — "
                          "from one-tap answers, flood observations and the 'Was the field flooded this time?' buttons under each water event."),
            "code": f"{REPO}/backend/app/services/flood_season.py",
        })

    # 5 — Kiểm chứng tin đăng (luật từ khoá) và chạm-là-có-ranh (trượt)
    # Cổng GĐ3 (18/10/2026): mỗi lần là một mẫu MỚI đăng ký trước — lần sau không chấm lại mẫu của lần trước.
    runs = [(v, r) for v, r in (("1", _load("eval", "listing_gate_result.json")), ("2", _load("eval", "listing_gate_v2_result.json")),
                                     ("3", _load("eval", "listing_gate_v3_result.json"))) if r]
    base = {
        "id": "listing_rules", "kind": tr("quy tắc NLP", "NLP rules"),
        "name": tr("Tách câu khẳng định trong tin đăng bán đất", "Claim extraction from land listings"),
        "task": tr("8 loại câu: không ngập, cao ráo, gần sông/biển, bằng phẳng, không sạt lở, thổ cư, nước ngọt",
                   "8 claim types: no flooding, high ground, near river/sea, flat, no landslides, residential, fresh water"),
        "not_for": tr("Không phải kết luận pháp lý về người bán.", "Not a legal finding about the seller."),
        "code": f"{REPO}/backend/app/services/listing_check.py",
    }
    if runs:
        v, last = runs[-1]
        names = {t: vi for t, vi, *_ in __import__("app.services.listing_check", fromlist=["CLAIMS"]).CLAIMS}
        out.append({**base,
            "status": "accepted" if last.get("passed") else "rejected",
            "status_label": (tr(f"cổng lần {v} đạt · luật từ khoá đang chạy", f"gate run {v} passed · keyword rules live") if last.get("passed")
                             else tr(f"cổng lần {v} trượt · vẫn chạy luật từ khoá (không có bộ thay thế), độ chính xác công khai",
                                     f"gate run {v} failed · keyword rules still live (no replacement), accuracy published")),
            "data": tr(f"{last['n']} tin đăng ĐẤT thật, lấy ngẫu nhiên theo hạt giống đăng ký trước từ bộ công khai tinixai/vietnam-real-estates "
                       f"(CC BY-NC 4.0, {last.get('population')} tin đất trong shard)",
                       f"{last['n']} real LAND listings, seeded random sample registered in advance from the public tinixai/vietnam-real-estates "
                       f"set (CC BY-NC 4.0, {last.get('population')} land listings in the shard)"),
            "split": tr("nhãn do Claude (AI) gán theo uỷ quyền chủ dự án, commit TRƯỚC khi chấm — KHÔNG phải nhãn người; ngưỡng F1 trung bình ≥ 0,80; "
                        + " · ".join(f"lần {k}: F1 {r.get('macro_f1')}" for k, r in runs),
                        "labels by Claude (AI) on the owner's authority, committed BEFORE scoring — NOT human labels; threshold macro F1 ≥ 0.80; "
                        + " · ".join(f"run {k}: F1 {r.get('macro_f1')}" for k, r in runs)),
            "metrics": [{"label": tr(f"{names.get(r['type'], r['type'])} — chính xác / độ phủ (đúng · thừa · sót)",
                                     f"{r['type']} — precision / recall (tp · fp · fn)"),
                         "value": f"{r['precision']} / {r['recall']} ({r['tp']} · {r['fp']} · {r['fn']})",
                         "threshold": f"F1 {r['f1']}", "passed": r["f1"] >= 0.8} for r in last.get("per_type", [])]
                       + [{"label": tr("F1 trung bình", "Macro F1"), "value": last.get("macro_f1"), "threshold": "≥ 0.80",
                           "passed": bool(last.get("passed"))}],
            "limits": tr("Nhãn của AI cùng 'tác giả' với bộ luật nên không độc lập hoàn toàn; tin đăng phần lớn ở TP.HCM, Hà Nội, ít tin ruộng "
                         "vườn ven sông/biển nên loại 'không ngập', 'gần sông' có rất ít mẫu. Muốn tin hơn: chủ dự án duyệt/gán lại ở /admin → Tin đăng GĐ3.",
                         "AI labels share an 'author' with the rules, so they are not fully independent; listings are mostly HCMC/Hanoi with few "
                         "riverside/coastal farm plots, so 'no flooding' and 'near river' have very few examples. For more trust: the owner reviews "
                         "or relabels in /admin → GĐ3 listings."),
        })
    else:
        out.append({**base, "status": "pending",
            "status_label": tr("đang chạy luật từ khoá · cổng chờ 20 tin thật", "keyword rules live · gate awaits 20 real listings"),
            "data": tr("luật tiếng Việt có dấu và không dấu", "Vietnamese rules with and without diacritics"),
            "split": tr("cổng: 20 tin thật gán nhãn; PhoBERT chỉ thay luật khi F1 ≥ 0,8", "gate: 20 labelled real listings; PhoBERT replaces rules only at F1 ≥ 0.8"),
            "metrics": [], "limits": tr("Chưa đo trên tin thật.", "Not yet measured on real listings.")})
    ab = _load("eval", "autoboundary_result.json")
    out.append({
        "id": "autoboundary", "kind": tr("thị giác máy tính", "computer vision"),
        "name": tr("Chạm là có ranh (Sentinel-2 10 m)", "Tap-to-boundary (Sentinel-2 10 m)"),
        "status": "rejected", "status_label": tr("trượt · không bật", "failed · off"),
        "task": tr("Tự vẽ ranh thửa từ một điểm chạm", "Auto-draw a plot boundary from one tap"),
        "data": tr("77 ranh OpenStreetMap đối chiếu", "77 OpenStreetMap boundaries"),
        "split": "—",
        "metrics": [{"label": "IoU", "value": str((ab or {}).get("median_iou_proposed")), "threshold": "0,60", "passed": False}],
        "limits": tr("10 m quá thô cho thửa nhỏ; cần ảnh ≤ 3 m hoặc mô hình tách ranh huấn luyện sẵn.",
                     "10 m is too coarse for small plots; needs ≤ 3 m imagery or a pretrained field-boundary model."),
        "not_for": "—", "code": f"{REPO}/backend/app/services/autoboundary.py",
    })
    return out
