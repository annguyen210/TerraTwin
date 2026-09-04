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

import { useState } from "react";
import { askCopilot, type CopilotAnswer } from "@/lib/api";

const MOD_NAME: Record<string, string> = {
  salinity: "Xâm nhập mặn",
  drought: "Hạn & thiếu nước",
  flood: "Lũ & ngập",
  wildfire: "Cháy rừng",
  landslide: "Sạt lở",
  land_risk: "Rủi ro mua đất",
  solar: "Điện mặt trời",
  pest: "Sâu bệnh",
  yield: "Năng suất",
};

const SUGGESTS = [
  "Ruộng tôi có bị mặn không?",
  "Tuần tới có nên xuống giống?",
  "Chỗ này mua đất có rủi ro gì?",
];

export default function Copilot({ lat, lon }: { lat: number; lon: number }) {
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
      <div className="chead">🤖 Hỏi trợ lý về vị trí này</div>

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
          placeholder="VD: ruộng tôi có bị mặn không?"
          onKeyDown={(e) => { if (e.key === "Enter") ask(); }}
        />
        <button onClick={() => ask()} disabled={loading}>
          {loading ? "…" : "Hỏi"}
        </button>
      </div>

      {ans && (
        <div className="cresult">
          <pre className="cans">{ans.answer}</pre>

          {/* NGUỒN DẪN — làm cái grounding hiện lên */}
          <div className="csrc">
            <span className="csrc-cap">
              🔎 Dựa trên
              <span className={`cbadge ${ans.llm ? "llm" : "rule"}`}>
                {ans.llm ? "diễn đạt bằng AI · số liệu đo được" : "trợ lý luật · số liệu đo được"}
              </span>
            </span>

            {ans.used_modules.length > 0 && (
              <div className="csrc-mods">
                {ans.used_modules.map((m) => (
                  <span key={m} className="csrc-chip">🛰️ {MOD_NAME[m] ?? m}</span>
                ))}
              </div>
            )}

            {cites.length > 0 && (
              <div className="csrc-cites">
                <span className="csrc-sub">🌾 Kinh nghiệm vùng cùng “gen đất” (không phải số đo):</span>
                {cites.map((c) => (
                  <div key={c.id} className="csrc-cite">
                    <b>{c.title}</b>
                    <span> — {c.author_name} · tương đồng {c.similarity_pct}% · cách {c.distance_km.toFixed(0)} km</span>
                  </div>
                ))}
              </div>
            )}

            <p className="csrc-note">
              Trợ lý chỉ trả lời dựa trên dữ liệu của thửa này — không bịa số. Chỗ nào
              chưa đủ dữ liệu, nó nói thẳng.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
