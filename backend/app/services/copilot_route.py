"""Chọn mô-đun dữ liệu cho câu hỏi trợ lý — so THEO TỪ sau khi bỏ dấu, xét MỌI hiểm hoạ (kiểm 21/11/2026).

Bản cũ (copilot._route) so CHUỖI CON và dừng ở luật khớp đầu tiên:
  · "manh dat nay co bi ngap khong" → "man" nằm trong "manh" → chỉ nạp MẶN → trợ lý nói "chưa đủ để xác định có bị
    ngập" dù radar thấy nước phủ thửa 5 đợt;
  · "han" khớp "thanh"/"khan", "man" khớp "many";
  · "Tóm tắt các rủi ro chính…" → chỉ land_risk → trợ lý nói radar và ERA5 "hiện chưa có".
"""
from __future__ import annotations

import re
import unicodedata

# Mỗi mục: mô-đun → các cụm TỪ đã bỏ dấu (một hoặc nhiều từ liền nhau).
_KEYS: dict[str, tuple[str, ...]] = {
    "flood": ("ngap", "lu", "lut", "lu lut", "nuoc len", "nuoc phu", "flood", "floods", "flooded", "flooding",
              "inundation", "inundated"),
    "salinity": ("man", "nhiem man", "xam nhap man", "salt", "salty", "saline", "salinity"),
    "drought": ("han", "kho han", "han han", "thieu nuoc", "tuoi", "drought", "dry", "dryness", "irrigation"),
    # 21/11/2026: KHÔNG để "lua" đứng riêng — "lúa" và "lửa" bỏ dấu đều là "lua" ("Đất này trồng lúa được không?" → cháy).
    "wildfire": ("chay rung", "lua rung", "dam chay", "nguy co chay", "fire", "wildfire", "wildfires"),
    "landslide": ("sat lo", "lo dat", "landslide", "landslides"),
    "solar": ("dien mat troi", "mat troi", "solar"),
}
# Câu hỏi tổng quát ("rủi ro", "tóm tắt", "nên làm gì", "mua đất") → nạp đánh giá nền đất + các hiểm hoạ chính.
_TONG_QUAT = ("rui ro", "tom tat", "tong quan", "tong hop", "nen lam gi", "mua dat", "dau tu", "risk", "risks",
              "summary", "summarize", "summarise", "overview", "invest", "investment", "buy", "buying")
_THU_TU = ("flood", "salinity", "drought", "landslide", "wildfire", "solar")
_MAC_DINH = ["salinity", "drought", "flood"]


