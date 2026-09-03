"use client";

/**
 * KẾ HOẠCH THỬA CỦA BẠN — tầng "vậy tôi PHẢI LÀM GÌ" mà trước đây thiếu.
 *
 * Trước: chọn chỗ → đọc lưới rủi ro → hết. Rất mông lung. Panel này gom bốn thứ
 * người dùng thật sự cần, ngay dưới lưới rủi ro, thành một câu trả lời hành động:
 *
 *   1. VIỆC CẦN LÀM   — mỗi cảnh báo → việc cụ thể, có NGÀY, nguy hiểm trước.
 *   2. NGÀY AN TOÀN   — 7 ngày tới ngày nào trống để làm đồng.
 *   3. GIÁ TRỊ RỦI RO — quy ra tiền (ƯỚC LƯỢNG, khai báo rõ, đổi theo cây trồng).
 *   4. TRÍ TUỆ VÙNG   — vùng cùng "bộ gen" đất để học kinh nghiệm (genome, gọi riêng).
 *   5. TỰ CANH        — trạng thái nền + năng lực rà soát tự động.
 *
 * Không mô hình mới: /api/plan compose từ scan; goalseek/genome là service đã có.
 * Mọi con số tiền đều gắn cờ 🧪 ước lượng, kèm giả định — không bịa số chính xác.
 */

import { useEffect, useState } from "react";
import {
  getPlan,
  runGenome,
  runGoalSeek,
  type GenomeResult,
  type GoalSeekResult,
  type PlotPlan as Plan,
} from "@/lib/api";

const RISK_HEX: Record<string, string> = {
  danger: "#e5705a",
  warning: "#e0a44a",
  safe: "#3ecb83",
};

function leadBadge(n: number | null): string {
  if (n == null) return "";
  if (n <= 0) return "hôm nay";
  if (n === 1) return "ngày mai";
  return `còn ${n} ngày`;
}

