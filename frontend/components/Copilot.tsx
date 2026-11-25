"use client";

/**
 * TRỢ LÝ RAG CÓ DẪN NGUỒN.
 *
 * copilot.py đã grounded: câu trả lời chỉ dựa trên dữ liệu đo được của thửa +
 * kinh nghiệm thực địa từ vùng CÙNG BỘ GEN ĐẤT, và cấm bịa số. Ở đây phô cái
 * grounding đó ra: mỗi câu trả lời kèm NGUỒN — mũi nhọn đo được đã dùng, và các
 * mẩu kinh nghiệm được trích (kèm % tương đồng đất). Người dùng thấy được câu
 * trả lời tựa vào đâu, thay vì tin một hộp đen.
 */

import { useEffect, useRef, useState } from "react";
import { askCopilot, type CopilotAnswer } from "@/lib/api";
import { useLang } from "@/lib/i18n";
import { boldParts } from "@/lib/richtext";
import { getRecognition, transcriptOf, type SpeechRecognitionLike } from "@/lib/speech";

const MOD_NAME: Record<string, [string, string]> = {
  // Nguồn của câu trả lời thẳng từ số đo (nâng cấp 24/11/2026) — không phải mô-đun hiểm hoạ.
  water_history: ["Lịch sử nước radar Sentinel-1", "Sentinel-1 radar water history"],
  weather_7d: ["Mưa dự báo 7 ngày", "7-day rain forecast"],
  salinity: ["Xâm nhập mặn", "Salinity"],
  drought: ["Hạn & thiếu nước", "Drought"],
  flood: ["Lũ & ngập", "Flood"],
  wildfire: ["Cháy rừng", "Wildfire"],
  landslide: ["Sạt lở", "Landslide"],
  land_risk: ["Rủi ro mua đất", "Land-purchase risk"],
  solar: ["Điện mặt trời", "Solar"],
  pest: ["Sâu bệnh", "Pest & disease"],
  yield: ["Năng suất", "Yield"],
  climate_2050: ["Khí hậu 2050 (CMIP6)", "2050 climate (CMIP6)"],
  upstream_flood: ["Lũ thượng nguồn", "Upstream flood"],
  urban: ["Ngập úng đô thị", "Urban flooding"],
  aquaculture: ["Ao nuôi", "Aquaculture"],
};

