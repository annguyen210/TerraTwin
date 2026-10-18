"use client";

/**
 * TÀI KHOẢN CỦA TÔI — bấm tên tài khoản ở góc trên là tới đây. Một chỗ thấy hết: mình là ai, vai trò gì (nói bằng
 * lời, có thể làm gì), tài khoản đang có những gì (thửa, hồ sơ, ảnh, thiết bị, khoá API…), lịch sử hoạt động
 * (đăng nhập, đổi mật khẩu, hai lớp…), bảo mật, và quyền với dữ liệu của mình (xuất, xoá).
 */
import { useEffect, useState } from "react";
import Link from "next/link";
import AppShell from "@/components/AppShell";
import TwoFactor from "@/components/TwoFactor";
import {
  changePassword, deleteMyAccount, exportMyData, getAccountAudit, getAccountSummary, getMyPlan, getToken, requestUpgrade, setToken,
  type AccountSummary, type AuditEntry, type AuthUser, type MyPlan,
} from "@/lib/api";
import { useLang } from "@/lib/i18n";

const COUNT_LABEL: Record<string, [string, string, string?]> = {
  plots: ["Thửa đã lưu", "Saved plots", "/"],
  dossiers: ["Hồ sơ đã phát hành", "Dossiers issued"],
  alerts: ["Cảnh báo đã nhận", "Alerts received", "/hom-nay"],
  observations: ["Quan sát / câu trả lời", "Observations / answers"],
  field_photos: ["Ảnh thực địa", "Field photos"],
  devices: ["Thiết bị IoT", "IoT devices", "/thiet-bi"],
  eudr_sets: ["Lô thửa EUDR", "EUDR plot sets", "/eudr"],
  lots: ["Lô hàng", "Lots", "/lo"],
  api_keys: ["Khoá API", "API keys"],
  channels: ["Kênh cảnh báo", "Alert channels"],
  twins: ["Twin đã lưu", "Saved twins"],
  batch_runs: ["Thẩm định hàng loạt", "Batch appraisals", "/batch"],
  push_subs: ["Thiết bị nhận thông báo", "Push devices"],
  pilot_feedback: ["Góp ý thí điểm", "Pilot feedback"],
  labels_v3: ["Nhãn kiểm định v3", "v3 validation labels", "/gan-nhan"],
};

