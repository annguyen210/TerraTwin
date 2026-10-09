"""GĐ4 · NĂNG LỰC 4 — LỜI DIỄN GIẢI MÀ MỖI CÂU BẤM VÀO LÀ RA BẰNG CHỨNG.

Hồ sơ đất số là một bảng số. Người mua đất, cán bộ tín dụng cần đọc nó thành câu. Nhưng một
câu văn KHÔNG có nguồn thì không khác gì lời môi giới. Nên ở đây:

  1. Kho bằng chứng `catalog(facts)` dựng THẲNG từ nội dung đã ký: mỗi mục có id, giá trị, nguồn,
     ngày đo, cách tái lập (đường dẫn API công khai hoặc tệp mã nguồn mở). Không gọi mạng, không
     thêm số nào ngoài nội dung đã ký.
  2. Mỗi câu diễn giải mang danh sách id bằng chứng nó dựa vào. Bấm câu → hiện các mục đó.
  3. Câu mặc định viết bằng MẪU CÂU (tất định, kiểm được). Có LLM thì LLM được viết lại lời cho
     dễ đọc — nhưng chỉ từ đúng các mục bằng chứng của câu đó (RAG trên kho bằng chứng của chính
     thửa), và mọi con số đi qua rào chắn con số (guard): số nào không có trong bằng chứng ĐƯỢC
     DẪN của câu thì câu LLM bị loại, giữ câu mẫu. Không phải "ẩn số rồi in tiếp" — câu có số bịa
     là câu hỏng, bỏ cả câu.

Lời diễn giải KHÔNG nằm trong nội dung ký (nó sinh lại được từ nội dung ký bất cứ lúc nào); trang
hồ sơ ghi rõ điều đó.
"""
from __future__ import annotations

import json
import re

from app.services import guard
from app.services.reqlang import cur_lang

REPO = "https://github.com/annguyen210/TerraTwin/blob/main"
WATER_RULE = "VV p10 < −18 dB và thấp hơn nền của chính thửa ≥ 3 dB"
WATER_RULE_EN = "VV p10 < −18 dB and ≥ 3 dB below the plot's own baseline"


def _t(vi: str, en: str, lang: str) -> str:
    return en if lang == "en" else vi


