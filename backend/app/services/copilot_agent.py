"""TRỢ LÝ TỰ GỌI CÔNG CỤ (nâng cấp 25/11/2026) — cho LLM tự tra thêm số đo khi dữ kiện theo từ khoá chưa đủ.

Trước đây: bộ định tuyến từ khoá chọn 1–4 mô-đun → gom dữ kiện → gọi LLM MỘT lần. Câu hỏi nằm ngoài từ khoá ("đến
2050 nóng hơn bao nhiêu?", "năm 2020 và 2024 có ngập không?", "sạt lở thì sao?" khi chỉ hỏi về lũ) thì LLM chỉ có dữ
kiện mặc định và trả "chưa đủ thông tin".

Nay: vẫn đưa dữ kiện theo từ khoá vào lời nhắc (đa số câu trả lời được ngay, MỘT lượt gọi — gói miễn phí bị giới hạn
theo phút), kèm 5 CÔNG CỤ CHỈ ĐỌC cho đúng thửa đang hỏi; LLM cần gì thì tự gọi, tối đa 2 vòng, nhiều công cụ một lúc.
Mọi con số trong câu trả lời vẫn qua guard.guard_llm, đối chiếu với dữ kiện + KẾT QUẢ CÔNG CỤ — công cụ không mở đường
cho số bịa. Công cụ không ghi gì, không gọi ra ngoài ngoài các nguồn mô-đun vốn dùng, và chỉ chạy cho toạ độ của thửa.

Không có nhà cung cấp kiểu OpenAI, hoặc lượt gọi có công cụ hỏng → trả None, copilot.answer quay về cách cũ.
"""
from __future__ import annotations

import json
import logging
import os
import time

from app.schemas import Location
from app.services import llm
from app.services.reqlang import tr

log = logging.getLogger("terratwin.copilot_agent")

MAX_ROUNDS = 2                    # số vòng gọi công cụ trước lượt viết câu trả lời
MAX_TOOL_CHARS = 2_400            # mỗi kết quả công cụ — giữ lời nhắc trong hạn mức token/phút của gói miễn phí
HAZARDS = ("flood", "upstream_flood", "landslide", "drought", "salinity", "wildfire", "urban", "land_risk", "pest",
           "yield", "solar", "aquaculture")


def enabled() -> bool:
    return os.environ.get("TERRATWIN_COPILOT_TOOLS", "1") != "0" and llm.tools_available()


def tool_specs() -> list[dict]:
    def fn(name: str, desc: str, props: dict | None = None, required: list[str] | None = None) -> dict:
        return {"type": "function", "function": {
            "name": name, "description": desc,
            "parameters": {"type": "object", "properties": props or {}, "required": required or []}}}
    return [
        fn("danh_gia_hiem_hoa", tr(
            "Đánh giá MỘT hiểm hoạ/chủ đề cho thửa đang hỏi trong 7 ngày tới (dữ liệu thật hoặc ước lượng, có ghi rõ). "
            "Dùng khi câu hỏi nói tới hiểm hoạ chưa có trong dữ kiện.",
            "Assess ONE hazard/topic for the plot for the next 7 days (real data or labelled estimate). Use when the "
            "question is about a hazard not already in the facts."),
           {"hazard": {"type": "string", "enum": list(HAZARDS)}}, ["hazard"]),
        fn("lich_su_ngap_radar", tr(
            "Các đợt NƯỚC QUAN SÁT ĐƯỢC tại thửa trong 10 năm qua từ radar Sentinel-1 (ngày, độ phủ). Dùng cho câu hỏi "
            "về một hay nhiều năm cụ thể, hoặc 'đã từng ngập chưa'.",
            "Water episodes OBSERVED at the plot over the last 10 years by Sentinel-1 radar (dates, coverage). Use for "
            "questions about specific years or 'has it ever flooded'.")),
        fn("mua_7_ngay", tr("Mưa dự báo TỪNG NGÀY trong 7 ngày tới tại thửa (mm/ngày).",
                            "DAILY forecast rain for the next 7 days at the plot (mm/day).")),
        fn("khi_hau_2050", tr(
            "Khí hậu 2041–2050 so với 1995–2014 của vùng quanh thửa (3 mô hình CMIP6, phát thải cao): ngày nắng nóng ≥35°C, "
            "ngày mưa ≥50 mm, mưa ngày lớn nhất, chuỗi ngày khô, tổng mưa năm; nước biển dâng nếu ven biển thấp. Dùng cho "
            "câu hỏi về tương lai xa, biến đổi khí hậu, 2030–2050.",
            "2041–2050 vs 1995–2014 climate of the area (3 CMIP6 models, high emissions): hot days ≥35°C, ≥50 mm rain "
            "days, wettest day, dry spell, annual rain; sea-level rise if coastal and low. Use for long-term / climate "
            "change / 2030–2050 questions.")),
        fn("tra_kien_thuc", tr(
            "Tra sổ tay kiến thức nông nghiệp – thuỷ lợi của TerraTwin (hướng dẫn phòng chống, canh tác). Trả đoạn trích "
            "có nguồn.",
            "Search TerraTwin's farming/water handbook (prevention, cultivation guidance). Returns cited excerpts."),
           {"cau_hoi": {"type": "string"}}, ["cau_hoi"]),
    ]


