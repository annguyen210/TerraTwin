"use client";

/**
 * Khu làm việc cấp tài khoản — bốn luồng trước đây chỉ có API mà không có UI:
 *
 *   C01  Twin đã lưu        — ảnh chụp đầy đủ của thửa tại một thời điểm
 *   C11  Bring-Your-Own-Data— HTX có 200 thửa không phải bấm 200 lần
 *   U01  Kênh gửi cảnh báo  — đưa cảnh báo RA KHỎI phần mềm
 *   C12  Khoá Twin API      — biến TerraTwin thành hạ tầng cho bên thứ ba
 *
 * Đặt trong lớp phủ toàn màn hình chứ không nhét vào cột phải 360 px: đây là
 * việc làm một lần rồi thôi (cấu hình, tải lên, tạo khoá), không phải thứ nhìn
 * song song với bản đồ.
 */

import { useCallback, useEffect, useState } from "react";
import {
  buildTwin, createChannel, createKey, deleteChannel, deleteDataset, getPlans,
  deleteTwin, listChannels, listDatasets, listKeys, listTwins, revokeKey,
  scoreDataset, testChannel, uploadDataset, getChannelStatus,
  exportMyData, deleteMyAccount, getAccountAudit, setToken, updateConsent, updateCoop,
  type ApiKeyRow, type AuditEntry, type AuthUser, type ChannelRow, type ChannelStatus, type DatasetRow,
  type TwinSummary,
  type Plan,
} from "@/lib/api";
import Learning from "@/components/Learning";
import PortfolioOverview from "@/components/PortfolioOverview";
import Roadmap from "@/components/Roadmap";
import { useLang } from "@/lib/i18n";

type Tab = "portfolio" | "twins" | "data" | "alerts" | "api" | "learn" | "status";

const TABS: { id: Tab; flow: string }[] = [
  { id: "portfolio", flow: "C08" },
  { id: "twins", flow: "C01" },
  { id: "data", flow: "C11" },
  { id: "alerts", flow: "U01" },
  { id: "api", flow: "C12" },
  { id: "learn", flow: "S05·S09·U04" },
  { id: "status", flow: "" },
];

const TAB_LABELS: Record<Tab, [string, string]> = {
  portfolio: ["Toàn cảnh danh mục", "Portfolio overview"],
  twins: ["Twin đã lưu", "Saved twins"],
  data: ["Dữ liệu của tôi", "My data"],
  alerts: ["Kênh cảnh báo", "Alert channels"],
  api: ["Khoá API", "API keys"],
  learn: ["Vòng học", "Learning loop"],
  status: ["26 luồng", "26 flows"],
};

function when(iso: string | null, lang: "vi" | "en" = "vi"): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(lang === "en" ? "en-US" : "vi-VN", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

/* ------------------------------------------------------------------ C01 */

function TwinsPanel({
  user, coord, area,
}: {
  user: AuthUser | null;
  coord: { lat: number; lon: number } | null;
  area?: number;
}) {
  const { t, lang } = useLang();
  const [rows, setRows] = useState<TwinSummary[]>([]);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!user) return;
    try {
      setRows(await listTwins());
    } catch (e: any) {
      setErr(e.message);
    }
  }, [user]);

  useEffect(() => { load(); }, [load]);

  async function build() {
    if (!coord) return;
    setBusy(true); setErr(null);
    try {
      await buildTwin(name.trim() || t("Thửa chưa đặt tên", "Unnamed plot"), coord.lat, coord.lon, area);
      setName("");
      await load();
    } catch (e: any) {
      setErr(e.message);
    } finally { setBusy(false); }
  }

  return (
    <>
      <p className="ws-sub">
        {t("Twin là ảnh chụp ĐẦY ĐỦ của thửa tại một thời điểm — địa hình, khí hậu, cả 14 mô-đun và TerraScore — lưu lại để về sau đối chiếu xem mọi thứ đã đổi thế nào. Khác với “thửa đã lưu” ở cột trái: cái kia chỉ nhớ toạ độ.",
           "A Twin is a FULL snapshot of a plot at one point in time — terrain, climate, all 14 modules and TerraScore — saved so you can later compare how things changed. Different from a “saved plot” in the left column, which only remembers the coordinates.")}
      </p>
      {err && <p className="ws-err">⚠️ {err}</p>}

      {coord ? (
        <div className="ws-row">
          <input
            placeholder={t("Tên Twin, vd. Ruộng sau nhà — vụ Đông Xuân", "Twin name, e.g. Back field — Winter-Spring crop")}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <button disabled={busy} onClick={build}>
            {busy ? t("Đang dựng…", "Building…") : t("Dựng Twin tại điểm đang chọn", "Build a Twin at the selected point")}
          </button>
        </div>
      ) : (
        <p className="ws-hint">{t("Bấm một điểm trên bản đồ trước rồi quay lại đây.", "Click a point on the map first, then come back here.")}</p>
      )}

      {rows.length === 0 && <p className="ws-hint">{t("Chưa có Twin nào được lưu.", "No Twins saved yet.")}</p>}
      {rows.map((tw) => (
        <div key={tw.id} className="ws-item">
          <div>
            <b>{tw.name}</b>
            <p>
              {tw.lat.toFixed(4)}, {tw.lon.toFixed(4)}
              {tw.area_ha != null && ` · ${tw.area_ha} ha`}
              {tw.score != null && ` · TerraScore ${tw.score} (${tw.grade})`}
            </p>
            <p className="ws-when">{t("Dựng lúc", "Built at")} {when(tw.built_at, lang)}</p>
          </div>
          <button
            className="ws-del"
            onClick={async () => { await deleteTwin(tw.id); load(); }}
          >
            {t("Xoá", "Delete")}
          </button>
        </div>
      ))}
    </>
  );
}

