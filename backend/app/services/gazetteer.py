"""TỪ ĐIỂN ĐỊA DANH NỘI BỘ — tìm huyện/tỉnh khi gõ KHÔNG DẤU, SAI CHÍNH TẢ, hoặc khi cả ba dịch vụ tra địa danh ngoài
(Open-Meteo, Photon, Nominatim) không phản hồi (nâng cấp 25/11/2026).

Dữ liệu: 708 huyện + 63 tỉnh của ranh 2020 (data/admin/vnm_adm2_2020.json, geoBoundaries/HDX, CC BY 3.0 IGO) — đã có
trong kho, không gọi mạng. Mỗi mục lấy điểm đại diện NẰM TRONG đa giác (shapely representative_point), không phải tâm
khung (tâm khung của huyện hình lưỡi liềm có thể rơi ra ngoài).

Thuật toán:
  · Trie trên tên đã bỏ dấu → gợi ý theo TIỀN TỐ ("quang d" → Quảng Điền, Quảng Đông…), O(độ dài chuỗi).
  · Jaro-Winkler (ưu tiên khớp đầu chuỗi — hợp tên riêng) + khoảng cách Levenshtein có trần → bắt lỗi gõ ("quang dienn",
    "hai phongg", "tue tinh" thiếu dấu).
Điểm: khớp đúng 1,0 > tiền tố 0,95 > Jaro-Winkler; chỉ nhận ≥ 0,88 (hoặc Levenshtein ≤ 1 với tên ≥ 5 ký tự).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data" / "admin" / "vnm_adm2_2020.json"
MIN_SCORE = 0.88


def fold(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFD", (s or "").replace("đ", "d").replace("Đ", "D"))
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn").lower()
    for pre in ("tinh ", "thanh pho ", "tp. ", "tp ", "huyen ", "quan ", "thi xa ", "tx "):
        if s.startswith(pre):
            s = s[len(pre):]
    return " ".join(s.replace("-", " ").replace(",", " ").split())


def jaro_winkler(a: str, b: str, p: float = 0.1) -> float:
    if a == b:
        return 1.0
    la, lb = len(a), len(b)
    if not la or not lb:
        return 0.0
    win = max(0, max(la, lb) // 2 - 1)
    ma, mb = [False] * la, [False] * lb
    m = 0
    for i, ch in enumerate(a):
        for j in range(max(0, i - win), min(lb, i + win + 1)):
            if not mb[j] and b[j] == ch:
                ma[i] = mb[j] = True
                m += 1
                break
    if not m:
        return 0.0
    k = t = 0
    for i in range(la):
        if ma[i]:
            while not mb[k]:
                k += 1
            if a[i] != b[k]:
                t += 1
            k += 1
    jaro = (m / la + m / lb + (m - t / 2) / m) / 3
    pre = 0
    for x, y in zip(a[:4], b[:4]):
        if x != y:
            break
        pre += 1
    return jaro + pre * p * (1 - jaro)


def levenshtein(a: str, b: str, cap: int = 3) -> int:
    """Khoảng cách chỉnh sửa, dừng sớm khi vượt `cap` (trả cap + 1)."""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
        if min(cur) > cap:
            return cap + 1
        prev = cur
    return prev[-1]


class Trie:
    """Cây tiền tố: mỗi nút giữ chỉ số các mục có tên đi qua nút đó (giới hạn để gợi ý nhanh)."""

    def __init__(self, keep: int = 40):
        self.root: dict = {}
        self.keep = keep

    def add(self, word: str, idx: int) -> None:
        node = self.root
        for ch in word:
            node = node.setdefault(ch, {})
            ids = node.setdefault("$ids", [])
            if len(ids) < self.keep:
                ids.append(idx)

    def prefix(self, word: str) -> list[int]:
        node = self.root
        for ch in word:
            node = node.get(ch)
            if node is None:
                return []
        return list(node.get("$ids", []))


@lru_cache(maxsize=1)
def _index() -> tuple[list[dict], Trie]:
    from shapely.geometry import shape
    from shapely.ops import unary_union
    from shapely.validation import make_valid

    units = json.loads(DATA.read_text(encoding="utf-8"))["units"]
    entries: list[dict] = []
    by_prov: dict[str, list] = {}
    for u in units:
        coords = json.loads(u["coordinates"]) if isinstance(u["coordinates"], str) else u["coordinates"]
        g = make_valid(shape({"type": u["type"], "coordinates": coords}))   # ranh đã đơn giản hoá ~100 m có thể tự cắt
        pt = g.representative_point()
        entries.append({"name": u["name"], "province": u["province"], "kind": "district",
                        "lat": round(pt.y, 5), "lon": round(pt.x, 5), "key": fold(u["name"])})
        by_prov.setdefault(u["province"], []).append(g)
    for prov, gs in by_prov.items():
        pt = unary_union(gs).representative_point()
        entries.append({"name": prov, "province": prov, "kind": "province", "lat": round(pt.y, 5), "lon": round(pt.x, 5),
                        "key": fold(prov)})
    trie = Trie()
    for i, e in enumerate(entries):
        trie.add(e["key"], i)
    return entries, trie


def suggest(q: str, k: int = 8) -> list[dict]:
    """Gợi ý huyện/tỉnh cho chuỗi gõ (không dấu, sai chính tả đều được). → [{label, lat, lon, kind, source, score}]."""
    fq = fold(q.split(",")[0])
    if len(fq) < 2:
        return []
    entries, trie = _index()
    scored: dict[int, float] = {}
    for i in trie.prefix(fq):
        scored[i] = 1.0 if entries[i]["key"] == fq else 0.95
    for i, e in enumerate(entries):
        if i in scored:
            continue
        s = jaro_winkler(fq, e["key"])
        if s >= MIN_SCORE or (len(e["key"]) >= 5 and levenshtein(fq, e["key"], 1) <= 1):
            scored[i] = max(s, 0.89)
    ctx = fold(q.split(",", 1)[1]) if "," in q else ""
    out = []
    for i, s in sorted(scored.items(), key=lambda x: (-x[1], entries[x[0]]["kind"] != "province", entries[x[0]]["name"])):
        e = entries[i]
        if ctx and ctx not in fold(e["province"]):
            continue
        label = e["province"] if e["kind"] == "province" else f"{e['name']} · {e['province']}"
        out.append({"label": label, "lat": e["lat"], "lon": e["lon"], "kind": e["kind"], "source": "local-gazetteer",
                    "score": round(s, 3)})
        if len(out) >= k:
            break
    return out
