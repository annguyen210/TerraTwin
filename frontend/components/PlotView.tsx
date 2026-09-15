"use client";

/**
 * CHO NGƯỜI TA THẤY MẢNH ĐẤT CỦA HỌ.
 *
 * Đây là thứ TerraTwin thiếu suốt từ đầu, và là lý do người dùng thử xong nói
 * "sơ sài, chẳng có gì" dù bên trong có 444 test. Sửa điều hướng không hết.
 * Thêm dữ liệu không hết. Vì gốc rễ nằm chỗ khác: cả sản phẩm là MỘT BẢNG CHỮ
 * bên phải màn hình. Bản đồ nhiệt là những ô màu trừu tượng. Người dùng chưa
 * bao giờ NHÌN THẤY thửa đất của mình — họ chỉ đọc câu văn kể về nó.
 *
 * Chữ "Twin" hứa một bản sao của vật thật. Không có hình ảnh nào của vật thật
 * thì lời hứa đó rỗng, và người ta cảm nhận được ngay cả khi không gọi tên ra.
 *
 * BA CÁCH NHÌN, mỗi cách trả lời một câu khác nhau:
 *   Màu thật   "thửa của tôi trông thế nào"   — không cần học gì để đọc
 *   Sức sống   "chỗ nào cây yếu"              — NDVI đỏ → xanh
 *   Đối chiếu  "một năm qua đổi gì"           — kéo thanh trượt giữa hai ảnh
 *
 * HAI ĐIỀU KHÔNG ĐƯỢC GIẤU, và đều hiện ngay trên ảnh:
 *   · NGÀY CHỤP. Ảnh không phải "hôm nay" — Sentinel-2 bay qua mỗi ~5 ngày.
 *     Người xem tưởng đang nhìn hiện tại là hiểu sai nguy hiểm.
 *   · ĐỘ MÂY. Ảnh nhiều mây vẫn được đưa ra kèm con số, chứ không lọc bỏ im
 *     lặng — giấu đi thì người ta tưởng vệ tinh không bay qua.
 */

import { useEffect, useRef, useState } from "react";
import { getImagery, type Imagery } from "@/lib/api";
import { isDataSaver } from "@/lib/net";
import { useLang } from "@/lib/i18n";

type Lop = "true" | "ndvi";