export default function Copilot({ lat, lon }: { lat: number; lon: number }) {
  const { t, lang } = useLang();
  // Hỏi bằng giọng nói (25/11/2026) — nhận dạng ngay trong trình duyệt, nói xong tự gửi câu hỏi.
  const [canTalk, setCanTalk] = useState(false);
  const [listening, setListening] = useState(false);
  const rec = useRef<SpeechRecognitionLike | null>(null);
  useEffect(() => { setCanTalk(getRecognition() !== null); return () => rec.current?.stop(); }, []);
  function talk() {
    if (listening) { rec.current?.stop(); return; }
    const r = getRecognition(lang === "en" ? "en" : "vi");
    if (!r) return;
    rec.current = r;
    r.onresult = (e) => {
      const { text, final } = transcriptOf(e);
      setQ(text);
      if (final && text) { r.stop(); ask(text); }
    };
    r.onerror = () => setListening(false);
    r.onend = () => setListening(false);
    setListening(true);
    r.start();
  }
  const SUGGESTS = [
    t("Ruộng tôi có bị mặn không?", "Is my field at risk of salinity?"),
    t("Tuần tới có nên xuống giống?", "Should I sow next week?"),
    t("Chỗ này mua đất có rủi ro gì?", "What are the risks of buying land here?"),
  ];
  const [q, setQ] = useState("");
  const [ans, setAns] = useState<CopilotAnswer | null>(null);
  const [loading, setLoading] = useState(false);

  async function ask(question?: string) {
    const text = (question ?? q).trim();
    if (!text || loading) return;
    if (question) setQ(question);
    setLoading(true);
    try {
      setAns(await askCopilot(text, lat, lon));
    } catch (e: any) {
      setAns({ answer: e.message, used_modules: [] });
    } finally {
      setLoading(false);
    }
  }

  const cites = ans?.knowledge_used ?? [];

  return (
    <div className="copilot">
      <div className="chead">🤖 {t("Hỏi trợ lý về vị trí này", "Ask the assistant about this location")}</div>

      {!ans && (
        <div className="csuggest">
          {SUGGESTS.map((s) => (
            <button key={s} onClick={() => ask(s)} disabled={loading}>{s}</button>
          ))}
        </div>
      )}

      <div className="crow">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={t("VD: ruộng tôi có bị mặn không?", "e.g. is my field at risk of salinity?")}
          onKeyDown={(e) => { if (e.key === "Enter") ask(); }}
        />
        {canTalk && (
          <button type="button" className={`cmic${listening ? " on" : ""}`} onClick={talk} disabled={loading}
                  aria-label={listening ? t("Dừng nghe", "Stop listening") : t("Hỏi bằng giọng nói", "Ask by voice")}
                  title={listening ? t("Đang nghe… bấm để dừng", "Listening… click to stop") : t("Hỏi bằng giọng nói", "Ask by voice")}>
            {listening ? "⏺" : "🎤"}
          </button>
        )}
        <button onClick={() => ask()} disabled={loading}>
          {loading ? "…" : t("Hỏi", "Ask")}
        </button>
      </div>

      {ans && (
        <div className="cresult">
          <pre className="cans">{boldParts(ans.answer).map((p, i) => (p.bold ? <b key={i}>{p.text}</b> : <span key={i}>{p.text}</span>))}</pre>

          {/* NGUỒN DẪN — làm cái grounding hiện lên */}
          <div className="csrc">
            <span className="csrc-cap">
              🔎 {t("Dựa trên", "Based on")}
              <span className={`cbadge ${ans.llm ? "llm" : "rule"}`}>
                {ans.llm ? t("diễn đạt bằng AI · số liệu đo được", "AI-phrased · measured data")
                         : t("trả lời thẳng từ số đo (không qua AI)", "answered directly from measurements (no AI)")}
              </span>
            </span>

            {ans.used_modules.length > 0 && (
              <div className="csrc-mods">
                {ans.used_modules.map((m) => (
                  <span key={m} className="csrc-chip">🛰️ {MOD_NAME[m] ? t(MOD_NAME[m][0], MOD_NAME[m][1]) : m}</span>
                ))}
              </div>
            )}

            {/* Công cụ trợ lý TỰ gọi thêm (nâng cấp 25/11/2026) — để thấy nó đã tra gì, không chỉ đọc dữ kiện có sẵn. */}
            {(ans.tools?.length ?? 0) > 0 && (
              <div className="csrc-mods csrc-tools">
                <span className="csrc-sub">🧰 {t("Trợ lý đã tự tra thêm:", "The assistant also looked up:")}</span>
                {ans.tools!.map((x, i) => (
                  <span key={`${x.tool}-${i}`} className={`csrc-chip${x.ok ? "" : " off"}`}
                        title={x.ms != null ? `${x.ms} ms` : undefined}>
                    {x.label}{x.tool === "danh_gia_hiem_hoa" && x.args?.hazard
                      ? ` · ${MOD_NAME[String(x.args.hazard)] ? t(MOD_NAME[String(x.args.hazard)][0], MOD_NAME[String(x.args.hazard)][1]) : String(x.args.hazard)}`
                      : ""}{x.ok ? "" : t(" (không tra được)", " (unavailable)")}
                  </span>
                ))}
              </div>
            )}

            {cites.length > 0 && (
              <div className="csrc-cites">
                <span className="csrc-sub">🌾 {t("Kinh nghiệm vùng cùng “gen đất” (không phải số đo):", "Experience from same-“soil-genome” regions (not measurements):")}</span>
                {cites.map((c) => (
                  <div key={c.id} className="csrc-cite">
                    <b>{c.title}</b>
                    <span> — {c.author_name} · {t("tương đồng", "similarity")} {c.similarity_pct}% · {t("cách", "away")} {c.distance_km.toFixed(0)} km</span>
                  </div>
                ))}
              </div>
            )}

            <p className="csrc-note">
              {t("Trợ lý chỉ trả lời dựa trên dữ liệu của thửa này — không bịa số. Chỗ nào chưa đủ dữ liệu, nó nói thẳng.",
                 "The assistant answers only from this plot's data — no fabricated numbers. Where data is missing, it says so plainly.")}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
