"use client";

/**
 * MỘT CÂU TRẢ LỜI, trước mọi thứ khác.
 *
 * VẤN ĐỀ ĐANG SỬA. Trước đây chọn một điểm thì thấy kết quả của ĐÚNG MỘT mô-đun
 * mà người dùng đã chọn từ trước — mà họ chọn lúc chưa biết mình cần gì. Quét
 * toàn cảnh 18 mũi nhọn trong 2,5 giây thì lại nằm sau một cái tab. Nghĩa là
 * thứ mạnh nhất của sản phẩm bị giấu, còn thứ hiện ra đầu tiên thì hẹp và dễ
 * sai. Người dùng kết luận "phần mềm chỉ có thế" — và họ kết luận đúng với thứ
 * họ được cho xem.
 *
 * Ở đây đảo lại: chọn chỗ xong là quét HẾT, rồi trả lời bằng một câu. Chi tiết
 * từng mô-đun tụt xuống dưới, dành cho ai muốn đào sâu.
 *
 * BA NGUYÊN TẮC VIẾT CÂU TRẢ LỜI:
 *
 * ① KHÔNG cộng gộp mọi mô-đun thành một điểm số rồi khoe. Người ta cần biết
 *    "sắp có chuyện gì", không cần biết "thửa này 72 điểm".
 * ② Câu đầu tiên phải trả lời được cho người CHƯA đọc gì phía dưới.
 * ③ Chỗ nào dữ liệu chưa đủ thì đếm riêng và nói ra, không trộn vào phần "an
 *    toàn". "Chưa biết" và "không sao" là hai chuyện khác hẳn nhau.
 */

import { useEffect, useRef, useState } from "react";
import { scanAll, trackEvent, type ScanResult, type ScanModule, type ModuleInfo } from "@/lib/api";
import SpeakButton from "@/components/SpeakButton";
import { useLang } from "@/lib/i18n";
import Passport from "./Passport";
import PlotView from "./PlotView";
import WhyTrust from "./WhyTrust";

const TONE: Record<string, string> = {
  danger: "bad",
  warning: "warn",
  safe: "ok",
};

// Màu ô trong lưới toàn cảnh. Mục chưa có dữ liệu / đang chạy / ngoài phạm vi →
// "chờ" (xám), KHÔNG tô như an toàn — "chưa biết" khác "không sao".
function cellTone(m: ScanModule): string {
  // pending = mũi nhọn cần ảnh vệ tinh, ĐANG chạy nền → nhấp nháy để thấy nó
  // sắp được lấp (khác need_data/out_of_scope: xám tĩnh vì chưa/không có số).
  if (m.status === "pending") return "pending";
  if (m.status === "need_data" || m.status === "out_of_scope") return "wait";
  return TONE[m.risk_level] ?? "wait";
}

const TONE_HEX: Record<string, string> = {
  bad: "#C2412E", warn: "#B07A2E", ok: "#2E9E67", pending: "#3aa0a0", wait: "#5a6b73",
};

type T = (vi: string, en: string) => string;

function statusLabel(st: string | undefined, t: T): string {
  if (st === "pending") return t("đang chạy…", "running…");
  if (st === "need_data") return t("chờ ảnh vệ tinh quang mây", "awaiting cloud-free satellite");
  if (st === "out_of_scope") return t("không áp dụng ở đây", "not applicable here");
  return "";
}

function fmt(v: number): string {
  return Number.isInteger(v) ? String(v) : v.toFixed(1);
}