def _num(v) -> str:
    """Viết số như trên trang hồ sơ (dấu chấm thập phân, bỏ .0)."""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def catalog(facts: dict, lang: str | None = None) -> dict[str, dict]:
    """Kho bằng chứng của MỘT hồ sơ: id → {label, value, source, measured, reproduce, url?}."""
    lang = lang or cur_lang()
    loc = facts.get("location") or {}
    lat, lon = loc.get("lat"), loc.get("lon")
    out: dict[str, dict] = {}

    lu = facts.get("land_use")
    if lu and lu.get("classes"):
        top = lu["classes"][0]
        out["land_use.dominant"] = {
            "label": _t("Lớp phủ chiếm nhiều nhất", "Dominant land cover", lang),
            "value": f"{top['name']} {_num(round(top['pct']))}%",
            "source": lu.get("source") or "ESA WorldCover",
            "measured": str(lu.get("year") or "2021"),
            "reproduce": _t(
                f"Đếm điểm ảnh 10 m của ESA WorldCover (Microsoft Planetary Computer, collection esa-worldcover"
                f"{', item ' + lu['item'] if lu.get('item') else ''}) trong bán kính 60 m quanh tâm thửa: "
                f"{lu.get('pixels', '?')} điểm ảnh.",
                f"Count the 10 m ESA WorldCover pixels (Microsoft Planetary Computer, collection esa-worldcover"
                f"{', item ' + lu['item'] if lu.get('item') else ''}) within 60 m of the plot centre: "
                f"{lu.get('pixels', '?')} pixels.", lang),
            "url": f"{REPO}/backend/app/services/landuse.py",
        }

    tr_ = facts.get("terrain")
    if tr_:
        dem_url = (f"https://api.open-meteo.com/v1/elevation?latitude={lat}&longitude={lon}"
                   if lat is not None and lon is not None else None)
        out["terrain.elevation"] = {
            "label": _t("Cao độ tâm thửa", "Elevation at the plot centre", lang),
            "value": f"{_num(tr_['elevation_m'])} m",
            "source": "Copernicus DEM GLO-90 — Open-Meteo Elevation API",
            "measured": _t("mô hình số độ cao (bản cố định)", "digital elevation model (static release)", lang),
            "reproduce": _t("Mở đường dẫn API (công khai, không cần khoá) với đúng toạ độ thửa.",
                            "Open the API link (public, no key) with the plot's coordinates.", lang),
            "url": dem_url,
        }
        out["terrain.relative"] = {
            "label": _t(f"Thấp hơn bao nhiêu phần đất trong {_num(tr_['radius_km'])} km",
                        f"Share of land within {_num(tr_['radius_km'])} km that is higher", lang),
            "value": f"{_num(tr_['lower_than_pct'])}%",
            "source": "Copernicus DEM GLO-90 — Open-Meteo Elevation API",
            "measured": _t("mô hình số độ cao (bản cố định)", "digital elevation model (static release)", lang),
            "reproduce": _t(
                f"Lấy cao độ {tr_.get('neighbours_sampled', '?')} điểm trên các vòng quanh thửa tới "
                f"{_num(tr_['radius_km'])} km (thấp nhất {_num(tr_.get('around_min_m', '?'))} m, cao nhất "
                f"{_num(tr_.get('around_max_m', '?'))} m), đếm tỉ lệ điểm cao hơn tâm thửa.",
                f"Sample the elevation of {tr_.get('neighbours_sampled', '?')} points on rings around the plot out "
                f"to {_num(tr_['radius_km'])} km (min {_num(tr_.get('around_min_m', '?'))} m, max "
                f"{_num(tr_.get('around_max_m', '?'))} m) and count the share higher than the centre.", lang),
            "url": f"{REPO}/backend/app/services/passport.py",
        }
        if tr_.get("slope_deg") is not None:
            out["terrain.slope"] = {
                "label": _t("Độ dốc", "Slope", lang), "value": f"{_num(tr_['slope_deg'])}°",
                "source": "Copernicus DEM GLO-90 — Open-Meteo Elevation API",
                "measured": _t("mô hình số độ cao (bản cố định)", "digital elevation model (static release)", lang),
                "reproduce": _t("Sai phân cao độ bốn điểm lân cận quanh tâm thửa.",
                                "Finite differences of the elevation at four neighbours of the plot centre.", lang),
                "url": f"{REPO}/backend/app/services/passport.py",
            }

    for mid, h in (facts.get("history_10y") or {}).items():
        val = (_t(f"{h['events']} đợt vượt ngưỡng", f"{h['events']} episode(s) over threshold", lang)
               + (_t(f", gần nhất {h['latest']}", f", latest {h['latest']}", lang) if h.get("latest") else "")
               + _t(f"; nặng nhất {h.get('worst_date')}", f"; most severe {h.get('worst_date')}", lang))
        out[f"history.{mid}"] = {
            "label": _t(f"Mười năm {h.get('name', mid)}", f"Ten years of {h.get('name', mid)}", lang),
            "value": val,
            "source": "ERA5 (ECMWF) — Open-Meteo Archive API",
            "measured": _t("chuỗi ngày 10 năm trước ngày phát hành", "daily series, 10 years before issuance", lang),
            "reproduce": _t(
                f"Tính chỉ số hiểm hoạ theo ngày từ ERA5 tại toạ độ thửa; cửa sổ vượt ngưỡng chung cả nước "
                f"({_num(h.get('national_threshold', '?'))}) gộp thành đợt (passport.history).",
                f"Compute the daily hazard index from ERA5 at the plot; windows above the national threshold "
                f"({_num(h.get('national_threshold', '?'))}) are merged into episodes (passport.history).", lang),
            "url": f"{REPO}/backend/app/services/passport.py",
        }

    w = facts.get("water_history_radar")
    if w:
        out["water.summary"] = {
            "label": _t("Lịch sử nước radar", "Radar water history", lang),
            "value": _t(f"{w['n_events']} đợt nước phủ trong {w['n_scenes']} cảnh ({w['first']} → {w['last']})",
                        f"{w['n_events']} water event(s) in {w['n_scenes']} scenes ({w['first']} → {w['last']})", lang),
            "source": "Sentinel-1 RTC (Copernicus) — Microsoft Planetary Computer",
            "measured": f"{w['first']} → {w['last']}",
            "reproduce": _t(f"Quy tắc: {WATER_RULE}; gộp cảnh cách nhau ≤ 24 ngày; một quỹ đạo. Chạy lại: "
                            f"POST /api/water/history với toạ độ thửa.",
                            f"Rule: {WATER_RULE_EN}; scenes ≤ 24 days apart are merged; one orbit track. "
                            f"Re-run: POST /api/water/history with the plot coordinates.", lang),
            "url": f"{REPO}/backend/app/services/water_history.py",
        }
        for i, e in enumerate(w.get("events") or []):
            out[f"water.event.{i + 1}"] = {
                "label": _t(f"Đợt nước {i + 1}", f"Water event {i + 1}", lang),
                "value": (f"{e['start']} → {e['end']}" if e["start"] != e["end"] else e["start"])
                         + _t(f", phủ {e['peak_cover']}, {e['n_scenes']} cảnh",
                              f", {e['peak_cover']} covered, {e['n_scenes']} scene(s)", lang),
                "source": "Sentinel-1 RTC (Copernicus) — Microsoft Planetary Computer",
                "measured": e["start"],
                "reproduce": _t(f"Cảnh radar ngày {e['start']}, VV thấp nhất (trung vị) {_num(e.get('min_p50_db', '?'))} dB.",
                                f"Radar scene of {e['start']}, lowest median VV {_num(e.get('min_p50_db', '?'))} dB.", lang),
                "url": f"{REPO}/backend/app/services/water_history.py",
            }

    ev = facts.get("field_evidence") or []
    if ev:
        out["photos"] = {
            "label": _t("Ảnh thực địa đã kiểm", "Verified field photos", lang),
            "value": ", ".join(f"{e.get('id')}: {e.get('verdict_label') or e.get('verdict')}" for e in ev),
            "source": _t("Ảnh gốc người dùng tải lên (GPS, thời điểm, dấu chỉnh sửa)",
                         "Original user photos (GPS, timestamp, edit traces)", lang),
            "measured": ", ".join(sorted({str(e.get("taken_at") or "?")[:10] for e in ev})),
            "reproduce": _t("SHA-256 ảnh gốc và ảnh thu nhỏ được đóng băng trong nội dung ký.",
                            "SHA-256 of the original and the thumbnail are frozen in the signed content.", lang),
            "url": f"{REPO}/backend/app/services/evidence.py",
        }

    lc = facts.get("listing_check") or {}
    for c in lc.get("claims") or []:
        word = {"contradicted": _t("mâu thuẫn", "contradicted", lang), "consistent": _t("khớp", "consistent", lang),
                "insufficient": _t("không đủ dữ liệu", "not enough data", lang)}[c["verdict"]]
        out[f"listing.{c['type']}"] = {
            "label": _t(f"Tin đăng khẳng định: {c['label']}", f"Listing claims: {c['label']}", lang),
            "value": f"{word} — {c['evidence']}",
            "source": c.get("source") or "",
            "measured": (lc.get("checked_at") or "")[:10],
            "reproduce": _t("Dán lại nguyên văn tin đăng vào ô Kiểm chứng tin đăng (POST /api/listing/check) — nguyên văn "
                            "không được lưu trong hồ sơ.",
                            "Paste the listing text again into the listing check (POST /api/listing/check) — the text "
                            "itself is not stored in the dossier.", lang),
            "url": f"{REPO}/backend/app/services/listing_check.py",
        }

    if facts.get("missing"):
        out["missing"] = {
            "label": _t("Mục không lấy được lúc phát hành", "Sections unavailable at issuance", lang),
            "value": ", ".join(facts["missing"]),
            "source": "TerraTwin", "measured": "—",
            "reproduce": _t("Hồ sơ ghi là thiếu, không điền số thay.", "Marked missing, never filled in.", lang),
        }
    return out


