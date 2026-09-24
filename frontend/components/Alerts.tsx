"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ackAlert,
  listAlerts,
  runRadar,
  type AlertRow,
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
    setErr(null);
    setNote(null);
    try {
      const r = await runRadar();
      setNote(
        r.message ??
          t(
            `Đã quét ${r.plots_scanned} thửa · ${r.new_alerts} cảnh báo mới` +
              (r.new_alerts === 0
                ? ` (đã có cảnh báo tương tự trong ${r.dedup_window_hours ?? 12} giờ qua nên không lặp lại)`
                : ""),
            `Scanned ${r.plots_scanned} plots · ${r.new_alerts} new alerts` +
              (r.new_alerts === 0
                ? ` (a similar alert already exists within the last ${r.dedup_window_hours ?? 12}h, so no duplicate)`
                : ""),
          ),
      );
      await refresh();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
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
        {busy ? t("Đang rà soát…", "Scanning…") : t("Rà soát toàn bộ thửa", "Scan all plots")}
      </button>

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
