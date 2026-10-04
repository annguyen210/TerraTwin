"use client";

/**
 * THIẾT BỊ — IoT ký số tại vườn. Thiết bị tự sinh khoá Ed25519, chỉ khoá CÔNG KHAI được
 * đăng ký ở đây; mọi số đo mang chữ ký kiểm được, kể cả máy chủ cũng không giả được.
 * Thiết bị giả lập (demo) luôn mang nhãn — không bao giờ lẫn với số đo thật.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { BadgeCheck, Cpu, Download, Radio, ShieldCheck, Trash2 } from "lucide-react";
import AppShell from "@/components/AppShell";
import {
  fetchMe, getToken, iotDevices, iotExport, iotReadings, iotRegister, iotRevoke,
  type AuthUser, type IotDevice, type IotSeries,
} from "@/lib/api";
import { useLang } from "@/lib/i18n";

function ago(iso: string | null, t: (vi: string, en: string) => string) {
  if (!iso) return t("chưa gửi lần nào", "never sent");
  const m = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (m < 60) return t(`${m} phút trước`, `${m} min ago`);
  const h = Math.round(m / 60);
  return h < 48 ? t(`${h} giờ trước`, `${h} h ago`) : t(`${Math.round(h / 24)} ngày trước`, `${Math.round(h / 24)} days ago`);
}

function Spark({ data, k, label, unit }: { data: IotSeries["series"]; k: string; label: string; unit: string }) {
  const pts = data.map((r) => r[k]).filter((v): v is number => typeof v === "number");
  if (pts.length < 2) return null;
  const lo = Math.min(...pts), hi = Math.max(...pts), span = hi - lo || 1;
  const W = 320, H = 64;
  const d = pts.map((v, i) => `${(i / (pts.length - 1)) * W},${H - 4 - ((v - lo) / span) * (H - 8)}`).join(" ");
  return (
    <figure className="iot-spark">
      <figcaption><span>{label}</span><b>{pts[pts.length - 1]}{unit}</b><small>{lo}–{hi}{unit}</small></figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label={`${label}: ${pts.length} điểm`}>
        <polyline points={d} fill="none" strokeWidth="2" vectorEffect="non-scaling-stroke" />
      </svg>
    </figure>
  );
}

export default function DevicesPage() {
  const { t } = useLang();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [devs, setDevs] = useState<IotDevice[]>([]);
  const [sel, setSel] = useState<IotSeries | null>(null);
  const [name, setName] = useState("");
  const [key, setKey] = useState("");
  const [sim, setSim] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => { setDevs((await iotDevices()).devices); }, []);
  useEffect(() => {
    if (!getToken()) return;
    fetchMe().then((u) => { setUser(u); refresh().catch((e) => setErr(e.message)); }).catch(() => setUser(null));
  }, [refresh]);

  async function add() {
    setErr(null); setBusy(true);
    try {
      await iotRegister({ name: name.trim(), public_key: key.trim(), kind: sim ? "simulator" : "sensor" });
      setName(""); setKey(""); setSim(false);
      await refresh();
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }
  async function open(d: IotDevice) {
    setErr(null);
    try { setSel(await iotReadings(d.id)); } catch (e) { setErr((e as Error).message); }
  }
  async function revoke(d: IotDevice) {
    if (!window.confirm(t("Thu hồi thiết bị? Số đo cũ vẫn kiểm được, thiết bị không gửi thêm được.",
                          "Revoke the device? Past readings stay verifiable; it can't send more."))) return;
    await iotRevoke(d.id); setSel(null); await refresh();
  }
  async function exportJson(d: IotDevice) {
    const doc = await iotExport(d.id);
    const url = URL.createObjectURL(new Blob([JSON.stringify(doc, null, 2)], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url; a.download = `terratwin-thiet-bi-${d.id}.json`; a.click();
    URL.revokeObjectURL(url);
  }
  const keys = useMemo(() => (sel ? Object.keys(sel.catalog).filter((k) => sel.series.some((r) => typeof r[k] === "number")) : []), [sel]);

  return (
    <AppShell user={user} onAuth={setUser}>
      <main className="bat-wrap eu-wrap tt-reveal">
        <div>
          <p className="eu-eyebrow">{t("IoT ký số · Ed25519 · chống giả mạo, chống phát lại", "Signed IoT · Ed25519 · anti-forgery, anti-replay")}</p>
          <h1>{t("Thiết bị tại vườn", "Field devices")}</h1>
          <p className="doc-lede">{t(
            "Trạm đo ẩm đất, mưa, nhiệt tự ký từng số đo bằng khoá riêng của nó. TerraTwin chỉ giữ khoá công khai — nên cả máy chủ cũng không sửa được số đo. Mất sóng ở vườn thì thiết bị lưu đệm và gửi bù tới 30 ngày.",
            "Soil-moisture, rain and temperature stations sign every reading with their own key. TerraTwin only keeps the public key — so not even the server can alter readings. No signal in the field? The device buffers and back-fills up to 30 days.")}</p>
        </div>

        {err && <p className="bat-err">{err}</p>}
        {!user ? (
          <p className="doc-note">{t("Đăng nhập (nút trên cùng) để đăng ký và xem thiết bị của bạn.", "Sign in (top button) to register and view your devices.")}</p>
        ) : (
          <>
            <section className="bat-card">
              <h2><Cpu size={18} aria-hidden="true" className="ui-ic" /> {t("Đăng ký thiết bị", "Register a device")}</h2>
              <div className="iot-form">
                <label>{t("Tên", "Name")}<input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} placeholder={t("Trạm vườn cà phê lô 3", "Coffee plot 3 station")} /></label>
                <label>{t("Khoá công khai Ed25519 (base64, 44 ký tự)", "Ed25519 public key (base64, 44 chars)")}<input value={key} onChange={(e) => setKey(e.target.value)} spellCheck={false} className="mono" /></label>
                <label className="iot-check"><input type="checkbox" checked={sim} onChange={(e) => setSim(e.target.checked)} /> {t("Đây là thiết bị GIẢ LẬP (demo) — số đo sẽ luôn mang nhãn giả lập", "This is a SIMULATED device (demo) — readings will always be labelled simulated")}</label>
                <button className="bat-btn" onClick={add} disabled={busy || !name.trim() || key.trim().length < 40}>{t("Đăng ký", "Register")}</button>
              </div>
              <p className="doc-note">{t("Khoá bí mật KHÔNG bao giờ dán vào đây — nó nằm trong thiết bị. Cách làm thiết bị và trình giả lập: ops/iot_simulator.py; danh mục chỉ số và ngưỡng: /api/iot/metrics.",
                "NEVER paste the private key here — it stays in the device. How to build a device and the simulator: ops/iot_simulator.py; metric catalogue and limits: /api/iot/metrics.")}</p>
            </section>

            <section className="bat-card">
              <h2><Radio size={18} aria-hidden="true" className="ui-ic" /> {t("Thiết bị của bạn", "Your devices")}</h2>
              {devs.length === 0 ? <p className="doc-note">{t("Chưa có thiết bị nào.", "No devices yet.")}</p> : (
                <ul className="iot-list">
                  {devs.map((d) => (
                    <li key={d.id} className={`tt-card ${sel?.device.id === d.id ? "on" : ""}`}>
                      <button className="iot-pick" onClick={() => open(d)}>
                        <b>{d.name}</b>
                        {d.kind === "simulator" && <span className="eu-badge eu-review">{t("Giả lập", "Simulated")}</span>}
                        {d.revoked && <span className="eu-badge eu-high">{t("Đã thu hồi", "Revoked")}</span>}
                        <small>{ago(d.last_seen, t)} · seq {d.last_seq}{d.latest?.metrics.soil_moisture_pct != null ? ` · ${t("ẩm đất", "soil")} ${d.latest.metrics.soil_moisture_pct}%` : ""}</small>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {sel && (
              <section className="bat-card">
                <div className="bat-row bat-between">
                  <h2>{sel.device.name}{sel.device.kind === "simulator" && <span className="eu-badge eu-review">{t("Số đo giả lập", "Simulated readings")}</span>}</h2>
                  <div className="bat-row">
                    <button className="bat-btn ghost" onClick={() => exportJson(sel.device)}><Download size={16} aria-hidden="true" /> {t("Xuất để kiểm độc lập", "Export for independent check")}</button>
                    {!sel.device.revoked && <button className="bat-btn ghost" onClick={() => revoke(sel.device)}><Trash2 size={16} aria-hidden="true" /> {t("Thu hồi", "Revoke")}</button>}
                  </div>
                </div>
                <p className="doc-note"><ShieldCheck size={14} aria-hidden="true" /> {t(`${sel.series.length} số đo trong 7 ngày, mỗi số đo đã kiểm chữ ký Ed25519 khi nhận. Khoá công khai: `, `${sel.series.length} readings in 7 days, each signature-checked on receipt. Public key: `)}<code>{sel.device.public_key}</code></p>
                <div className="iot-grid">
                  {keys.map((k) => <Spark key={k} data={sel.series} k={k} label={sel.catalog[k].label} unit={sel.catalog[k].unit} />)}
                </div>
                {sel.series.length === 0 && <p className="doc-note"><BadgeCheck size={14} aria-hidden="true" /> {t("Chưa có số đo trong 7 ngày.", "No readings in the last 7 days.")}</p>}
              </section>
            )}
          </>
        )}
      </main>
    </AppShell>
  );
}