TOOL_LABEL = {"danh_gia_hiem_hoa": ("đánh giá hiểm hoạ", "hazard assessment"),
              "lich_su_ngap_radar": ("lịch sử radar 10 năm", "10-year radar history"),
              "mua_7_ngay": ("mưa từng ngày 7 ngày tới", "daily rain, next 7 days"),
              "khi_hau_2050": ("khí hậu 2050", "2050 climate"),
              "tra_kien_thuc": ("sổ tay kiến thức", "knowledge handbook")}


def _run_tool(name: str, args: dict, loc: Location) -> tuple[str, list[str], list]:
    """→ (văn bản kết quả, mô-đun đã dùng, trích dẫn kiến thức). Lỗi → câu báo lỗi (LLM phải nói là chưa tra được)."""
    from app.services import copilot
    if name == "danh_gia_hiem_hoa":
        from app.modules.registry import get_module
        hz = str(args.get("hazard") or "")
        m = get_module(hz) if hz in HAZARDS else None
        if m is None:
            return tr(f"Không có hiểm hoạ '{hz}'.", f"No hazard '{hz}'."), [], []
        a = m.assess(loc)
        tag = (tr("dữ liệu thật, 7 ngày", "real data, 7 days") if a.is_real
               else tr("ƯỚC LƯỢNG chưa hiệu chỉnh", "uncalibrated ESTIMATE"))
        return (tr(f"{a.module_name} ({tag}) — mức {a.risk_level}: {a.headline}. {a.detail} Khuyến nghị: {a.recommendation}",
                   f"{a.module_name} ({tag}) — level {a.risk_level}: {a.headline}. {a.detail} Recommendation: "
                   f"{a.recommendation}"), [hz], [])
    if name == "lich_su_ngap_radar":
        from app.services import water_history
        radar = water_history.summary(loc.lat, loc.lon)
        if not (radar or {}).get("available"):
            return tr("Chưa có lịch sử radar cho thửa này (chưa quét xong).", "No radar history for this plot yet."), [], []
        un = None
        if not radar.get("events"):
            u = water_history.urban(loc.lat, loc.lon)
            un = u.get("note") if u else None
        evs = radar.get("events") or []
        rows = "; ".join(f"{e.get('start')}→{e.get('end') or e.get('start')}" + (f" ({e['cover']})" if e.get("cover") else "")
                         for e in evs[-40:])
        extra = (NL + tr("Danh sách đợt: ", "Episodes: ") + rows) if rows else ""
        return copilot._history_answer(radar, un) + extra, ["water_history"], []
    if name == "mua_7_ngay":
        from app.services import realdata
        w7 = realdata.weather_7d(loc.lat, loc.lon)
        if not w7:
            return tr("Không lấy được dự báo mưa lúc này.", "Rain forecast unavailable right now."), [], []
        days = "; ".join(f"{int(d['date'][8:10])}/{int(d['date'][5:7])}: {d['precip']:.0f} mm" for d in w7)
        return copilot._rain_answer(w7) + NL + tr("Từng ngày: ", "Daily: ") + days, ["weather_7d"], []
    if name == "khi_hau_2050":
        from app.services import climate_2050
        r = climate_2050.assess(loc.lat, loc.lon)
        if not r.get("available"):
            return r.get("message") or tr("Chưa tính được khí hậu 2050.", "2050 climate unavailable."), [], []
        lines = [f"- {i['name']}: 1995–2014 {i['base_txt']} → 2041–2050 {i['future_txt']}; {i['change']}; {i['trend']}"
                 for i in r["indicators"]]
        if r.get("sea_level"):
            lines.append("- " + r["sea_level"]["text"])
        return (tr("Kịch bản: ", "Scenario: ") + r["scenario"] + NL + NL.join(lines) + NL + r["caveats"][0],
                ["climate_2050"], [])
    if name == "tra_kien_thuc":
        cites, txt = copilot._knowledge(str(args.get("cau_hoi") or ""), loc)
        return (txt or tr("Sổ tay không có đoạn nào khớp.", "No matching handbook passage.")), [], cites
    return tr(f"Không có công cụ '{name}'.", f"No tool '{name}'."), [], []


