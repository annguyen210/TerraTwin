"use client";

/**
 * THẺ MÔ HÌNH (GĐ5) — mọi mô hình / quy tắc AI của TerraTwin, KỂ CẢ cái đã trượt: dữ liệu, cách chia tập, điểm trên
 * tập giữ lại so với ngưỡng đặt trước, giới hạn đã biết, trường hợp không nên dùng, mã nguồn. Số đọc từ API, API
 * đọc thẳng từ tệp kiểm định đã commit — không ai gõ tay số đẹp vào đây.
 */
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import { getModelCards, type AiModelCards } from "@/lib/api";
import { useLang } from "@/lib/i18n";

const ST: Record<string, string> = { accepted: "mc-ok", active_v1: "mc-mid", pending: "mc-mid", rejected: "mc-bad" };

export default function ModelCardsPage() {
  const { t, lang } = useLang();
  const [d, setD] = useState<AiModelCards | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { getModelCards().then(setD).catch((e) => setErr(e.message)); }, [lang]);

  return (
    <AppShell>
      <main className="mc-wrap">
        <p className="dos-eyebrow">{t("THẺ MÔ HÌNH · TERRATWIN", "MODEL CARDS · TERRATWIN")}</p>
        <h1>{t("Mọi mô hình AI, kể cả cái đã trượt", "Every AI model, including the ones that failed")}</h1>
        {d && <p className="cmp-lede">{d.rule}</p>}
        {err && <p className="bat-err">{err}</p>}
        {!d && !err && <p className="doc-note">{t("Đang tải…", "Loading…")}</p>}
        <div className="mc-grid">
          {d?.cards.map((c) => (
            <article key={c.id} className={`mc-card ${ST[c.status] ?? "mc-mid"}`}>
              <header>
                <span className="mc-kind">{c.kind}</span>
                <h2>{c.name}</h2>
                <b className="mc-status">{c.status_label}</b>
              </header>
              <p>{c.task}</p>
              {c.metrics.length > 0 && (
                <table className="mc-table">
                  <thead><tr><th>{t("Chỉ số", "Metric")}</th><th>{t("Kết quả", "Result")}</th><th>{t("Ngưỡng đặt trước", "Pre-set threshold")}</th></tr></thead>
                  <tbody>
                    {c.metrics.map((m, i) => (
                      <tr key={i}>
                        <td>{m.label}</td>
                        <td className={m.passed === true ? "mc-pass" : m.passed === false ? "mc-fail" : ""}>
                          {m.value ?? "—"}{m.passed === true ? " ✓" : m.passed === false ? " ✗" : ""}</td>
                        <td>{m.threshold}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              <dl>
                <dt>{t("Dữ liệu", "Data")}</dt><dd>{c.data ?? "—"}</dd>
                <dt>{t("Chia tập / cổng", "Split / gate")}</dt><dd>{c.split}</dd>
                {c.limits && <><dt>{t("Giới hạn đã biết", "Known limits")}</dt><dd>{c.limits}</dd></>}
                <dt>{t("Không nên dùng cho", "Not for")}</dt><dd>{c.not_for}</dd>
              </dl>
              <a href={c.code} target="_blank" rel="noreferrer" className="mc-code">{t("Mã nguồn", "Source code")} →</a>
            </article>
          ))}
        </div>
      </main>
    </AppShell>
  );
}
