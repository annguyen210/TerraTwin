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
  getPilotSummary, downloadPilotCsv, adminLabelers, adminAddLabeler, adminRemoveLabeler, adminLabelSummary,
  adminLabelExport, adminUsers, adminUpdateUser, adminUpgradeRequests, adminDecideUpgrade, adminPayments, type AdminPayment, adminWaterConfirms, adminSeasonCases, adminListingGold, adminListingGoldAdd, adminListingGoldDelete,
  type AdminUser, type UpgradeReq, type AdminWaterConfirms, type AdminSeasonCases, type ListingGoldView,
  type AuthUser, type HealthStatus, type CoopPlot, type PilotSummary, type LabelSummary,
} from "@/lib/api";
import { useLang } from "@/lib/i18n";
import AppShell from "@/components/AppShell";
import { getToken } from "@/lib/api";

type Tab = "users" | "upgrades" | "health" | "funnel" | "pilot" | "label" | "truth" | "gold" | "backup" | "drift" | "coop";

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
      {data.sales && (
        <>
          <h4 style={{ margin: "18px 0 6px" }}>Phễu bán hàng (kế hoạch tổng GĐ7)</h4>
          <table className="ws-table">
            <thead><tr><th>Bước</th><th>Số lượt</th><th>% so với "mở app"</th></tr></thead>
            <tbody>
              {data.sales.map((s) => (
                <tr key={s.step}>
                  <td>{{ open: "Mở app", pick_plot: "Chọn thửa", dossier: "Phát hành hồ sơ", pay: "Trả tiền (chưa mở)" }[s.step] ?? s.step}</td>
                  <td>{s.count}</td>
                  <td>{s.pct_of_open != null ? `${s.pct_of_open}%` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {data.return_7d && (
        <p className="ws-hint" style={{ marginTop: 12 }}>
          <b>Quay lại trong 7 ngày:</b> {data.return_7d.rate_pct != null ? `${data.return_7d.rate_pct}%` : "—"} ({data.return_7d.returned}/{data.return_7d.cohort} tài khoản) — {data.return_7d.note}
        </p>
      )}
    </div>
  );
}

function PilotTab() {
  const [data, setData] = useState<PilotSummary | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    getPilotSummary().then((r) => live && setData(r)).catch((e) => live && setErr(e.message));
    return () => { live = false; };
  }, []);

  if (err) return <p className="ws-err">⚠️ {err}</p>;
  if (!data) return <p className="ws-hint">Đang tải…</p>;
  const ROLE: Record<string, string> = { farmer: "Nông hộ", coop: "Cán bộ HTX", exporter: "Xuất khẩu", other: "Khác" };
  const rows = [["Tất cả", data.all] as const, ...Object.entries(data.by_role).map(([k, b]) => [ROLE[k] ?? k, b] as const)];

  return (
    <div>
      {data.note && <p className="ws-hint">{data.note}</p>}
      <table className="ws-table">
        <thead><tr><th>Nhóm</th><th>Số phiếu</th><th>Dễ dùng (1–5)</th><th>Tin kết quả (1–5)</th><th>Phút/hồ sơ (trung vị)</th><th>Dùng tiếp: có / có thể / không</th></tr></thead>
        <tbody>
          {rows.map(([name, b]) => (
            <tr key={name}>
              <td>{name}</td><td>{b.n}</td><td>{b.ease_mean ?? "—"}</td><td>{b.trust_mean ?? "—"}</td>
              <td>{b.minutes_median ?? "—"}</td><td>{b.would_use.yes} / {b.would_use.maybe} / {b.would_use.no}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="ws-hint">Bước khó nhất: {Object.entries(data.all.hardest).map(([k, n]) => `${k} ${n}`).join(" · ")}</p>
      <button className="doc-btn" onClick={() => downloadPilotCsv().catch((e) => setErr(e.message))}>Tải CSV</button>
      <h4 style={{ marginTop: 18 }}>Góp ý mới nhất</h4>
      {data.latest.length === 0 ? <p className="ws-hint">Chưa có phiếu nào. Gửi thử ở <Link href="/thi-diem">/thi-diem</Link>.</p> : (
        <ul>
          {data.latest.filter((r) => r.comment).slice(0, 30).map((r) => (
            <li key={r.id}>{when(r.created_at)} · {ROLE[r.role] ?? r.role}{r.region ? ` · ${r.region}` : ""}{r.source === "paper" ? " · phiếu giấy" : ""}: {r.comment}{r.contact ? ` (liên hệ: ${r.contact})` : ""}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function UsersTab() {
  const [q, setQ] = useState("");
  const [d, setD] = useState<Awaited<ReturnType<typeof adminUsers>> | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [months, setMonths] = useState(3);
  const load = (qq = q) => adminUsers(qq).then(setD).catch((e) => setErr(e.message));
  useEffect(() => { load(""); }, []);  // eslint-disable-line react-hooks/exhaustive-deps
  async function act(u: AdminUser, body: Parameters<typeof adminUpdateUser>[1]) {
    setErr(null); setMsg(null);
    try { const r = await adminUpdateUser(u.id, body); setMsg(`${u.email}: ${r.changed.join("; ") || "không đổi"}`); load(); }
    catch (e) { setErr((e as Error).message); }
  }
  return (
    <div>
      <p className="ws-hint">Mọi tài khoản có <b>đủ mọi tính năng</b>. Ở đây quản trị <b>cấp hạn mức</b> (gói) có thời hạn, vai trò hợp tác xã và cả
        <b> quyền quản trị</b>. Không tự bỏ quyền của chính mình được; email quản trị gốc (biến TERRATWIN_ADMIN_EMAILS) chỉ bỏ được trên máy chủ.</p>
      <div className="ws-row">
        <input placeholder="Tìm theo email hoặc tên" value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load()} />
        <button className="doc-btn" onClick={() => load()}>Tìm</button>
        <label className="ws-hint">Thời hạn gói cấp: <select value={months} onChange={(e) => setMonths(Number(e.target.value))}>
          {[1, 3, 6, 12, 0].map((m) => <option key={m} value={m}>{m ? `${m} tháng` : "không hạn"}</option>)}</select></label>
      </div>
      {err && <p className="ws-err">⚠️ {err}</p>}
      {msg && <p className="ws-hint">✓ {msg}</p>}
      {d && <p className="ws-hint">{d.total} tài khoản · {d.pending_requests} yêu cầu nâng cấp đang chờ</p>}
      {d && (
        <div style={{ overflowX: "auto" }}>
          <table className="ws-table">
            <thead><tr><th>Tài khoản</th><th>Vai trò</th><th>Gói (hạn mức)</th><th>Thửa / hồ sơ</th><th>Hoạt động gần nhất</th><th>Cấp</th></tr></thead>
            <tbody>
              {d.users.map((u) => (
                <tr key={u.id}>
                  <td><b>{u.email}</b><br /><small>{u.name || "—"} · {u.email_verified ? "email ✓" : "email chưa xác thực"} · {u.totp_enabled ? "2FA ✓" : "2FA —"}</small></td>
                  <td>{u.role}</td>
                  <td>{u.plan_name}{u.plan_until ? <><br /><small>đến {when(u.plan_until)}</small></> : null}</td>
                  <td>{u.plots} / {u.dossiers}</td>
                  <td>{when(u.last_active)}</td>
                  <td style={{ whiteSpace: "nowrap" }}>
                    <button className="ws-link" onClick={() => act(u, { plan: "pro", months })}>Mở rộng ×3</button>{" · "}
                    <button className="ws-link" onClick={() => act(u, { plan: "enterprise", months })}>Doanh nghiệp ×10</button>{" · "}
                    <button className="ws-link" onClick={() => act(u, { plan: "free" })}>Về miễn phí</button><br />
                    {u.role !== "admin" && <>
                      <button className="ws-link" onClick={() => act(u, { role: u.role === "coop" ? "user" : "coop" })}>
                        {u.role === "coop" ? "Bỏ vai trò HTX" : "Cấp vai trò HTX"}</button>{" · "}
                      <button className="ws-link" onClick={() => { if (window.confirm(`Cấp QUYỀN QUẢN TRỊ cho ${u.email}? Người này sẽ thấy và làm được mọi thứ trong trang Quản trị.`)) act(u, { role: "admin" }); }}>
                        Cấp quyền quản trị</button>
                    </>}
                    {u.role === "admin" && (
                      <button className="ws-link" onClick={() => { if (window.confirm(`Bỏ quyền quản trị của ${u.email}?`)) act(u, { role: "user" }); }}>Bỏ quyền quản trị</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function UpgradesTab() {
  const [status, setStatus] = useState("pending");
  const [list, setList] = useState<UpgradeReq[] | null>(null);
  const [note, setNote] = useState<Record<number, string>>({});
  const [months, setMonths] = useState(3);
  const [err, setErr] = useState<string | null>(null);
  const load = (st = status) => adminUpgradeRequests(st).then((r) => setList(r.requests)).catch((e) => setErr(e.message));
  useEffect(() => { load(status); }, [status]);  // eslint-disable-line react-hooks/exhaustive-deps
  async function decide(r: UpgradeReq, approve: boolean) {
    try { await adminDecideUpgrade(r.id, { approve, months, note: note[r.id] ?? "" }); load(); } catch (e) { setErr((e as Error).message); }
  }
  const ST: Record<string, string> = { pending: "Đang chờ", approved: "Đã duyệt", rejected: "Đã từ chối" };
  const [pay, setPay] = useState<{ sepay_configured: boolean; payments: AdminPayment[] } | null>(null);
  useEffect(() => { adminPayments().then(setPay).catch(() => setPay(null)); }, [list]);
  const PS: Record<string, string> = { matched: "đã cấp gói", underpaid: "thiếu tiền", unmatched: "chưa khớp", ignored: "bỏ qua" };
  return (
    <div>
      {pay && (
        <div className="adm-note">
          <b>Chuyển khoản SePay</b> · {pay.sepay_configured ? "đang bật — tiền vào đúng mã + đủ giá thì gói tự kích hoạt"
            : "chưa bật (máy chủ chưa đặt TERRATWIN_SEPAY_API_KEY) — đối chiếu sao kê tay"}
          {pay.payments.length > 0 && (
            <table className="ws-table" style={{ marginTop: 8 }}>
              <thead><tr><th>Lúc</th><th>Số tiền</th><th>Nội dung</th><th>Yêu cầu</th><th>Kết quả</th></tr></thead>
              <tbody>{pay.payments.map((p) => (
                <tr key={p.id}><td>{when(p.created_at)}</td><td>{p.amount_vnd.toLocaleString("vi-VN")} đ</td><td><small>{p.content}</small></td>
                  <td>{p.request_id ? `#${p.request_id}` : "—"}</td><td>{PS[p.status] ?? p.status}{p.note ? ` · ${p.note}` : ""}</td></tr>))}</tbody>
            </table>
          )}
        </div>
      )}
      <p className="ws-hint">Người dùng xin <b>nâng hạn mức</b> (không phải tính năng — tính năng đã mở hết). Duyệt là cấp gói ngay, có thời hạn; ghi chú hiện cho người dùng ở Tài khoản của tôi.</p>
      <div className="ws-row">
        {["pending", "approved", "rejected", "all"].map((s) => (
          <button key={s} className={status === s ? "doc-btn" : "ws-link"} onClick={() => setStatus(s)}>{ST[s] ?? "Tất cả"}</button>
        ))}
        <label className="ws-hint">Thời hạn khi duyệt: <select value={months} onChange={(e) => setMonths(Number(e.target.value))}>
          {[1, 3, 6, 12, 0].map((m) => <option key={m} value={m}>{m ? `${m} tháng` : "không hạn"}</option>)}</select></label>
      </div>
      {err && <p className="ws-err">⚠️ {err}</p>}
      {list && list.length === 0 && <p className="ws-hint">Không có yêu cầu nào.</p>}
      {list?.map((r) => (
        <div key={r.id} className="adm-note">
          <b>{r.email}</b> xin <b>{r.plan_wanted_name}</b> · {when(r.created_at)} · {ST[r.status]}
          {r.reason && <p style={{ margin: "6px 0" }}>“{r.reason}”</p>}
          {r.status === "pending" ? (
            <div className="ws-row">
              <input placeholder="Ghi chú cho người dùng (tuỳ chọn)" value={note[r.id] ?? ""} onChange={(e) => setNote({ ...note, [r.id]: e.target.value })} />
              <button className="doc-btn" onClick={() => decide(r, true)}>Duyệt & cấp</button>
              <button className="ws-link" onClick={() => decide(r, false)}>Từ chối</button>
            </div>
          ) : r.admin_note ? <p className="ws-hint">Ghi chú: {r.admin_note}</p> : null}
        </div>
      ))}
    </div>
  );
}

function LabelTab() {
  const [sum, setSum] = useState<LabelSummary | null>(null);
  const [list, setList] = useState<{ email: string }[]>([]);
  const [email, setEmail] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const load = () => {
    adminLabelSummary().then(setSum).catch((e) => setErr(e.message));
    adminLabelers().then((r) => setList(r.labelers)).catch((e) => setErr(e.message));
  };
  useEffect(load, []);
  const add = async () => {
    if (!email.trim()) return;
    try { await adminAddLabeler(email.trim()); setEmail(""); load(); } catch (e) { setErr((e as Error).message); }
  };
  const T = { T_lost: "Rừng 2020 + mất", T_forest: "Rừng 2020, không mất", T_clean: "Không phải rừng 2020" } as const;
  return (
    <div>
      <p className="ws-hint">Kiểm định EUDR v3: hai người ĐỘC LẬP gán nhãn ảnh 2020 ở <Link href="/gan-nhan">/gan-nhan</Link>. Trang này
        chỉ hiện tiến độ và độ đồng thuận — KHÔNG có kết quả máy; chỉ chấm một lần sau khi khoá nhãn.</p>
      {err && <p className="ws-err">⚠️ {err}</p>}
      <h4>Người được gán nhãn (ngoài quản trị viên)</h4>
      <ul>{list.map((l) => <li key={l.email}>{l.email}{" "}
        <button className="ws-link" onClick={() => adminRemoveLabeler(l.email).then(load).catch((e) => setErr(e.message))}>gỡ</button></li>)}
        {list.length === 0 && <li className="ws-hint">Chưa có ai — thêm email người gán thứ hai.</li>}</ul>
      <div className="ws-row">
        <input type="email" placeholder="email@vd.vn" value={email} onChange={(e) => setEmail(e.target.value)} />
        <button className="doc-btn" onClick={add}>Cấp quyền gán nhãn</button>
      </div>
      {sum && (
        <>
          <h4 style={{ marginTop: 18 }}>Tiến độ ({sum.n_cells} ô)</h4>
          <ul>{sum.per_labeler.map((p) => <li key={p.email}>{p.email}: {p.labeled} ô</li>)}</ul>
          <p>Ô có ≥2 nhãn: <b>{sum.cells_2plus}</b> · đồng thuận rừng/không rừng: <b>{sum.agree_forest ?? "—"}</b> ·
            Cohen&apos;s kappa: <b>{sum.kappa_forest ?? "—"}</b></p>
          <table className="ws-table">
            <thead><tr><th>Nhóm sự thật</th><th>Số ô</th><th>Cần tối thiểu</th></tr></thead>
            <tbody>{(Object.keys(T) as (keyof typeof T)[]).map((k) => (
              <tr key={k}><td>{T[k]}</td><td>{sum.truth_counts[k]}</td><td>{sum.min_n_per_set}</td></tr>))}</tbody>
          </table>
          <p className="ws-hint">Bị loại: {Object.entries(sum.excluded).map(([k, n]) => `${k} ${n}`).join(" · ")}</p>
          <button className="doc-btn" onClick={() => adminLabelExport().catch((e) => setErr(e.message))}>Xuất nhãn (JSON) để chấm</button>
        </>
      )}
    </div>
  );
}

/** Tập vàng cổng GĐ3: dán tin đăng THẬT bạn tự thu thập + tích loại câu khẳng định CÓ trong tin. Không có ô nào
 *  được tích sẵn — gợi ý của máy sẽ làm lệch nhãn (bộ tách câu là thứ đang được chấm). */
function GoldTab() {
  const [v, setV] = useState<ListingGoldView | null>(null);
  const [text, setText] = useState("");
  const [note, setNote] = useState("");
  const [claims, setClaims] = useState<string[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const load = () => { adminListingGold().then(setV).catch((e) => setErr(e.message)); };
  useEffect(load, []);
  const add = async () => {
    setErr(null);
    try { await adminListingGoldAdd(text, claims, note); setText(""); setNote(""); setClaims([]); load(); }
    catch (e) { setErr((e as Error).message); }
  };
  const name = (id: string) => v?.claim_types.find((c) => c.id === id)?.vi ?? id;
  return (
    <div>
      <p className="ws-hint">Cổng GĐ3 đo bộ tách câu khẳng định trên ≥ 20 tin đăng THẬT do bạn tự thu thập (tin bạn bè gửi, nhóm Zalo, tờ rơi —
        KHÔNG cào trang bất động sản). Dán nguyên văn, rồi tích những loại câu tin đó KHẲNG ĐỊNH. Số điện thoại, email, đường dẫn tự bị xoá trước khi lưu.
        Không ô nào tích sẵn: máy gợi ý sẽ làm lệch nhãn, vì bộ tách câu chính là thứ đang được chấm.</p>
      {err && <p className="ws-err">⚠️ {err}</p>}
      <textarea rows={4} style={{ width: "100%" }} placeholder="Dán nội dung tin đăng…" value={text} onChange={(e) => setText(e.target.value)} />
      <div className="ws-row" style={{ flexWrap: "wrap", gap: 10 }}>
        {v?.claim_types.map((c) => (
          <label key={c.id} style={{ display: "inline-flex", gap: 4, alignItems: "center" }}>
            <input type="checkbox" checked={claims.includes(c.id)}
                   onChange={(e) => setClaims((cur) => e.target.checked ? [...cur, c.id] : cur.filter((x) => x !== c.id))} /> {c.vi}
          </label>
        ))}
      </div>
      <div className="ws-row">
        <input placeholder="Nguồn (vd: tin bạn gửi, nhóm Zalo xã) — không dán đường dẫn" value={note} onChange={(e) => setNote(e.target.value)} />
        <button className="doc-btn" disabled={text.trim().length < 10} onClick={add}>Thêm tin</button>
      </div>
      {v && (
        <>
          <h4 style={{ marginTop: 16 }}>Đã có {v.score.n}/20 tin {v.score.enough ? "— đủ để chấm cổng" : ""}</h4>
          {v.score.per_type.length > 0 && (
            <table className="ws-table">
              <thead><tr><th>Loại câu</th><th>Chính xác</th><th>Độ phủ</th><th>F1</th><th>Đúng / thừa / sót</th></tr></thead>
              <tbody>{v.score.per_type.map((r) => (
                <tr key={r.type}><td>{name(r.type)}</td><td>{r.precision}</td><td>{r.recall}</td><td>{r.f1}</td><td>{r.tp} / {r.fp} / {r.fn}</td></tr>))}</tbody>
            </table>
          )}
          {v.score.macro_f1 != null && <p>F1 trung bình: <b>{v.score.macro_f1}</b>{v.score.enough ? "" : " (chưa đủ 20 tin — chỉ để xem)"}</p>}
          <ul>{v.items.slice().reverse().map((g) => (
            <li key={g.id} style={{ marginBottom: 6 }}><small>{g.text.slice(0, 160)}{g.text.length > 160 ? "…" : ""}</small><br />
              <b>{g.claims.length ? g.claims.map(name).join(", ") : "không câu khẳng định nào"}</b>{g.source_note ? ` · ${g.source_note}` : ""}{" "}
              <button className="ws-link" onClick={() => adminListingGoldDelete(g.id).then(load).catch((e) => setErr(e.message))}>xoá</button></li>))}</ul>
        </>
      )}
    </div>
  );
}

/** Sự thật mặt đất người dùng gửi: xác nhận từng đợt nước + ca mùa lũ v4. Chỉ đọc — đưa vào cổng nào cũng phải đăng ký trước. */
function TruthTab() {
  const [w, setW] = useState<AdminWaterConfirms | null>(null);
  const [s, setS] = useState<AdminSeasonCases | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    adminWaterConfirms().then(setW).catch((e) => setErr(e.message));
    adminSeasonCases().then(setS).catch((e) => setErr(e.message));
  }, []);
  return (
    <div>
      <p className="ws-hint">Người dùng trả lời &quot;ruộng có ngập đợt này không&quot; ngay trên lịch sử nước của thửa. Toạ độ làm tròn 0,01°;
        không hiện ai trả lời gì. Dùng làm ca kiểm cho bộ phát hiện đợt nước và lớp mùa lũ v4 — chỉ sau khi đăng ký trước.</p>
      {err && <p className="ws-err">⚠️ {err}</p>}
      {w && (
        <>
          <h4>Xác nhận từng đợt nước</h4>
          <p><b>{w.n_answers}</b> câu trả lời · <b>{w.n_events}</b> đợt · có ngập <b>{w.totals.yes}</b> · không <b>{w.totals.no}</b> · không rõ <b>{w.totals.unsure}</b></p>
          <p>Kiểm thực địa (giao thức đăng ký trước):{" "}
            {w.field_check.result
              ? <b>đã chấm {w.field_check.result.scored_at} — P = {w.field_check.result.precision} (95%: {w.field_check.result.wilson95.join("–")}) → {w.field_check.result.outcome}</b>
              : <>đợt có nhãn <b>{w.field_check.have.labelled_events}/{w.field_check.need.labelled_events}</b> · người <b>{w.field_check.have.distinct_users}/{w.field_check.need.distinct_users}</b> · ô 1° <b>{w.field_check.have.distinct_1deg_cells}/{w.field_check.need.distinct_1deg_cells}</b>
                  {w.field_check.ready ? " — ĐỦ cỡ mẫu: chạy ops/water_field_gate.py (một lần) rồi commit kết quả." : " — chưa đủ cỡ mẫu."}</>}</p>
          {w.events.length > 0 && (
            <table className="ws-table">
              <thead><tr><th>Đợt</th><th>Toạ độ ~1 km</th><th>Mùa lũ v1</th><th>Có</th><th>Không</th><th>Không rõ</th></tr></thead>
              <tbody>{w.events.slice(0, 200).map((e) => (
                <tr key={`${e.lat},${e.lon},${e.event_start}`}><td>{e.event_start}</td><td>{e.lat}, {e.lon}</td>
                  <td>{e.v1_label === "in" ? "trong mùa" : e.v1_label === "out" ? "ngoài mùa" : "—"}</td>
                  <td>{e.yes}</td><td>{e.no}</td><td>{e.unsure}</td></tr>))}</tbody>
            </table>
          )}
          <p className="ws-hint">{w.note}</p>
        </>
      )}
      {s && (
        <>
          <h4 style={{ marginTop: 18 }}>Ca mùa lũ v4 (lũ ngoài mùa có người xác nhận): {s.n}</h4>
          {s.cases.length > 0 && (
            <table className="ws-table">
              <thead><tr><th>Đợt radar</th><th>Ngày báo</th><th>Toạ độ ~1 km</th><th>Mùa lũ v1</th><th>Nguồn</th><th>Trạng thái</th></tr></thead>
              <tbody>{s.cases.slice(0, 200).map((c) => (
                <tr key={c.id}><td>{c.event[0]}{c.event[1] !== c.event[0] ? ` → ${c.event[1]}` : ""}</td><td>{c.observed_on}</td>
                  <td>{c.lat}, {c.lon}</td><td>tháng {c.season_months}</td><td>{c.source}</td><td>{c.status}</td></tr>))}</tbody>
            </table>
          )}
          <p className="ws-hint">{s.note}</p>
        </>
      )}
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
  const [tab, setTab] = useState<Tab>("users");

  useEffect(() => {
    if (!getToken()) { setUser(null); return; }
    fetchMe().then(setUser).catch(() => setUser(null));
  }, []);

  const isAdmin = user?.role === "admin";
  const isCoop = user?.role === "coop" || isAdmin;
  useEffect(() => { if (user && !isAdmin && tab === "users") setTab(isCoop ? "coop" : "health"); }, [user, isAdmin, isCoop, tab]);

  const TABS: { id: Tab; label: string; show: boolean }[] = [
    { id: "users", label: "Người dùng", show: isAdmin },
    { id: "upgrades", label: "Yêu cầu nâng cấp", show: isAdmin },
    { id: "health", label: "Sức khoẻ", show: true },
    { id: "funnel", label: "Phễu người dùng", show: isAdmin },
    { id: "pilot", label: "Góp ý thí điểm", show: isAdmin },
    { id: "label", label: "Gán nhãn v3", show: isAdmin },
    { id: "truth", label: "Xác nhận thực địa", show: isAdmin },
    { id: "gold", label: "Tin đăng GĐ3", show: isAdmin },
    { id: "backup", label: "Sao lưu", show: isAdmin },
    { id: "drift", label: "Trôi mô hình", show: isAdmin },
    { id: "coop", label: "Hợp tác xã", show: isCoop },
  ];

  return (
    <AppShell user={user ?? null} onAuth={(u) => setUser(u)}>
      <main className="doc-body" style={{ maxWidth: 900 }}>
        <h1>{t("Quản trị", "Admin")}</h1>

        {user === undefined && <p className="ws-hint">Đang tải…</p>}
        {user === null && (
          <div className="adm-note">
            <b>{t("Chưa đăng nhập.", "Not signed in.")}</b>{" "}
            {t("Bấm nút \"Đăng nhập\" ở góc trên bên phải, dùng email quản trị (email nằm trong TERRATWIN_ADMIN_EMAILS trên máy chủ). Đăng nhập xong trang này tự hiện các mục quản trị.",
               "Press \"Log in\" at the top right with the admin email (listed in TERRATWIN_ADMIN_EMAILS on the server). The admin sections appear once you are signed in.")}
          </div>
        )}
        {user && (
          <p className="adm-who">{t("Đang đăng nhập", "Signed in as")}: <b>{user.email}</b> · {t("vai trò", "role")}: <b>{user.role ?? "user"}</b>
            {user.totp_enabled ? " · 🔐 " + t("hai lớp: bật", "2FA: on") : " · " + t("hai lớp: chưa bật", "2FA: off")}</p>
        )}
        {user && !isAdmin && !isCoop && (
          <div className="adm-note adm-warn">
            <b>{t("Tài khoản này chưa có quyền quản trị.", "This account has no admin rights yet.")}</b>
            <ul>
              <li>{t("Quyền quản trị được cấp LÚC ĐĂNG NHẬP cho email nằm trong biến TERRATWIN_ADMIN_EMAILS trên Render (terratwin-api → Environment).",
                     "Admin rights are granted AT LOGIN to emails listed in TERRATWIN_ADMIN_EMAILS on Render (terratwin-api → Environment).")}</li>
              <li>{t("Nếu vừa thêm email vào biến đó: Đăng xuất (góc trên phải) rồi đăng nhập lại.", "If the email was just added: log out (top right) and log in again.")}</li>
              <li>{t("Kiểm email đúng chính tả, không thừa dấu cách.", "Check the email spelling, no stray spaces.")}</li>
            </ul>
          </div>
        )}
        {user && isAdmin && (
          <details className="adm-help" open={tab === "health"}>
            <summary>{t("Trang quản trị có gì?", "What is on this page?")}</summary>
            <ul>
              <li><b>Người dùng</b> — {t("tìm tài khoản, xem thửa/hồ sơ/hoạt động, cấp gói hạn mức có thời hạn, cấp vai trò hợp tác xã.", "find accounts, see plots/dossiers/activity, grant time-limited quota plans and the co-op role.")}</li>
              <li><b>Yêu cầu nâng cấp</b> — {t("người dùng xin thêm hạn mức → duyệt & cấp hoặc từ chối kèm ghi chú.", "users ask for more quota → approve & grant or reject with a note.")}</li>
              <li><b>Sức khoẻ</b> — {t("máy chủ, CSDL Neon, khoá ký, hạn mức nguồn dữ liệu, gói Open-Meteo.", "server, Neon DB, signing key, data-source quotas, Open-Meteo plan.")}</li>
              <li><b>Phễu người dùng</b> — {t("mở app → quét → lưu thửa…; phễu bán hàng mở → chọn thửa → hồ sơ → trả tiền; tỉ lệ quay lại 7 ngày.", "open → scan → save…; sales funnel open → pick plot → dossier → pay; 7-day return rate.")}</li>
              <li><b>Góp ý thí điểm</b> — {t("phiếu góp ý từ hợp tác xã (trực tuyến + phiếu giấy nhập lại), tải CSV.", "pilot feedback from co-ops (online + paper), CSV download.")}</li>
              <li><b>Gán nhãn v3</b> — {t("thêm người gán nhãn (email), xem tiến độ, độ đồng thuận, xuất nhãn để chấm kiểm định v3.", "add labelers, progress, agreement, export labels to score validation v3.")}</li>
              <li><b>Xác nhận thực địa</b> — {t("người dùng xác nhận từng đợt nước radar có ngập thật không; ca lũ ngoài mùa cho lớp mùa lũ v4.", "users confirm whether each radar water event really flooded; out-of-season flood cases for flood-season v4.")}</li>
              <li><b>Sao lưu</b> — {t("lần sao lưu CSDL mã hoá gần nhất.", "latest encrypted DB backup.")}</li>
              <li><b>Trôi mô hình</b> — {t("dữ liệu đầu vào có lệch khỏi lúc huấn luyện không.", "whether inputs drift from training data.")}</li>
              <li><b>Hợp tác xã</b> — {t("thửa của thành viên đã đồng ý chia sẻ.", "members' plots shared with consent.")}</li>
            </ul>
            <p className="ws-hint">{t("Bảo mật: bật xác thực hai lớp ở Thửa đất → Khu làm việc → Xác thực hai lớp, rồi đặt TERRATWIN_ADMIN_REQUIRE_2FA=1 trên Render.",
                                      "Security: turn on 2FA in Land → Workspace → Two-factor, then set TERRATWIN_ADMIN_REQUIRE_2FA=1 on Render.")}</p>
          </details>
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
              {tab === "users" && isAdmin && <UsersTab />}
              {tab === "upgrades" && isAdmin && <UpgradesTab />}
              {tab === "health" && <HealthTab />}
              {tab === "funnel" && isAdmin && <FunnelTab />}
              {tab === "pilot" && isAdmin && <PilotTab />}
              {tab === "label" && isAdmin && <LabelTab />}
              {tab === "truth" && isAdmin && <TruthTab />}
              {tab === "gold" && isAdmin && <GoldTab />}
              {tab === "backup" && isAdmin && <BackupTab />}
              {tab === "drift" && isAdmin && <DriftTab />}
              {tab === "coop" && isCoop && <CoopTab user={user} />}
            </div>
          </>
        )}
      </main>
    </AppShell>
  );
}
