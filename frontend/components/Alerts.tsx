"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ackAlert,
  listAlerts,
  runRadar,
  type AlertRow,
  type AuthUser,
} from "@/lib/api";

const RISK_COLOR: Record<string, string> = {
  danger: "#C2412E",
  warning: "#B07A2E",
  safe: "#2E9E67",
};

export default function Alerts({ user }: { user: AuthUser | null }) {
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
          `Đã quét ${r.plots_scanned} thửa · ${r.new_alerts} cảnh báo mới` +
            (r.new_alerts === 0
              ? ` (đã có cảnh báo tương tự trong ${r.dedup_window_hours ?? 12} giờ qua nên không lặp lại)`
              : ""),
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
        🛎️ Rà soát chủ động
        {unread.length > 0 && <span className="al-badge">{unread.length}</span>}
      </div>
      <p className="al-sub">
        Quét lại mọi thửa đã lưu và chỉ ghi cảnh báo mới — chạy nhiều lần không
        sinh trùng.
      </p>
      <button className="al-run" onClick={scan} disabled={busy}>
        {busy ? "Đang rà soát…" : "Rà soát toàn bộ thửa"}
      </button>

      {note && <p className="al-note">{note}</p>}
      {err && <p className="err">{err}</p>}

      {rows.length === 0 && !note && (
        <p className="al-empty">Chưa có cảnh báo nào.</p>
      )}

      {rows.map((a) => (
        <div
          key={a.id}
          className={`al-item ${a.acknowledged ? "done" : ""}`}
          style={{ borderLeftColor: RISK_COLOR[a.risk_level] ?? "#5a6b73" }}
        >
          <div className="al-item-top">
            <span className="al-when">
              {new Date(a.created_at).toLocaleString("vi-VN")}
            </span>
            {!a.acknowledged && (
              <button className="al-ack" onClick={() => ack(a.id)}>
                Đã xem
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
