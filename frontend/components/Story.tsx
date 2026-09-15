"use client";

/**
 * Chế độ "Câu chuyện" — 90 giây cho người mở lần đầu / ban giám khảo.
 *
 * VÌ SAO CẦN: phần mềm có rất nhiều chiều sâu nhưng nằm dưới màn cuộn, và lần
 * đầu mở một nơi mới thì chờ ~15 giây mới thấy gì. Người xem chưa kịp hiểu đã
 * đóng. Chế độ này dẫn đúng ba nước đắt giá nhất, mỗi nước dùng DỮ LIỆU THẬT của
 * một thảm họa có thật (lũ Huế 10/2020), không phải ảnh minh họa:
 *   1. NHÌN THẤY đất thật từ vệ tinh
 *   2. BIẾT TRƯỚC — và có bằng chứng backtest (báo trước mấy ngày, báo bừa mấy %)
 *   3. XEM kịch bản tương lai phủ trên ảnh thật
 *
 * Không dựng số liệu giả để cho đẹp: mọi con số ở đây gọi thẳng API như khi
 * người dùng tự bấm.
 */

import { useEffect, useState } from "react";
import {
  getImagery,
  getScorecard,
  runBacktest,
  runFuture,
  type Imagery,
  type BacktestResult,
  type FutureResult,
  type Scorecard as SC,
} from "@/lib/api";
import { useLang } from "@/lib/i18n";

// Lũ lịch sử Thừa Thiên Huế 10/2020 — sự kiện có thật, có tài liệu, và model
// backtest được: báo trước nhiều ngày với tỉ lệ báo bừa thấp.
const HUE = { lat: 16.46, lon: 107.59, name: "Huế" };