def template_sentences(facts: dict, cat: dict, lang: str | None = None) -> list[dict]:
    """Câu mẫu tất định — mỗi câu chỉ dùng số có trong các mục bằng chứng nó dẫn."""
    lang = lang or cur_lang()
    s: list[dict] = []

    if "water.summary" in cat:
        w = facts["water_history_radar"]
        if w["n_events"] == 0:
            text = _t(f"Radar Sentinel-1 chưa thấy nước phủ thửa lần nào trong {w['n_scenes']} cảnh, "
                      f"từ {w['first']} đến {w['last']}.",
                      f"Sentinel-1 radar saw no water over the plot in {w['n_scenes']} scenes, "
                      f"from {w['first']} to {w['last']}.", lang)
            ids = ["water.summary"]
        else:
            last = w["events"][-1]["start"] if w.get("events") else None
            text = _t(f"Radar Sentinel-1 thấy nước phủ thửa {w['n_events']} đợt trong {w['n_scenes']} cảnh "
                      f"từ {w['first']} đến {w['last']}" + (f"; đợt gần nhất bắt đầu {last}." if last else "."),
                      f"Sentinel-1 radar saw water over the plot {w['n_events']} time(s) in {w['n_scenes']} scenes "
                      f"from {w['first']} to {w['last']}" + (f"; the latest began {last}." if last else "."), lang)
            ids = ["water.summary"] + ([f"water.event.{len(w['events'])}"] if w.get("events") else [])
        s.append({"text": text, "evidence": ids})

    for c in (facts.get("listing_check") or {}).get("claims") or []:
        if c["verdict"] == "contradicted":
            s.append({"text": _t(f"Tin đăng khẳng định “{c['label'].lower()}”, nhưng dữ liệu đo ghi nhận: {c['evidence']}",
                                 f"The listing claims “{c['label'].lower()}”, but the measured data shows: {c['evidence']}", lang),
                      "evidence": [f"listing.{c['type']}"]})

    if "land_use.dominant" in cat:
        lu = facts["land_use"]
        top = lu["classes"][0]
        s.append({"text": _t(f"Phần lớn thửa là {top['name'].lower()} ({_num(round(top['pct']))}%), theo ảnh vệ tinh "
                             f"ESA WorldCover {lu.get('year') or 2021}.",
                             f"Most of the plot is {top['name'].lower()} ({_num(round(top['pct']))}%), according to "
                             f"ESA WorldCover {lu.get('year') or 2021} satellite imagery.", lang),
                  "evidence": ["land_use.dominant"]})

    if "terrain.elevation" in cat:
        t = facts["terrain"]
        p = t["lower_than_pct"]
        how = (_t("trũng hơn hầu hết đất xung quanh, nước dồn về trước và rút sau cùng",
                  "lower than most surrounding land, so water arrives first and leaves last", lang) if p >= 70 else
               _t("cao hơn hầu hết đất xung quanh, ít bị nước nơi khác dồn về",
                  "higher than most surrounding land, so little water flows in from elsewhere", lang) if p <= 30 else
               _t("ở mức trung bình so với đất xung quanh", "about average compared with surrounding land", lang))
        s.append({"text": _t(f"Thửa cao {_num(t['elevation_m'])} m, thấp hơn {_num(p)}% đất trong bán kính "
                             f"{_num(t['radius_km'])} km — tức là {how}.",
                             f"The plot sits at {_num(t['elevation_m'])} m, lower than {_num(p)}% of land within "
                             f"{_num(t['radius_km'])} km — i.e. {how}.", lang),
                  "evidence": ["terrain.elevation", "terrain.relative"]})

    hist = facts.get("history_10y") or {}
    hit = [(mid, h) for mid, h in hist.items() if h.get("events")]
    for mid, h in hit:
        s.append({"text": _t(f"Mười năm qua tại thửa có {h['events']} đợt {h.get('name', mid).lower()} vượt ngưỡng "
                             f"chung cả nước, gần nhất {h.get('latest')}.",
                             f"In the past ten years the plot had {h['events']} {h.get('name', mid).lower()} "
                             f"episode(s) above the national threshold, the latest on {h.get('latest')}.", lang),
                  "evidence": [f"history.{mid}"]})
    if hist and not hit:
        s.append({"text": _t("Mười năm qua tại thửa chưa có hiểm hoạ nào vượt ngưỡng chung cả nước.",
                             "In the past ten years no hazard at the plot exceeded the national threshold.", lang),
                  "evidence": [f"history.{mid}" for mid in hist]})

    if "photos" in cat:
        n = len(facts.get("field_evidence") or [])
        s.append({"text": _t(f"Hồ sơ đóng băng {n} ảnh thực địa đã kiểm GPS và thời điểm chụp.",
                             f"The dossier freezes {n} field photo(s) checked for GPS and capture time.", lang),
                  "evidence": ["photos"]})

    if "missing" in cat:
        s.append({"text": _t("Một số mục không lấy được lúc phát hành; hồ sơ ghi là thiếu chứ không điền số thay.",
                             "Some sections were unavailable at issuance; the dossier marks them missing instead "
                             "of filling in numbers.", lang),
                  "evidence": ["missing"]})
    return s