// Sparkline 7 ngày — SVG nhẹ, không thư viện. Cho thấy XU HƯỚNG ngay trong ô.
function Spark({ values, color }: { values: number[]; color: string }) {
  const n = values.length;
  if (n < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const W = 62, H = 18;
  const pts = values
    .map((v, i) => `${(i / (n - 1)) * W},${H - ((v - min) / span) * (H - 3) - 1.5}`)
    .join(" ");
  return (
    <svg className="ans-spark" viewBox={`0 0 ${W} ${H}`} width={W} height={H} aria-hidden>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5"
        strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={W} cy={H - ((values[n - 1] - min) / span) * (H - 3) - 1.5} r="1.8" fill={color} />
    </svg>
  );
}

function headline(d: ScanResult, t: T): { tone: string; big: string; sub: string } {
  const nguy = d.alerts.filter((a) => a.risk_level === "danger");
  const canh = d.alerts.filter((a) => a.risk_level === "warning");
  // BỐN TRẠNG THÁI, đếm riêng. Gộp lại là tự bôi xấu mình: một mục ĐANG CHẠY
  // và một mục KHÔNG CÓ DỮ LIỆU trông như nhau, còn "ở đây không áp dụng" thì
  // vốn là câu trả lời đúng chứ không phải lỗ hổng.
  const chuaBiet = d.modules.filter((m) => m.status === "need_data").length;

  const duoi = chuaBiet
    ? t(`${chuaBiet} mục chưa đủ dữ liệu để kết luận — xem bên dưới.`,
        `${chuaBiet} item(s) lack enough data to conclude — see below.`)
    : t("Mọi mục đều có dữ liệu thật để kết luận.",
        "Every item has real data to conclude on.");

  if (nguy.length) {
    return {
      tone: "bad",
      big:
        nguy.length === 1
          ? t(`Cần xử lý ngay: ${nguy[0].name.toLowerCase()}`,
              `Act now: ${nguy[0].name.toLowerCase()}`)
          : t(`Cần xử lý ngay: ${nguy.length} rủi ro`,
              `Act now: ${nguy.length} risks`),
      sub: duoi,
    };
  }
  if (canh.length) {
    return {
      tone: "warn",
      big:
        canh.length === 1
          ? t(`Nên chú ý: ${canh[0].name.toLowerCase()}`,
              `Worth noting: ${canh[0].name.toLowerCase()}`)
          : t(`Nên chú ý: ${canh.length} rủi ro`,
              `Worth noting: ${canh.length} risks`),
      sub: duoi,
    };
  }

  // KHÔNG được nói "chưa thấy rủi ro" khi phần lớn còn mù.
  //
  // Đo thật ở Bến Tre lúc nguồn dữ liệu đang bị chặn: 0 cảnh báo nhưng 7/16 mục
  // không kết luận được — kể cả xâm nhập mặn, thứ quan trọng nhất ở đúng chỗ
  // đó. Câu "bảy ngày tới chưa thấy rủi ro nào" khi ấy đọc như một lời trấn an,
  // trong khi sự thật là KHÔNG BIẾT. Đẩy cảnh báo xuống dòng phụ là chưa đủ:
  // người ta đọc dòng to rồi đóng app.
  const dung = d.modules.length - chuaBiet;
  if (chuaBiet > 0 && chuaBiet >= d.modules.length / 3) {
    return {
      tone: "warn",
      big: t(`Chưa kết luận được — ${chuaBiet}/${d.modules.length} mục thiếu dữ liệu`,
             `Can't conclude — ${chuaBiet}/${d.modules.length} items lack data`),
      sub:
        dung > 0
          ? t(`${dung} mục còn lại chưa thấy rủi ro. Phần thiếu không có nghĩa là an toàn.`,
              `The other ${dung} show no risk. Missing data does NOT mean safe.`)
          : t("Chưa mục nào có đủ dữ liệu thật để kết luận.",
              "No item has enough real data to conclude yet."),
    };
  }

  return {
    tone: "ok",
    big: t("Bảy ngày tới chưa thấy rủi ro nào", "No risks in the next 7 days"),
    sub: duoi,
  };
}

export default function Answer({
  lat,
  lon,
  area,
  label,
  modules,
  onSelectModule,
  onDetail,
  onRisk,
  onTerra,
}: {
  lat: number;
  lon: number;
  area?: number;
  label?: string;
  // Danh sách mũi nhọn để vẽ lưới skeleton NGAY khi đang quét — cho người dùng
  // thấy phần mềm đang kiểm cả 18 thứ, thay vì một vòng xoay câm 15 giây.
  modules?: ModuleInfo[];
  onSelectModule?: (id: string) => void;
  onDetail?: () => void;
  // Báo mức rủi ro cao nhất ra ngoài để bản đồ tô khung cùng màu — nối phần
  // lớn nhất của màn hình với câu trả lời, thay vì để nó là tấm nền trơn.
  onRisk?: (risk: string) => void;
  // Chuyển TerraScore ra ngoài. Lượt quét đã tính sẵn nó, nên trang không cần
  // gọi /api/terrascore lần nữa — đó chính là lời gọi thừa làm chậm gấp năm lần.
  onTerra?: (t: ScanResult["terrascore"]) => void;
}) {
  const { t } = useLang();
  const [d, setD] = useState<ScanResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // N10 — khi mất mạng, hiện lại kết quả ĐÃ LƯU của đúng thửa này, kèm mốc thời
  // gian để không ai nhầm là mới. null = đang xem kết quả tươi.
  const [stale, setStale] = useState<string | null>(null);
  const [giay, setGiay] = useState(0);
  const dong = useRef<ReturnType<typeof setInterval> | null>(null);

  // Đếm giây khi chờ. LÝ DO CÓ CÁI NÀY: đo thật cho thấy nơi đã có cache trả
  // lời trong 2,5 giây, nhưng nơi CHƯA TỪNG XEM mất tới 15 giây — vì phải tải
  // 10 năm lịch sử của đúng toạ độ đó về mới hiệu chuẩn được ngưỡng. Con số
  // 2,5 giây vẫn hay được nêu là trường hợp ĐÃ ẤM, không phải lần đầu.
  //
  // Mười lăm giây nhìn một vòng xoay câm là quá đủ để người ta đóng app. Không
  // giấu được thì nói ra: đang làm gì, vì sao lâu, và lần sau sẽ nhanh.
  useEffect(() => {
    if (!busy) {
      if (dong.current) clearInterval(dong.current);
      setGiay(0);
      return;
    }
    dong.current = setInterval(() => setGiay((g) => g + 1), 1000);
    return () => {
      if (dong.current) clearInterval(dong.current);
    };
  }, [busy]);

  useEffect(() => {
    let huy = false;
    // N10 — lưu kết quả gần nhất theo thửa. Dọn LRU giữ 8 thửa để không làm đầy
    // localStorage. localStorage đầy/tắt thì bỏ qua — offline là tiện ích thêm.
    const key = `tt_scan:${lat.toFixed(3)},${lon.toFixed(3)}`;
    const save = (r: ScanResult) => {
      try {
        localStorage.setItem(key, JSON.stringify({ at: Date.now(), result: r }));
        let idx: string[] = [];
        try { idx = JSON.parse(localStorage.getItem("tt_scan_index") || "[]"); } catch { /* */ }
        idx = [key, ...idx.filter((k) => k !== key)];
        while (idx.length > 8) { const drop = idx.pop(); if (drop) localStorage.removeItem(drop); }
        localStorage.setItem("tt_scan_index", JSON.stringify(idx));
      } catch { /* localStorage đầy/tắt → bỏ qua */ }
    };

    setBusy(true);
    setErr(null);
    setD(null);
    setStale(null);
    trackEvent("scan");                               // N6
    scanAll(lat, lon, area)
      .then((r) => {
        if (huy) return;
        setD(r);
        save(r);                                       // N10
        // LƯỢT SÂU CHẠY NGAY SAU, ở nền. Bảy mũi nhọn cần ảnh vệ tinh mất 6–60
        // giây mỗi cái nên không thể để trong lượt nhanh. Nhưng bỏ mặc chúng ở
        // trạng thái "đang kiểm tra" thì chúng treo vĩnh viễn, và trông y hệt
        // như thiếu dữ liệu — đúng thứ làm người dùng thấy phần mềm sơ sài.
        // Gọi tiếp và thay kết quả vào khi xong.
        scanAll(lat, lon, area, true)
          .then((sau) => { if (!huy) { setD(sau); save(sau); } })
          .catch(() => {});
      })
      .catch((e) => {
        if (huy) return;
        // N10 — mất mạng: nếu có kết quả ĐÃ LƯU cho đúng thửa này thì hiện lại,
        // ghi rõ mốc thời gian để không ai nhầm là mới. Không có thì báo lỗi.
        try {
          const raw = localStorage.getItem(key);
          if (raw) {
            const { at, result } = JSON.parse(raw);
            setD(result);
            setStale(new Date(at).toLocaleString("vi-VN"));
            return;
          }
        } catch { /* bỏ qua */ }
        setErr(e.message);
      })
      .finally(() => !huy && setBusy(false));
    return () => {
      huy = true;
    };
  }, [lat, lon, area]);

  useEffect(() => {
    if (!d || !onRisk) return;
    const co = d.alerts.some((a) => a.risk_level === "danger")
      ? "danger"
      : d.alerts.some((a) => a.risk_level === "warning")
        ? "warning"
        : "safe";
    onRisk(co);
  }, [d, onRisk]);

  useEffect(() => {
    if (d?.terrascore && onTerra) onTerra(d.terrascore);
  }, [d, onTerra]);

  if (busy) {
    return (
      <div className="ans">
        {label && <p className="ans-where">📍 {label}</p>}
        <div className="ans-scanning">
          <span className="ans-spin sm" />
          <b>{t(`Đang quét ${modules?.length ?? 18} mũi nhọn cho thửa này`,
                `Scanning ${modules?.length ?? 18} spearheads for this plot`)}{giay ? ` · ${giay}s` : ""}…</b>
        </div>
        {/* Lưới SỐNG: hiện ngay mọi mũi nhọn đang được kiểm (skeleton nhấp nháy),
            để 15 giây chờ trở thành bằng chứng phần mềm đang làm RẤT NHIỀU việc —
            thay vì một vòng xoay câm khiến người ta tưởng nó "sơ sài". */}
        {modules && modules.length > 0 && (
          <div className="ans-grid ans-grid-skel">
            {modules.map((m) => (
              <div key={m.id} className="ans-cell skel">
                <span className="ans-cell-ic">{m.icon}</span>
                <span className="ans-cell-nm">{m.name}</span>
                <span className="ans-cell-dot" />
              </div>
            ))}
          </div>
        )}
        {giay >= 4 && (
          <p className="ans-wait">
            {t("Lần đầu xem một nơi mới thì lâu hơn — TerraTwin đang tải 10 năm lịch sử thời tiết của đúng toạ độ này để biết thế nào mới là bất thường ở đây, thay vì dùng một ngưỡng chung cho cả nước. Lần sau chỗ này trả lời trong vài giây.",
                "First look at a new place takes longer — TerraTwin is loading 10 years of weather history for this exact point to learn what's abnormal HERE, instead of one nationwide threshold. Next time this spot answers in seconds.")}
          </p>
        )}
      </div>
    );
  }

  if (err) {
    return (
      <div className="ans">
        <p className="ans-err">⚠️ {err}</p>
      </div>
    );
  }
  if (!d) return null;

  // Ngoài vùng phục vụ thì nói thẳng, không chấm điểm cho mặt nước.
  if (d.region && d.region.serviceable === false) {
    return (
      <div className="ans">
        <div className="ans-head off">
          <b>
            {d.region.kind === "sea"
              ? t("🌊 Chỗ này là mặt nước", "🌊 This is open water")
              : t("🗺️ Ngoài phạm vi phục vụ", "🗺️ Outside service area")}
          </b>
          <p>{d.region.note}</p>
        </div>
      </div>
    );
  }

  const h = headline(d, t);
  const canLam = d.alerts.filter((a) => a.recommendation);
  const chuaDu = d.modules.filter((m) => m.status === "need_data");
  const dangChay = d.modules.filter((m) => m.status === "pending");
  const khongApDung = d.modules.filter((m) => m.status === "out_of_scope");

  return (
    <div className="ans">
      {label && <p className="ans-where">📍 {label}</p>}

      {/* N10 — đang xem kết quả ĐÃ LƯU (mất mạng). Nói thẳng đã cũ, đừng để ai
          tưởng là cảnh báo mới — với app thiên tai, nhầm chỗ này là nguy hiểm. */}
      {stale && (
        <p style={{
          margin: "0 0 10px", padding: "8px 12px", borderRadius: 6,
          background: "var(--clay-soft, #f7e9df)", color: "var(--clay, #a0522c)",
          fontSize: 13, fontWeight: 600, border: "1px solid var(--clay, #a0522c)",
        }}>
          📴 {t(`Đang xem kết quả đã lưu lúc ${stale}`, `Showing result saved at ${stale}`)} — <b>{t("có thể đã cũ", "may be stale")}</b>. {t("Mở lại khi có mạng để cập nhật (cảnh báo mới KHÔNG hiện khi offline).", "Reopen when online to refresh (new alerts do NOT show offline).")}
        </p>
      )}

      {/* ẢNH ĐẶT TRƯỚC CHỮ. Người ta nhận ra mảnh đất của mình bằng mắt trong
          một giây; đọc một đoạn văn tả về nó thì mất lâu hơn và vẫn không chắc
          là đúng thửa. Thấy đúng chỗ rồi mới có lý do đọc tiếp. */}
      <PlotView lat={lat} lon={lon} />

      <div className={`ans-head ${h.tone}`}>
        <b>{h.big}</b>
        <p>{h.sub}</p>
        {/* A10 — đọc kết quả ra tiếng cho người đọc chữ khó. Đọc câu chính +
            tối đa 3 việc cần làm; giọng tiếng Việt của trình duyệt, không mạng. */}
        <div style={{ marginTop: 8 }}>
          <SpeakButton text={[
            h.big, h.sub,
            ...canLam.slice(0, 3).map((a) => `${a.name}. ${a.recommendation}`),
          ].filter(Boolean).join(". ")} />
        </div>
      </div>

      {canLam.length > 0 && (
        <div className="ans-todo">
          <span className="ans-cap">{t("Nên làm gì", "What to do")}</span>
          {canLam.map((a) => (
            <div key={a.id} className={`ans-item ${TONE[a.risk_level] ?? ""}`}>
              <button className="ans-name" onClick={() => onSelectModule?.(a.id)}>
                {a.icon} {a.name}
              </button>
              <p className="ans-why">{a.headline}</p>
              <p className="ans-do">→ {a.recommendation}</p>
            </div>
          ))}
        </div>
      )}

      {canLam.length === 0 && (
        <p className="ans-calm">
          {t("Không có việc gì cần làm gấp. Bật cảnh báo để TerraTwin tự báo khi tình hình đổi, thay vì bạn phải mở lên xem.",
             "Nothing urgent to do. Turn on alerts so TerraTwin tells you when things change, instead of you having to check.")}
        </p>
      )}

      {/* TOÀN CẢNH 1 MẮT: cho thấy phần mềm vừa kiểm CẢ 18 mũi nhọn, không phải
          chỉ một kết luận. Đây là thứ chữa trực tiếp cảm giác "sơ sài" — breadth
          hiện ngay, không cần đổi tab. Bấm ô nào là nhảy vào chi tiết mục đó. */}
      {d.modules.length > 0 && (
        <div className="ans-grid-wrap">
          <span className="ans-cap">
            {t(`Đã quét toàn bộ ${d.modules.length} mũi nhọn cho thửa này`,
               `Scanned all ${d.modules.length} spearheads for this plot`)}
          </span>
          <div className="ans-grid rich">
            {d.modules.map((m) => {
              const tone = cellTone(m);
              const hasSpark = (m.spark?.length ?? 0) > 1;
              return (
                <button
                  key={m.id}
                  className={`ans-cell ${tone}`}
                  title={`${m.name}: ${m.headline}`}
                  onClick={() => onSelectModule?.(m.id)}
                >
                  <span className="ans-cell-top">
                    <span className="ans-cell-ic">{m.icon}</span>
                    <span className="ans-cell-nm">{m.name}</span>
                    <span className="ans-cell-dot" />
                  </span>
                  {hasSpark ? (
                    <span className="ans-cell-data">
                      <Spark values={m.spark!} color={TONE_HEX[tone]} />
                      {m.peak != null && (
                        <b>{fmt(m.peak)}{m.unit === "%" ? "%" : ""}</b>
                      )}
                    </span>
                  ) : m.status === "ok" ? (
                    <span className="ans-cell-hl">{m.headline}</span>
                  ) : (
                    <span className="ans-cell-st">{statusLabel(m.status, t)}</span>
                  )}
                </button>
              );
            })}
          </div>
          <div className="ans-grid-key">
            <span><i className="k-bad" /> {t("nguy hiểm", "danger")}</span>
            <span><i className="k-warn" /> {t("cảnh báo", "warning")}</span>
            <span><i className="k-ok" /> {t("an toàn", "safe")}</span>
            <span><i className="k-wait" /> {t("đang/ chờ dữ liệu", "running/awaiting data")}</span>
          </div>
        </div>
      )}

      {dangChay.length > 0 && (
        <div className="ans-pending">
          <span className="ans-spin sm" />
          <div>
            <b>{t(`Đang kiểm tra thêm ${dangChay.length} mục`, `Still checking ${dangChay.length} more`)}</b>
            <p>
              {t("Những mục này cần ảnh vệ tinh nên lâu hơn hẳn — chúng đang chạy nền, không phải thiếu dữ liệu. Mở ",
                 "These need satellite imagery so they take longer — running in the background, not missing data. Open ")}
              <i>{dangChay.slice(0, 3).map((m) => m.name.toLowerCase()).join(", ")}</i>
              {dangChay.length > 3 ? "…" : ""} {t("ở cột trái để xem từng cái.", "in the left column to see each.")}
            </p>
          </div>
        </div>
      )}

      {khongApDung.length > 0 && (
        <p className="ans-na">
          {khongApDung.length} {t("mục", "item(s)")} <b>{t("không áp dụng", "not applicable")}</b> {t("ở đây", "here")} (
          {khongApDung.map((m) => m.name.toLowerCase()).join(", ")}) — {t("đó là câu trả lời đúng cho vị trí này, không phải thiếu sót.", "that's the correct answer for this location, not a gap.")}
        </p>
      )}

      {chuaDu.length > 0 && (
        <details className="ans-unknown">
          <summary>
            {t(`${chuaDu.length} mục chưa đủ dữ liệu để kết luận`,
               `${chuaDu.length} item(s) lack enough data to conclude`)}
          </summary>
          <p className="ans-note">
            {t("Những mục này không phải là an toàn — chỉ là chưa có đủ dữ liệu thật để nói. Phần lớn chờ kết nối ảnh vệ tinh Sentinel-2.",
               "These are NOT safe — there just isn't enough real data yet. Most await Sentinel-2 satellite imagery.")}
          </p>
          <ul>
            {chuaDu.map((m) => (
              <li key={m.id}>
                {m.icon} {m.name} — {m.headline}
              </li>
            ))}
          </ul>
        </details>
      )}

      {/* Hồ sơ riêng đặt TRƯỚC khối đối chiếu: nó trả lời "phần mềm này hơn
          app thời tiết ở chỗ nào" bằng ba con số cụ thể của chính thửa này,
          còn khối đối chiếu trả lời "vì sao tin được con số đó". */}
      <Passport lat={lat} lon={lon} />

      <WhyTrust lat={lat} lon={lon} />

      <div className="ans-more">
        <button onClick={onDetail}>{t("Xem chi tiết từng mục", "See each item in detail")}</button>
        <span className="ans-src">
          {Math.round((d.real_data_ratio ?? 0) * 100)}% {t("kết luận dựa trên dữ liệu đo được", "of conclusions use measured data")}
        </span>
      </div>
    </div>
  );
}
