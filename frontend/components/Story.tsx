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
  runBacktest,
  runFuture,
  type Imagery,
  type BacktestResult,
  type FutureResult,
} from "@/lib/api";

// Lũ lịch sử Thừa Thiên Huế 10/2020 — sự kiện có thật, có tài liệu, và model
// backtest được: báo trước nhiều ngày với tỉ lệ báo bừa thấp.
const HUE = { lat: 16.46, lon: 107.59, name: "Huế" };

export default function Story({ onClose, onExplore }: {
  onClose: () => void;
  onExplore: (lat: number, lon: number, label: string) => void;
}) {
  const [step, setStep] = useState(0);
  const [img, setImg] = useState<Imagery | null>(null);
  const [bt, setBt] = useState<BacktestResult | null>(null);
  const [fut, setFut] = useState<FutureResult | null>(null);
  const [busy, setBusy] = useState(false);

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
      cap: "Bước 1/3 · Nhìn thấy đất thật",
      title: "Không phải app thời tiết — bạn thấy CHÍNH mảnh đất",
      body: "TerraTwin lấy ảnh vệ tinh Sentinel-2 thật của đúng thửa, không cần đăng ký khoá nào.",
    },
    {
      cap: "Bước 2/3 · Biết trước, có bằng chứng",
      title: "Đã kiểm chứng trên thảm họa THẬT: lũ Huế 10/2020",
      body: "Chạy đúng mô hình cảnh báo trên dữ liệu lịch sử — đo xem nó báo trước mấy ngày, và quan trọng hơn: báo bừa bao nhiêu %.",
    },
    {
      cap: "Bước 3/3 · Xem trước tương lai",
      title: "Ảnh tương lai: thật ở dưới, dự phóng ở trên",
      body: "Phủ kịch bản lên chính ảnh vệ tinh thật — nền là quan sát, lớp phủ là dự đoán có nhãn. Không điểm ảnh nào do AI bịa.",
    },
  ];
  const s = steps[step];

  return (
    <div className="story-back" onClick={onClose}>
      <div className="story" onClick={(e) => e.stopPropagation()}>
        <button className="story-x" onClick={onClose} aria-label="Đóng">✕</button>
        <span className="story-cap">{s.cap}</span>
        <h2 className="story-title">{s.title}</h2>
        <p className="story-body">{s.body}</p>

        <div className="story-stage">
          {busy && <div className="story-load"><span className="ans-spin" /> Đang lấy dữ liệu thật…</div>}

          {step === 0 && img?.available && (
            <div className="story-imgwrap">
              <img className="story-img" src={img.now.true_color} alt={`Ảnh vệ tinh Huế ${img.now.date}`} />
              <span className="story-tag">🛰️ Ảnh thật {img.now.date} · mây {img.now.cloud_scene_pct}%</span>
            </div>
          )}
          {step === 0 && img && !img.available && (
            <p className="story-note">{img.message} (mùa mưa Huế mây che — chính điều phần mềm nói thẳng thay vì giấu.)</p>
          )}

          {step === 1 && bt?.available && (
            <div className="story-bt">
              <div className={`story-verdict ${bt.success ? "ok" : "no"}`}>{bt.verdict}</div>
              <div className="story-tiers">
                {bt.lead_days_warning != null && (
                  <div className="story-lead"><b>{bt.lead_days_warning}</b><span>ngày báo trước<br/><small>mức cảnh báo</small></span></div>
                )}
                {bt.alarm_rate && (
                  <div className="story-lead"><b>{bt.alarm_rate.alarm_rate_pct}%</b><span>tỉ lệ báo bừa<br/><small>10 năm tại điểm này</small></span></div>
                )}
              </div>
              <p className="story-note">Lead time chỉ có nghĩa khi đi kèm tỉ lệ báo bừa — một model luôn hét "nguy hiểm" cũng bắt trúng mọi thảm họa.</p>
            </div>
          )}
          {step === 1 && bt && !bt.available && (
            <p className="story-note">{bt.message ?? "Nguồn dữ liệu lịch sử tạm bận, thử lại sau ít phút."}</p>
          )}

          {step === 2 && fut?.available && fut.base_image && (
            <div className="story-imgwrap">
              <img className="story-img" src={fut.base_image.true_color} alt="Ảnh tương lai Huế" />
              {(() => {
                const sc = (fut.scenarios ?? []).reduce((a, b) => (b.peak > a.peak ? b : a), (fut.scenarios ?? [{ peak: 0, opacity: 0 } as any])[0]);
                return <div className="story-overlay" style={{ backgroundColor: fut.overlay_color, opacity: sc?.opacity ?? 0.2 }} />;
              })()}
              <span className="story-tag">DỰ PHÓNG · nền ảnh thật {fut.base_image.date}</span>
            </div>
          )}
          {step === 2 && fut && (!fut.available || !fut.base_image) && (
            <p className="story-note">{fut.base_message ?? fut.message ?? "Chưa dựng được ảnh tương lai cho điểm này."}</p>
          )}
        </div>

        <div className="story-nav">
          <button className="ghost" onClick={onClose}>Bỏ qua</button>
          <div className="story-dots">
            {steps.map((_, i) => <i key={i} className={i === step ? "on" : ""} />)}
          </div>
          {step < 2 ? (
            <button onClick={() => setStep((x) => x + 1)}>Tiếp →</button>
          ) : (
            <button onClick={() => { onClose(); onExplore(HUE.lat, HUE.lon, HUE.name); }}>
              Tự khám phá Huế →
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
