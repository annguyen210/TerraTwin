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

type Lop = "true" | "ndvi";

export default function PlotView({ lat, lon }: { lat: number; lon: number }) {
  const [d, setD] = useState<Imagery | null>(null);
  const [busy, setBusy] = useState(false);
  const [lop, setLop] = useState<Lop>("true");
  const [soSanh, setSoSanh] = useState(false);
  const [keo, setKeo] = useState(50);
  const [loaded, setLoaded] = useState(false);
  const khung = useRef<HTMLDivElement>(null);

  useEffect(() => {
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

  if (busy) {
    return (
      <div className="pv pv-busy">
        <div className="ans-spin" />
        <p>Đang tìm ảnh vệ tinh gần nhất của thửa này…</p>
      </div>
    );
  }
  if (!d) return null;

  if (!d.available) {
    return (
      <div className="pv">
        <div className="pv-head">🛰️ Ảnh thửa đất</div>
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
        🛰️ Thửa đất của bạn, nhìn từ vệ tinh
      </div>

      <div className="pv-tabs">
        <button className={lop === "true" ? "on" : ""} onClick={() => setLop("true")}>
          Màu thật
        </button>
        <button className={lop === "ndvi" ? "on" : ""} onClick={() => setLop("ndvi")}>
          Sức sống cây
        </button>
        {coSoSanh && (
          <button
            className={`pv-cmp ${soSanh ? "on" : ""}`}
            onClick={() => setSoSanh(!soSanh)}
          >
            {soSanh ? "Tắt đối chiếu" : "So với năm ngoái"}
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
          <span>cây yếu / đất trống</span>
          <i className="pv-ramp" />
          <span>cây khoẻ</span>
        </div>
      )}

      <p className="pv-meta">
        Chụp <b>{d.now.date}</b> · mây toàn cảnh {d.now.cloud_scene_pct}% ·
        mỗi điểm ảnh {d.resolution_m}×{d.resolution_m} m
      </p>
      {soSanh && <p className="pv-note">{d.compare_note}</p>}
      <p className="pv-src">{d.source}</p>
    </div>
  );
}
