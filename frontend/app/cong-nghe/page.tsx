"use client";

/**
 * BẢN ĐỒ CÔNG NGHỆ (26/11/2026) — đủ 413 mục trong danh sách nâng cấp của chủ dự án, đối chiếu TỪNG mục với mã nguồn:
 * đang dùng (ở đâu), có sẵn trong nền tảng (không tự cài), hoặc không dùng (vì sao). Không bỏ sót, không tô vẽ.
 */
import { useEffect, useMemo, useState } from "react";
import AppShell from "@/components/AppShell";
import { getTechMap, type TechMap, type TechMapItem } from "@/lib/api";
import { useLang } from "@/lib/i18n";

const ST = { used: { cls: "tm-used", vi: "Đang dùng" }, platform: { cls: "tm-plat", vi: "Nền tảng" }, no: { cls: "tm-no", vi: "Không dùng" } };

export default function TechMapPage() {
  const { t } = useLang();
  const [d, setD] = useState<TechMap | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [f, setF] = useState<"all" | TechMapItem["status"]>("all");
  const [q, setQ] = useState("");
  useEffect(() => { getTechMap().then(setD).catch((e) => setErr(e.message)); }, []);

  const groups = useMemo(() => {
    const k = q.trim().toLowerCase();
    const rows = (d?.items ?? []).filter((x) => (f === "all" || x.status === f) &&
      (!k || x.item.toLowerCase().includes(k) || x.note.toLowerCase().includes(k) || x.category.toLowerCase().includes(k)));
    const g = new Map<string, TechMapItem[]>();
    for (const r of rows) {
      const key = `${r.part} — ${r.section}`;
      g.set(key, [...(g.get(key) ?? []), r]);
    }
    return [...g.entries()];
  }, [d, f, q]);

  return (
    <AppShell>
      <main className="mc-wrap">
        <p className="dos-eyebrow">{t("BẢN ĐỒ CÔNG NGHỆ · TERRATWIN", "TECHNOLOGY MAP · TERRATWIN")}</p>
        <h1>{t("Từng công nghệ: dùng ở đâu, hay vì sao không dùng", "Every technology: where it is used, or why not")}</h1>
        <p className="cmp-lede">{t("Đối chiếu đủ danh sách khoa học máy tính, dữ liệu, AI và kỹ thuật phần mềm với mã nguồn TerraTwin. Công nghệ chỉ được dùng khi nó giải một việc thật cho người dùng và kiểm chứng được — gắn cho đủ tên là làm phần mềm tệ đi.",
                                   "The full computer-science, data, AI and software-engineering list checked against TerraTwin's source. A technology is used only when it solves a real user problem and can be verified — adding names for show makes software worse.")}</p>
        {err && <p className="bat-err">{err}</p>}
        {!d && !err && <p className="doc-note">{t("Đang tải…", "Loading…")}</p>}
        {d && (
          <>
            <div className="tm-filter" role="group" aria-label={t("Lọc theo trạng thái", "Filter by status")}>
              {(["all", "used", "platform", "no"] as const).map((k) => (
                <button key={k} type="button" className={f === k ? "on" : ""} aria-pressed={f === k} onClick={() => setF(k)}>
                  {k === "all" ? t(`Tất cả (${d.items.length})`, `All (${d.items.length})`)
                    : `${ST[k].vi} (${d.counts[k] ?? 0})`}
                </button>
              ))}
              <input className="bat-input" placeholder={t("Tìm: A*, Bloom, ONNX…", "Search: A*, Bloom, ONNX…")} value={q}
                     onChange={(e) => setQ(e.target.value)} aria-label={t("Tìm công nghệ", "Search technologies")} />
            </div>
            {groups.map(([g, rows]) => (
              <section key={g} className="tm-group">
                <h2>{g}</h2>
                <table className="mc-table tm-table">
                  <tbody>
                    {rows.map((r, i) => (
                      <tr key={`${r.item}-${i}`}>
                        <td className="tm-item"><b>{r.item}</b><small>{r.category}</small></td>
                        <td><span className={`tm-badge ${ST[r.status].cls}`}>{ST[r.status].vi}</span></td>
                        <td className="tm-note">{r.note}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            ))}
            <p className="doc-note">{d.source}</p>
          </>
        )}
      </main>
    </AppShell>
  );
}
