"""C03 — What-If bằng NGÔN NGỮ TỰ NHIÊN.

"Nếu mưa gấp đôi trong tuần tới thì ruộng tôi có ngập không?"
  → {module: flood, rain_mult: 2.0, temp_delta: 0}
  → chạy ĐÚNG mô hình cảnh báo trên nền thời tiết thật
  → trả lời kèm con số kiểm chứng được.

Hai tầng, và tầng nào cũng chạy được:
  1. Bộ luật tiếng Việt (không cần key) — bắt các mẫu hỏi thông dụng.
  2. LLM (nếu đã cấu hình) — hiểu câu hỏi tự do hơn.

LLM chỉ được phép DỊCH câu hỏi thành tham số. Con số luôn do mô hình vật lý
tính, không bao giờ do LLM bịa — đây là ranh giới quan trọng nhất của tính năng.
"""
from __future__ import annotations

import json
import re
import unicodedata

from app.modules.util import risk_of
from app.services import hazard, llm
from app.services import realdata

_MODULE_WORDS = {
    "flood": ["lũ", "lụt", "ngập", "úng", "nước dâng", "flood"],
    "drought": ["hạn", "khô", "thiếu nước", "tưới", "drought"],
    "wildfire": ["cháy", "lửa", "hỏa hoạn", "fire"],
    "landslide": ["sạt", "lở", "trượt đất", "landslide"],
}

_MAX_MULT = 10.0
_MAX_TEMP = 15.0


def _norm(s: str) -> str:
    """Bỏ dấu + hạ chữ thường, để bắt được cả khi người dùng gõ không dấu.

    Phải thay đ→d THỦ CÔNG: U+0111 (đ) không có phân rã chuẩn nên NFD giữ
    nguyên nó, khiến "gấp đôi" chuẩn hóa thành "gap đoi" chứ không phải "gap doi".
    """
    s = s.lower().replace("đ", "d").replace("Đ", "d")
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


# Từ khóa đã chuẩn hóa, khớp theo ranh giới từ (xem _detect_module).
_MODULE_PATTERNS = {
    mid: re.compile(r"\b(?:" + "|".join(re.escape(_norm(w)) for w in words) + r")\b")
    for mid, words in _MODULE_WORDS.items()
}


def _detect_module(q: str, fallback: str) -> str:
    """Chọn module theo từ khóa, khớp theo RANH GIỚI TỪ.

    Khớp chuỗi con là sai: "ung" nằm trong "rừng" (→ ngỡ là lũ khi hỏi cháy
    rừng), "kho" nằm trong "không" (→ ngỡ là hạn ở mọi câu hỏi phủ định).
    Module nào có nhiều từ khóa khớp nhất thì thắng.
    """
    plain = _norm(q)
    best, best_hits = fallback, 0
    for mid, pattern in _MODULE_PATTERNS.items():
        hits = len(pattern.findall(plain))
        if hits > best_hits:
            best, best_hits = mid, hits
    return best


def parse_rules(question: str) -> dict | None:
    """Bộ luật tiếng Việt — không cần key. None nếu không bắt được mẫu nào."""
    plain = _norm(question)
    rain: float | None = None
    temp = 0.0

    if re.search(r"gap\s*(doi|2)|x\s*2\b", plain):
        rain = 2.0
    elif re.search(r"gap\s*(ba|3)|x\s*3\b", plain):
        rain = 3.0
    elif re.search(r"gap\s*(ruoi|1[.,]5)", plain):
        rain = 1.5
    elif (m := re.search(r"(tang|them)\s*(\d{1,3})\s*%", plain)):
        rain = 1.0 + int(m.group(2)) / 100.0
    elif (m := re.search(r"(giam|bot)\s*(\d{1,3})\s*%", plain)):
        rain = max(0.0, 1.0 - int(m.group(2)) / 100.0)
    elif re.search(r"khong\s*mua|het\s*mua|ngung\s*mua|kho\s*han\s*keo\s*dai", plain):
        rain = 0.0
    elif re.search(r"mua\s*(to|lon|nhieu|rat to)", plain):
        rain = 2.0
    elif re.search(r"mua\s*(nho|it)", plain):
        rain = 0.5

    if (m := re.search(r"(nong|tang nhiet)\s*(them\s*)?(\d{1,2})\s*do", plain)):
        temp = float(m.group(3))
    elif (m := re.search(r"(lanh|giam nhiet)\s*(di\s*)?(\d{1,2})\s*do", plain)):
        temp = -float(m.group(3))
    elif re.search(r"nong\s*hon|nang\s*nong", plain):
        temp = 2.0

    if rain is None and temp == 0.0:
        return None
    return {"rain_mult": 1.0 if rain is None else rain, "temp_delta": temp,
            "source": "rule"}