NL = "\n"


def run(system: str, prompt: str, loc: Location) -> dict | None:
    """Vòng gọi công cụ. → {text, trace, context (văn bản mọi kết quả công cụ, cho guard), modules, cites} hoặc None."""
    from app.services import jobs

    rules = tr(
        " Bạn có CÔNG CỤ để tra thêm số đo của ĐÚNG thửa này. Dữ kiện đã đủ thì trả lời luôn, KHÔNG gọi công cụ. Thiếu "
        "(năm cụ thể, khí hậu tương lai, hiểm hoạ khác, mưa từng ngày, cách phòng chống) thì gọi đúng công cụ — có thể "
        "gọi nhiều công cụ cùng lúc. Chỉ dùng con số có trong dữ kiện hoặc kết quả công cụ; công cụ báo không có thì "
        "nói là chưa có.",
        " You have TOOLS to look up more measurements for THIS plot. If the facts suffice, answer directly WITHOUT "
        "tools. If something is missing (specific years, future climate, another hazard, daily rain, prevention "
        "advice), call the right tool — several at once is fine. Use only numbers from the facts or tool results; if a "
        "tool has nothing, say so.")
    msgs: list[dict] = [{"role": "system", "content": system + rules}, {"role": "user", "content": prompt}]
    specs = tool_specs()
    trace: list[dict] = []
    ctx: list[str] = []
    modules: list[str] = []
    cites: list = []
    for rnd in range(MAX_ROUNDS + 1):
        last = rnd == MAX_ROUNDS
        msg = llm.chat(msgs, tools=specs, tool_choice="none" if last else "auto")
        if msg is None:
            return None
        calls = [] if last else (msg.get("tool_calls") or [])
        if not calls:
            text = (msg.get("content") or "").strip()
            return {"text": text, "trace": trace, "context": NL.join(ctx), "modules": modules, "cites": cites} if text \
                else None
        msgs.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})

        def call(c: dict):
            fn = c.get("function") or {}
            name = fn.get("name") or ""
            try:
                args = json.loads(fn.get("arguments") or "{}")
                if not isinstance(args, dict):
                    args = {}
            except ValueError:
                args = {}
            t0 = time.perf_counter()
            try:
                out = _run_tool(name, args, loc)
                ok = True
            except Exception as e:  # noqa: BLE001 — công cụ hỏng: báo cho LLM, không làm sập câu trả lời
                log.warning("công cụ %s lỗi: %s", name, e)
                out, ok = (tr("Công cụ lỗi — chưa tra được.", "Tool failed — not available."), [], []), False
            return name, args, out, ok, round((time.perf_counter() - t0) * 1000)

        got = jobs.gather([lambda c=c: call(c) for c in calls[:6]], timeout=120.0)
        for c, g in zip(calls[:6], got):
            if g is None:
                name, args, out, ok, ms = ((c.get("function") or {}).get("name") or "", {},
                                           (tr("Công cụ quá giờ.", "Tool timed out."), [], []), False, None)
            else:
                name, args, out, ok, ms = g
            text, mods, cs = out
            text = text[:MAX_TOOL_CHARS]
            msgs.append({"role": "tool", "tool_call_id": c.get("id") or name, "content": text})
            ctx.append(text)
            modules += [m for m in mods if m not in modules]
            cites += cs
            vi, en = TOOL_LABEL.get(name, (name, name))
            trace.append({"tool": name, "label": tr(vi, en), "args": args, "ok": ok, "ms": ms})
    return None
