"""ĐỌC SỔ ĐỎ VÀ ĐỐI CHIẾU — phần "HỢP PHÁP" của EUDR mà ảnh vệ tinh không trả lời được.

EUDR đòi hai thứ: không phá rừng (vệ tinh trả lời được) VÀ sản xuất đúng luật nước sở
tại, trước hết là quyền sử dụng đất (Điều 2(40)). Ở Việt Nam bằng chứng đó nằm trên
GIẤY CHỨNG NHẬN QUYỀN SỬ DỤNG ĐẤT (sổ đỏ / sổ hồng): số thửa, tờ bản đồ, diện tích,
MỤC ĐÍCH SỬ DỤNG, thời hạn.

Hai việc:
  1. ĐỌC (tuỳ chọn, cần khoá LLM đa phương thức): chụp sổ → AI trích các trường thành
     JSON. Không có khoá → người dùng nhập tay, phần đối chiếu vẫn chạy y hệt.
  2. ĐỐI CHIẾU (luôn chạy, không AI, tất định):
       · diện tích trên sổ ↔ diện tích ranh đo thật,
       · mục đích sử dụng: đất nông nghiệp (CLN, LUA, HNK…) ổn; đất RỪNG SẢN XUẤT
         (RSX) cần xem; đất RỪNG PHÒNG HỘ (RPH) / ĐẶC DỤNG (RDD) là CỜ ĐỎ,
       · thời hạn sử dụng còn hay đã hết,
       · tên chủ trên sổ ↔ tên chủ hộ khai (không dấu, không phân biệt hoa thường).

NHÃN TIN CẬY: "declared" — trường do người khai cung cấp (TerraTwin đọc + đối chiếu,
KHÔNG xác minh với văn phòng đăng ký đất đai). KHÔNG lưu ảnh sổ: chỉ lưu SHA-256 của
ảnh (chứng minh sau này đúng ảnh đó) và các trường đã trích. Tên chủ trên sổ là dữ
liệu cá nhân → đi qua tiết lộ chọn lọc như họ tên chủ hộ.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import date

from app.services.reqlang import tr

# Ký hiệu loại đất trên bản đồ địa chính / giấy chứng nhận → (tên, nhóm)
LAND_USE = {
    "CLN": ("Đất trồng cây lâu năm", "agri"), "LUC": ("Đất chuyên trồng lúa nước", "agri"),
    "LUK": ("Đất trồng lúa nước còn lại", "agri"), "LUN": ("Đất lúa nương", "agri"),
    "LUA": ("Đất trồng lúa", "agri"), "BHK": ("Đất bằng trồng cây hàng năm khác", "agri"),
    "NHK": ("Đất nương rẫy trồng cây hàng năm khác", "agri"), "HNK": ("Đất trồng cây hàng năm khác", "agri"),
    "NTS": ("Đất nuôi trồng thuỷ sản", "agri"), "NKH": ("Đất nông nghiệp khác", "agri"),
    "RSX": ("Đất rừng sản xuất", "forest_production"), "RPH": ("Đất rừng phòng hộ", "forest_protection"),
    "RDD": ("Đất rừng đặc dụng", "forest_special"),
    "ONT": ("Đất ở tại nông thôn", "residential"), "ODT": ("Đất ở tại đô thị", "residential"),
}
FIELDS = ("so_thua", "to_ban_do", "dien_tich_m2", "ma_muc_dich", "muc_dich", "thoi_han", "dia_chi_thua",
          "so_phat_hanh", "ten_chu")

PROMPT = (
    "Đây là ảnh Giấy chứng nhận quyền sử dụng đất của Việt Nam. Trích CHÍNH XÁC các trường sau, không đoán. "
    "Trả về DUY NHẤT một đối tượng JSON với các khoá: so_thua (chuỗi), to_ban_do (chuỗi), dien_tich_m2 (số, "
    "mét vuông), ma_muc_dich (ký hiệu loại đất như CLN, LUC, RSX, RPH, RDD, ONT… hoặc null), muc_dich (nguyên "
    "văn mục đích sử dụng), thoi_han (ngày dạng YYYY-MM-DD, hoặc \"lâu dài\", hoặc null), dia_chi_thua (chuỗi), "
    "so_phat_hanh (số seri phát hành, chuỗi), ten_chu (họ tên người sử dụng đất), confidence (0–1). Trường nào "
    "không đọc được thì để null. Nếu ảnh KHÔNG phải giấy chứng nhận quyền sử dụng đất, trả {\"not_a_certificate\": true}."
)


def _strip(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d").replace("Đ", "D")
    return re.sub(r"\s+", " ", s).strip().lower()


def _num(v) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).lower().replace("m2", "").replace("m²", "").strip()
    # "1.234,5" (kiểu Việt) → 1234.5 ; "12.000" (kiểu Việt, chấm ngăn hàng nghìn) → 12000 ;
    # "1234.5" (kiểu Anh, AI hay trả) → 1234.5
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    elif "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(re.findall(r"-?\d+(?:\.\d+)?", s)[0])
    except (IndexError, ValueError):
        return None


def normalize(fields: dict) -> dict:
    out = {k: (fields.get(k) if fields.get(k) not in ("", None) else None) for k in FIELDS}
    out["dien_tich_m2"] = _num(out["dien_tich_m2"])
    code = (str(out["ma_muc_dich"]).upper().strip() if out["ma_muc_dich"] else None)
    if not code and out["muc_dich"]:
        mm = _strip(str(out["muc_dich"]))
        for c, (name, _) in LAND_USE.items():
            if _strip(name) in mm:
                code = c
                break
    out["ma_muc_dich"] = code
    for k in ("so_thua", "to_ban_do", "muc_dich", "thoi_han", "dia_chi_thua", "so_phat_hanh", "ten_chu"):
        if out[k] is not None:
            out[k] = str(out[k]).strip()[:200]
    return out


def extract(image_b64: str, media_type: str = "image/jpeg") -> dict | None:
    """AI đọc ảnh sổ → trường đã chuẩn hoá, hoặc None (chưa cấu hình / không đọc được)."""
    from app.services import llm
    text = llm.complete_vision(PROMPT, image_b64, media_type,
                               system="Bạn là công cụ trích xuất dữ liệu giấy tờ. Chỉ trả JSON.", max_tokens=700)
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if d.get("not_a_certificate"):
        return {"not_a_certificate": True}
    out = normalize(d)
    try:
        out["confidence"] = max(0.0, min(1.0, float(d.get("confidence"))))
    except (TypeError, ValueError):
        out["confidence"] = None
    return out


def check(fields: dict, plot_area_ha: float | None, producer: str | None = None,
          today: date | None = None) -> dict:
    """Đối chiếu TẤT ĐỊNH. → {checks [{id, ok True/False/None, label}], verdict ok|review|red_flag}."""
    f = normalize(fields)
    today = today or date.today()
    checks = []

    a = f["dien_tich_m2"]
    if a and plot_area_ha:
        plot_m2 = plot_area_ha * 10_000
        diff = abs(plot_m2 - a) / a * 100
        ok = True if diff <= 10 else (None if diff <= 25 else False)
        checks.append({"id": "area", "ok": ok, "diff_pct": round(diff, 1), "label": tr(
            f"Diện tích trên sổ {a:,.0f} m², ranh đo {plot_m2:,.0f} m² (lệch {diff:.0f}%)"
            + ("" if ok else " — một sổ có thể gồm nhiều thửa, hoặc vườn chỉ là một phần thửa; cần giải thích."),
            f"Certificate area {a:,.0f} m², measured boundary {plot_m2:,.0f} m² ({diff:.0f}% off)"
            + ("" if ok else " — one certificate may cover several plots, or the farm is part of a plot; explain."))})
    else:
        checks.append({"id": "area", "ok": None, "label": tr("Thiếu diện tích trên sổ hoặc ranh đo — chưa đối chiếu được.",
                                                             "Certificate or boundary area missing — not compared.")})

    code = f["ma_muc_dich"]
    name, group = LAND_USE.get(code or "", (f["muc_dich"] or tr("không rõ", "unknown"), None))
    if group == "agri":
        checks.append({"id": "land_use", "ok": True, "label": tr(f"Mục đích: {name} ({code}) — đất nông nghiệp.",
                                                                 f"Use: {name} ({code}) — agricultural land.")})
    elif group == "forest_production":
        checks.append({"id": "land_use", "ok": None, "label": tr(
            f"Mục đích: {name} ({code}). Trồng cà phê, cao su trên đất rừng sản xuất cần phương án/giấy phép phù hợp, "
            "và với EUDR thửa có thể vẫn là rừng — cần xem kỹ.",
            f"Use: {name} ({code}). Growing coffee or rubber on production-forest land needs a matching plan/permit, and "
            "under the EUDR the plot may still be forest — review carefully.")})
    elif group in ("forest_protection", "forest_special"):
        checks.append({"id": "land_use", "ok": False, "label": tr(
            f"CỜ ĐỎ — mục đích: {name} ({code}). Sản xuất nông nghiệp trên đất rừng phòng hộ / đặc dụng nhiều khả năng "
            "trái luật — không đưa vào chuỗi cung ứng EU khi chưa làm rõ.",
            f"RED FLAG — use: {name} ({code}). Farming on protection / special-use forest land is likely illegal — keep "
            "it out of the EU supply chain until clarified.")})
    else:
        checks.append({"id": "land_use", "ok": None, "label": tr(
            f"Mục đích: {name}{f' ({code})' if code else ''} — không phải nhóm đất nông nghiệp đã biết; kiểm lại.",
            f"Use: {name}{f' ({code})' if code else ''} — not a known agricultural category; check it.")})

    th = f["thoi_han"]
    if th and _strip(th).startswith("lau dai"):
        checks.append({"id": "term", "ok": True, "label": tr("Thời hạn sử dụng: lâu dài.", "Term: indefinite.")})
    elif th:
        try:
            end = date.fromisoformat(th[:10])
            ok = end >= today
            checks.append({"id": "term", "ok": ok, "label": tr(
                f"Thời hạn sử dụng đến {end:%d/%m/%Y}" + ("." if ok else " — ĐÃ HẾT HẠN."),
                f"Term until {end:%d/%m/%Y}" + ("." if ok else " — EXPIRED."))})
        except ValueError:
            checks.append({"id": "term", "ok": None, "label": tr(f"Thời hạn: “{th}” — không đọc được ngày.",
                                                                 f"Term: “{th}” — date unreadable.")})
    else:
        checks.append({"id": "term", "ok": None, "label": tr("Không có thời hạn sử dụng.", "No term given.")})

    if f["ten_chu"] and producer:
        a_tok, b_tok = set(_strip(f["ten_chu"]).split()), set(_strip(producer).split())
        overlap = len(a_tok & b_tok) / max(1, min(len(a_tok), len(b_tok)))
        ok = True if overlap >= 0.99 else (None if overlap >= 0.5 else False)
        checks.append({"id": "owner", "ok": ok, "label": tr(
            "Tên chủ trên sổ khớp chủ hộ khai." if ok else
            ("Tên chủ trên sổ chỉ khớp một phần với chủ hộ khai — có thể là người thân, cần giải thích." if ok is None
             else "Tên chủ trên sổ KHÁC chủ hộ khai — cần hợp đồng thuê / uỷ quyền."),
            "Certificate holder matches the declared producer." if ok else
            ("Certificate holder only partly matches the producer — maybe a relative; explain." if ok is None
             else "Certificate holder DIFFERS from the producer — a lease / authorisation is needed."))})

    oks = [c["ok"] for c in checks]
    verdict = "red_flag" if any(c["id"] == "land_use" and c["ok"] is False for c in checks) else (
        "review" if False in oks or None in oks else "ok")
    return {"fields": f, "checks": checks, "verdict": verdict,
            "label": {"ok": tr("Giấy tờ khớp", "Documents consistent"),
                      "review": tr("Giấy tờ cần xem lại", "Documents need review"),
                      "red_flag": tr("Cờ đỏ pháp lý", "Legal red flag")}[verdict]}