export default function PlotView({ lat, lon }: { lat: number; lon: number }) {
  const { t } = useLang();
  const [d, setD] = useState<Imagery | null>(null);
  const [busy, setBusy] = useState(false);
  const [lop, setLop] = useState<Lop>("true");
  const [soSanh, setSoSanh] = useState(false);
  const [keo, setKeo] = useState(50);
  const [loaded, setLoaded] = useState(false);
  // P2 — tiết kiệm dữ liệu: hoãn tải ảnh (~0,5 MB) sau một cú chạm.
  const [defer, setDefer] = useState(false);
  const khung = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isDataSaver()) { setDefer(true); return; }   // chờ người dùng chạm
    let huy = false;
    setBusy(true);
    setD(null);
    setLoaded(false);
    getImagery(lat, lon)
      .then((r) => !huy && setD(r))
      .catch(() => !huy && setD(null))
      .finally(() => !huy && setBusy(false));
    return () => {
      huy = true;
    };
  }, [lat, lon]);

  function loadNow() {
    setDefer(false);
    setBusy(true);
    getImagery(lat, lon)
      .then(setD)
      .catch(() => setD(null))
      .finally(() => setBusy(false));
  }

  if (defer) {
    return (
      <div className="pv">
        <div className="pv-head">🛰️ Ảnh thửa đất</div>
        <button className="pv-load" onClick={loadNow} style={{
          width: "100%", padding: "14px", borderRadius: 8, cursor: "pointer",
          border: "1px dashed var(--line, #d7ddd8)", background: "var(--surface-2,#f8faf7)",
          color: "var(--ink, #0f1411)", fontWeight: 600 }}>
          📷 {t("Bấm để tải ảnh vệ tinh (~0,5 MB)", "Tap to load satellite image (~0.5 MB)")}
          <br /><small style={{ fontWeight: 400, color: "var(--muted,#66716a)" }}>
            {t("Đang ở chế độ tiết kiệm dữ liệu — ảnh không tự tải.", "Data-saver on — images don't auto-load.")}
          </small>
        </button>
      </div>
    );
  }

  if (busy) {
    return (
      <div className="pv pv-busy">
        <div className="ans-spin" />
        <p>{t("Đang tìm ảnh vệ tinh gần nhất của thửa này…", "Finding the nearest satellite image for this plot…")}</p>
      </div>
    );
  }
  if (!d) return null;

  if (!d.available) {
    return (
      <div className="pv">
        <div className="pv-head">🛰️ {t("Ảnh thửa đất", "Plot imagery")}</div>
        <p className="pv-none">{d.message}</p>
      </div>
    );
  }

  const nay = lop === "true" ? d.now.true_color : d.now.ndvi;
  const xua = d.then
    ? lop === "true"
      ? d.then.true_color
      : d.then.ndvi
    : null;
  const coSoSanh = Boolean(d.then);

  return (
    <div className="pv">
      <div className="pv-head">
        🛰️ {t("Thửa đất của bạn, nhìn từ vệ tinh", "Your plot, seen from satellite")}
      </div>

      <div className="pv-tabs">
        <button className={lop === "true" ? "on" : ""} onClick={() => setLop("true")}>
          {t("Màu thật", "True color")}
        </button>
        <button className={lop === "ndvi" ? "on" : ""} onClick={() => setLop("ndvi")}>
          {t("Sức sống cây", "Plant vigor")}
        </button>
        {coSoSanh && (
          <button
            className={`pv-cmp ${soSanh ? "on" : ""}`}
            onClick={() => setSoSanh(!soSanh)}
          >
            {soSanh ? t("Tắt đối chiếu", "Hide compare") : t("So với năm ngoái", "vs last year")}
          </button>
        )}
      </div>

      <div className="pv-frame" ref={khung}>
        {!loaded && <div className="pv-skel" />}
        <img
          src={nay}
          alt={`Ảnh vệ tinh thửa đất ngày ${d.now.date}`}
          onLoad={() => setLoaded(true)}
          className="pv-img"
        />
        {soSanh && xua && (
          <>
            <div className="pv-old" style={{ width: `${keo}%` }}>
              <img
                src={xua}
                alt={`Ảnh cùng thửa ngày ${d.then!.date}`}
                style={{ width: khung.current?.clientWidth ?? 512 }}
              />
            </div>
            <div className="pv-handle" style={{ left: `${keo}%` }} />
            <input
              className="pv-range"
              type="range"
              min={0}
              max={100}
              value={keo}
              onChange={(e) => setKeo(Number(e.target.value))}
              aria-label="Kéo để so hai thời điểm"
            />
            <span className="pv-tag left">{d.then!.date}</span>
          </>
        )}
        <span className="pv-tag right">{d.now.date}</span>

        {/* Thước tỉ lệ — không có nó thì không ai biết đang nhìn 1 km hay 10 km */}
        <span className="pv-scale">
          <i />
          {d.span_m >= 1000 ? `${(d.span_m / 1000).toFixed(1)} km` : `${d.span_m} m`}
        </span>
      </div>

      {lop === "ndvi" && (
        <div className="pv-legend">
          <span>{t("cây yếu / đất trống", "weak plants / bare soil")}</span>
          <i className="pv-ramp" />
          <span>{t("cây khoẻ", "healthy plants")}</span>
        </div>
      )}

      <p className="pv-meta">
        {t("Chụp", "Taken")} <b>{d.now.date}</b> · {t("mây toàn cảnh", "scene cloud")} {d.now.cloud_scene_pct}% ·
        {t(" mỗi điểm ảnh", " each pixel")} {d.resolution_m}×{d.resolution_m} m
      </p>
      {soSanh && <p className="pv-note">{d.compare_note}</p>}
      <p className="pv-src">{d.source}</p>
    </div>
  );
}
