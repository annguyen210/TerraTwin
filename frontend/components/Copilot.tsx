"use client";

import { useState } from "react";
import { askCopilot, type CopilotAnswer } from "@/lib/api";

export default function Copilot({ lat, lon }: { lat: number; lon: number }) {
  const [q, setQ] = useState("");
  const [ans, setAns] = useState<CopilotAnswer | null>(null);
  const [loading, setLoading] = useState(false);

  async function ask() {
    if (!q.trim()) return;
    setLoading(true);
    try {
      setAns(await askCopilot(q, lat, lon));
    } catch (e: any) {
      setAns({ answer: e.message, used_modules: [] });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="copilot">
      <div className="chead">🤖 Hỏi trợ lý về vị trí này</div>
      <div className="crow">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="VD: ruộng tôi có bị mặn không?"
          onKeyDown={(e) => {
            if (e.key === "Enter") ask();
          }}
        />
        <button onClick={ask} disabled={loading}>
          {loading ? "…" : "Hỏi"}
        </button>
      </div>
      {ans && <pre className="cans">{ans.answer}</pre>}
    </div>
  );
}
