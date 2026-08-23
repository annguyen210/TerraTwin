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
  scoreDataset, testChannel, uploadDataset,
  type ApiKeyRow, type AuthUser, type ChannelRow, type DatasetRow,
  type TwinSummary,
  type Plan,
} from "@/lib/api";
import Learning from "@/components/Learning";
import PortfolioOverview from "@/components/PortfolioOverview";
import Roadmap from "@/components/Roadmap";

type Tab = "portfolio" | "twins" | "data" | "alerts" | "api" | "learn" | "status";

const TABS: { id: Tab; label: string; flow: string }[] = [
  { id: "portfolio", label: "Toàn cảnh danh mục", flow: "C08" },
  { id: "twins", label: "Twin đã lưu", flow: "C01" },
  { id: "data", label: "Dữ liệu của tôi", flow: "C11" },
  { id: "alerts", label: "Kênh cảnh báo", flow: "U01" },
  { id: "api", label: "Khoá API", flow: "C12" },
  { id: "learn", label: "Vòng học", flow: "S05·S09·U04" },
  { id: "status", label: "26 luồng", flow: "" },
];

function when(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("vi-VN", {
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
      await buildTwin(name.trim() || "Thửa chưa đặt tên", coord.lat, coord.lon, area);
      setName("");
      await load();
    } catch (e: any) {
      setErr(e.message);
    } finally { setBusy(false); }
  }

  return (
    <>
      <p className="ws-sub">
        Twin là ảnh chụp ĐẦY ĐỦ của thửa tại một thời điểm — địa hình, khí hậu,
        cả 14 mô-đun và TerraScore — lưu lại để về sau đối chiếu xem mọi thứ đã
        đổi thế nào. Khác với “thửa đã lưu” ở cột trái: cái kia chỉ nhớ toạ độ.
      </p>
      {err && <p className="ws-err">⚠️ {err}</p>}

      {coord ? (
        <div className="ws-row">
          <input
            placeholder="Tên Twin, vd. Ruộng sau nhà — vụ Đông Xuân"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <button disabled={busy} onClick={build}>
            {busy ? "Đang dựng…" : "Dựng Twin tại điểm đang chọn"}
          </button>
        </div>
      ) : (
        <p className="ws-hint">Bấm một điểm trên bản đồ trước rồi quay lại đây.</p>
      )}

      {rows.length === 0 && <p className="ws-hint">Chưa có Twin nào được lưu.</p>}
      {rows.map((t) => (
        <div key={t.id} className="ws-item">
          <div>
            <b>{t.name}</b>
            <p>
              {t.lat.toFixed(4)}, {t.lon.toFixed(4)}
              {t.area_ha != null && ` · ${t.area_ha} ha`}
              {t.score != null && ` · TerraScore ${t.score} (${t.grade})`}
            </p>
            <p className="ws-when">Dựng lúc {when(t.built_at)}</p>
          </div>
          <button
            className="ws-del"
            onClick={async () => { await deleteTwin(t.id); load(); }}
          >
            Xoá
          </button>
        </div>
      ))}
    </>
  );
}

/* ------------------------------------------------------------------ C11 */

function DataPanel({ user }: { user: AuthUser | null }) {
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
        Tải lên danh sách điểm của bạn (CSV có cột <code>lat, lon</code> và tuỳ
        chọn <code>name</code>, hoặc GeoJSON) rồi chấm TerraScore hàng loạt. Hợp
        tác xã 200 thửa không phải bấm 200 lần.
      </p>
      {err && <p className="ws-err">⚠️ {err}</p>}

      <label className="ws-file">
        <input
          type="file"
          accept=".csv,.geojson,.json"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); }}
        />
        {busy ? "Đang tải lên…" : "Chọn tệp CSV hoặc GeoJSON"}
      </label>

      {rows.length === 0 && <p className="ws-hint">Chưa tải lên tệp nào.</p>}
      {rows.map((d) => (
        <div key={d.id} className="ws-item">
          <div>
            <b>{d.name}</b>
            <p>{d.kind.toUpperCase()} · {d.row_count} điểm hợp lệ</p>
            <p className="ws-when">{when(d.created_at)}</p>
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
              Chấm điểm
            </button>
            <button
              className="ws-del"
              onClick={async () => { await deleteDataset(d.id); load(); }}
            >
              Xoá
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
  const [rows, setRows] = useState<ChannelRow[]>([]);
  const [kind, setKind] = useState<"webhook" | "email">("email");
  const [target, setTarget] = useState("");
  const [level, setLevel] = useState<"warning" | "danger">("warning");
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!user) return;
    try { setRows(await listChannels()); } catch (e: any) { setErr(e.message); }
  }, [user]);

  useEffect(() => { load(); }, [load]);

  return (
    <>
      <p className="ws-sub">
        Cảnh báo nằm trong phần mềm thì chỉ hữu ích khi người dùng đang mở phần
        mềm — mà thiên tai không chờ điều đó. Thêm kênh để cảnh báo tự tìm đến
        bạn: email, hoặc webhook để nối sang Zalo OA, Telegram, hệ thống nội bộ.
      </p>
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
          <option value="warning">Từ mức cảnh báo</option>
          <option value="danger">Chỉ mức nguy hiểm</option>
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
          Thêm
        </button>
      </div>

      {rows.length === 0 && <p className="ws-hint">Chưa có kênh nào.</p>}
      {rows.map((c) => (
        <div key={c.id} className="ws-item">
          <div>
            <b>{c.kind === "email" ? "📧" : "🔗"} {c.target}</b>
            <p>Gửi từ mức {c.min_level === "danger" ? "nguy hiểm" : "cảnh báo"}</p>
            <p className="ws-when">
              Gửi lần cuối {when(c.last_sent_at)}
              {c.last_error && <span className="ws-bad"> · lỗi: {c.last_error}</span>}
            </p>
          </div>
          <div className="ws-btns">
            <button
              onClick={async () => {
                setErr(null); setMsg(null);
                try {
                  const r: any = await testChannel(c.id);
                  setMsg(r?.sent ? "Đã gửi thử." : "Đã gọi, kiểm tra kênh nhận.");
                  await load();
                } catch (e: any) { setErr(e.message); }
              }}
            >
              Gửi thử
            </button>
            <button
              className="ws-del"
              onClick={async () => { await deleteChannel(c.id); load(); }}
            >
              Xoá
            </button>
          </div>
        </div>
      ))}

      <p className="ws-note">
        Webhook chặn địa chỉ nội bộ (localhost, 10.x, 192.168.x) để không ai dùng
        phần mềm làm bàn đạp gọi vào mạng riêng của máy chủ.
      </p>
    </>
  );
}

