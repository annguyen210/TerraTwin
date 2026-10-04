"use client";

/**
 * THẺ VƯỜN A6 — bản giấy của Hồ sơ vườn, để nông hộ giữ và người mua quét.
 *
 * Vì sao cần bản giấy: thương lái và cán bộ HTX đến tận vườn, nhiều nơi không có sóng.
 * Thẻ in gọn khổ A6 (105×148 mm), QR to dẫn tới trang kiểm chứng; mã hồ sơ và dấu vân
 * tay khoá ký in rõ để đối chiếu tay. KHÔNG in họ tên chủ hộ — cùng mặc định ẩn danh
 * với hồ sơ số (tên chỉ lộ qua đường link đầy đủ do chính chủ hộ đưa).
 */
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { getDossier, type Dossier, type EudrDossierFacts } from "@/lib/api";
import { useLang } from "@/lib/i18n";

const LEVEL_CLS: Record<string, string> = { low: "ok", review: "warn", high: "bad", unknown: "dim" };

function dmy(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getUTCDate())}/${p(d.getUTCMonth() + 1)}/${d.getUTCFullYear()}`;
}

export default function PlotCard() {
  const params = useParams();
  const id = String(Array.isArray(params.id) ? params.id[0] : params.id ?? "");
  const { t } = useLang();
  const [d, setD] = useState<Dossier | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    getDossier(id, null).then((x) => live && setD(x)).catch((e) => live && setErr(e.message));
    return () => { live = false; };
  }, [id]);

  if (err) return <main className="a6-wrap"><p className="bat-err">{err}</p></main>;
  if (!d) return <main className="a6-wrap"><div className="tt-skel" style={{ height: 420 }} /></main>;

  const f = d.facts as unknown as EudrDossierFacts;
  const isPlot = f && f.kind === "eudr_plot";
  const sc = isPlot ? f.screening : null;
  const changed = !!d.monitor?.changed;

  return (
    <main className="a6-wrap">
      <div className="a6-tools no-print">
        <Link href={`/h/${id}`} className="doc-home">← {t("Về hồ sơ", "Back to dossier")}</Link>
        <button className="doc-btn" onClick={() => window.print()}>{t("In thẻ A6", "Print A6 card")}</button>
      </div>

      <article className="a6-card" aria-label={t("Thẻ vườn", "Plot card")}>
        <header className="a6-head">
          <b>◵ TerraTwin</b>
          <span>{isPlot ? t("Hồ sơ vườn EUDR", "EUDR plot dossier") : t("Hồ sơ đất số", "Digital land dossier")}</span>
        </header>

        {isPlot && (
          <section className="a6-plot">
            <h1>{f.plot.ref || t("Vườn", "Plot")}</h1>
            <p>
              {[f.plot.commodity_label, `${f.plot.area_ha} ha`, f.plot.kind === "polygon" ? t("ranh đa giác", "polygon boundary") : t("điểm", "point")]
                .filter(Boolean).join(" · ")}
            </p>
            <p className="a6-coord">{f.plot.centroid.lat.toFixed(5)}, {f.plot.centroid.lon.toFixed(5)}</p>
          </section>
        )}

        {sc && (
          <div className={`a6-verdict ${changed ? "bad" : LEVEL_CLS[sc.level] ?? "dim"}`}>
            <b>{changed ? t("Đã có thay đổi sau phát hành", "Changed after issuance") : sc.label}</b>
            <small>
              {t("Sàng lọc phá rừng sau", "Deforestation screening after")} {dmy(sc.cutoff)} · {t("đo ngày", "measured")} {dmy(sc.computed_at)}
            </small>
          </div>
        )}

        {d.qr && <img className="a6-qr" src={d.qr} alt={t("Mã QR tới trang kiểm chứng", "QR code to the verification page")} />}

        <dl className="a6-meta">
          <div><dt>{t("Mã hồ sơ", "Dossier ID")}</dt><dd>{d.id}</dd></div>
          <div><dt>{t("Phát hành", "Issued")}</dt><dd>{dmy(d.issued_at)} · #{d.seq}</dd></div>
          <div><dt>{t("Khoá ký", "Signing key")}</dt><dd>{d.proof.algorithm} {d.proof.key_id}</dd></div>
        </dl>

        <footer className="a6-foot">
          {t("Quét QR để kiểm chữ ký và sổ minh bạch. Không có mạng: tải tệp JSON của hồ sơ, mở trang /kiem — kiểm ngay trong máy.",
             "Scan the QR to verify the signature and transparency log. Offline: download the dossier JSON and open /kiem — verified on-device.")}
          <br />
          {t("Sàng lọc không phải chứng nhận tuân thủ. Họ tên chủ hộ không in trên thẻ.",
             "Screening is not compliance certification. The producer's name is not printed.")}
        </footer>
      </article>
    </main>
  );
}
