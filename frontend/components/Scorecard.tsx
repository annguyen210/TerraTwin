"use client";

/**
 * SỔ ĐIỂM TỰ CHẤM — "Vì sao tin được", phần công khai.
 *
 * VÌ SAO. Điểm mạnh nhất của TerraTwin (báo động giả thấp nhờ hiệu chuẩn) là
 * thứ vô hình: một lần KHÔNG kêu oan thì không ai thấy. Trang này làm nó hiện
 * lên bằng con số phần mềm TỰ CHẤM về chính mình — POD (bắt được bao nhiêu %
 * đợt thật), FAR (báo bừa), CSI (điểm tổng) — không sửa được từ giao diện.
 *
 * DÙNG ĐƯỢC HAI KIỂU:
 *   <Scorecard data={sc} />   — nhận sẵn số liệu (trang đón đã gọi 1 lần, khỏi
 *                               gọi lại; null trong lúc đang tải).
 *   <Scorecard onClose={..} /> — tự gọi số liệu, hiện dạng cửa sổ nổi (modal).
 *
 * Trung thực trước hết: chưa đủ mẫu thì KHÔNG tô hồng — hiện thẳng "chưa đủ để
 * công bố tỉ lệ". Kho quan sát thực địa (ground-truth) cũng hiện, vì đó là tài
 * sản không tải được từ vệ tinh.
 */

import { useEffect, useRef, useState } from "react";
import {
  getReliability,
  getScorecard,
  getScorecardTimeline,
  trackEvent,
  type ReliabilityResult,
  type Scorecard as SC,
  type ScorecardBucket,
} from "@/lib/api";
import { useLang } from "@/lib/i18n";

const fmtPct = (v: number | null) => (v == null ? "—" : `${v}%`);

/**
 * H2 — XU HƯỚNG BÁO BỪA THEO THỜI GIAN.
 *
 * Sổ điểm cho một con số hôm nay; biểu đồ này cho biết con số đó đang tốt lên
 * hay xấu đi. Nếu vòng lặp hiệu chỉnh có tác dụng thì cột báo bừa (FAR) phải
 * thấp dần. Trung thực trước hết: kỳ nào CHƯA có cảnh báo được chấm thì cột để
 * mờ, và nếu chưa kỳ nào có thì nói thẳng chứ không vẽ một đường phẳng giả.
 */
function ScoreTrend({ buckets, t }: {
  buckets: ScorecardBucket[]; t: (vi: string, en: string) => string;
}) {
  const anyScored = buckets.some((b) => b.scored > 0);
  const monthOf = (iso: string) => iso.slice(5, 7);
  return (
    <div className="sc-trend" style={{ marginTop: 16 }}>
      <h4 style={{ marginBottom: 6 }}>
        📈 {t("Xu hướng báo bừa theo thời gian", "False-alarm trend over time")}
      </h4>
      {!anyScored ? (
        <p className="sc-gt-note">
          {t("Chưa kỳ nào có cảnh báo được chấm — biểu đồ xu hướng sẽ hiện dần khi cảnh báo thật đầu tiên đủ tuổi để chấm.",
             "No period has scored alerts yet — this trend fills in as the first real alerts age enough to be scored.")}
        </p>
      ) : (
        <>
          <div style={{
            display: "flex", alignItems: "flex-end", gap: 4, height: 68,
            padding: "6px 2px 0", borderBottom: "1px solid var(--line, #d7ddd8)",
          }}>
            {buckets.map((b, i) => {
              const far = b.far_pct;
              const h = far == null ? 0 : Math.max(3, far);   // % chiều cao
              const scored = b.scored > 0;
              return (
                <div key={i} title={`${b.from} → ${b.to}\n${b.scored} ${t("cảnh báo", "alerts")}${far == null ? "" : ` · FAR ${far}%`}`}
                     style={{ flex: 1, display: "flex", alignItems: "flex-end", height: "100%" }}>
                  <div style={{
                    width: "100%", height: `${h}%`,
                    background: scored ? "var(--bad, #e5705a)" : "var(--line, #d7ddd8)",
                    opacity: scored ? 0.9 : 0.35, borderRadius: "2px 2px 0 0",
                    minHeight: scored ? 3 : 2,
                  }} />
                </div>
              );
            })}
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--dim, #66716a)", marginTop: 3 }}>
            <span>{t("tháng", "mo.")} {monthOf(buckets[0].from)}</span>
            <span>{t("tháng", "mo.")} {monthOf(buckets[buckets.length - 1].to)}</span>
          </div>
          <p className="sc-gt-note">
            {t("Cột thấp dần = vòng lặp hiệu chỉnh đang có tác dụng. Cột mờ = kỳ chưa có cảnh báo nào được chấm.",
               "Bars trending down = the calibration loop is working. Faint bars = periods with no scored alerts yet.")}
          </p>
        </>
      )}
    </div>
  );
}

