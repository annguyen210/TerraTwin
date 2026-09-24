"use client";

/**
 * "Thửa của tôi" — trang chủ cho người ĐÃ đăng nhập.
 *
 * VÌ SAO CẦN CHO "PHỔ CẬP". Một công cụ người ta phải NHỚ mở thì mở vài lần rồi
 * quên. Một thứ TỰ CANH đất và báo trước khi có chuyện thì người ta mở mỗi ngày
 * — và không rời được. Backend đã có Radar quét nền + kho cảnh báo; màn này đưa
 * đúng thứ đó lên đầu: "TerraTwin đang canh N thửa của bạn, đây là việc sắp tới".
 *
 * Chỉ hiện khi đã đăng nhập VÀ có thửa đã lưu — nếu chưa, để màn "đất của bạn ở
 * đâu" dẫn người dùng phân tích + lưu trước.
 */

import { useCallback, useEffect, useState } from "react";
import {
  ackAlert,
  getContribution,
  getMyQuestions,
  listAlerts,
  listPlots,
  resendVerification,
  runRadar,
  sendTapAnswer,
  type AlertRow,
  type AuthUser,
  type Contribution,
  type ServerPlot,
  type TapQuestion,
} from "@/lib/api";
import { enablePush, pushState } from "@/lib/push";
import { getBriefStatus, toggleBrief } from "@/lib/api";
import PlotHistory from "@/components/PlotHistory";
import { useLang } from "@/lib/i18n";

const GRADE_COLOR: Record<string, string> = {
  A: "#2E9E67", B: "#3aa0a0", C: "#B07A2E", D: "#C2412E",
};
const RISK_COLOR: Record<string, string> = {
  danger: "#C2412E", warning: "#B07A2E", safe: "#2E9E67",
};