function when(iso: string) {
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z");
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

export default function MyAccountPage() {
  const { t, lang } = useLang();
  const [user, setUser] = useState<AuthUser | null | undefined>(undefined);
  const [s, setS] = useState<AccountSummary | null>(null);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [pw, setPw] = useState({ old: "", next: "" });
  const [pwMsg, setPwMsg] = useState<string | null>(null);
  const [confirm, setConfirm] = useState("");
  const [plan, setPlan] = useState<MyPlan | null>(null);
  // SePay báo tiền về → gói tự kích hoạt: còn yêu cầu chờ có QR tự xác nhận thì hỏi lại mỗi 15 giây (tối đa 20 phút)
  const waitingPay = !!plan?.requests.some((r) => r.status === "pending" && r.payment?.available && r.payment?.auto_confirm);
  useEffect(() => {
    if (!waitingPay) return;
    let n = 0;
    const id = setInterval(() => { if (++n > 80) return clearInterval(id); getMyPlan().then(setPlan).catch(() => {}); }, 15000);
    return () => clearInterval(id);
  }, [waitingPay]);
  const [want, setWant] = useState<"pro" | "enterprise">("pro");
  const [reason, setReason] = useState("");
  const [reqMsg, setReqMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) { setUser(null); return; }
    getAccountSummary().then((x) => { setS(x); setUser(x.account); }).catch((e) => { setErr(e.message); setUser(null); });
    getAccountAudit(100).then((r) => setAudit(r.entries)).catch(() => {});
    getMyPlan().then(setPlan).catch(() => {});
  }, [lang]);

  async function download() {
    const data = await exportMyData();
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
    const a = document.createElement("a"); a.href = url; a.download = "terratwin-du-lieu-cua-toi.json"; a.click(); URL.revokeObjectURL(url);
  }
  async function savePw() {
    setPwMsg(null);
    try { setPwMsg((await changePassword(pw.old, pw.next)).message || t("Đã đổi mật khẩu.", "Password changed.")); setPw({ old: "", next: "" }); }
    catch (e) { setPwMsg((e as Error).message); }
  }
  async function sendUpgrade() {
    setReqMsg(null);
    try { await requestUpgrade(want, reason); setReason(""); setReqMsg(t("Đã gửi — quản trị sẽ xem và trả lời ở đây.", "Sent — an admin will review and reply here.")); setPlan(await getMyPlan()); }
    catch (e) { setReqMsg((e as Error).message); }
  }
  async function removeAccount() {
    await deleteMyAccount(); setToken(null); window.location.href = "/";
  }

  return (
    <AppShell user={user ?? null} onAuth={(u) => { setUser(u); if (u) window.location.reload(); }}>
      <main className="tk-wrap">
        <h1>{t("Tài khoản của tôi", "My account")}</h1>
        {user === undefined && <p className="doc-note">{t("Đang tải…", "Loading…")}</p>}
        {user === null && <p className="adm-note">{err ?? t("Chưa đăng nhập — bấm \"Đăng nhập\" ở góc trên bên phải.", "Not signed in — press \"Log in\" at the top right.")}</p>}

        {s && (
          <>
            <div className="tk-grid2">
              <section className="tk-card">
                <h2>{t("Thông tin", "Details")}</h2>
                <dl className="tk-dl">
                  <dt>{t("Tên", "Name")}</dt><dd>{s.account.name || "—"}</dd>
                  <dt>Email</dt><dd>{s.account.email} · {s.account.email_verified ? t("đã xác thực", "verified") : t("chưa xác thực", "not verified")}</dd>
                  <dt>{t("Tạo lúc", "Created")}</dt><dd>{s.account.created_at ? when(s.account.created_at) : "—"}</dd>
                  <dt>{t("Xác thực hai lớp", "Two-factor")}</dt><dd>{s.account.totp_enabled ? t("đang bật", "on") : t("chưa bật", "off")}</dd>
                  <dt>{t("Bản tin sáng", "Morning brief")}</dt><dd>{s.account.morning_brief ? t("đang bật", "on") : t("tắt", "off")}</dd>
                  <dt>{t("Hợp tác xã", "Co-op")}</dt><dd>{s.account.coop_code || "—"}{s.account.coop_code ? (s.account.share_with_coop ? t(" · đang chia sẻ thửa", " · sharing plots") : t(" · chưa chia sẻ", " · not sharing")) : ""}</dd>
                </dl>
              </section>
              <section className="tk-card">
                <h2>{t("Vai trò", "Role")}: {s.role.name}</h2>
                <p className="tk-role">{s.role.can}</p>
                <ul className="tk-list">
                  <li><span><b>{t("Người dùng", "User")}</b> — {t("dùng cho thửa của mình", "for your own plots")}</span></li>
                  <li><span><b>{t("Hợp tác xã", "Co-op")}</b> — {t("thêm: xem thửa thành viên đã đồng ý chia sẻ", "plus: see members' shared plots")}</span></li>
                  <li><span><b>{t("Quản trị (admin)", "Admin")}</b> — {t("thêm: vận hành cả hệ thống", "plus: operate the whole system")}</span>
                    {s.role.id === "admin" && <Link href="/admin">{t("Mở trang quản trị →", "Open admin →")}</Link>}</li>
                </ul>
                <p className="ws-hint">{t("\"Quản trị\" và \"admin\" là một. Quyền quản trị cấp theo email trong cấu hình máy chủ, lúc đăng nhập.",
                                         "\"Admin\" is the operator role, granted by email in the server config at login.")}</p>
              </section>
            </div>

            {plan && (
              <section className="tk-card">
                <h2>{t("Gói & hạn mức", "Plan & quotas")}: {plan.name}{plan.until ? ` · ${t("đến", "until")} ${when(plan.until)}` : ""}</h2>
                <p className="tk-role">✓ {plan.principle}</p>
                <dl className="tk-dl">
                  <dt>{t("Hồ sơ ký số / ngày", "Signed dossiers / day")}</dt><dd>{plan.limits.dossier_per_day.toLocaleString("vi-VN")}</dd>
                  <dt>{t("Lượt quét nặng / giờ", "Heavy scans / hour")}</dt><dd>{plan.limits.screen_per_hour.toLocaleString("vi-VN")}</dd>
                  <dt>{t("Lượt API / tháng", "API calls / month")}</dt><dd>{plan.limits.api_per_month.toLocaleString("vi-VN")}</dd>
                </dl>
                {plan.requests.length > 0 && (
                  <ul className="tk-list">
                    {plan.requests.map((r) => (
                      <li key={r.id}><span>{t("Yêu cầu", "Request")} {r.plan_wanted_name}: <b>{{ pending: t("đang chờ", "pending"), approved: t("đã duyệt", "approved"), rejected: t("từ chối", "rejected") }[r.status]}</b>
                        {r.admin_note ? ` — ${r.admin_note}` : ""}</span><small>{when(r.created_at)}</small>
                        {r.status === "pending" && r.payment && r.payment.amount_vnd > 0 && (
                          <div className="tk-pay">
                            {r.payment.available && r.payment.qr_svg ? (
                              <>
                                {/* eslint-disable-next-line @next/next/no-img-element */}
                                <img src={r.payment.qr_svg} alt={t("Mã VietQR chuyển khoản", "VietQR bank-transfer code")} width={180} height={180} />
                                <div>
                                  <p><b>{r.payment.amount_vnd.toLocaleString("vi-VN")} đ</b> · {t("nội dung", "memo")}: <code>{r.payment.memo}</code></p>
                                  <p className="ws-mini">{t(`Tài khoản …${r.payment.account_tail}`, `Account …${r.payment.account_tail}`)}{r.payment.account_name ? ` · ${r.payment.account_name}` : ""}</p>
                                  <p className="ws-mini">{r.payment.auto_confirm
                                    ? t("Quét bằng app ngân hàng bất kỳ (VietQR, miễn phí). Giữ ĐÚNG nội dung — gói tự kích hoạt khoảng 1 phút sau khi tiền vào; trang tự cập nhật.",
                                        "Scan with any banking app (VietQR, free). Keep the memo EXACTLY — the plan activates about a minute after the money arrives; this page refreshes itself.")
                                    : t("Quét bằng app ngân hàng bất kỳ (VietQR, miễn phí). Giữ ĐÚNG nội dung — quản trị đối chiếu rồi kích hoạt gói.",
                                        "Scan with any banking app (VietQR, free). Keep the memo EXACTLY — an admin matches it and activates the plan.")}</p>
                                </div>
                              </>
                            ) : (
                              <p className="ws-mini">{t(`Phí gói: ${r.payment.amount_vnd.toLocaleString("vi-VN")} đ. `, `Plan fee: ${r.payment.amount_vnd.toLocaleString("vi-VN")} VND. `)}{r.payment.note}</p>
                            )}
                          </div>
                        )}</li>
                    ))}
                  </ul>
                )}
                {!plan.requests.some((r) => r.status === "pending") && (
                  <div className="ws-row">
                    <select value={want} onChange={(e) => setWant(e.target.value as "pro" | "enterprise")} aria-label={t("Gói muốn xin", "Plan wanted")}>
                      {plan.catalogue.filter((c) => c.id !== "free").map((c) => <option key={c.id} value={c.id}>{c.name} — {t("hạn mức", "quota")} ×{c.mult}</option>)}
                    </select>
                    <input placeholder={t("Vì sao cần thêm hạn mức? (vd HTX 40 hộ)", "Why more quota? (e.g. co-op with 40 farms)")} value={reason} maxLength={1000} onChange={(e) => setReason(e.target.value)} />
                    <button className="bat-btn ghost" onClick={sendUpgrade}>{t("Xin nâng hạn mức", "Request more quota")}</button>
                  </div>
                )}
                {reqMsg && <p className="ws-hint">{reqMsg}</p>}
              </section>
            )}

            <section className="tk-card">
              <h2>{t("Dữ liệu của tôi", "My data")}</h2>
              <div className="tk-counts">
                {Object.entries(s.counts).filter(([k, n]) => n > 0 || ["plots", "dossiers", "alerts", "observations"].includes(k)).map(([k, n]) => {
                  const lab = COUNT_LABEL[k] ?? [k, k];
                  const inner = <><b>{n}</b><span>{t(lab[0], lab[1])}</span></>;
                  return lab[2] ? <Link key={k} href={lab[2]} className="tk-count">{inner}</Link> : <div key={k} className="tk-count">{inner}</div>;
                })}
                {Object.values(s.counts).every((n) => n === 0) && <p className="ws-hint">{t("Chưa có gì — chọn một thửa trên bản đồ và bấm Lưu.", "Nothing yet — pick a plot on the map and save it.")}</p>}
              </div>
              <div className="tk-grid2">
                <div>
                  <h3 className="ws-hint">{t("Hồ sơ gần đây", "Recent dossiers")}</h3>
                  <ul className="tk-list">
                    {s.recent_dossiers.length === 0 && <li><span>—</span></li>}
                    {s.recent_dossiers.map((d) => (
                      <li key={d.id}><Link prefetch={false} href={`/h/${d.id}`}>{d.kind === "eudr_plot" ? "EUDR" : d.kind === "lot_certificate" ? t("Chứng thư lô", "Lot") : t("Hồ sơ đất", "Land")} · {d.where} · <code>{d.id}</code></Link><small>{when(d.issued_at)}</small></li>
                    ))}
                  </ul>
                </div>
                <div>
                  <h3 className="ws-hint">{t("Thửa đã lưu gần đây", "Recently saved plots")}</h3>
                  <ul className="tk-list">
                    {s.recent_plots.length === 0 && <li><span>—</span></li>}
                    {s.recent_plots.map((p) => (
                      <li key={p.id}><Link prefetch={false} href={`/plot/${p.lat},${p.lon}`}>{p.name}</Link><small>{when(p.created_at)}</small></li>
                    ))}
                  </ul>
                </div>
              </div>
            </section>

            <section className="tk-card">
              <h2>{t("Lịch sử hoạt động", "Activity history")}</h2>
              <p className="ws-hint">{t("Đăng nhập, đổi mật khẩu, khoá API, hai lớp, đổi lựa chọn đồng ý… — thấy lạ là đổi mật khẩu ngay.",
                                       "Logins, password changes, API keys, 2FA, consent changes… — anything odd, change your password.")}</p>
              <ul className="tk-list">
                {audit.length === 0 && <li><span>—</span></li>}
                {audit.map((a, i) => <li key={i}><span>{a.label}{a.detail ? ` · ${a.detail}` : ""}</span><small>{when(a.at)}</small></li>)}
              </ul>
            </section>

            <div className="tk-grid2">
              <section className="tk-card">
                <h2>{t("Bảo mật", "Security")}</h2>
                <TwoFactor user={s.account} />
                <h3 className="ws-hint">{t("Đổi mật khẩu", "Change password")}</h3>
                <label className="pk-field">{t("Mật khẩu hiện tại", "Current password")}
                  <input type="password" autoComplete="current-password" value={pw.old} onChange={(e) => setPw({ ...pw, old: e.target.value })} /></label>
                <label className="pk-field">{t("Mật khẩu mới (≥8 ký tự, có chữ và số)", "New password (≥8 chars, letters + digits)")}
                  <input type="password" autoComplete="new-password" value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} /></label>
                <button className="bat-btn ghost" onClick={savePw} disabled={!pw.old || pw.next.length < 8}>{t("Đổi mật khẩu", "Change password")}</button>
                {pwMsg && <p className="ws-hint">{pwMsg}</p>}
              </section>
              <section className="tk-card tk-danger">
                <h2>{t("Dữ liệu cá nhân (Luật 91/2025/QH15)", "Personal data")}</h2>
                <button className="bat-btn ghost" onClick={download}>{t("Tải toàn bộ dữ liệu của tôi (JSON)", "Download all my data (JSON)")}</button>
                <p className="ws-hint">{t("Xoá tài khoản xoá vĩnh viễn thửa, cảnh báo, thiết bị, khoá API… Hồ sơ đã phát hành ở lại sổ công khai nhưng gỡ tên bạn.",
                                         "Deleting removes plots, alerts, devices, API keys… permanently. Issued dossiers stay in the public log, unlinked from you.")}</p>
                <label className="pk-field">{t("Gõ đúng email của bạn để xác nhận xoá", "Type your email to confirm deletion")}
                  <input value={confirm} onChange={(e) => setConfirm(e.target.value)} /></label>
                <button className="bat-btn ghost tk-del" onClick={removeAccount} disabled={confirm.trim().toLowerCase() !== s.account.email.toLowerCase()}>
                  {t("Xoá tài khoản vĩnh viễn", "Delete account permanently")}</button>
              </section>
            </div>
          </>
        )}
      </main>
    </AppShell>
  );
}