function Rate({ label, value, tone, hint }: {
  label: string; value: number | null; tone: string; hint: string;
}) {
  return (
    <div className="sc-rate">
      <span className="sc-rate-val" style={{ color: value == null ? "var(--dim)" : tone }}>
        {fmtPct(value)}
      </span>
      <span className="sc-rate-lbl">{label}</span>
      <span className="sc-rate-hint">{hint}</span>
    </div>
  );
}

export default function Scorecard({ data, onClose }: {
  data?: SC | null;
  onClose?: () => void;
}) {
  // Chế độ tự-gọi chỉ bật khi KHÔNG được truyền `data` (kể cả null). `null` là
  // "đang tải, do bên ngoài quản"; `undefined` là "không ai truyền → tự lo".
  const { t } = useLang();
  const selfFetch = data === undefined;
  const [fetched, setFetched] = useState<SC | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [rel, setRel] = useState<ReliabilityResult | null>(null);
  const [tl, setTl] = useState<ScorecardBucket[] | null>(null);   // H2
  const rootRef = useRef<HTMLDivElement>(null);                   // N6 view_scorecard
  const sc = selfFetch ? fetched : data;

  // N6 — đếm "view_scorecard" khi sổ điểm THẬT SỰ vào tầm nhìn (cuộn tới), một
  // lần duy nhất. Không đếm lúc mount vì trang đón nào cũng nhúng sẵn → sẽ trùng
  // với "open" và mất hết ý nghĩa của phễu.
  useEffect(() => {
    const el = rootRef.current;
    if (!el || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) {
        trackEvent("view_scorecard");
        io.disconnect();
      }
    }, { threshold: 0.4 });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  useEffect(() => {
    if (!selfFetch) return;
    let live = true;
    getScorecard(90)
      .then((d) => live && setFetched(d))
      .catch((e) => live && setErr(e.message));
    return () => { live = false; };
  }, [selfFetch]);

  useEffect(() => {
    let live = true;
    getReliability(365).then((r) => live && setRel(r)).catch(() => {});
    getScorecardTimeline(180, 12)
      .then((r) => live && setTl(r.buckets)).catch(() => {});   // H2
    return () => { live = false; };
  }, []);

  const body = (
    <div className="sc" ref={rootRef}>
      <div className="sc-head">
        <div>
          <h3 className="sc-title">🎯 {t("Sổ điểm tự chấm — vì sao tin được", "Self-scorecard — why to trust it")}</h3>
          <p className="sc-sub">
            {t("TerraTwin tự chấm về chính mình, không sửa được từ giao diện. 90 ngày gần nhất.",
               "TerraTwin scores itself — not editable from the UI. Last 90 days.")}
          </p>
        </div>
        {onClose && (
          <button className="sc-close" onClick={onClose} aria-label="Đóng">✕</button>
        )}
      </div>

      {err && <p className="sc-err">{t("Chưa tải được sổ điểm:", "Couldn't load the scorecard:")} {err}</p>}
      {!sc && !err && <p className="sc-load">{t("Đang tải sổ điểm…", "Loading scorecard…")}</p>}

      {sc && (
        <>
          <p className={`sc-headline${sc.enough ? " ok" : ""}`}>{sc.headline}</p>

          {sc.enough && (
            <div className="sc-rates">
              <Rate label={t("Bắt được", "Caught")} value={sc.pod_pct} tone="var(--ok)"
                    hint={t("% số đợt thực tế mà TerraTwin có báo trước",
                            "% of real events TerraTwin warned about")} />
              <Rate label={t("Báo bừa", "False alarm")} value={sc.far_pct} tone="var(--bad)"
                    hint={t("% lần báo mà thực tế không xảy ra",
                            "% of alerts where nothing happened")} />
              <Rate label={t("Điểm tổng (CSI)", "Overall (CSI)")} value={sc.csi_pct} tone="var(--terra)"
                    hint={t("gộp cả bắt được lẫn báo bừa", "combines catch rate and false alarms")} />
            </div>
          )}

          {/* Đếm thô — luôn hiện, kể cả khi chưa đủ mẫu */}
          <div className="sc-counts">
            <div><b>{sc.counts.hit ?? 0}</b><span>{t("báo đúng", "correct")}</span></div>
            <div><b>{sc.counts.false_alarm ?? 0}</b><span>{t("báo bừa", "false")}</span></div>
            <div><b>{sc.counts.miss ?? 0}</b><span>{t("bỏ sót", "missed")}</span></div>
            <div><b>{sc.pending}</b><span>{t("đang chờ chấm", "pending")}</span></div>
          </div>

          {/* H2 — xu hướng báo bừa theo thời gian */}
          {tl && <ScoreTrend buckets={tl} t={t} />}

          {/* Kho quan sát thực địa = moat */}
          <div className="sc-gt">
            <h4>🌾 {t("Kho quan sát thực địa", "Field-observation store")}</h4>
            <div className="sc-gt-row">
              <div><b>{sc.ground_truth.observations}</b><span>{t("quan sát", "observations")}</span></div>
              <div><b>{sc.ground_truth.by_onetap}</b><span>{t("qua một chạm", "via one-tap")}</span></div>
              <div><b>{sc.ground_truth.cells_covered}</b><span>{t("vùng (~55 km)", "regions (~55 km)")}</span></div>
            </div>
            <p className="sc-gt-note">{sc.ground_truth.note}</p>
          </div>

          {/* Tách theo mô-đun — chỉ những mục đã có lần chấm */}
          {sc.by_module.some((m) => m.scored > 0) && (
            <div className="sc-mods">
              <h4>{t("Theo từng mũi nhọn", "By spearhead")}</h4>
              <table>
                <thead>
                  <tr>
                    <th>{t("Mũi nhọn", "Spearhead")}</th>
                    <th>{t("Đã chấm", "Scored")}</th>
                    <th>{t("Bắt được", "Caught")}</th>
                    <th>{t("Báo bừa", "False")}</th>
                  </tr>
                </thead>
                <tbody>
                  {sc.by_module.filter((m) => m.scored > 0).map((m) => (
                    <tr key={m.module_id}>
                      <td>{m.name}</td>
                      <td className="sc-num">{m.scored}</td>
                      <td className="sc-num">{m.enough ? fmtPct(m.pod_pct) : "—"}</td>
                      <td className="sc-num">{m.enough ? fmtPct(m.far_pct) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Độ tin cậy theo vùng — nơi mô hình ĐÃ được kiểm chứng (lớn dần theo moat) */}
          {rel && (
            <div className="sc-rel">
              <h4>🗺️ {t("Độ tin cậy theo vùng", "Reliability by region")}</h4>
              {rel.cells.length === 0 ? (
                <p className="sc-gt-note">
                  {t("Chưa vùng nào đủ mẫu — bản đồ này lớn dần khi người dùng gửi quan sát thực địa về.",
                     "No region has enough samples yet — this map grows as users send field observations back.")}
                </p>
              ) : (
                <>
                  <div className="sc-rel-list">
                    {rel.cells.slice(0, 6).map((c) => (
                      <div key={c.cell} className={`sc-rel-cell${c.enough ? " ok" : ""}`}>
                        <b>{c.lat.toFixed(1)}, {c.lon.toFixed(1)}</b>
                        {c.enough ? (
                          <span>{t("bắt", "POD")} {fmtPct(c.pod_pct)} · {t("bừa", "FAR")} {fmtPct(c.far_pct)}</span>
                        ) : (
                          <span>{t("đang tích luỹ", "accumulating")} {c.scored}/{rel.min_cell_sample}</span>
                        )}
                      </div>
                    ))}
                  </div>
                  <p className="sc-gt-note">{rel.note}</p>
                </>
              )}
            </div>
          )}

          <p className="sc-method">{sc.method}</p>
        </>
      )}
    </div>
  );

  if (!onClose) return body;
  return (
    <div className="sc-overlay" onClick={onClose}>
      <div className="sc-modal" onClick={(e) => e.stopPropagation()}>{body}</div>
    </div>
  );
}
