"use client";

/**
 * C02 + C06 — diễn tiến rủi ro theo NGÀY trên bản đồ, cho cả 4 kịch bản.
 *
 * Bản thiết kế gọi đây là "điểm cộng demo số 1". Nhưng hoạt hình mang ba rủi
 * ro, và mỗi rủi ro ở đây được trả lời bằng một QUYẾT ĐỊNH THIẾT KẾ, không
 * phải một dòng chú thích:
 *
 * ① "Chỉ đẹp hơn, không chính xác hơn"
 *    → Chế độ mặc định KHÔNG phải hoạt hình mà là bản đồ NGÀY ĐẾN: mỗi ô tô
 *      màu theo thời điểm rủi ro chạm ngưỡng. Bản đồ nhiệt cũ chỉ giữ ĐỈNH của
 *      7 ngày và vứt đi thời điểm — nhưng "ngập ngày mai" và "ngập thứ Bảy" là
 *      hai quyết định khác hẳn nhau. Đây là thông tin MỚI, không phải trang trí.
 *
 * ② "Trông chắc chắn hơn thực tế"
 *    → Khi ô hiển thị mịn hơn dữ liệu, cảnh báo hiện NGAY trên khung, không
 *      giấu xuống cuối. Kèm ô vuông tham chiếu vẽ đúng kích thước một điểm dữ
 *      liệu thật, để người dùng NHÌN THẤY độ thô thay vì đọc về nó.
 *
 * ③ "Dễ thành trang trí"
 *    → Mọi thứ nhìn thấy khi chạy đều đọc được bằng SỐ khi đứng yên: ngày, số
 *      ô vượt ngưỡng của ngày đó, ngày đến sớm nhất, số ngày kéo dài. Không tự
 *      động chạy, và tôn trọng prefers-reduced-motion.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  runTimeline, type HeatmapResult, type TimelineResult,
} from "@/lib/api";

// Thang màu theo NGÀY ĐẾN — chuyển từ đỏ (ngay) sang xanh (còn xa).
// Cố ý khác hẳn thang màu mức độ, để không ai đọc nhầm hai bản đồ.
const ARRIVAL_COLORS = [
  "#B32E1C", "#C75A2B", "#D18A38", "#C9B03F",
  "#8FA84A", "#5B9455", "#3F7D5C",
];
const NO_RISK = "#3a4a44";

function riskColor(v: number, safe: number, warn: number) {
  if (v >= warn) return "#C2412E";
  if (v >= safe) return "#B07A2E";
  return "#2E9E67";
}

export default function Timeline({
  moduleId,
  lat,
  lon,
  onHeat,
}: {
  moduleId: string;
  lat: number;
  lon: number;
  onHeat: (h: HeatmapResult | null) => void;
}) {
  const [d, setD] = useState<TimelineResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [scen, setScen] = useState(0);
  const [mode, setMode] = useState<"arrival" | "day">("arrival");
  const [day, setDay] = useState(0);
  const [playing, setPlaying] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const reduced =
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

  async function run() {
    setBusy(true);
    setErr(null);
    try {
      const r = await runTimeline(moduleId, lat, lon, 7, 8);
      setD(r);
      setScen(0);
      setDay(0);
      setMode("arrival");
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  const s = d?.scenarios?.[scen];
  const nDays = d?.dates?.length ?? 0;

  // Đẩy khung hình hiện tại lên bản đồ. Không gọi mạng — mọi giá trị đã có sẵn.
  const paint = useCallback(() => {
    if (!d?.available || !s || !d.cell_dlat || !d.cell_dlon) {
      onHeat(null);
      return;
    }
    const safe = d.safe ?? 40;
    const warn = d.warning ?? 70;
    onHeat({
      module_id: d.module_id ?? moduleId,
      module_name: d.module_name ?? "",
      unit: d.unit ?? "",
      center: d.center ?? { lat, lon },
      radius_km: d.radius_km ?? 8,
      side: d.side ?? 7,
      cell_dlat: d.cell_dlat,
      cell_dlon: d.cell_dlon,
      calibrated: d.calibrated ?? false,
      safe,
      warning: warn,
      n_danger: 0,
      n_warning: 0,
      hottest: null,
      headline: d.headline ?? "",
      cached: false,
      caveat: d.caveat ?? "",
      method: "",
      cells: s.cells.map((c) => {
        if (mode === "arrival") {
          const a = c.arrival_day;
          return {
            lat: c.lat, lon: c.lon,
            value: a,
            risk: a === null ? "safe" : "danger",
            color: a === null ? NO_RISK : ARRIVAL_COLORS[Math.min(a, 6)],
          };
        }
        const v = c.values?.[day] ?? null;
        return {
          lat: c.lat, lon: c.lon, value: v,
          risk: v === null ? "unknown" : "safe",
          color: v === null ? NO_RISK : riskColor(v, safe, warn),
        };
      }),
    });
  }, [d, s, mode, day, moduleId, lat, lon, onHeat]);

  useEffect(() => {
    paint();
  }, [paint]);

  // Dọn lớp phủ khi rời khối, để nó không kẹt lại trên bản đồ.
  useEffect(() => () => onHeat(null), [onHeat]);

  useEffect(() => {
    if (!playing || nDays === 0) return;
    timer.current = setInterval(() => {
      setDay((k) => (k + 1) % nDays);
    }, 900);
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [playing, nDays]);

  const overToday = s?.n_over_by_day?.[day] ?? 0;
  const total = s?.cells.length ?? 0;

  const legend = useMemo(
    () =>
      mode === "arrival"
        ? ARRIVAL_COLORS.map((c, i) => ({ c, t: i === 0 ? "hôm nay" : `+${i}` }))
        : [
            { c: "#2E9E67", t: "an toàn" },
            { c: "#B07A2E", t: "cảnh báo" },
            { c: "#C2412E", t: "nguy hiểm" },
          ],
    [mode],
  );

  return (
    <div className="pan">
      <div className="pan-head">🎬 Diễn tiến trên bản đồ — khi nào, kéo dài bao lâu</div>

      {!d && (
        <>
          <p className="pan-sub">
            Bản đồ nhiệt chỉ cho biết <b>mức độ cao nhất</b> trong 7 ngày. Khối
            này cho biết <b>ngày nào rủi ro tới</b> và <b>kéo dài mấy ngày</b> —
            hai thứ quyết định bạn làm gì, và tốn đúng bằng một lượt bản đồ nhiệt.
          </p>
          <button className="pan-go" disabled={busy} onClick={run}>
            {busy ? "Đang dựng…" : "Dựng diễn tiến"}
          </button>
        </>
      )}

      {err && <p className="pan-err">⚠️ {err}</p>}
      {d && !d.available && <p className="pan-err">⚠️ {d.message}</p>}

      {d?.available && s && (
        <>
          <p className="pan-line">{d.headline}</p>

          {/* ② cảnh báo độ phân giải — ngay trên khung, không giấu xuống dưới */}
          {d.resolution?.oversampled && (
            <div className="tl-res">
              <b>⚠️ Bản đồ mịn hơn dữ liệu</b>
              <p>{d.resolution.note}</p>
            </div>
          )}

          <div className="tl-scen">
            {d.scenarios?.map((x, i) => (
              <button
                key={i}
                className={i === scen ? "on" : ""}
                onClick={() => setScen(i)}
              >
                {x.label}
              </button>
            ))}
          </div>

          <div className="tl-modes">
            <button
              className={mode === "arrival" ? "on" : ""}
              onClick={() => {
                setMode("arrival");
                setPlaying(false);
              }}
            >
              Ngày rủi ro tới
            </button>
            <button
              className={mode === "day" ? "on" : ""}
              onClick={() => setMode("day")}
            >
              Xem từng ngày
            </button>
          </div>

          {/* ③ số liệu luôn hiện — hoạt hình không phải cách duy nhất để đọc */}
          <div className="tl-stats">
            <div>
              <b>{s.cells_affected}</b>
              <span>/{total} ô chạm ngưỡng</span>
            </div>
            <div>
              <b>
                {s.first_arrival_day === null
                  ? "—"
                  : s.first_arrival_day === 0
                    ? "hôm nay"
                    : `+${s.first_arrival_day} ngày`}
              </b>
              <span>sớm nhất</span>
            </div>
            <div>
              <b>{s.max_days_over}</b>
              <span>ngày kéo dài nhất</span>
            </div>
          </div>

          {mode === "day" && (
            <>
              <div className="tl-player">
                <button
                  className="tl-play"
                  onClick={() => setPlaying((p) => !p)}
                  aria-label={playing ? "Dừng" : "Chạy"}
                >
                  {playing ? "❚❚" : "▶"}
                </button>
                <input
                  type="range"
                  min={0}
                  max={Math.max(0, nDays - 1)}
                  value={day}
                  onChange={(e) => {
                    setPlaying(false);
                    setDay(Number(e.target.value));
                  }}
                />
              </div>
              <p className="tl-frame">
                <b>{d.dates?.[day]}</b> · {overToday}/{total} ô vượt ngưỡng
                {reduced && playing && " · đã tắt tự chạy theo thiết lập hệ thống"}
              </p>
              <div className="tl-spark">
                {s.n_over_by_day.map((n, i) => (
                  <button
                    key={i}
                    className={`tl-bar ${i === day ? "on" : ""}`}
                    title={`${d.dates?.[i]}: ${n}/${total} ô`}
                    onClick={() => {
                      setPlaying(false);
                      setDay(i);
                    }}
                  >
                    <i
                      style={{
                        height: `${total ? Math.max(4, (n / total) * 100) : 4}%`,
                      }}
                    />
                  </button>
                ))}
              </div>
            </>
          )}

          <div className="tl-legend">
            {legend.map((l) => (
              <span key={l.t}>
                <i style={{ background: l.c }} />
                {l.t}
              </span>
            ))}
          </div>

          <p className="pan-caveat">{d.caveat}</p>
          {d.resolution && <p className="pan-method">{d.resolution.why}</p>}
        </>
      )}
    </div>
  );
}