/* ------------------------------------------------------------------ C11 */

function DataPanel({ user }: { user: AuthUser | null }) {
  const { t, lang } = useLang();
  const [rows, setRows] = useState<DatasetRow[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);

  const load = useCallback(async () => {
    if (!user) return;
    try { setRows(await listDatasets()); } catch (e: any) { setErr(e.message); }
  }, [user]);

  useEffect(() => { load(); }, [load]);

  async function onFile(f: File) {
    setBusy(true); setErr(null); setResult(null);
    try {
      const text = await f.text();
      const kind = f.name.toLowerCase().endsWith(".csv") ? "csv" : "geojson";
      await uploadDataset(f.name, kind, text);
      await load();
    } catch (e: any) {
      setErr(e.message);
    } finally { setBusy(false); }
  }

  return (
    <>
      <p className="ws-sub">
        {t("Tải lên danh sách điểm của bạn (CSV có cột ", "Upload your list of points (CSV with ")}
        <code>lat, lon</code>
        {t(" và tuỳ chọn ", " columns, optionally ")}
        <code>name</code>
        {t(", hoặc GeoJSON) rồi chấm TerraScore hàng loạt. Hợp tác xã 200 thửa không phải bấm 200 lần.",
           ", or GeoJSON) then score TerraScore in bulk. A co-op with 200 plots doesn't have to click 200 times.")}
      </p>
      {err && <p className="ws-err">⚠️ {err}</p>}

      <label className="ws-file">
        <input
          type="file"
          accept=".csv,.geojson,.json"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); }}
        />
        {busy ? t("Đang tải lên…", "Uploading…") : t("Chọn tệp CSV hoặc GeoJSON", "Choose a CSV or GeoJSON file")}
      </label>

      {rows.length === 0 && <p className="ws-hint">{t("Chưa tải lên tệp nào.", "No files uploaded yet.")}</p>}
      {rows.map((d) => (
        <div key={d.id} className="ws-item">
          <div>
            <b>{d.name}</b>
            <p>{d.kind.toUpperCase()} · {d.row_count} {t("điểm hợp lệ", "valid points")}</p>
            <p className="ws-when">{when(d.created_at, lang)}</p>
          </div>
          <div className="ws-btns">
            <button
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                try { setResult(await scoreDataset(d.id)); }
                catch (e: any) { setErr(e.message); }
                finally { setBusy(false); }
              }}
            >
              {t("Chấm điểm", "Score")}
            </button>
            <button
              className="ws-del"
              onClick={async () => { await deleteDataset(d.id); load(); }}
            >
              {t("Xoá", "Delete")}
            </button>
          </div>
        </div>
      ))}

      {result != null && (
        <pre className="ws-json">{JSON.stringify(result, null, 2)}</pre>
      )}
    </>
  );
}

/* ------------------------------------------------------------------ U01 */

