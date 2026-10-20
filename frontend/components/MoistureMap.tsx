"use client";

/**
 * S10 ① — ĐỘ ẨM TÁN LÁ (NDMI) 10 m TRONG THỬA. B11 (20 m) làm sắc bằng các băng 10 m đã đo; mỗi ô 20 m vẫn trung bình
 * đúng bằng ảnh đo gốc (backend/app/services/s2_sharpen.py). Chỉ hiện khi phép kiểm Wald đăng ký trước ĐẠT.
 * Ảnh 20 m gốc đặt CẠNH ảnh 10 m để người xem tự thấy phần nào là đo, phần nào là làm sắc. Tham khảo, không vào hồ sơ ký.
 * Nằm ở tab Canh đất, CHỈ chạy khi bấm (mỗi lượt đọc ảnh tính một lượt quét của hạn mức).
 */
import { useEffect, useRef, useState } from "react";
import { Droplets } from "lucide-react";
import { ndmi10, type Ndmi10 } from "@/lib/api";
import { useLang } from "@/lib/i18n";

const STOPS: [number, [number, number, number]][] = [
  [-0.2, [140, 90, 40]], [0.0, [214, 178, 92]], [0.2, [190, 214, 120]], [0.4, [70, 160, 190]], [0.6, [30, 80, 160]],
];

function color(v: number): [number, number, number] {
  if (v <= STOPS[0][0]) return STOPS[0][1];
  for (let i = 1; i < STOPS.length; i++) {
    const [x1, c1] = STOPS[i];
    const [x0, c0] = STOPS[i - 1];
    if (v <= x1) {
      const k = (v - x0) / (x1 - x0);
      return [0, 1, 2].map((j) => Math.round(c0[j] + k * (c1[j] - c0[j]))) as [number, number, number];
    }
  }
  return STOPS[STOPS.length - 1][1];
}

function Grid({ g, label }: { g: (number | null)[][]; label: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const cv = ref.current;
    if (!cv || !g.length) return;
    const n = g.length;
    cv.width = n; cv.height = n;
    const ctx = cv.getContext("2d");
    if (!ctx) return;
    const img = ctx.createImageData(n, n);
    g.forEach((row, y) => row.forEach((v, x) => {
      const [r, gg, b] = v == null ? [150, 150, 150] : color(v);
      const i = 4 * (y * n + x);
      img.data[i] = r; img.data[i + 1] = gg; img.data[i + 2] = b; img.data[i + 3] = v == null ? 110 : 255;
    }));
    ctx.putImageData(img, 0, 0);
  }, [g]);
  return (
    <figure className="mm-fig">
      <div className="mm-wrap">
        <canvas ref={ref} className="mm-cv" role="img" aria-label={label} />
        <span className="mm-x" aria-hidden="true" />
      </div>
      <figcaption>{label}</figcaption>
    </figure>
  );
}

export default function MoistureMap({ lat, lon }: { lat: number; lon: number }) {
  const { t } = useLang();
  const [r, setR] = useState<Ndmi10 | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const gen = useRef(0);

  async function run() {
    const my = ++gen.current;
    setR(null); setErr(null); setBusy(true);
    try {
      const x = await ndmi10(lat, lon);
      if (my === gen.current) setR(x);
    } catch (e) {
      if (my === gen.current) setErr((e as Error).message);
    } finally {
      if (my === gen.current) setBusy(false);
    }
  }

  useEffect(() => {                                            // đổi thửa → bỏ kết quả cũ, chờ bấm lại
    gen.current++;
    setR(null); setErr(null); setBusy(false);
  }, [lat, lon]);

  const g1 = r?.gate?.g1_median_rel_gain?.[0];
  const nt = r?.gate?.n_test_scenes?.[0];
  return (
    <section className="mm">
      <div className="wh-head">
        <Droplets size={18} aria-hidden="true" />
        <h3>{t("Độ ẩm tán lá trong thửa (NDMI 10 m)", "Canopy moisture inside the plot (10 m NDMI)")}</h3>
        <span className="wh-badge">{t("làm sắc từ 20 m · tham khảo", "sharpened from 20 m · reference")}</span>
      </div>
      {!r && !err && !busy && (
        <div className="wh-start">
          <p>{t("Bản đồ lượng nước trong tán lá (NDMI) 10 m quanh thửa, từ ảnh Sentinel-2 quang mây gần nhất — chỗ nào khô hơn phần còn lại của ruộng/vườn.",
                "A 10 m canopy-water (NDMI) map around the plot from the latest cloud-free Sentinel-2 image — which patches are drier than the rest of the field.")}</p>
          <button className="bat-btn ghost" onClick={run}>{t("Xem độ ẩm tán lá 10 m", "Show 10 m canopy moisture")}</button>
        </div>
      )}
      {!r && !err && busy && (
        <div className="wh-start" aria-live="polite">
          <p>{t("Đang tìm cảnh Sentinel-2 quang mây gần nhất và làm sắc băng hồng ngoại sóng ngắn 20 m → 10 m…",
                "Finding the latest cloud-free Sentinel-2 scene and sharpening the 20 m shortwave-infrared band to 10 m…")}</p>
          <div className="wh-prog ind" role="progressbar" aria-label={t("Đang làm sắc", "Sharpening")}><span /></div>
        </div>
      )}
      {err && (
        <div className="wh-start">
          <p className="bat-err">{err}</p>
          <button className="bat-btn ghost" onClick={run}>{t("Thử lại", "Retry")}</button>
        </div>
      )}
      {r && !r.available && <p className="doc-note">{r.reason}</p>}
      {r && r.available && !r.found && <p className="doc-note">{r.message}</p>}
      {r && r.available && r.found && r.ndmi_10m && r.ndmi_20m && (
        <>
          <p className="wh-sum">
            {t(`Ảnh ngày ${r.date} · quang mây ${r.clear_pct}% · khung 640 m, dấu + là thửa.`,
               `Image of ${r.date} · ${r.clear_pct}% cloud-free · 640 m frame, + marks the plot.`)}
            {r.center_ndmi_10m != null && <> {t("NDMI giữa thửa", "Plot-centre NDMI")} <b>{r.center_ndmi_10m}</b>
              {r.center_spread_10m != null && <> {t(`(chênh trong 100 m: ${r.center_spread_10m})`, `(spread within 100 m: ${r.center_spread_10m})`)}</>}.</>}
          </p>
          <div className="mm-pair">
            <Grid g={r.ndmi_20m} label={t("20 m — đo gốc", "20 m — as measured")} />
            <Grid g={r.ndmi_10m} label={t("10 m — làm sắc", "10 m — sharpened")} />
          </div>
          <div className="mm-legend" aria-hidden="true">
            <span>{t("khô", "dry")} −0,2</span><i /><span>0,6 {t("nhiều nước", "wet")}</span>
          </div>
          <p className="doc-note">{r.note}{g1 != null && nt != null && <> {t(`Phép kiểm Wald đăng ký trước trên ${nt} tỉnh giữ riêng: sai số B11 giảm trung vị ${Math.round(g1 * 100)}% so với phóng ảnh thường.`,
            `Pre-registered Wald test on ${nt} held-out provinces: median B11 error ${Math.round(g1 * 100)}% lower than plain upsampling.`)}</>}</p>
        </>
      )}
    </section>
  );
}
