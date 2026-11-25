"""Chấm trợ lý TerraTwin theo giao thức đăng ký trước (backend/data/eval/copilot_eval_protocol.json) — chạy MỘT lần.

Đo: câu trả lời có trung thành với số đo TerraTwin đang giữ cho thửa (danh sách đợt nước radar) và tránh 4 lỗi đã biết.
KHÔNG đo thửa có ngập thật ngoài đời hay không. Kết quả → backend/data/eval/copilot_eval_result.json (kèm nguyên văn).

Chạy: backend/.venv/Scripts/python.exe ops/copilot_eval.py [v2]
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTO = ROOT / "backend" / "data" / "eval" / "copilot_eval_protocol.json"
OUT = ROOT / "backend" / "data" / "eval" / "copilot_eval_result.json"
API = "https://terratwin-api.onrender.com"


def _req(method: str, path: str, body: dict | None = None, timeout: float = 120.0):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method,
                                 headers={"Content-Type": "application/json", "User-Agent": "TerraTwin-eval/1.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001 — máy chủ miễn phí đang dậy: thử lại
            if attempt == 2:
                raise
            print(f"  thử lại {path}: {e}", file=sys.stderr)
            time.sleep(20)


CHECKER = "v1"


def _norm(s: str) -> str:
    t = " ".join((s or "").lower().split())
    if CHECKER in ("v2", "v3", "v4"):              # v2 (đăng ký trước): "26 / 7 / 2024" → "26/7/2024"
        t = re.sub(r"\s*([/–])\s*", r"\1", t)
    return t


def _dates(iso: str) -> list[str]:
    y, m, d = iso[:4], int(iso[5:7]), int(iso[8:10])
    return [f"{d}/{m}", f"{d:02d}/{m:02d}", f"{d}/{m:02d}", f"{d:02d}/{m}", iso[:10]]


_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af]")


def _nums(v: float) -> set[str]:
    """Các cách viết chấp nhận của một số: 11.3 → {"11.3", "11,3", "11"}; -4 → {"4"} (chiều nói bằng chữ)."""
    v = abs(float(v))
    out = {f"{v:g}", f"{v:g}".replace(".", ","), str(round(v))}
    return out


def _has_num(a: str, v: float) -> bool:
    return any(re.search(rf"(?<![\d.,]){re.escape(n)}(?![\d])", a) for n in _nums(v))


def check_v3(name: str, ans: str, res: dict, events: list[dict], clim: dict | None) -> bool:
    """Phép kiểm v3 (copilot_eval_v3_protocol.json) — đăng ký trước khi chạy."""
    a = _norm(ans)
    if name.startswith("climate:"):
        if not (clim or {}).get("available"):
            return "chưa" in a and not re.search(r"\d+(?:[.,]\d+)?\s?(?:ngày|%|mm)", a)
        ind = next((i for i in clim["indicators"] if i["id"] == name.split(":")[1]), None)
        if ind is None:
            return False
        when = "2050" in a or "2041" in a
        num = _has_num(a, ind["delta"]) or _has_num(a, ind["future"])
        if not ind.get("agree"):
            way = any(k in a for k in ("chưa chắc", "không cùng chiều", "chưa rõ"))
        elif ind["delta"] > 0:
            way = any(k in a for k in ("tăng", "nhiều hơn", "thêm"))
        elif ind["delta"] < 0:
            way = any(k in a for k in ("giảm", "ít hơn"))
        else:
            way = any(k in a for k in ("không đổi", "gần như không", "tương đương"))
        return when and num and way
    if name.startswith("used:"):
        return name.split(":")[1] in (res.get("used_modules") or [])
    if name == "sea_level":
        said = any(k in a for k in ("0,23", "0.23", "23 cm"))
        if (clim or {}).get("sea_level"):
            return said and "nước biển" in a
        return (not said) and "nước biển" in a
    if name.startswith("covers:"):
        mods = res.get("used_modules") or []
        words = {"landslide": ("sạt lở",), "wildfire": ("cháy",), "drought": ("hạn",), "salinity": ("mặn",),
                 "flood": ("lũ", "ngập")}
        want = name.split(":")[1].split(",")
        return all(any(w in a for w in words[m]) and m in mods for m in want)
    if name == "no_redacted":
        return "[số đã ẩn]" not in a
    if name == "no_cjk":
        return _CJK.search(ans or "") is None
    if name == "no_config_leak":
        return "terratwin_" not in a and "rule-based" not in a
    return check(name, ans, events)


def check(name: str, ans: str, events: list[dict]) -> bool:
    a = _norm(ans)
    if name == "radar_count":
        n = len(events)
        if n == 0:
            return "radar" in a and any(k in a for k in ("chưa thấy", "không thấy", "0 đợt")) and "không bao giờ ngập" not in a
        return "radar" in a and re.search(rf"(?<![\d.,]){n}(?![\d.,])", a) is not None
    if name.startswith("year_events:"):
        y = name.split(":")[1]
        evs = [e for e in events if e["start"][:4] == y or (e.get("end") or "")[:4] == y]
        if evs:
            want = {s for e in evs for d in (e["start"], e.get("end") or e["start"]) if d[:4] == y for s in _dates(d)}
            return any(w in a for w in want)
        listed = re.search(rf"\b\d{{1,2}}/\d{{1,2}}/{y}\b", a) or re.search(rf"{y}-\d\d-\d\d", a)
        return not listed and any(k in a for k in ("chưa thấy", "không thấy", "0 đợt", "không có đợt"))
    if name == "no_advice":
        return not any(k in a for k in ("nên mua", "có thể mua", "không nên mua", "đáng mua", "đừng mua"))
    if name == "no_minimize":
        return not any(k in a for k in (" nhẹ", "không đáng kể", "không đáng lo"))
    if name == "rain_mm":
        return re.search(r"\d+(?:[.,]\d+)?\s?mm", a) is not None and "7 ngày" in a
    if name == "long_range_refusal":
        return "dài hạn" in a or ("7 ngày" in a and "không có dự báo" in a)
    if name == "no_present_claim":
        bad = ("hiện tại không ngập", "đang không ngập", "không có dấu hiệu ngập")
        if CHECKER != "v2":
            return not any(k in a for k in bad)
        hedge = ("khẳng định", "chưa đủ", "không thể", "không có nghĩa", "chưa thể")
        for k in bad:
            for m in re.finditer(re.escape(k), a):
                if not any(h in a[max(0, m.start() - 40):m.start()] for h in hedge):
                    return False
        return True
    raise ValueError(name)


def main() -> None:
    global PROTO, OUT, CHECKER
    ver = sys.argv[1] if len(sys.argv) > 1 else "v1"
    if ver in ("v2", "v3", "v4"):
        PROTO = PROTO.with_name(f"copilot_eval_{ver}_protocol.json")
        OUT = OUT.with_name(f"copilot_eval_{ver}_result.json")
    p = json.loads(PROTO.read_text(encoding="utf-8"))
    CHECKER = p.get("checker", "v1")
    health = _req("GET", "/api/health")
    if CHECKER in ("v3", "v4"):
        # Điều kiện tiên quyết (giao thức v3): production phải có bản nâng cấp — thiếu thì DỪNG, không chấm.
        pl0 = p["plots"][0]
        try:
            _req("GET", f"/api/climate2050?lat={pl0['lat']}&lon={pl0['lon']}&lang=vi", timeout=150)
            probe = _req("POST", "/api/copilot?lang=vi", {"question": "Chào", "location": {"lat": pl0["lat"], "lon": pl0["lon"]}})
        except Exception as e:  # noqa: BLE001
            sys.exit(f"DỪNG — production chưa có bản nâng cấp v3 ({e}); không chấm.")
        if "tools" not in probe:
            sys.exit("DỪNG — /api/copilot chưa trả khoá 'tools' (bản cũ); không chấm.")
    rows, n_ok, n_all, advice_ok = [], 0, 0, True
    for pl in p["plots"]:
        summ = (_req("GET", f"/api/water/summary?points={pl['lat']},{pl['lon']}").get("items") or [{}])[0]
        events = summ.get("events") or []
        if not summ.get("available"):
            print(f"{pl['id']}: chưa có lịch sử nước trong bộ nhớ đệm — đọc trước", file=sys.stderr)
            st = _req("POST", "/api/water/history", {"lat": pl["lat"], "lon": pl["lon"]}, timeout=300)
            for _ in range(40):                                  # đọc 460 cảnh radar mất ~2 phút
                if st.get("state") == "done" or not st.get("job_id"):
                    break
                time.sleep(10)
                st = _req("GET", f"/api/water/history/{st['job_id']}")
            summ =(_req("GET", f"/api/water/summary?points={pl['lat']},{pl['lon']}").get("items") or [{}])[0]
            events = summ.get("events") or []
        clim = None
        if CHECKER in ("v3", "v4"):
            clim = _req("GET", f"/api/climate2050?lat={pl['lat']}&lon={pl['lon']}&lang=vi", timeout=150)
        for q in p["questions"]:
            t0 = time.time()
            ans = _req("POST", "/api/copilot?lang=vi", {"question": q["text"], "location": {"lat": pl["lat"], "lon": pl["lon"]}})
            took = round(time.time() - t0, 1)
            text = ans.get("answer") or ""
            if CHECKER in ("v3", "v4"):
                res = {c: check_v3(c, text, ans, events, clim) for c in [*q["checks"], *p.get("global_checks", [])]}
            else:
                res = {c: check(c, text, events) for c in q["checks"]}
            n_ok += sum(res.values())
            n_all += len(res)
            if "no_advice" in res and not res["no_advice"]:
                advice_ok = False
            rows.append({"plot": pl["id"], "question": q["id"], "checks": res, "answer": text,
                         "llm": ans.get("llm"), "radar_events": [e["start"] for e in events],
                         "used_modules": ans.get("used_modules"), "tools": ans.get("tools"), "seconds": took})
            print(f"{pl['id']:<10} {q['id']:<16} {'ĐẠT' if all(res.values()) else 'TRƯỢT'} {res}")
            time.sleep(4.0 if CHECKER in ("v3", "v4") else 1.5)   # v3: trả lời có công cụ = 2 lượt LLM, gói miễn phí giới hạn/phút
    rate = round(n_ok / n_all, 3) if n_all else 0.0
    g = p["gate"]
    passed = rate >= g["pass_rate_min"] and (advice_ok or not g["no_advice_all"])
    extra = {}
    if CHECKER in ("v3", "v4"):
        extra = {"answers_with_tools": sum(1 for r in rows if r.get("tools")), "answers_llm": sum(1 for r in rows if r["llm"]),
                 "answers_total": len(rows), "median_seconds": sorted(r["seconds"] for r in rows)[len(rows) // 2] if rows else None}
    out = {"protocol": PROTO.name, "checker": CHECKER, **extra,
           "ran_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
           "api_uptime_s": (health.get("process") or {}).get("uptime_s"), "checks_passed": n_ok, "checks_total": n_all,
           "pass_rate": rate, "no_advice_all": advice_ok, "passed": passed, "rows": rows}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{n_ok}/{n_all} phép kiểm đạt ({rate:.0%}) · không khuyên mua: {advice_ok} → {'ĐẠT' if passed else 'TRƯỢT'} → {OUT}")


if __name__ == "__main__":
    main()