def fold(s: str) -> str:
    """Thường hoá + bỏ dấu tiếng Việt (đ → d)."""
    s = unicodedata.normalize("NFD", (s or "").lower().replace("đ", "d"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _words(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", fold(s))


def _has(words: list[str], phrase: str) -> bool:
    p = phrase.split()
    n = len(p)
    return any(words[i:i + n] == p for i in range(len(words) - n + 1))


def route(question: str) -> list[str]:
    w = _words(question)
    hit = [m for m in _THU_TU if any(_has(w, k) for k in _KEYS[m])]
    if any(_has(w, k) for k in _TONG_QUAT):
        return ["land_risk"] + [m for m in ("flood", "drought", "salinity") if m not in hit] + hit
    return hit or list(_MAC_DINH)


_MUA = ("mua kho", "mua mua", "mua toi", "thang toi", "thang sau", "nam toi", "nam sau", "ca mua", "lau dai",
        "season", "seasons", "seasonal", "next month", "next year", "long term", "long-term")


_HIEN_TRANG = ("khong co dau hieu ngap", "chua co dau hieu ngap", "khong bi ngap", "chua bi ngap", "khong ngap",
               "no sign of flooding", "no signs of flooding", "not flooded", "not currently flooded", "isn t flooded",
               "no flooding")
_LUC_NAY = ("hien tai", "hien nay", "currently", "right now", "at present")
# Vế chỉ có "hiện tại" mà không mang ý cảnh báo/số nào ("trong thời gian hiện tại và dự báo ngắn hạn") là phần đi kèm
# của câu khẳng định hiện trạng — bỏ cùng. Vế có ý cảnh báo thì GIỮ.
_CANH = ("nguy co", "canh bao", "nguy hiem", "cao", "risk", "warning", "danger", "high")
_NOI = {"vi vay", "do do", "vi the", "nhu vay", "tuy nhien", "nhung", "va", "nen", "so", "therefore", "thus", "hence",
        "however", "but", "and"}
_CAU = re.compile(r"[.!?]+(?=\s|$)|\n+")
_VE = re.compile(r"\s*[,;]\s*|\s+(?=(?:nhưng|tuy nhiên|but|however)\s)", re.I)
_DAU_NOI = re.compile(r"^(?:nhưng|tuy nhiên|và|but|however|and)\s+", re.I)
_DAU_DONG = re.compile(r"^(\s*(?:[-•*+]\s+|\d+[.)]\s+)?)(.*?)([.!?…]*)(\s*)$", re.S)


def _co(words: list[str], keys) -> bool:
    return any(_has(words, k) for k in keys)


def claims_present_dry(answer: str) -> bool:
    """Câu trả lời khẳng định HIỆN TRẠNG không ngập (kiểm 21/11/2026: "Vì vậy hiện tại đất này không có dấu hiệu ngập" đặt
    ngay sau câu radar 5 đợt) — trong khi chỉ số chỉ là dự báo 7 ngày. Xét từng câu: có "hiện tại"/"currently"/"now" và
    một cụm phủ định ngập trong CÙNG câu (so theo TỪ — "thiên tai" không phải "hiện tại")."""
    for cau in _CAU.split(answer):
        w = _words(cau)
        if _co(w, _LUC_NAY) and _co(w, _HIEN_TRANG):
            return True
    return False


def strip_present_dry(sentence: str, fallback: str = "") -> str:
    """Bỏ ĐÚNG vế "hiện tại không ngập" trong một câu, giữ các vế còn lại — nhất là vế cảnh báo ("…, nhưng 7 ngày tới nguy
    cơ ngập cao") — kèm dấu gạch đầu dòng và dấu câu cuối. Không còn gì đáng giữ (chỉ còn từ nối) → `fallback`, vẫn giữ
    dấu gạch đầu dòng."""
    m = _DAU_DONG.match(sentence)
    dau, than, cuoi, trang = m.groups()

    def bo(v: str) -> bool:
        w = _words(v)
        if not w or " ".join(w) in _NOI or _co(w, _HIEN_TRANG):
            return True
        return _co(w, _LUC_NAY) and not _co(w, _CANH) and not re.search(r"\d", v)

    giu = [v.strip() for v in _VE.split(than) if not bo(v)]
    if not giu:
        return f"{dau}{fallback}{trang}" if fallback else ""
    giu[0] = _DAU_NOI.sub("", giu[0])
    giu[0] = giu[0][:1].upper() + giu[0][1:]
    return f"{dau}{', '.join(giu)}{cuoi or ''}{trang}"


_THIEU = ("khong du de", "chua du de", "khong du du lieu", "chua du du lieu", "khong the ket luan", "chua the ket luan",
          "khong the khang dinh", "chua the khang dinh", "khong the xac dinh", "chua the xac dinh", "not enough to",
          "not enough data", "insufficient", "cannot confirm", "cannot conclude", "cannot determine", "can t confirm",
          "can t say", "unable to confirm", "unable to determine")
_DANG_NGAP = ("dang ngap", "dang bi ngap", "currently flooded", "flooded now", "flooded right now")


# Chỉ câu nói về QUÁ KHỨ mới mâu thuẫn với radar (kiểm PR #39: bản đầu bắt cả câu về 7 ngày tới, độ sâu, độ phù hợp cây).
_QUA_KHU = ("da ngap", "da bi ngap", "tung ngap", "tung bi ngap", "ngap hay chua", "ngap chua", "has flooded",
            "have flooded", "has been flooded", "ever flooded", "flooded before", "flooded in the past", "before")
_KHONG_PHAI_QUA_KHU = ("7 ngay toi", "sap toi", "mua toi", "tuan toi", "thang toi", "nam toi", "se", "will", "next",
                       "upcoming", "muc", "do sau", "sau bao nhieu", "phu hop", "thich hop", "trong lua", "trong cay",
                       "depth", "deep", "how deep", "suitable", "grow", "plant")


def doubts_past_water(sentence: str) -> bool:
    """Câu nói "không đủ để khẳng định ĐÃ ngập hay chưa" (kiểm 21/11/2026, 1/8 lần trên 9bba22d) — sai khi radar ĐÃ thấy
    nước phủ thửa. Chỉ bắt câu về QUÁ KHỨ; câu về hiện trạng ("đang ngập"), 7 ngày/mùa tới, độ sâu, độ phù hợp cây trồng
    là dè dặt ĐÚNG, không đụng."""
    w = _words(sentence)
    return (_co(w, _THIEU) and _co(w, _QUA_KHU) and not _co(w, _DANG_NGAP)
            and not _co(w, _KHONG_PHAI_QUA_KHU))


# Mỗi hiểm hoạ: cụm tiếng Việt / cụm tiếng Anh (sau "no … risk" hoặc "no risk of …").
_HIEM = {
    "flood": ("ngập", "flood(?:ing)?"),
    "salinity": ("xâm nhập mặn|nhiễm mặn|mặn", "salinity(?: intrusion)?|salt(?:water)?(?: intrusion)?"),
    "drought": ("khô hạn|hạn hán|thiếu nước|hạn", "drought"),
}
_TRU = r"(?!\s*(?:cao|lớn|nghiêm trọng|nặng|đáng|high|severe|major|significant|is\s+high))"


def soften_overclaim(text: str, hazards=("flood",)) -> str:
    """Dự báo "ít nguy cơ" mà câu trả lời nâng thành "không có nguy cơ …" (kiểm PR #39: "…ruộng lúa không có nguy cơ
    ngập", chỉ số 7.9; PR #40: "không có nguy cơ xâm nhập mặn" từ số mặn ước lượng) → đổi về đúng chữ của dự báo.
    "không có nguy cơ ngập CAO" là đúng, giữ nguyên. Chỉ áp cho các hiểm hoạ có mức "safe" truyền vào."""
    def hoa(goc, s):
        return s[:1].upper() + s[1:] if goc[:1].isupper() else s

    for h in hazards:
        vi_h, en_h = _HIEM[h]
        text = re.sub(rf"\b(không có|chẳng có) (nguy cơ|rủi ro) (bị )?({vi_h})\b{_TRU}",
                      lambda m: hoa(m.group(1), f"ít {m.group(2)} {m.group(3) or ''}{m.group(4)}"), text, flags=re.I)
        text = re.sub(rf"\bno (risk of )({en_h})\b{_TRU}",
                      lambda m: hoa(m.group(0), f"a low risk of {m.group(2)}"), text, flags=re.I)
        text = re.sub(rf"\bno ({en_h}) risk\b{_TRU}",
                      lambda m: hoa(m.group(0), f"low {m.group(1)} risk"), text, flags=re.I)
    return text


# "Vì vậy, hiện tại ít nguy cơ ngập" — mức nguy cơ là DỰ BÁO 7 ngày, không phải hiện trạng. Chỉ đổi "hiện tại" đứng ĐẦU
# vế (đầu câu, sau dấu phẩy, sau "vì vậy/do đó/nên") — "dữ liệu hiện tại" (= dữ liệu đang có) giữ nguyên.
_HIEM_VI = r"(?:bị\s+)?(?:ngập|lũ|xâm nhập mặn|nhiễm mặn|mặn|khô hạn|hạn|thiếu nước|sạt lở|cháy)"
_HIEN_TAI_DU_BAO = re.compile(
    r"(^|[,;:]\s*|\b(?:vì vậy|do đó|như vậy|vậy|nên)\s+)(hiện tại|hiện nay)(,?\s+)"
    rf"(?=[^.!?\n]{{0,40}}?(?:\b(?:ít|không có|chưa có)\s+(?:nguy cơ|rủi ro)\s+{_HIEM_VI}"
    rf"|\b(?:nguy cơ|rủi ro)\s+{_HIEM_VI}\s+(?:là\s+)?(?:thấp|ít)\b))", re.I)


def present_to_forecast(sentence: str) -> str:
    """Trong câu nói MỨC NGUY CƠ, đổi "hiện tại" đầu vế thành "trong 7 ngày tới" (câu đã có "7 ngày" thì bỏ hẳn chữ đó)."""
    co_7 = "7 ngày" in sentence or "7 ngay" in fold(sentence)

    def doi(m):
        if co_7:
            return m.group(1)
        moi = "trong 7 ngày tới"
        if m.group(2)[:1].isupper():
            moi = moi.capitalize()
        return m.group(1) + moi + m.group(3)
    out = _HIEN_TAI_DU_BAO.sub(doi, sentence)
    return out[:1].upper() + out[1:] if out != sentence and sentence[:1].isupper() else out


_CAY = ("trong lua", "trong cay", "trong rau", "trong ngo", "trong ca phe", "trong duoc", "cay trong", "nang suat",
        "thu hoach", "mua vu", "crop", "crops", "grow", "growing", "plant", "planting", "cultivate", "cultivation",
        "yield", "harvest")


def asks_crop(question: str) -> bool:
    """Câu hỏi về trồng cây / mùa vụ / năng suất (không tính "solar plant")."""
    w = _words(question)
    return _co(w, _CAY) and not _co(w, ("solar", "mat troi"))


def asks_long_range(question: str) -> bool:
    """Hỏi về mùa/tháng/năm tới — TerraTwin chỉ có dự báo 7 ngày."""
    w = _words(question)
    return any(_has(w, k.replace("-", " ")) for k in _MUA)
