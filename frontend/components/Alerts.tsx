"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ackAlert,
  listAlerts,
  runRadar,
  type AlertRow,
  type RadarProgress,
  type AuthUser,
} from "@/lib/api";
import { useLang } from "@/lib/i18n";

const RISK_COLOR: Record<string, string> = {
  danger: "#C2412E",
  warning: "#B07A2E",
  safe: "#2E9E67",
};

export default function Alerts({ user }: { user: AuthUser | null }) {
  const { t, lang } = useLang();
  const [rows, setRows] = useState<AlertRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [prog, setProg] = useState<RadarProgress | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!user) {
      setRows([]);
      return;
    }
    try {
      setRows(await listAlerts(false));
      setErr(null);
    } catch (e) {
      setErr((e as Error).message);
    }
  }, [user]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function scan() {
    setBusy(true);
    setProg(null);
    setErr(null);
    setNote(null);
    try {
      const r = await runRadar(setProg);
      // 0 cảnh báo mới thường nghĩa là KHÔNG CÓ RỦI RO MỚI — câu cũ ("đã có
      // cảnh báo tương tự") nói sai trong đúng trường hợp hay gặp nhất.
      setNote(
        r.message ??
          t(
            `Đã quét ${r.plots_scanned} thửa · ${r.new_alerts} cảnh báo mới` +
              (r.new_alerts === 0
                ? ` — không có rủi ro mới (cùng một tình trạng chỉ nhắc lại sau ${r.dedup_window_hours ?? 72} giờ, trừ khi nặng lên)`
                : ""),
            `Scanned ${r.plots_scanned} plots · ${r.new_alerts} new alerts` +
              (r.new_alerts === 0
                ? ` — no new risk (an unchanged condition is re-sent only after ${r.dedup_window_hours ?? 72}h, unless it gets worse)`
                : ""),
          ),
      );
      await refresh();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
      setProg(null);
    }
  }

  async function ack(id: number) {
    try {
      await ackAlert(id);
      await refresh();
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  if (!user) return null;

  const unread = rows.filter((r) => !r.acknowledged);

  return (
    <div className="alerts">
      <div className="al-head">
        🛎️ {t("Rà soát chủ động", "Proactive sweep")}
        {unread.length > 0 && <span className="al-badge">{unread.length}</span>}
      </div>
      <p className="al-sub">
        {t("Quét lại mọi thửa đã lưu và chỉ ghi cảnh báo mới — chạy nhiều lần không sinh trùng.",
           "Re-scans every saved plot and only records new alerts — running it repeatedly doesn't create duplicates.")}
      </p>
      <button className="al-run" onClick={scan} disabled={busy}>
        {!busy ? t("Rà soát toàn bộ thửa", "Scan all plots")
          : prog && prog.total > 0
            ? t(`Đang rà soát thửa ${Math.min(prog.done + 1, prog.total)}/${prog.total}${prog.current ? ` — ${prog.current}` : ""}…`,
                `Scanning plot ${Math.min(prog.done + 1, prog.total)}/${prog.total}${prog.current ? ` — ${prog.current}` : ""}…`)
            : t("Đang xếp hàng rà soát…", "Queued for scanning…")}
      </button>
      {busy && (
        <p className="al-sub">
          {t("Chạy nền — mỗi thửa cần ảnh vệ tinh nên mất 1–3 phút. Có thể đóng trang, cảnh báo vẫn được ghi.",
             "Runs in the background — each plot needs satellite imagery, so 1–3 min each. You can close the page; alerts are still recorded.")}
        </p>
      )}

      {note && <p className="al-note">{note}</p>}
      {err && <p className="err">{err}</p>}

      {rows.length === 0 && !note && (
        <p className="al-empty">{t("Chưa có cảnh báo nào.", "No alerts yet.")}</p>
      )}

      {rows.map((a) => (
        <div
          key={a.id}
          className={`al-item ${a.acknowledged ? "done" : ""}`}
          style={{ borderLeftColor: RISK_COLOR[a.risk_level] ?? "#5a6b73" }}
        >
          <div className="al-item-top">
            <span className="al-when">
              {new Date(a.created_at).toLocaleString(lang === "en" ? "en-US" : "vi-VN")}
            </span>
            {!a.acknowledged && (
              <button className="al-ack" onClick={() => ack(a.id)}>
                {t("Đã xem", "Seen")}
              </button>
            )}
          </div>
          <div className="al-title">{a.headline}</div>
          <div className="al-rec">→ {a.recommendation}</div>
        </div>
      ))}
    </div>
  );
}
