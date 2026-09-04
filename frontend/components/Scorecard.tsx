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

import { useEffect, useState } from "react";
import { getScorecard, type Scorecard as SC } from "@/lib/api";

const fmtPct = (v: number | null) => (v == null ? "—" : `${v}%`);

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
  const selfFetch = data === undefined;
  const [fetched, setFetched] = useState<SC | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const sc = selfFetch ? fetched : data;

  useEffect(() => {
    if (!selfFetch) return;
    let live = true;
    getScorecard(90)
      .then((d) => live && setFetched(d))
      .catch((e) => live && setErr(e.message));
    return () => { live = false; };
  }, [selfFetch]);

  const body = (
    <div className="sc">
      <div className="sc-head">
        <div>
          <h3 className="sc-title">🎯 Sổ điểm tự chấm — vì sao tin được</h3>
          <p className="sc-sub">
            TerraTwin tự chấm về chính mình, không sửa được từ giao diện. 90 ngày gần nhất.
          </p>
        </div>
        {onClose && (
          <button className="sc-close" onClick={onClose} aria-label="Đóng">✕</button>
        )}
      </div>

      {err && <p className="sc-err">Chưa tải được sổ điểm: {err}</p>}
      {!sc && !err && <p className="sc-load">Đang tải sổ điểm…</p>}

      {sc && (
        <>
          <p className={`sc-headline${sc.enough ? " ok" : ""}`}>{sc.headline}</p>

          {sc.enough && (
            <div className="sc-rates">
              <Rate label="Bắt được" value={sc.pod_pct} tone="var(--ok)"
                    hint="% số đợt thực tế mà TerraTwin có báo trước" />
              <Rate label="Báo bừa" value={sc.far_pct} tone="var(--bad)"
                    hint="% lần báo mà thực tế không xảy ra" />
              <Rate label="Điểm tổng (CSI)" value={sc.csi_pct} tone="var(--terra)"
                    hint="gộp cả bắt được lẫn báo bừa" />
            </div>
          )}

          {/* Đếm thô — luôn hiện, kể cả khi chưa đủ mẫu */}
          <div className="sc-counts">
            <div><b>{sc.counts.hit ?? 0}</b><span>báo đúng</span></div>
            <div><b>{sc.counts.false_alarm ?? 0}</b><span>báo bừa</span></div>
            <div><b>{sc.counts.miss ?? 0}</b><span>bỏ sót</span></div>
            <div><b>{sc.pending}</b><span>đang chờ chấm</span></div>
          </div>

          {/* Kho quan sát thực địa = moat */}
          <div className="sc-gt">
            <h4>🌾 Kho quan sát thực địa</h4>
            <div className="sc-gt-row">
              <div><b>{sc.ground_truth.observations}</b><span>quan sát</span></div>
              <div><b>{sc.ground_truth.by_onetap}</b><span>qua một chạm</span></div>
              <div><b>{sc.ground_truth.cells_covered}</b><span>vùng (~55 km)</span></div>
            </div>
            <p className="sc-gt-note">{sc.ground_truth.note}</p>
          </div>

          {/* Tách theo mô-đun — chỉ những mục đã có lần chấm */}
          {sc.by_module.some((m) => m.scored > 0) && (
            <div className="sc-mods">
              <h4>Theo từng mũi nhọn</h4>
              <table>
                <thead>
                  <tr><th>Mũi nhọn</th><th>Đã chấm</th><th>Bắt được</th><th>Báo bừa</th></tr>
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
