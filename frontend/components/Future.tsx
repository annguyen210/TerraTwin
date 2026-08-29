"use client";

/**
 * S10 ③ — ẢNH "TƯƠNG LAI", bản TRUNG THỰC không cần model sinh.
 *
 * Nền là ẢNH VỆ TINH THẬT của thửa (có ngày chụp). Lớp phủ màu là DỰ PHÓNG từ
 * kịch bản Parallel Futures — vẽ như một lớp riêng, trong suốt, có nhãn "DỰ
 * PHÓNG" + mức tin cậy hiện ngay trên ảnh. Người xem luôn phân biệt được đâu là
 * quan sát (nền), đâu là dự đoán (lớp phủ). Không điểm ảnh nào do model bịa ra.
 */

import { useEffect, useState } from "react";
import {
  runFuture,
  FUTURE_MODULES,
  type FutureResult,
  type FutureScenario,
} from "@/lib/api";

export default function Future({
  moduleId,
  lat,
  lon,
}: {
  moduleId: string;
  lat: number;
  lon: number;
}) {
  const [d, setD] = useState<FutureResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [pick, setPick] = useState(0);
  const [loaded, setLoaded] = useState(false);

  const eligible = FUTURE_MODULES.includes(moduleId);

  useEffect(() => {
    if (!eligible) {
      setD(null);
      return;
    }
    let dead = false;
    setBusy(true);
    setD(null);
    setLoaded(false);
    runFuture(moduleId, lat, lon)
      .then((r) => {
        if (dead) return;
        setD(r);
        // Mặc định chọn kịch bản nặng nhất — đó là "tương lai" đáng xem nhất.
        const sc = r.scenarios ?? [];
        if (sc.length) {
          let mi = 0;
          sc.forEach((s, i) => {
            if (s.peak > sc[mi].peak) mi = i;
          });
          setPick(mi);
        }
      })
      .catch(() => !dead && setD(null))
      .finally(() => !dead && setBusy(false));
    return () => {
      dead = true;
    };
  }, [moduleId, lat, lon, eligible]);

  if (!eligible) return null;

  if (busy) {
    return (
      <div className="fut">
        <div className="fut-head">🔮 Ảnh tương lai theo kịch bản</div>
        <p className="hint">Đang ghép ảnh vệ tinh thật với dự phóng…</p>
      </div>
    );
  }
  if (!d || d.available === false || !d.scenarios?.length) {
    return (
      <div className="fut">
        <div className="fut-head">🔮 Ảnh tương lai theo kịch bản</div>
        <p className="hint">{d?.message ?? "Chưa dựng được ảnh tương lai."}</p>
      </div>
    );
  }

  const scenarios = d.scenarios;
  const s: FutureScenario = scenarios[pick] ?? scenarios[0];
  const color = d.overlay_color ?? "#2E6BB0";

  return (
    <div className="fut">
      <div className="fut-head">🔮 Ảnh tương lai — thửa của bạn nếu kịch bản xảy ra</div>

      <div className="fut-scen">
        {scenarios.map((sc, i) => (
          <button
            key={sc.label}
            className={i === pick ? "on" : ""}
            onClick={() => setPick(i)}
            title={sc.caption}
          >
            {sc.label}
          </button>
        ))}
      </div>

      {d.base_image ? (
        <div className="fut-frame">
          {!loaded && <div className="pv-skel" />}
          <img
            className="fut-img"
            src={d.base_image.true_color}
            alt={`Ảnh vệ tinh thật của thửa, chụp ${d.base_image.date}`}
            onLoad={() => setLoaded(true)}
          />
          {/* Lớp phủ DỰ PHÓNG — tách khỏi ảnh: có vân sọc + nhãn nên không ai
              nhầm là ảnh chụp. Độ mờ theo mức độ kịch bản. */}
          <div
            className={`fut-overlay ${s.risk}`}
            style={{
              backgroundColor: color,
              opacity: s.opacity,
            }}
          />
          <span className="fut-badge">DỰ PHÓNG · không phải ảnh chụp</span>
          <span className="fut-date">nền: ảnh thật {d.base_image.date}</span>
          <span className="fut-layerlabel" style={{ color }}>
            ▩ {d.layer_label} · {s.risk_vi}
          </span>
        </div>
      ) : (
        <p className="hint">
          {d.base_message ?? "Chưa có ảnh quang mây cho thửa này (mùa mưa mây che)."}
          {" "}Vẫn xem được dự phóng dạng số bên dưới.
        </p>
      )}

      <p className="fut-cap">{s.caption}</p>

      {d.confidence != null && (
        <p className="fut-conf">
          Độ tin cậy dự phóng: <b>{Math.round(d.confidence * 100)}%</b>
          {d.confidence_low != null && d.confidence_high != null && (
            <>
              {" "}(khoảng {Math.round(d.confidence_low * 100)}–
              {Math.round(d.confidence_high * 100)}%)
            </>
          )}
          {" · "}
          {d.is_real ? "trên nền thời tiết thật" : "mô phỏng"}
        </p>
      )}

      <p className="fut-disc">⚠️ {d.disclaimer}</p>
      {d.source && <p className="fut-src">{d.source}</p>}
    </div>
  );
}