_LLM_SYSTEM = (
    "Bạn dịch câu hỏi tiếng Việt về thời tiết thành THAM SỐ MÔ PHỎNG. "
    "Chỉ trả về JSON, không giải thích, không markdown. Khóa: "
    '{"module": "flood|drought|wildfire|landslide", '
    '"rain_mult": số (1.0 = như dự báo, 2.0 = gấp đôi, 0.0 = không mưa), '
    '"temp_delta": số (độ C cộng thêm, âm là lạnh đi)}. '
    "TUYỆT ĐỐI không tự đoán kết quả — bạn chỉ dịch câu hỏi thành tham số."
)


def parse_llm(question: str, fallback_module: str) -> dict | None:
    raw = llm.complete(
        f"Câu hỏi: {question}\nModule đang xem: {fallback_module}\nJSON:",
        system=_LLM_SYSTEM, max_tokens=150)
    if not raw:
        return None
    m = re.search(r"\{.*\}", raw, re.S)      # gỡ ```json ... ``` nếu có
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    try:
        return {
            "module": str(d.get("module") or fallback_module),
            "rain_mult": float(d.get("rain_mult", 1.0)),
            "temp_delta": float(d.get("temp_delta", 0.0)),
            "source": "llm",
        }
    except (TypeError, ValueError):
        return None


def ask(question: str, lat: float, lon: float,
        default_module: str = "flood") -> dict:
    """Hiểu câu hỏi → chạy mô hình thật → trả lời kèm số kiểm chứng được."""
    if not hazard.supports(default_module):
        default_module = "flood"

    parsed = parse_rules(question)
    if parsed is not None:
        parsed["module"] = _detect_module(question, default_module)
    else:
        parsed = parse_llm(question, _detect_module(question, default_module))

    if parsed is None:
        return {
            "understood": False,
            "question": question,
            "message": ("Chưa hiểu câu hỏi. Thử diễn đạt kiểu: “nếu mưa gấp đôi "
                        "thì có ngập không?”, “mưa giảm 60% thì hạn thế nào?”, "
                        "“nóng thêm 3 độ thì nguy cơ cháy ra sao?”."),
            "llm_available": llm.available(),
        }

    module_id = parsed["module"] if hazard.supports(parsed["module"]) else default_module
    rain = max(0.0, min(float(parsed["rain_mult"]), _MAX_MULT))
    temp = max(-_MAX_TEMP, min(float(parsed["temp_delta"]), _MAX_TEMP))
    name, unit = hazard.name_unit(module_id)

    rows = realdata.weather_7d(lat, lon)
    if not rows:
        return {"understood": True, "available": False, "question": question,
                "module_id": module_id, "module_name": name,
                "message": "Chưa lấy được thời tiết thật — không mô phỏng trên số liệu mẫu."}

    base = hazard.peak_of(hazard.index_series(module_id, lat, lon, rows))
    scen = hazard.peak_of(hazard.index_series(
        module_id, lat, lon, hazard.transform(rows, rain, temp)))
    risk = risk_of(scen, hazard.SAFE, hazard.WARNING)

    changes = []
    if abs(rain - 1.0) > 0.01:
        changes.append(f"mưa {'gấp ' + format(rain, '.2g') + '×' if rain > 1 else f'giảm còn {rain:.0%}'}")
    if abs(temp) > 0.01:
        changes.append(f"nhiệt {'+' if temp > 0 else ''}{temp:g}°C")
    change_txt = " và ".join(changes) if changes else "giữ nguyên dự báo"

    verdict = {"danger": "NGUY HIỂM", "warning": "CẢNH BÁO", "safe": "an toàn"}[risk]
    delta = scen - base
    direction = ("tăng" if delta > 0.05 else "giảm" if delta < -0.05 else "gần như không đổi")
    # Bỏ tiền tố "Cảnh báo " khỏi tên module, nếu không câu thành
    # "cảnh báo lũ/ngập sớm ở mức an toàn" — đọc rất lấn cấn.
    subject = name[len("Cảnh báo "):] if name.startswith("Cảnh báo ") else name
    headline = (f"Nếu {change_txt}: {subject.lower()} ở mức {verdict} "
                f"({scen:.1f} {unit}, {direction} so với {base:.1f} hiện tại).")

    return {
        "understood": True, "available": True, "question": question,
        "module_id": module_id, "module_name": name, "unit": unit,
        "rain_mult": round(rain, 3), "temp_delta": temp,
        "parsed_by": parsed["source"],
        "baseline_peak": round(base, 1), "scenario_peak": round(scen, 1),
        "delta": round(delta, 1), "risk_level": risk,
        "safe": hazard.SAFE, "warning": hazard.WARNING,
        "headline": headline,
        "method": ("Câu hỏi chỉ được dùng để CHỌN THAM SỐ; con số do chính mô hình "
                   "cảnh báo tính trên nền thời tiết thật, không phải LLM đoán."),
        "llm_available": llm.available(),
    }
