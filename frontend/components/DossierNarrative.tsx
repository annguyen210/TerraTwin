"use client";

/**
 * GĐ4 · NĂNG LỰC 4 — "Mỗi câu bấm vào là ra bằng chứng". Lời diễn giải của hồ sơ đất số; bấm một câu
 * hiện số liệu gốc, nguồn, ngày đo, cách tái lập. Lời sinh lại từ nội dung đã ký (không nằm trong phần
 * ký); câu AI viết lại mà có số lạ đã bị máy chủ loại trước khi tới đây.
 */
import { useState } from "react";
import type { DossierNarrative as N } from "@/lib/api";
import { useLang } from "@/lib/i18n";

export default function DossierNarrative({ n }: { n: N }) {
  const { t } = useLang();
  const [open, setOpen] = useState<string | null>(null);

  return (
    <section className="dn">
      <h2>{t("Tóm tắt dễ hiểu — bấm một câu để xem bằng chứng", "Plain summary — tap a sentence to see its evidence")}</h2>
      <ol className="dn-list">
        {n.sentences.map((s) => {
          const on = open === s.id;
          return (
            <li key={s.id} className={on ? "on" : ""}>
              <button type="button" className="dn-s" aria-expanded={on} aria-controls={`dn-${s.id}`}
                      onClick={() => setOpen(on ? null : s.id)}>
                <span>{s.text}</span>
                <small className="dn-count">{s.evidence.length} {t("bằng chứng", s.evidence.length > 1 ? "sources" : "source")}</small>
              </button>
              {on && (
                <div id={`dn-${s.id}`} className="dn-ev">
                  {s.evidence.map((id) => {
                    const e = n.evidence[id];
                    if (!e) return null;
                    return (
                      <dl key={id}>
                        <dt>{e.label}</dt>
                        <dd className="dn-val">{e.value}</dd>
                        <dt>{t("Nguồn", "Source")}</dt><dd>{e.source}</dd>
                        <dt>{t("Ngày đo", "Measured")}</dt><dd>{e.measured}</dd>
                        <dt>{t("Cách tái lập", "How to reproduce")}</dt>
                        <dd>{e.reproduce}{e.url && <> <a href={e.url} target="_blank" rel="noreferrer">{
                          e.url.includes("github.com") ? t("mã nguồn", "source code") : t("mở API", "open API")}</a></>}</dd>
                        <dd className="dn-id"><code>{id}</code></dd>
                      </dl>
                    );
                  })}
                </div>
              )}
            </li>
          );
        })}
      </ol>
      <p className="dos-src">{n.note}{n.mode === "llm" ? ` ${t("Lời đã được AI viết lại cho dễ đọc.", "Wording was rewritten by AI for readability.")}` : ""}
        {n.blocked_sentences > 0 ? ` ${t(`${n.blocked_sentences} câu AI viết có số lạ đã bị loại.`, `${n.blocked_sentences} AI sentence(s) with unknown numbers were dropped.`)}` : ""}</p>
    </section>
  );
}