export default function PlotPlan({
  lat,
  lon,
  area,
  onSelectModule,
}: {
  lat: number;
  lon: number;
  area?: number | null;
  onSelectModule?: (id: string) => void;
}) {
  const [crop, setCrop] = useState("lua");
  const [plan, setPlan] = useState<Plan | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [genome, setGenome] = useState<GenomeResult | null>(null);
  const [genErr, setGenErr] = useState(false);
  const [ask, setAsk] = useState<Record<string, GoalSeekResult | "loading">>({});

  useEffect(() => {
    let live = true;
    setLoading(true);
    setErr(null);
    getPlan(lat, lon, area ?? undefined, crop)
      .then((p) => live && (setPlan(p), setLoading(false)))
      .catch((e) => live && (setErr(e.message), setLoading(false)));
    return () => {
      live = false;
    };
  }, [lat, lon, area, crop]);

  // Vùng tương đồng gọi RIÊNG: lần đầu phải dựng lưới cả nước nên chậm, không
  // được để nó chặn kế hoạch chính hiện ra.
  useEffect(() => {
    let live = true;
    setGenome(null);
    setGenErr(false);
    runGenome(lat, lon, 3)
      .then((g) => live && setGenome(g))
      .catch(() => live && setGenErr(true));
    return () => {
      live = false;
    };
  }, [lat, lon]);

  async function doAsk(id: string) {
    setAsk((a) => ({ ...a, [id]: "loading" }));
    try {
      const r = await runGoalSeek(id, lat, lon);
      setAsk((a) => ({ ...a, [id]: r }));
    } catch {
      setAsk((a) => {
        const n = { ...a };
        delete n[id];
        return n;
      });
    }
  }

  if (loading && !plan) {
    return (
      <div className="plan plan-skel">
        <div className="plan-head">🧭 Đang lập kế hoạch cho thửa…</div>
      </div>
    );
  }
  if (err || !plan || plan.serviceable === false) return null;

  const actions = plan.actions ?? [];
  const sw = plan.safe_window;
  const value = plan.value;
  const watch = plan.watch;
  const crops = plan.crops ?? [];
  const twin = genome?.available ? genome.twins?.[0] : null;

  return (
    <div className="plan">
      <div className="plan-head">
        🧭 Kế hoạch cho thửa của bạn
        <span className="plan-sub">
          {plan.n_alerts
            ? `${plan.n_alerts} việc cần lưu ý · sắp theo mức nguy hiểm`
            : "Không có cảnh báo — nhưng vẫn có kế hoạch canh nền"}
        </span>
      </div>

      {/* 1. VIỆC CẦN LÀM */}
      <section className="plan-sec">
        <h4 className="plan-h">▶ Việc cần làm{actions.length ? ` (${actions.length})` : ""}</h4>
        {actions.length === 0 ? (
          <p className="plan-clear">
            ✅ 7 ngày tới không có mối đe doạ nào dùng dữ liệu thật. Không phải làm gì
            gấp — TerraTwin vẫn canh nền cho bạn (xem mục Tự canh bên dưới).
          </p>
        ) : (
          <ul className="plan-actions">
            {actions.map((a) => {
              const r = ask[a.id];
              return (
                <li key={a.id} style={{ borderLeftColor: RISK_HEX[a.risk_level] }}>
                  <div className="pa-top">
                    <b
                      className="pa-name"
                      onClick={() => onSelectModule?.(a.id)}
                      title="Xem chi tiết mũi nhọn này"
                    >
                      {a.icon} {a.name}
                    </b>
                    {a.when && (
                      <span
                        className="pa-when"
                        style={{ color: RISK_HEX[a.risk_level] }}
                      >
                        {a.when_weekday} {a.when.slice(5)} · {leadBadge(a.lead_days)}
                      </span>
                    )}
                  </div>
                  <p className="pa-head">{a.headline}</p>
                  <p className="pa-do">
                    <span>Nên làm:</span> {a.do}
                  </p>
                  {a.can_ask &&
                    (r === "loading" ? (
                      <p className="pa-ask-load">Đang mô phỏng ngược…</p>
                    ) : r ? (
                      <div className="pa-ask">
                        <b>🧭 {r.headline}</b>
                        <ul>
                          {r.levers.map((l, i) => (
                            <li key={i} className={l.feasible ? "" : "infeasible"}>
                              <span>{l.lever}:</span> {l.answer}
                            </li>
                          ))}
                        </ul>
                        {r.combined && <p className="pa-comb">{r.combined.answer}</p>}
                        <small>{r.method}</small>
                      </div>
                    ) : (
                      <button className="pa-askbtn" onClick={() => doAsk(a.id)}>
                        🧭 Cần điều kiện gì mới an toàn?
                      </button>
                    ))}
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {/* 2. NGÀY AN TOÀN */}
      {sw && (
        <section className="plan-sec">
          <h4 className="plan-h">📅 Ngày an toàn để làm đồng (7 ngày tới)</h4>
          <div className="plan-week">
            {sw.days.map((d) => (
              <div
                key={d.date}
                className={`pw-day ${d.safe ? "safe" : "risky"}`}
                title={d.safe ? "Không cảnh báo" : d.hazards.join(", ")}
              >
                <span className="pw-wd">{d.weekday}</span>
                <span className="pw-dt">{d.date.slice(5)}</span>
                <span className="pw-dot">{d.safe ? "✓" : d.hazards.length}</span>
              </div>
            ))}
          </div>
          <p className="plan-note">{sw.headline}</p>
        </section>
      )}

      {/* 3. GIÁ TRỊ ĐANG CHỊU RỦI RO */}
      {value && (
        <section className="plan-sec">
          <h4 className="plan-h">💰 Giá trị đang chịu rủi ro</h4>
          <div className="plan-crops">
            <span>Loại canh tác:</span>
            {crops.map((c) => (
              <button
                key={c.id}
                className={crop === c.id ? "on" : ""}
                onClick={() => setCrop(c.id)}
              >
                {c.label}
              </button>
            ))}
          </div>
          <p className={`plan-value-head${value.at_risk ? "" : " safe"}`}>
            {value.headline}
          </p>
          {value.items.length > 0 && (
            <ul className="plan-value">
              {value.items.map((it) => (
                <li key={it.id}>
                  <span className="pv-name">
                    {it.icon} {it.name}
                  </span>
                  <span className="pv-stake">{it.stake_text}</span>
                  <span className="pv-pct">
                    thiệt hại {it.loss_pct[0]}–{it.loss_pct[1]}%
                  </span>
                </li>
              ))}
            </ul>
          )}
          <p className="plan-assume">🧪 {value.assumption}</p>
        </section>
      )}

      {/* 4. TRÍ TUỆ VÙNG (genome) */}
      <section className="plan-sec">
        <h4 className="plan-h">🛰️ Vùng giống thửa bạn — học từ nơi cùng “bộ gen” đất</h4>
        {genErr ? (
          <p className="plan-note">Chưa dựng được vùng tương đồng (kiểm tra mạng).</p>
        ) : !genome ? (
          <p className="plan-note">Đang tìm vùng cùng địa hình & khí hậu…</p>
        ) : twin ? (
          <>
            <p className="plan-value-head">{genome.headline}</p>
            <div className="plan-twins">
              {genome.twins!.slice(0, 3).map((t, i) => (
                <div key={i} className="pt-cell">
                  <b>{t.similarity_pct}%</b>
                  <span>giống</span>
                  <small>cách {t.distance_km.toFixed(0)} km</small>
                </div>
              ))}
            </div>
            <p className="plan-note">{genome.why_useful}</p>
            {genome.caveat && <p className="plan-assume">⚠️ {genome.caveat}</p>}
          </>
        ) : (
          <p className="plan-note">{genome.message || "Không tìm được vùng tương đồng."}</p>
        )}
      </section>

      {/* 5. TỰ CANH */}
      {watch && (
        <section className="plan-sec plan-watch">
          <h4 className="plan-h">🛡️ TerraTwin tự canh thửa này</h4>
          <p className="plan-value-head">{watch.headline}</p>
          <p className="plan-note">{watch.capability}</p>
        </section>
      )}
    </div>
  );
}