def _evidence_text(cat: dict, ids: list[str]) -> str:
    return " | ".join(f"{cat[i]['label']}: {cat[i]['value']} ({cat[i]['measured']})" for i in ids if i in cat)


_SYSTEM = ("Bạn viết lại câu cho người dân đọc dễ hiểu. TUYỆT ĐỐI không thêm con số, ngày tháng, tên địa danh "
           "hay nhận định nào không có trong BẰNG CHỨNG của chính câu đó. Không khuyên mua/bán. Giữ nguyên nghĩa. "
           "Trả về DUY NHẤT một mảng JSON các chuỗi, đúng số phần tử và đúng thứ tự như đầu vào.")


def _llm_rewrite(sents: list[dict], cat: dict, lang: str) -> tuple[list[dict], int, bool]:
    """Viết lại lời bằng LLM (nếu có). Trả (câu, số câu bị rào chắn loại, có dùng LLM không)."""
    from app.services import llm
    if not sents or not llm.available():
        return sents, 0, False
    items = [{"draft": x["text"], "evidence": _evidence_text(cat, x["evidence"])} for x in sents]
    prompt = (("Ngôn ngữ đầu ra: tiếng Việt.\n" if lang != "en" else "Output language: English.\n")
              + "Mỗi phần tử: câu nháp + bằng chứng duy nhất được phép dùng.\n"
              + json.dumps(items, ensure_ascii=False))
    raw = llm.complete(prompt, system=_SYSTEM, max_tokens=900)
    if not raw:
        return sents, 0, False
    m = re.search(r"\[.*\]", raw, re.S)
    try:
        out = json.loads(m.group(0)) if m else None
    except ValueError:
        out = None
    if not isinstance(out, list) or len(out) != len(sents):
        return sents, 0, False
    res, blocked, used = [], 0, False
    for draft, new in zip(sents, out):
        if not isinstance(new, str) or not new.strip():
            res.append(draft)
            continue
        allowed = guard.numbers_in(_evidence_text(cat, draft["evidence"]))
        _, removed = guard.strip_invented_numbers(new, allowed)
        if removed:                       # câu có số không nằm trong bằng chứng của nó → bỏ cả câu
            blocked += 1
            res.append({**draft, "blocked_numbers": removed})
        else:
            used = True
            res.append({**draft, "text": new.strip(), "by": "llm"})
    return res, blocked, used