export default function MyLand({
  user,
  onOpen,
}: {
  user: AuthUser | null;
  onOpen: (lat: number, lon: number, label: string) => void;
}) {
  const { t, lang } = useLang();
  const [plots, setPlots] = useState<ServerPlot[]>([]);
  const [alerts, setAlerts] = useState<AlertRow[]>([]);
  const [questions, setQuestions] = useState<TapQuestion[]>([]);   // H6
  const [answered, setAnswered] = useState<Record<number, string>>({});
  const [loaded, setLoaded] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [push, setPush] = useState<string>("");   // M1 — trạng thái web push
  const [brief, setBrief] = useState<boolean | null>(null);   // M4
  const [openId, setOpenId] = useState<number | null>(null);   // Đ9 — thửa đang mở lịch sử
  const [verifyMsg, setVerifyMsg] = useState<string | null>(null);   // N1
  const [contribution, setContribution] = useState<Contribution | null>(null);   // M5

  async function resend() {
    setVerifyMsg(t("Đang gửi…", "Sending…"));
    try {
      const r = await resendVerification();
      setVerifyMsg(r.message);
    } catch (e) {
      setVerifyMsg((e as Error).message);
    }
  }

  useEffect(() => { pushState().then(setPush).catch(() => {}); }, []);
  useEffect(() => { getBriefStatus().then((r) => setBrief(r.enabled)).catch(() => {}); }, []);
  useEffect(() => { getContribution().then(setContribution).catch(() => {}); }, []);   // M5
  async function turnOnPush() {
    setPush("...");
    try { setPush(await enablePush()); } catch { setPush("off"); }
  }
  async function flipBrief() {
    const next = !brief;
    setBrief(next);
    try { await toggleBrief(next); } catch { setBrief(!next); }
  }

  const refresh = useCallback(async () => {
    if (!user) return;
    try {
      const [p, a, q] = await Promise.all([
        listPlots().catch(() => []),
        listAlerts(true).catch(() => []),
        getMyQuestions(5).then((r) => r.questions).catch(() => []),
      ]);
      setPlots(p);
      setAlerts(a);
      setQuestions(q);
    } finally {
      setLoaded(true);
    }
  }, [user]);

  // H6 — trả lời câu hỏi chờ NGAY tại đây (đóng vòng lặp tin cậy trong app).
  async function answer(q: TapQuestion, value: "yes" | "no" | "unsure") {
    if (!q.token) return;
    setAnswered((m) => ({ ...m, [q.alert_id]: value }));
    try {
      await sendTapAnswer(q.token, value);
    } catch {
      setAnswered((m) => { const n = { ...m }; delete n[q.alert_id]; return n; });
    }
  }

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function scanNow() {
    setScanning(true);
    try {
      await runRadar();
      await refresh();
    } catch {
      /* im lặng — nút này chỉ là tiện, hỏng không được chặn màn */
    } finally {
      setScanning(false);
    }
  }

  async function ack(id: number) {
    setAlerts((xs) => xs.filter((a) => a.id !== id));
    try {
      await ackAlert(id);
    } catch {
      refresh();
    }
  }

  // Chưa đăng nhập, hoặc đăng nhập nhưng chưa lưu thửa nào → nhường màn Start.
  if (!user || (loaded && plots.length === 0)) return null;
  if (!loaded) return null;

  const plotName = (id: number | null) =>
    plots.find((p) => p.id === id)?.name ?? t("một thửa", "a plot");
  const dateFmt = lang === "en" ? "en-US" : "vi-VN";

  return (
    <div className="myland">
      <div className="ml-head">
        <div>
          <b>🛡️ {t(`TerraTwin đang canh ${plots.length} thửa của bạn`, `TerraTwin is watching ${plots.length} of your plots`)}</b>
          <p className="ml-brief">
            ☀️{" "}
            {new Date().toLocaleDateString(dateFmt, { weekday: "long", day: "numeric", month: "numeric" })}
            {" · "}
            {alerts.length ? (
              <b style={{ color: "var(--warn)" }}>{t(`${alerts.length} cảnh báo mới cần xem`, `${alerts.length} new alert(s) to review`)}</b>
            ) : (
              <b style={{ color: "var(--ok)" }}>{t("tất cả thửa đang an toàn", "all plots are safe")}</b>
            )}
          </p>
          <p className="ml-brief-sub">{t("Tự quét nền và báo trước khi có rủi ro — bạn không cần nhớ mở.",
                                          "Scans in the background and warns before risk hits — no need to remember to open it.")}</p>
          {/* M5 — đóng góp CÓ ÍCH, không chỉ "cảm ơn" thoáng qua lúc trả lời một
              chạm (xem onetap._contribution). Chỉ hiện khi có gì để khoe — tài
              khoản mới toanh chưa góp gì thì một dòng "0 · 0" chỉ gây rối. */}
          {contribution && (contribution.observations_contributed > 0 || contribution.alerts_verified > 0) && (
            <p className="ml-brief-sub">
              🌱 {t("Bạn đã góp", "You've contributed")} <b>{contribution.observations_contributed}</b> {t("quan sát", "observations")}
              {contribution.alerts_verified > 0 && (
                <> · {t("cảnh báo của bạn đã được xác minh", "your alerts have been verified")} <b>{contribution.alerts_verified}</b> {t("lần", "times")}
                  {contribution.alerts_hit > 0 && t(` (đúng ${contribution.alerts_hit} lần)`, ` (${contribution.alerts_hit} correct)`)}</>
              )}
            </p>
          )}
        </div>
        <button onClick={scanNow} disabled={scanning}>
          {scanning ? t("Đang quét…", "Scanning…") : t("Quét lại ngay", "Scan again now")}
        </button>
      </div>

      {/* M1 — bật Web Push. Kênh cảnh báo sống-được-ngay (không cần Zalo/Telegram).
          Chỉ hiện nút khi bật được mà CHƯA bật. */}
      {push === "off" && (
        <button onClick={turnOnPush} style={{
          margin: "0 0 10px", padding: "9px 14px", borderRadius: 8, cursor: "pointer",
          border: "1px solid var(--terra, #1f5137)", background: "var(--pine-soft, #dfede5)",
          color: "var(--pine, #1f5137)", fontWeight: 600, width: "100%" }}>
          🔔 {t("Bật thông báo đẩy — nhận cảnh báo kể cả khi không mở app",
                "Enable push notifications — get alerts even when the app isn't open")}
        </button>
      )}
      {push === "..." && <p className="ml-brief-sub">{t("Đang bật thông báo…", "Enabling notifications…")}</p>}
      {push === "on" && <p className="ml-brief-sub" style={{ color: "var(--ok, #2E9E67)" }}>🔔 {t("Thông báo đẩy đang bật.", "Push notifications are on.")}</p>}
      {push === "denied" && <p className="ml-brief-sub">{t("Thông báo bị chặn trong trình duyệt — mở lại trong cài đặt trang để nhận cảnh báo.",
                                                             "Notifications are blocked in the browser — re-enable them in site settings to get alerts.")}</p>}

      {/* N1 — email chưa xác thực thì cảnh báo vẫn TẠO nhưng KHÔNG gửi ra kênh
          ngoài (email/Zalo/Telegram/webhook) — nói rõ ở đúng màn nói về cảnh
          báo, không phải chôn trong trang tài khoản không ai mở. */}
      {user.email_verified === false && (
        <p className="ml-brief-sub" style={{ color: "var(--warn, #B07A2E)" }}>
          ⚠️ {t(`Email ${user.email} chưa xác thực — cảnh báo vẫn hiện ở đây nhưng KHÔNG gửi ra kênh ngoài (email/Zalo/Telegram) cho tới khi xác thực.`,
                `Email ${user.email} is not verified — alerts still show up here but will NOT be sent to outside channels (email/Zalo/Telegram) until verified.`)}{" "}
          <button onClick={resend} style={{ border: "none", background: "none",
            color: "var(--terra, #1f5137)", textDecoration: "underline", cursor: "pointer",
            font: "inherit", padding: 0 }}>
            {t("Gửi lại liên kết xác thực", "Resend verification link")}
          </button>
          {verifyMsg && <span> — {verifyMsg}</span>}
        </p>
      )}

      {/* M4 — bản tin sáng (opt-in). Hiện khi push đã bật (mới gửi được). */}
      {push === "on" && brief !== null && (
        <label style={{ display: "flex", alignItems: "center", gap: 8, margin: "0 0 10px",
          fontSize: 13, color: "var(--ink-2, #333d36)", cursor: "pointer" }}>
          <input type="checkbox" checked={brief} onChange={flipBrief} />
          ☀️ {t("Gửi bản tin sáng mỗi ngày (kể cả khi an toàn) — tạo thói quen theo dõi",
                "Send a morning brief every day (even when safe) — builds a monitoring habit")}
        </label>
      )}

      {/* H6 — CÂU HỎI CHỜ LÊN TRÊN CÙNG (trên cả cảnh báo). Đây là thứ đóng vòng
          lặp tin cậy; nằm dưới màn cuộn thì tỉ lệ trả lời ≈ 0. Đặt trên vì một
          câu trả lời của người vừa chấm điểm cảnh báo vừa hiệu chỉnh cả vùng. */}
      {questions.length > 0 && (
        <div className="ml-alerts" style={{ borderColor: "var(--terra, #1f5137)" }}>
          <span className="ml-cap">📩 {t(`${questions.length} câu cần bạn xác nhận — giúp TerraTwin chính xác hơn cho cả vùng`,
                                          `${questions.length} question(s) need your confirmation — helps TerraTwin be more accurate for the whole area`)}</span>
          {questions.map((q) => {
            const done = answered[q.alert_id];
            return (
              <div key={q.alert_id} className="ml-alert" style={{ borderLeftColor: "var(--terra, #1f5137)" }}>
                {done ? (
                  <p style={{ margin: 0, color: "var(--ok, #2E9E67)", fontWeight: 600 }}>
                    ✓ {t("Cảm ơn bạn đã trả lời!", "Thanks for answering!")}
                  </p>
                ) : (
                  <>
                    <p style={{ margin: "0 0 8px", fontWeight: 600 }}>{q.question}</p>
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      {([["yes", "Có", "Yes"], ["no", "Không", "No"], ["unsure", "Không rõ", "Not sure"]] as const).map(([v, labelVi, labelEn]) => (
                        <button key={v} onClick={() => answer(q, v as "yes" | "no" | "unsure")}
                          style={{ padding: "6px 16px", borderRadius: 6, cursor: "pointer",
                            border: "1px solid var(--line, #d7ddd8)", background: "transparent",
                            color: "var(--ink, #0f1411)", fontWeight: 600 }}>
                          {t(labelVi, labelEn)}
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </div>
            );
          })}
        </div>
      )}

      {alerts.length > 0 && (
        <div className="ml-alerts">
          <span className="ml-cap">⚠️ {t(`${alerts.length} việc sắp tới cần chú ý`, `${alerts.length} upcoming item(s) needing attention`)}</span>
          {alerts.map((a) => (
            <div
              key={a.id}
              className="ml-alert"
              style={{ borderLeftColor: RISK_COLOR[a.risk_level] ?? "#5a6b73" }}
            >
              <div className="ml-alert-top">
                <span className="ml-alert-plot">{plotName(a.plot_id)}</span>
                <button className="ml-ack" onClick={() => ack(a.id)}>{t("đã xem", "seen")}</button>
              </div>
              <p className="ml-alert-head">{a.headline}</p>
              {a.recommendation && <p className="ml-alert-do">→ {a.recommendation}</p>}
            </div>
          ))}
          <p className="ml-disclaimer">
            ⚠️ {t("Dự báo có sai số, không thay thế chỉ đạo của cơ quan phòng chống thiên tai địa phương.",
                  "Forecasts carry error and do not replace guidance from local disaster-prevention authorities.")}{" "}
            <a href="/about">{t("Xem tỉ lệ đúng/sai", "See the accuracy rate")}</a>.
          </p>
        </div>
      )}

      {alerts.length === 0 && (
        <p className="ml-calm">✅ {t("Chưa có rủi ro mới ở các thửa đã lưu. Yên tâm — có gì TerraTwin sẽ báo.",
                                       "No new risk on your saved plots. Rest easy — TerraTwin will alert you if anything comes up.")}</p>
      )}

      <span className="ml-cap">{t("Thửa của bạn", "Your plots")}</span>
      <div className="ml-plots">
        {plots.map((p) => (
          <div key={p.id}>
            <div style={{ display: "flex", alignItems: "stretch", gap: 4 }}>
              <button
                className="ml-plot"
                style={{ flex: 1 }}
                onClick={() => onOpen(p.lat, p.lon, p.name)}
              >
                <span
                  className="ml-grade"
                  style={{ background: GRADE_COLOR[p.grade ?? ""] ?? "#5a6b73" }}
                >
                  {p.grade ?? "—"}
                </span>
                <span className="ml-plot-info">
                  <span className="ml-plot-name">{p.name}</span>
                  <span className="ml-plot-meta">
                    {p.lat.toFixed(3)}, {p.lon.toFixed(3)}
                    {p.area_ha ? ` · ${p.area_ha} ha` : ""}
                  </span>
                </span>
                <span className="ml-open">{t("mở →", "open →")}</span>
              </button>
              {/* Đ9 — dòng thời gian thửa ngay tại "Thửa của tôi" (gộp H4). */}
              <button
                onClick={() => setOpenId(openId === p.id ? null : p.id)}
                aria-label={openId === p.id ? t("Ẩn lịch sử thửa", "Hide plot history") : t("Xem lịch sử thửa", "View plot history")}
                title={openId === p.id ? t("Ẩn lịch sử", "Hide history") : t("Lịch sử: đã báo gì, đúng/hụt", "History: what was reported, right/wrong")}
                style={{ padding: "0 12px", borderRadius: 8, cursor: "pointer",
                  border: "1px solid var(--line, #d7ddd8)", background: "transparent",
                  color: "var(--ink-2, #333d36)", fontSize: 16 }}
              >
                📜
              </button>
            </div>
            {openId === p.id && <PlotHistory plotId={p.id} />}
          </div>
        ))}
      </div>

      <div className="ml-or"><span>{t("hoặc xem một thửa mới", "or view a new plot")}</span></div>
    </div>
  );
}