function ChannelsPanel({ user }: { user: AuthUser | null }) {
  const { t, lang } = useLang();
  const [rows, setRows] = useState<ChannelRow[]>([]);
  const [kind, setKind] = useState<"webhook" | "email">("email");
  const [target, setTarget] = useState("");
  const [level, setLevel] = useState<"warning" | "danger">("warning");
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [recipe, setRecipe] = useState<string | null>(null);
  const [status, setStatus] = useState<ChannelStatus | null>(null);   // H5

  const load = useCallback(async () => {
    if (!user) return;
    try { setRows(await listChannels()); } catch (e: any) { setErr(e.message); }
  }, [user]);

  useEffect(() => { load(); }, [load]);
  // H5 — trạng thái kênh phía máy chủ (công khai, không cần đăng nhập).
  useEffect(() => {
    let live = true;
    getChannelStatus().then((s) => live && setStatus(s)).catch(() => {});
    return () => { live = false; };
  }, []);

  return (
    <>
      <p className="ws-sub">
        {t("Cảnh báo nằm trong phần mềm thì chỉ hữu ích khi người dùng đang mở phần mềm — mà thiên tai không chờ điều đó. Thêm kênh để cảnh báo tự tìm đến bạn: email, hoặc webhook để nối sang Zalo OA, Telegram, hệ thống nội bộ.",
           "An alert sitting inside the app is only useful while you have the app open — and disasters don't wait for that. Add a channel so alerts find you: email, or a webhook to connect to Zalo OA, Telegram, or an internal system.")}
      </p>

      {/* Công thức nối nhanh. TRUNG THỰC: Zalo/Telegram KHÔNG nhận thẳng JSON của
          TerraTwin — cần một webhook trung gian chuyển tiếp. Nói rõ từng bước
          thay vì hứa "1 chạm cắm là chạy". */}
      <div className="ws-recipes">
        {[
          ["email", "📧 Email", "📧 Email", "email"],
          ["zalo", "📱 Zalo OA", "📱 Zalo OA", "webhook"],
          ["telegram", "✈️ Telegram", "✈️ Telegram", "webhook"],
          ["webhook", "🔗 Webhook riêng", "🔗 Custom webhook", "webhook"],
        ].map(([id, labelVi, labelEn, k]) => {
          // H5 — kênh này máy chủ đã cấu hình chưa (● xanh = gửi được, ○ = chưa).
          const ready = status?.ready?.[id as keyof ChannelStatus["ready"]];
          return (
            <button
              key={id}
              className={recipe === id || (id === "email" && kind === "email" && !recipe) ? "on" : ""}
              onClick={() => { setRecipe(id === "email" ? null : id); setKind(k as "webhook" | "email"); }}
            >
              {t(labelVi, labelEn)}
              {status && (
                <span
                  title={ready ? t("Máy chủ đã cấu hình kênh này — gửi được ngay.", "The server already has this channel configured — it can send right away.")
                               : t("Máy chủ CHƯA cấu hình kênh này — thêm token/SMTP mới gửi được.", "The server has NOT configured this channel yet — add a token/SMTP before it can send.")}
                  style={{ marginLeft: 6, fontSize: 10, fontWeight: 700,
                           color: ready ? "var(--ok, #3ecb83)" : "var(--dim, #66716a)" }}
                >
                  {ready ? t("● sẵn sàng", "● ready") : t("○ chưa", "○ not yet")}
                </span>
              )}
            </button>
          );
        })}
      </div>
      {/* H5 — nói thẳng nếu kênh đang chọn chưa gửi được phía máy chủ, kèm việc cần làm. */}
      {status && recipe && status.ready?.[recipe as keyof ChannelStatus["ready"]] === false && (
        <p className="ws-mini" style={{ color: "var(--clay, #a0522c)" }}>
          ⚠️ {t("Máy chủ chưa cấu hình kênh này nên tin sẽ KHÔNG gửi được dù bạn thêm.",
                "The server hasn't configured this channel, so messages will NOT send even if you add it.")}
          {status.note?.[recipe] ? ` ${status.note[recipe]}` : ""}
        </p>
      )}
      {recipe === "zalo" && (
        <div className="ws-recipe">
          <b>{t("Nối Zalo OA (miễn phí):", "Connect Zalo OA (free):")}</b>
          <ol>
            <li>{t("Tạo ", "Create an ")}<b>Official Account</b>{t(" tại ", " at ")}<span className="ws-mono">oa.zalo.me</span>.</li>
            <li>{t("Dựng một webhook trung gian (một hàm serverless ~15 dòng: nhận JSON ",
                    "Build a middleman webhook (a ~15-line serverless function: receive TerraTwin's ")}
              <span className="ws-mono">{"{alerts:[…]}"}</span>
              {t(" của TerraTwin → gọi API gửi tin Zalo OA). Mẫu có trong ",
                 " JSON → call the Zalo OA send-message API). A sample is in ")}
              <span className="ws-mono">DEPLOY.md</span>.</li>
            <li>{t("Dán URL webhook trung gian vào ô bên dưới → Thêm → Gửi thử.",
                    "Paste the middleman webhook URL into the box below → Add → Send test.")}</li>
          </ol>
          <p className="ws-mini">{t("Zalo OA không nhận JSON tuỳ ý trực tiếp — bước trung gian là bắt buộc, không thể bỏ.",
                                     "Zalo OA doesn't accept arbitrary JSON directly — the middleman step is mandatory, it can't be skipped.")}</p>
        </div>
      )}
      {recipe === "telegram" && (
        <div className="ws-recipe">
          <b>{t("Nối Telegram (nhanh nhất):", "Connect Telegram (fastest):")}</b>
          <ol>
            <li>{t("Nhắn ", "Message ")}<span className="ws-mono">@BotFather</span> → <span className="ws-mono">/newbot</span> → {t("lấy ", "get a ")}<b>token</b>.</li>
            <li>{t("Lấy ", "Get your ")}<b>chat_id</b>{t(" của bạn (nhắn ", " (message ")}<span className="ws-mono">@userinfobot</span>).</li>
            <li>{t("Dựng webhook trung gian đổi JSON của TerraTwin thành lệnh ",
                    "Build a middleman webhook that turns TerraTwin's JSON into a ")}
              <span className="ws-mono">sendMessage</span>
              {t(" (token + chat_id). Dán URL trung gian vào ô dưới.", " call (token + chat_id). Paste the middleman URL into the box below.")}</li>
          </ol>
        </div>
      )}
      {recipe === "webhook" && (
        <div className="ws-recipe">
          <b>{t("Webhook hệ thống của bạn:", "Your own system's webhook:")}</b> {t("TerraTwin gửi ", "TerraTwin sends a ")}<span className="ws-mono">POST</span> JSON
          <span className="ws-mono">{"{alerts:[{module,risk_level,headline,recommendation,link}…]}"}</span>
          {t(" tới URL khi có rủi ro. ", " to the URL when there's a risk. ")}<span className="ws-mono">link</span> {t("là đường một-chạm để người nhận xác nhận.", "is the one-tap link for the recipient to confirm.")}
        </div>
      )}

      {err && <p className="ws-err">⚠️ {err}</p>}
      {msg && <p className="ws-ok">✓ {msg}</p>}

      <div className="ws-row">
        <select value={kind} onChange={(e) => setKind(e.target.value as any)}>
          <option value="email">Email</option>
          <option value="webhook">Webhook</option>
        </select>
        <input
          placeholder={kind === "email" ? "dia-chi@email.com" : "https://…"}
          value={target}
          onChange={(e) => setTarget(e.target.value)}
        />
        <select value={level} onChange={(e) => setLevel(e.target.value as any)}>
          <option value="warning">{t("Từ mức cảnh báo", "From warning level up")}</option>
          <option value="danger">{t("Chỉ mức nguy hiểm", "Danger level only")}</option>
        </select>
        <button
          onClick={async () => {
            setErr(null);
            try {
              await createChannel(kind, target.trim(), level);
              setTarget("");
              await load();
            } catch (e: any) { setErr(e.message); }
          }}
        >
          {t("Thêm", "Add")}
        </button>
      </div>

      {rows.length === 0 && <p className="ws-hint">{t("Chưa có kênh nào.", "No channels yet.")}</p>}
      {rows.map((c) => (
        <div key={c.id} className="ws-item">
          <div>
            <b>{c.kind === "email" ? "📧" : "🔗"} {c.target}</b>
            <p>{t("Gửi từ mức", "Sends from")} {c.min_level === "danger" ? t("nguy hiểm", "danger") : t("cảnh báo", "warning")}</p>
            <p className="ws-when">
              {t("Gửi lần cuối", "Last sent")} {when(c.last_sent_at, lang)}
              {c.last_error && <span className="ws-bad"> · {t("lỗi", "error")}: {c.last_error}</span>}
            </p>
          </div>
          <div className="ws-btns">
            <button
              onClick={async () => {
                setErr(null); setMsg(null);
                try {
                  const r: any = await testChannel(c.id);
                  setMsg(r?.sent ? t("Đã gửi thử.", "Test sent.") : t("Đã gọi, kiểm tra kênh nhận.", "Called — check the receiving channel."));
                  await load();
                } catch (e: any) { setErr(e.message); }
              }}
            >
              {t("Gửi thử", "Send test")}
            </button>
            <button
              className="ws-del"
              onClick={async () => { await deleteChannel(c.id); load(); }}
            >
              {t("Xoá", "Delete")}
            </button>
          </div>
        </div>
      ))}

      <p className="ws-note">
        {t("Webhook chặn địa chỉ nội bộ (localhost, 10.x, 192.168.x) để không ai dùng phần mềm làm bàn đạp gọi vào mạng riêng của máy chủ.",
           "Webhooks block internal addresses (localhost, 10.x, 192.168.x) so no one can use the app as a launchpad into the server's private network.")}
      </p>

      <ConsentBlock user={user} />
      <DataPrivacyBlock />
    </>
  );
}

