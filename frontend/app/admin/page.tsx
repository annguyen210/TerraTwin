"use client";

/**
 * Đ11 — trang quản trị. Trước đây "coop" chỉ là một dòng bình luận trong code,
 * chưa route/giao diện nào dùng tới, và health/quota/radar/funnel/backup-status/
 * drift mỗi thứ chỉ có API, không ai xem được ngoài gọi tay curl.
 *
 * Hai vai trò khác nhau thấy khác nhau:
 *   admin — mọi tab (sức khoẻ + phễu + sao lưu + trôi + hợp tác xã).
 *   coop  — chỉ tab "Hợp tác xã" (xem thửa thành viên đã đồng ý chia sẻ).
 * Vai trò 'user' thường: 403 rõ ràng, không phải màn trắng.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  fetchMe, getHealth, getFunnel, getBackupStatus, getDrift, getCoopPlots, updateCoop,
  type AuthUser, type HealthStatus, type CoopPlot,
} from "@/lib/api";
import { LangToggle, useLang } from "@/lib/i18n";

type Tab = "health" | "funnel" | "backup" | "drift" | "coop";

function when(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("vi-VN", {
    day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

function HealthTab() {
  const [h, setH] = useState<HealthStatus | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    getHealth().then((r) => live && setH(r)).catch((e) => live && setErr(e.message));
    return () => { live = false; };
  }, []);

  if (err) return <p className="ws-err">⚠️ {err}</p>;
  if (!h) return <p className="ws-hint">Đang tải…</p>;

  return (
    <div>
      <p>
        Trạng thái: <b style={{ color: h.status === "ok" ? "var(--ok, #3ecb83)" : "var(--warn, #e0a44a)" }}>
          {h.status === "ok" ? "✅ bình thường" : "⚠️ suy giảm"}
        </b>
        {" · "}{h.modules} mô-đun · {h.service}
      </p>

      <h4 style={{ marginTop: 18 }}>Hạn mức nguồn dữ liệu</h4>
      {h.quota.exhausted.length === 0 ? (
        <p className="ws-hint">Chưa nguồn nào hết hạn mức.</p>
      ) : (
        <ul>
          {h.quota.exhausted.map((src) => (
            <li key={src}>
              <b>{src}</b> — hết hạn mức {h.quota.minutes_since_detected[src] ?? "?"} phút trước
              ({h.quota.count_429_24h[src] ?? 0} lượt 429/24h)
            </li>
          ))}
        </ul>
      )}
      <p className="ws-hint">{h.quota.message}</p>

      <h4 style={{ marginTop: 18 }}>Radar (rà soát nền)</h4>
      <p>Lượt quét gần nhất: <b>{when(h.radar.last_sweep_at)}</b></p>

      <h4 style={{ marginTop: 18 }}>Email</h4>
      <p>
        SMTP: {h.email.smtp_configured ? "✅ đã cấu hình" : "⚠️ CHƯA cấu hình"}
        {h.email.message && <span className="ws-hint"> — {h.email.message}</span>}
      </p>

      <h4 style={{ marginTop: 18 }}>Lượt gọi</h4>
      <p>{h.calls.total} lượt · {h.calls.cache_hits} từ cache
        {h.calls.hit_rate_pct != null && ` (${h.calls.hit_rate_pct}%)`}</p>
    </div>
  );
}

function FunnelTab() {
  const [data, setData] = useState<Awaited<ReturnType<typeof getFunnel>> | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    getFunnel(30).then((r) => live && setData(r)).catch((e) => live && setErr(e.message));
    return () => { live = false; };
  }, []);

  if (err) return <p className="ws-err">⚠️ {err}</p>;
  if (!data) return <p className="ws-hint">Đang tải…</p>;

  return (
    <div>
      <p className="ws-hint">{data.note}</p>
      <table className="ws-table">
        <thead><tr><th>Bước</th><th>Số lượt</th><th>% so với "mở app"</th></tr></thead>
        <tbody>
          {data.steps.map((s) => (
            <tr key={s.step}>
              <td>{s.step}</td>
              <td>{s.count}</td>
              <td>{s.pct_of_open != null ? `${s.pct_of_open}%` : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function BackupTab() {
  const [data, setData] = useState<Awaited<ReturnType<typeof getBackupStatus>> | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    getBackupStatus().then((r) => live && setData(r)).catch((e) => live && setErr(e.message));
    return () => { live = false; };
  }, []);

  if (err) return <p className="ws-err">⚠️ {err}</p>;
  if (!data) return <p className="ws-hint">Đang tải…</p>;

  return (
    <div>
      <p style={{ color: data.stale ? "var(--warn, #e0a44a)" : "var(--ok, #3ecb83)" }}>
        {data.stale ? "⚠️" : "✅"} {data.message}
      </p>
      {data.configured && (
        <ul>
          <li>Bản mới nhất: <b>{data.latest}</b></li>
          <li>Cách đây: {data.age_hours} giờ</li>
          <li>Tổng số bản: {data.count}</li>
        </ul>
      )}
    </div>
  );
}

function DriftTab() {
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    getDrift().then((r) => live && setData(r)).catch((e) => live && setErr(e.message));
    return () => { live = false; };
  }, []);

  if (err) return <p className="ws-err">⚠️ {err}</p>;
  if (!data) return <p className="ws-hint">Đang tải…</p>;

  return <pre className="ws-pre">{JSON.stringify(data, null, 2)}</pre>;
}

function CoopTab({ user }: { user: AuthUser }) {
  const [code, setCode] = useState(user.coop_code || "");
  const [share, setShare] = useState(user.share_with_coop);
  const [data, setData] = useState<{ coop_code: string; members: number; plots: CoopPlot[]; message?: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () => {
    getCoopPlots().then(setData).catch((e) => setErr(e.message));
  };
  useEffect(load, []);

  async function save() {
    setBusy(true); setErr(null);
    try {
      await updateCoop({ coop_code: code.trim(), share_with_coop: share });
      load();
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  }

  return (
    <div>
      <p className="ws-hint">
        Đặt cùng một mã với các thành viên khác để "vào cùng nhóm". Đặt mã KHÔNG
        tự động cho ai xem thửa của bạn — phải bật riêng "chia sẻ với nhóm".
      </p>
      <div className="ws-row">
        <input placeholder="Mã hợp tác xã, vd HTX-BEN-TRE-01" value={code}
               onChange={(e) => setCode(e.target.value)} />
        <label className="ws-check" style={{ margin: 0 }}>
          <input type="checkbox" checked={share} onChange={(e) => setShare(e.target.checked)} />
          <span>Chia sẻ thửa của tôi với nhóm</span>
        </label>
        <button onClick={save} disabled={busy}>Lưu</button>
      </div>
      {err && <p className="ws-err">⚠️ {err}</p>}

      {data && (
        <>
          <h4 style={{ marginTop: 18 }}>
            Nhóm "{data.coop_code || "—"}" — {data.members} thành viên đã chia sẻ
          </h4>
          {data.message && <p className="ws-hint">{data.message}</p>}
          {data.plots.length > 0 && (
            <table className="ws-table">
              <thead><tr><th>Thửa</th><th>Chủ</th><th>Toạ độ</th><th>Diện tích</th><th>Điểm</th></tr></thead>
              <tbody>
                {data.plots.map((p) => (
                  <tr key={p.id}>
                    <td>{p.name}</td>
                    <td>{p.owner_name}</td>
                    <td>{p.lat.toFixed(4)}, {p.lon.toFixed(4)}</td>
                    <td>{p.area_ha != null ? `${p.area_ha} ha` : "—"}</td>
                    <td>{p.score != null ? `${p.score} (${p.grade})` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  );
}

export default function AdminPage() {
  const { t } = useLang();
  const [user, setUser] = useState<AuthUser | null | undefined>(undefined);
  const [tab, setTab] = useState<Tab>("health");

  useEffect(() => {
    fetchMe().then(setUser).catch(() => setUser(null));
  }, []);

  const isAdmin = user?.role === "admin";
  const isCoop = user?.role === "coop" || isAdmin;

  const TABS: { id: Tab; label: string; show: boolean }[] = [
    { id: "health", label: "Sức khoẻ", show: true },
    { id: "funnel", label: "Phễu người dùng", show: isAdmin },
    { id: "backup", label: "Sao lưu", show: isAdmin },
    { id: "drift", label: "Trôi mô hình", show: isAdmin },
    { id: "coop", label: "Hợp tác xã", show: isCoop },
  ];

  return (
    <div className="doc">
      <header className="doc-top">
        <Link href="/" className="doc-brand">◵ TerraTwin</Link>
        <div className="doc-actions"><LangToggle /><Link href="/" className="doc-home">{t("← Về trang chính", "← Home")}</Link></div>
      </header>
      <article className="doc-body" style={{ maxWidth: 820 }}>
        <h1>Quản trị</h1>

        {user === undefined && <p className="ws-hint">Đang tải…</p>}
        {user === null && (
          <p className="ws-err">⚠️ Cần đăng nhập để xem trang này.</p>
        )}
        {user && !isAdmin && !isCoop && (
          <p className="ws-err">⚠️ Chỉ quản trị viên hoặc hợp tác xã mới xem được trang này.</p>
        )}

        {user && (isAdmin || isCoop) && (
          <>
            <div className="ws-tabs" style={{ marginTop: 14 }}>
              {TABS.filter((x) => x.show).map((tb) => (
                <button key={tb.id} className={tab === tb.id ? "on" : ""} onClick={() => setTab(tb.id)}>
                  {tb.label}
                </button>
              ))}
            </div>
            <div style={{ marginTop: 18 }}>
              {tab === "health" && <HealthTab />}
              {tab === "funnel" && isAdmin && <FunnelTab />}
              {tab === "backup" && isAdmin && <BackupTab />}
              {tab === "drift" && isAdmin && <DriftTab />}
              {tab === "coop" && isCoop && <CoopTab user={user} />}
            </div>
          </>
        )}
      </article>
    </div>
  );
}