export default function Story({ onClose, onExplore }: {
  onClose: () => void;
  onExplore: (lat: number, lon: number, label: string) => void;
}) {
  const { t } = useLang();
  const [step, setStep] = useState(0);
  const [img, setImg] = useState<Imagery | null>(null);
  const [bt, setBt] = useState<BacktestResult | null>(null);
  const [fut, setFut] = useState<FutureResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [sc, setSc] = useState<SC | null>(null);   // T4 — sổ điểm tự chấm toàn hệ thống

  // T4 — tải sổ điểm tổng một lần: gắn bằng chứng backtest MỘT sự kiện với con
  // số tự chấm trên MỌI cảnh báo, để câu chuyện không dựa vào đúng một ví dụ đẹp.
  useEffect(() => {
    let dead = false;
    getScorecard(90).then((r) => !dead && setSc(r)).catch(() => {});
    return () => { dead = true; };
  }, []);

  // Tải dữ liệu cho từng bước khi tới bước đó (lazy) — không nã hết một lúc.
  useEffect(() => {
    let dead = false;
    setBusy(true);
    const job =
      step === 0 && !img ? getImagery(HUE.lat, HUE.lon).then((r) => !dead && setImg(r))
      : step === 1 && !bt ? runBacktest("hue_flood_2020").then((r) => !dead && setBt(r))
      : step === 2 && !fut ? runFuture("flood", HUE.lat, HUE.lon).then((r) => !dead && setFut(r))
      : Promise.resolve();
    job.catch(() => {}).finally(() => !dead && setBusy(false));
    return () => { dead = true; };
  }, [step]); // eslint-disable-line react-hooks/exhaustive-deps

  const steps = [
    {
      cap: t("Bước 1/3 · Nhìn thấy đất thật", "Step 1/3 · See the real land"),
      title: t("Không phải app thời tiết — bạn thấy CHÍNH mảnh đất",
               "Not a weather app — you see YOUR actual plot"),
      body: t("TerraTwin lấy ảnh vệ tinh Sentinel-2 thật của đúng thửa, không cần đăng ký khoá nào.",
              "TerraTwin pulls real Sentinel-2 imagery of the exact plot, no API key needed."),
    },
    {
      cap: t("Bước 2/3 · Biết trước, có bằng chứng", "Step 2/3 · Warn early, with proof"),
      title: t("Đã kiểm chứng trên thảm họa THẬT: lũ Huế 10/2020",
               "Validated on a REAL disaster: the Oct 2020 Huế flood"),
      body: t("Chạy đúng mô hình cảnh báo trên dữ liệu lịch sử — đo xem nó báo trước mấy ngày, và quan trọng hơn: báo bừa bao nhiêu %.",
              "Runs the same alert model on historical data — measuring how many days ahead it warns, and more importantly: its false-alarm rate."),
    },
    {
      cap: t("Bước 3/3 · Xem trước tương lai", "Step 3/3 · Preview the future"),
      title: t("Ảnh tương lai: thật ở dưới, dự phóng ở trên",
               "Future imagery: real below, projection on top"),
      body: t("Phủ kịch bản lên chính ảnh vệ tinh thật — nền là quan sát, lớp phủ là dự đoán có nhãn. Không điểm ảnh nào do AI bịa.",
              "Overlays scenarios on the real satellite image — the base is observation, the overlay is a labeled projection. No pixel is AI-fabricated."),
    },
  ];
  const s = steps[step];

  return (
    <div className="story-back" onClick={onClose}>
      <div className="story" onClick={(e) => e.stopPropagation()}>
        <button className="story-x" onClick={onClose} aria-label={t("Đóng", "Close")}>✕</button>
        <span className="story-cap">{s.cap}</span>
        <h2 className="story-title">{s.title}</h2>
        <p className="story-body">{s.body}</p>

        <div className="story-stage">
          {busy && <div className="story-load"><span className="ans-spin" /> {t("Đang lấy dữ liệu thật…", "Fetching real data…")}</div>}

          {step === 0 && img?.available && (
            <div className="story-imgwrap">
              <img className="story-img" src={img.now.true_color} alt={`Ảnh vệ tinh Huế ${img.now.date}`} />
              <span className="story-tag">🛰️ {t("Ảnh thật", "Real image")} {img.now.date} · {t("mây", "cloud")} {img.now.cloud_scene_pct}%</span>
            </div>
          )}
          {step === 0 && img && !img.available && (
            <p className="story-note">{img.message} {t("(mùa mưa Huế mây che — chính điều phần mềm nói thẳng thay vì giấu.)",
                                                       "(Huế's rainy season is cloudy — which the app states plainly rather than hiding.)")}</p>
          )}

          {step === 1 && bt?.available && (
            <div className="story-bt">
              <div className={`story-verdict ${bt.success ? "ok" : "no"}`}>{bt.verdict}</div>
              <div className="story-tiers">
                {bt.lead_days_warning != null && (
                  <div className="story-lead"><b>{bt.lead_days_warning}</b><span>{t("ngày báo trước", "days early")}<br/><small>{t("mức cảnh báo", "at warning level")}</small></span></div>
                )}
                {bt.alarm_rate && (
                  <div className="story-lead"><b>{bt.alarm_rate.alarm_rate_pct}%</b><span>{t("tỉ lệ báo bừa", "false-alarm rate")}<br/><small>{t("10 năm tại điểm này", "10 years at this point")}</small></span></div>
                )}
              </div>
              <p className="story-note">{t("Lead time chỉ có nghĩa khi đi kèm tỉ lệ báo bừa — một model luôn hét \"nguy hiểm\" cũng bắt trúng mọi thảm họa.",
                                          "Lead time only matters alongside the false-alarm rate — a model that always screams \"danger\" also catches every disaster.")}</p>
            </div>
          )}
          {step === 1 && bt && !bt.available && (
            <p className="story-note">{bt.message ?? t("Nguồn dữ liệu lịch sử tạm bận, thử lại sau ít phút.", "The historical data source is busy, try again shortly.")}</p>
          )}

          {/* T4 — gắn backtest MỘT sự kiện với sổ điểm tự chấm trên MỌI cảnh báo,
              để câu chuyện không dựa vào đúng một ví dụ đẹp. Trung thực: chưa đủ
              mẫu thì nói thẳng, không bịa tỉ lệ. */}
          {step === 1 && sc && (
            <div style={{
              marginTop: 12, padding: "10px 14px", borderRadius: 8,
              background: "var(--surface-2, #f8faf7)", border: "1px solid var(--line, #d7ddd8)",
            }}>
              {sc.enough ? (
                <p className="story-note" style={{ margin: 0 }}>
                  🎯 <b>{t("Sổ điểm tự chấm toàn hệ thống", "System-wide self-scorecard")}</b> {t("(90 ngày, không chỉ ví dụ này): bắt được", "(90 days, not just this example): caught")} <b>{sc.pod_pct}%</b> {t("số đợt thật · báo bừa", "of real events · false alarms")}{" "}
                  <b>{sc.far_pct}%</b>. {t("Phần mềm tự chấm về chính mình, không sửa được từ giao diện.", "The software scores itself and can't be edited from the UI.")}
                </p>
              ) : (
                <p className="story-note" style={{ margin: 0 }}>
                  🎯 <b>{t("Sổ điểm tự chấm toàn hệ thống:", "System-wide self-scorecard:")}</b> {t("chưa đủ cảnh báo thật để công bố tỉ lệ — nên backtest trên thảm họa lịch sử THẬT (ở trên) là bằng chứng hiện có. Con số sẽ tự hiện khi cảnh báo thật đầu tiên đủ tuổi để chấm.", "not enough real alerts to publish rates yet — so the backtest on a REAL historical disaster (above) is the evidence for now. Numbers appear once the first real alerts are old enough to score.")} <b>{t("Không bịa số để trông đẹp.", "No fabricated numbers to look good.")}</b>
                </p>
              )}
            </div>
          )}

          {step === 2 && fut?.available && fut.base_image && (
            <div className="story-imgwrap">
              <img className="story-img" src={fut.base_image.true_color} alt="Ảnh tương lai Huế" />
              {(() => {
                const sc = (fut.scenarios ?? []).reduce((a, b) => (b.peak > a.peak ? b : a), (fut.scenarios ?? [{ peak: 0, opacity: 0 } as any])[0]);
                return <div className="story-overlay" style={{ backgroundColor: fut.overlay_color, opacity: sc?.opacity ?? 0.2 }} />;
              })()}
              <span className="story-tag">{t("DỰ PHÓNG · nền ảnh thật", "PROJECTION · real image base")} {fut.base_image.date}</span>
            </div>
          )}
          {step === 2 && fut && (!fut.available || !fut.base_image) && (
            <p className="story-note">{fut.base_message ?? fut.message ?? t("Chưa dựng được ảnh tương lai cho điểm này.", "Couldn't build future imagery for this point.")}</p>
          )}
        </div>

        <div className="story-nav">
          <button className="ghost" onClick={onClose}>{t("Bỏ qua", "Skip")}</button>
          <div className="story-dots">
            {steps.map((_, i) => <i key={i} className={i === step ? "on" : ""} />)}
          </div>
          {step < 2 ? (
            <button onClick={() => setStep((x) => x + 1)}>{t("Tiếp →", "Next →")}</button>
          ) : (
            <button onClick={() => { onClose(); onExplore(HUE.lat, HUE.lon, HUE.name); }}>
              {t("Tự khám phá Huế →", "Explore Huế yourself →")}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