/**
 * N8 — ba mục đích TÁCH RIÊNG, mỗi mục một công tắc: nhận cảnh báo có thể cần
 * mà không muốn bị hỏi góp quan sát; ai đó có thể góp quan sát nhưng từ chối
 * dữ liệu của mình phục vụ nghiên cứu. Một ô "Tôi đồng ý" chung cho tất cả là
 * không trung thực về việc dữ liệu thực sự được dùng vào đâu.
 */
function ConsentBlock({ user }: { user: AuthUser | null }) {
  const { t } = useLang();
  const [alerts, setAlerts] = useState(user?.consent_alerts !== false);
  const [observations, setObservations] = useState(user?.consent_observations !== false);
  const [research, setResearch] = useState(user?.consent_research === true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function toggle(
    key: "consent_alerts" | "consent_observations" | "consent_research",
    next: boolean,
    setLocal: (v: boolean) => void,
  ) {
    const prev = { alerts, observations, research };
    setLocal(next);
    setErr(null); setBusy(true);
    try {
      await updateConsent({ [key]: next });
    } catch (e: any) {
      setErr(e.message);
      setAlerts(prev.alerts); setObservations(prev.observations); setResearch(prev.research);
    } finally { setBusy(false); }
  }

  if (!user) return null;

  return (
    <div className="ws-privacy" style={{ marginTop: 16 }}>
      <h4>🎛️ {t("Đồng ý theo mục đích", "Consent by purpose")}</h4>
      {err && <p className="ws-err">⚠️ {err}</p>}
      <label className="ws-check">
        <input type="checkbox" checked={alerts} disabled={busy}
               onChange={(e) => toggle("consent_alerts", e.target.checked, setAlerts)} />
        <span><b>{t("Nhận cảnh báo", "Receive alerts")}</b> — {t("email/webhook khi thửa của bạn có rủi ro. Tắt thì cảnh báo vẫn lưu trong app, chỉ không gửi ra ngoài.",
              "email/webhook when your plot has a risk. Turning this off still keeps alerts in the app, just doesn't send them externally.")}</span>
      </label>
      <label className="ws-check">
        <input type="checkbox" checked={observations} disabled={busy}
               onChange={(e) => toggle("consent_observations", e.target.checked, setObservations)} />
        <span><b>{t("Góp quan sát", "Contribute observations")}</b> — {t('thỉnh thoảng được hỏi một-chạm "cảnh báo trước có đúng không" để mô hình học được.',
              'occasionally asked a one-tap question — "was the earlier alert correct?" — so the model can learn.')}</span>
      </label>
      <label className="ws-check">
        <input type="checkbox" checked={research} disabled={busy}
               onChange={(e) => toggle("consent_research", e.target.checked, setResearch)} />
        <span><b>{t("Phục vụ nghiên cứu", "Research use")}</b> — {t("dữ liệu ẩn danh được dùng để cải thiện mô hình chung. Mặc định TẮT — bạn chủ động bật.",
              "anonymized data used to improve the shared model. OFF by default — you turn it on yourself.")}</span>
      </label>

      <CoopShareBlock user={user} />
    </div>
  );
}

/**
 * Đ11 — mọi người dùng (không chỉ vai trò 'coop') tự đặt mã nhóm + bật/tắt
 * chia sẻ, VÌ người bị xem thửa thường là nông dân thường ('user'), không
 * phải người có vai trò coop (người đó chỉ ĐỌC). Đặt ở đây (Khu làm việc,
 * ai đăng nhập cũng vào được) chứ không phải /admin (chỉ coop/admin vào được)
 * — nếu chỉ đặt ở /admin thì chính chủ thửa không có chỗ nào để tự bật.
 */
function CoopShareBlock({ user }: { user: AuthUser | null }) {
  const { t } = useLang();
  const [code, setCode] = useState(user?.coop_code || "");
  const [share, setShare] = useState(user?.share_with_coop === true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState(false);

  async function save() {
    setBusy(true); setErr(null); setOk(false);
    try {
      await updateCoop({ coop_code: code.trim(), share_with_coop: share });
      setOk(true);
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  }

  return (
    <div style={{ marginTop: 14, paddingTop: 14, borderTop: "1px solid var(--line-2, #e8ece8)" }}>
      <p className="ws-hint" style={{ marginBottom: 8 }}>
        🤝 <b>{t("Hợp tác xã", "Cooperative")}</b> — {t('gõ cùng một mã với các thành viên khác để vào chung nhóm. Người có vai trò coop trong nhóm chỉ xem được thửa của bạn nếu bạn BẬT RIÊNG "chia sẻ với nhóm" bên dưới — đặt mã thôi chưa lộ gì.',
              'type the same code as other members to join a shared group. Someone with the coop role in your group can only see your plot if you separately turn ON "share with group" below — just setting the code doesn\'t expose anything.')}
      </p>
      <div className="ws-row">
        <input placeholder={t("Mã hợp tác xã, vd HTX-BEN-TRE-01", "Cooperative code, e.g. HTX-BEN-TRE-01")} value={code}
               onChange={(e) => setCode(e.target.value)} />
        <label className="ws-check" style={{ margin: 0 }}>
          <input type="checkbox" checked={share} onChange={(e) => setShare(e.target.checked)} />
          <span>{t("Chia sẻ thửa của tôi với nhóm", "Share my plot with the group")}</span>
        </label>
        <button onClick={save} disabled={busy}>{t("Lưu", "Save")}</button>
      </div>
      {err && <p className="ws-err">⚠️ {err}</p>}
      {ok && <p className="ws-ok">✓ {t("Đã lưu.", "Saved.")}</p>}
    </div>
  );
}

/** Xuất/xoá dữ liệu — quyền riêng tư của người dùng, khớp trang /privacy. */
function DataPrivacyBlock() {
  const { t, lang } = useLang();
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [audit, setAudit] = useState<AuditEntry[]>([]);   // Đ12

  useEffect(() => {
    let live = true;
    getAccountAudit(20).then((r) => live && setAudit(r.entries)).catch(() => {});
    return () => { live = false; };
  }, []);

  async function download() {
    setErr(null); setBusy(true);
    try {
      const data = await exportMyData();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `terratwin-du-lieu-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  }

  async function removeAccount() {
    if (confirm !== "XOA") return;
    setErr(null); setBusy(true);
    try {
      await deleteMyAccount();
      setToken(null);
      window.location.href = "/";
    } catch (e: any) { setErr(e.message); setBusy(false); }
  }

  return (
    <div className="ws-privacy">
      <h4>🔒 {t("Dữ liệu & quyền riêng tư", "Data & privacy")}</h4>
      {err && <p className="ws-err">⚠️ {err}</p>}
      <div className="ws-row">
        <button onClick={download} disabled={busy}>⬇️ {t("Tải toàn bộ dữ liệu của tôi (JSON)", "Download all my data (JSON)")}</button>
      </div>

      {/* Đ12 — nhật ký kiểm toán: chủ nhà tự thấy hoạt động lạ trên tài khoản.
          a.label/a.detail đến từ server (_AUDIT_LABELS) — dữ liệu API, không dịch. */}
      {audit.length > 0 && (
        <div style={{ margin: "12px 0 4px" }}>
          <p className="ws-hint" style={{ marginBottom: 6 }}>
            🕒 <b>{t("Hoạt động tài khoản gần đây", "Recent account activity")}</b> — {t("nếu thấy lần đăng nhập bạn không nhận ra, hãy đổi mật khẩu ngay.",
                  "if you see a login you don't recognize, change your password right away.")}
          </p>
          <ul style={{ listStyle: "none", padding: 0, margin: 0, fontSize: 12.5 }}>
            {audit.map((a, i) => (
              <li key={i} style={{
                display: "flex", justifyContent: "space-between", gap: 10,
                padding: "4px 0", borderBottom: "1px solid var(--line-2, #e8ece8)",
              }}>
                <span>{a.label}{a.detail ? ` · ${a.detail}` : ""}</span>
                <span style={{ color: "var(--muted, #66716a)", whiteSpace: "nowrap" }}>
                  {new Date(a.at).toLocaleString(lang === "en" ? "en-US" : "vi-VN")}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* N8 — chính sách lưu trữ hiện NGAY tại nơi quyết định xoá, không chỉ ở
          trang /privacy xa xôi mà lúc này không ai còn muốn bấm sang đọc. */}
      <p className="ws-hint" style={{ borderTop: "1px solid var(--line-2, #e8ece8)", paddingTop: 10, marginTop: 6 }}>
        📦 <b>{t("Chính sách lưu trữ:", "Retention policy:")}</b> {t("dữ liệu thửa/quan sát/cảnh báo được giữ trong lúc tài khoản còn hoạt động. Xoá tài khoản xoá NGAY khỏi ứng dụng; bản sao trong sao lưu mã hoá định kỳ tự hết hạn sau tối đa 7 ngày (sao lưu hằng ngày) hoặc 4 tuần (sao lưu hằng tuần) — xem chi tiết ở",
              "plot/observation/alert data is kept while the account stays active. Deleting your account removes it from the app IMMEDIATELY; a copy in the encrypted periodic backups auto-expires after at most 7 days (daily backups) or 4 weeks (weekly backups) — see details at the")}{" "}
        <a href="/privacy">{t("trang quyền riêng tư", "privacy page")}</a>.
      </p>
      <p className="ws-hint">
        {t("Xoá tài khoản là", "Deleting your account is")} <b>{t("vĩnh viễn", "permanent")}</b> — {t("mọi thửa, quan sát, cảnh báo, khoá API sẽ mất.",
              "every plot, observation, alert, and API key will be lost.")}
        {" "}{t("Gõ", "Type")} <b>XOA</b> {t("để xác nhận.", "to confirm.")}
      </p>
      <div className="ws-row">
        <input placeholder={t("Gõ XOA để xác nhận", "Type XOA to confirm")} value={confirm}
               onChange={(e) => setConfirm(e.target.value)} />
        <button className="ws-del" onClick={removeAccount} disabled={busy || confirm !== "XOA"}>
          {t("Xoá tài khoản", "Delete account")}
        </button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ C12 */

function KeysPanel({ user }: { user: AuthUser | null }) {
  const { t, lang } = useLang();
  const [rows, setRows] = useState<ApiKeyRow[]>([]);
  const [label, setLabel] = useState("");
  const [plan, setPlan] = useState("free");
  const [cat, setCat] = useState<Plan[]>([]);

  // Bảng giá tải một lần, không chặn màn hình nếu lỗi — người dùng vẫn tạo
  // được khoá gói mặc định.
  useEffect(() => {
    getPlans().then((c) => setCat(c.plans)).catch(() => {});
  }, []);
  const [fresh, setFresh] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!user) return;
    try { setRows(await listKeys()); } catch (e: any) { setErr(e.message); }
  }, [user]);

  useEffect(() => { load(); }, [load]);

  return (
    <>
      <p className="ws-sub">
        {t("Khoá để hệ thống khác gọi thẳng vào Twin của bạn — đây là chỗ TerraTwin thôi làm một ứng dụng và bắt đầu làm hạ tầng. Tài liệu đầy đủ ở",
           "A key lets another system call straight into your Twin — this is where TerraTwin stops being just an app and starts being infrastructure. Full docs at")}{" "}
        <code>/docs</code>, {t("SDK Python một tệp trong thư mục", "a single-file Python SDK in the folder")} <code>sdk/</code>.
      </p>
      {err && <p className="ws-err">⚠️ {err}</p>}

      <div className="ws-plan">
        {cat.map((p) => (
          <button
            key={p.id}
            className={plan === p.id ? "on" : ""}
            onClick={() => setPlan(p.id)}
            title={p.for}
          >
            {p.name}
            <small>
              {p.quota.toLocaleString(lang === "en" ? "en" : "vi")} {t("lượt/tháng", "calls/month")}
              {p.price_vnd > 0 && ` · ${p.price_vnd.toLocaleString(lang === "en" ? "en" : "vi")}đ`}
            </small>
          </button>
        ))}
      </div>
      <div className="ws-row">
        <input
          placeholder={t("Đặt tên, vd. Hệ thống HTX Bình Đại", "Give it a name, e.g. Bình Đại co-op system")}
          value={label}
          onChange={(e) => setLabel(e.target.value)}
        />
        <button
          onClick={async () => {
            setErr(null);
            try {
              const k = await createKey(label.trim() || t("Khoá mới", "New key"), plan);
              setFresh(k.key);
              setLabel("");
              await load();
            } catch (e: any) { setErr(e.message); }
          }}
        >
          {t("Tạo khoá", "Create key")}
        </button>
      </div>

      {fresh && (
        <div className="ws-fresh">
          <b>{t("Chép ngay — khoá này không hiện lại lần nào nữa:", "Copy it now — this key will never be shown again:")}</b>
          <code>{fresh}</code>
          <button onClick={() => navigator.clipboard?.writeText(fresh)}>{t("Chép", "Copy")}</button>
        </div>
      )}

      {rows.length === 0 && <p className="ws-hint">{t("Chưa có khoá nào.", "No keys yet.")}</p>}
      {rows.map((k) => (
        <div key={k.id} className={`ws-item ${k.revoked ? "off" : ""}`}>
          <div>
            <b>{k.label || t("(không tên)", "(unnamed)")}</b>
            <span className="ws-tag">{k.plan}</span>
            <p><code>{k.prefix}…</code>{k.revoked && ` · ${t("ĐÃ THU HỒI", "REVOKED")}`}</p>
            <p className="ws-when">
              {t("Tạo", "Created")} {when(k.created_at, lang)} · {t("dùng lần cuối", "last used")} {when(k.last_used_at, lang)}
            </p>
            <p className="ws-when">
              {t("Đã gọi", "Called")} {k.calls_total} {t("lượt", "times")}
              {k.monthly_quota > 0
                ? ` · ${t("tháng này", "this month")} ${k.calls_period}/${k.monthly_quota}`
                : ` · ${t("không giới hạn tháng", "no monthly limit")}`}
            </p>
          </div>
          {!k.revoked && (
            <button
              className="ws-del"
              onClick={async () => { await revokeKey(k.id); load(); }}
            >
              {t("Thu hồi", "Revoke")}
            </button>
          )}
        </div>
      ))}

      <p className="ws-note">
        {t("Máy chủ chỉ giữ bản băm của khoá, không giữ khoá gốc — mất thì tạo cái mới, không ai lấy lại được cho bạn, kể cả quản trị hệ thống.",
           "The server only keeps a hash of the key, never the raw key — if you lose it, create a new one; no one can recover it for you, not even system admins.")}
      </p>
      <p className="ws-note">
        {t("Mỗi khoá có hạn mức lượt gọi theo tháng. Đây là chống lạm dụng chứ chưa phải tính tiền: một khoá bị lộ mà không có trần sẽ đốt hết hạn mức ngày của nguồn dữ liệu miễn phí, và lúc đó mọi người dùng khác mất dữ liệu theo, không riêng chủ khoá.",
           "Each key has a monthly call quota. This is abuse prevention, not billing: a leaked key without a cap would burn through the free data sources' daily quota, and every other user would lose data along with the key's owner.")}
      </p>
    </>
  );
}

/* ------------------------------------------------------------------ shell */

export default function Workspace({
  user, coord, area, onClose, onOpenPlot,
}: {
  user: AuthUser | null;
  coord: { lat: number; lon: number } | null;
  area?: number;
  onClose: () => void;
  onOpenPlot?: (lat: number, lon: number) => void;
}) {
  const { t } = useLang();
  const [tab, setTab] = useState<Tab>("portfolio");
  const needsAuth = tab !== "status" && tab !== "learn" && !user;

  return (
    <div className="ws-overlay" onClick={onClose}>
      <div className="ws" onClick={(e) => e.stopPropagation()}>
        <div className="ws-head">
          <b>{t("Khu làm việc", "Workspace")}</b>
          <button className="ws-close" onClick={onClose} aria-label={t("Đóng", "Close")}>
            ✕
          </button>
        </div>

        <div className="ws-tabs">
          {TABS.map((tb) => (
            <button
              key={tb.id}
              className={tab === tb.id ? "on" : ""}
              onClick={() => setTab(tb.id)}
            >
              {t(...TAB_LABELS[tb.id])}
              {tb.flow && <span className="ws-flow">{tb.flow}</span>}
            </button>
          ))}
        </div>

        <div className="ws-body">
          {needsAuth ? (
            <p className="ws-hint">
              {t("Đăng nhập ở cột trái để dùng phần này — dữ liệu ở đây gắn với tài khoản của bạn.",
                 "Sign in on the left to use this section — the data here is tied to your account.")}
            </p>
          ) : (
            <>
              {tab === "portfolio" && (
                <PortfolioOverview user={user} onOpen={onOpenPlot} />
              )}
              {tab === "twins" && <TwinsPanel user={user} coord={coord} area={area} />}
              {tab === "data" && <DataPanel user={user} />}
              {tab === "alerts" && <ChannelsPanel user={user} />}
              {tab === "api" && <KeysPanel user={user} />}
              {tab === "learn" && <Learning user={user} />}
              {tab === "status" && <Roadmap />}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