/* ------------------------------------------------------------------ C12 */

function KeysPanel({ user }: { user: AuthUser | null }) {
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
        Khoá để hệ thống khác gọi thẳng vào Twin của bạn — đây là chỗ TerraTwin
        thôi làm một ứng dụng và bắt đầu làm hạ tầng. Tài liệu đầy đủ ở{" "}
        <code>/docs</code>, SDK Python một tệp trong thư mục <code>sdk/</code>.
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
              {p.quota.toLocaleString("vi")} lượt/tháng
              {p.price_vnd > 0 && ` · ${p.price_vnd.toLocaleString("vi")}đ`}
            </small>
          </button>
        ))}
      </div>
      <div className="ws-row">
        <input
          placeholder="Đặt tên, vd. Hệ thống HTX Bình Đại"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
        />
        <button
          onClick={async () => {
            setErr(null);
            try {
              const k = await createKey(label.trim() || "Khoá mới", plan);
              setFresh(k.key);
              setLabel("");
              await load();
            } catch (e: any) { setErr(e.message); }
          }}
        >
          Tạo khoá
        </button>
      </div>

      {fresh && (
        <div className="ws-fresh">
          <b>Chép ngay — khoá này không hiện lại lần nào nữa:</b>
          <code>{fresh}</code>
          <button onClick={() => navigator.clipboard?.writeText(fresh)}>Chép</button>
        </div>
      )}

      {rows.length === 0 && <p className="ws-hint">Chưa có khoá nào.</p>}
      {rows.map((k) => (
        <div key={k.id} className={`ws-item ${k.revoked ? "off" : ""}`}>
          <div>
            <b>{k.label || "(không tên)"}</b>
            <span className="ws-tag">{k.plan}</span>
            <p><code>{k.prefix}…</code>{k.revoked && " · ĐÃ THU HỒI"}</p>
            <p className="ws-when">
              Tạo {when(k.created_at)} · dùng lần cuối {when(k.last_used_at)}
            </p>
            <p className="ws-when">
              Đã gọi {k.calls_total} lượt
              {k.monthly_quota > 0
                ? ` · tháng này ${k.calls_period}/${k.monthly_quota}`
                : " · không giới hạn tháng"}
            </p>
          </div>
          {!k.revoked && (
            <button
              className="ws-del"
              onClick={async () => { await revokeKey(k.id); load(); }}
            >
              Thu hồi
            </button>
          )}
        </div>
      ))}

      <p className="ws-note">
        Máy chủ chỉ giữ bản băm của khoá, không giữ khoá gốc — mất thì tạo cái
        mới, không ai lấy lại được cho bạn, kể cả quản trị hệ thống.
      </p>
      <p className="ws-note">
        Mỗi khoá có hạn mức lượt gọi theo tháng. Đây là chống lạm dụng chứ chưa
        phải tính tiền: một khoá bị lộ mà không có trần sẽ đốt hết hạn mức ngày
        của nguồn dữ liệu miễn phí, và lúc đó mọi người dùng khác mất dữ liệu
        theo, không riêng chủ khoá.
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
  const [tab, setTab] = useState<Tab>("portfolio");
  const needsAuth = tab !== "status" && tab !== "learn" && !user;

  return (
    <div className="ws-overlay" onClick={onClose}>
      <div className="ws" onClick={(e) => e.stopPropagation()}>
        <div className="ws-head">
          <b>Khu làm việc</b>
          <button className="ws-close" onClick={onClose} aria-label="Đóng">
            ✕
          </button>
        </div>

        <div className="ws-tabs">
          {TABS.map((t) => (
            <button
              key={t.id}
              className={tab === t.id ? "on" : ""}
              onClick={() => setTab(t.id)}
            >
              {t.label}
              {t.flow && <span className="ws-flow">{t.flow}</span>}
            </button>
          ))}
        </div>

        <div className="ws-body">
          {needsAuth ? (
            <p className="ws-hint">
              Đăng nhập ở cột trái để dùng phần này — dữ liệu ở đây gắn với tài
              khoản của bạn.
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