def build(facts: dict, dossier_id: str | None = None, lang: str | None = None) -> dict | None:
    """Lời diễn giải + kho bằng chứng cho trang hồ sơ. None với hồ sơ không phải hồ sơ đất."""
    if facts.get("kind") in ("eudr_plot", "lot_certificate"):
        return None
    lang = lang or cur_lang()
    cat = catalog(facts, lang)
    sents = template_sentences(facts, cat, lang)
    if not sents:
        return None

    from app.services import cache_store, llm
    key = cache_store.make_key("narrative", dossier_id or "", lang, llm.info().get("model") or "")
    hit = cache_store.get(key) if dossier_id and llm.available() else None
    if hit:
        sents, blocked, used = hit["sentences"], hit["blocked"], hit["used"]
    else:
        sents, blocked, used = _llm_rewrite(sents, cat, lang)
        if dossier_id and used:
            cache_store.put(key, {"sentences": sents, "blocked": blocked, "used": used}, 30 * 86400)
    for i, x in enumerate(sents):
        x["id"] = f"s{i + 1}"
    return {
        "mode": "llm" if used else "template",
        "blocked_sentences": blocked,
        "sentences": [{k: v for k, v in x.items() if k != "blocked_numbers"} for x in sents],
        "evidence": cat,
        "note": _t("Lời diễn giải sinh lại từ nội dung đã ký, không nằm trong phần ký. Mỗi câu chỉ dùng số có trong "
                   "bằng chứng nó dẫn; câu do AI viết lại mà có số lạ bị loại, giữ câu mẫu.",
                   "This summary is regenerated from the signed content and is not itself signed. Each sentence "
                   "only uses numbers from the evidence it cites; AI-rewritten sentences with unknown numbers are "
                   "dropped in favour of the template.", lang),
    }
