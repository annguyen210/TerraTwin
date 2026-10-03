"use client";

/**
 * HỒ SƠ ĐẤT SỐ — trang công khai của một hồ sơ đã phát hành (/h/<mã>).
 *
 * Người nhận (ngân hàng, người mua, bảo hiểm) quét QR trên bản in là tới đây:
 * thấy đúng nội dung đã phát hành và kết quả BỐN phép kiểm do máy chủ chạy lại
 * ngay lúc mở (nội dung ↔ mã băm, mục sổ, chữ ký Ed25519, móc xích). Họ cũng tự
 * kiểm được một tệp JSON ai đó gửi cho họ. Nội dung đóng băng lúc phát hành,
 * bằng ngôn ngữ lúc phát hành — đây là giấy tờ, không phải trang sống.
 */

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  evidenceThumbSrc, getDossier, verifyDossierFile,
  type Dossier, type DossierFileCheck, type DossierModule,
} from "@/lib/api";
import EudrDossierView from "@/components/EudrDossierView";
import LotCertificateView from "@/components/LotCertificateView";
import DeliveryConfirm from "@/components/DeliveryConfirm";
import AppShell from "@/components/AppShell";
import { useLang } from "@/lib/i18n";
import { levelOf } from "@/lib/riskScale";
import type { EudrDossierFacts, LotCertificateFacts } from "@/lib/api";

function fmtTime(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getUTCDate())}/${p(d.getUTCMonth() + 1)}/${d.getUTCFullYear()} ` +
    `${p(d.getUTCHours())}:${p(d.getUTCMinutes())} UTC`;
}

function fmtDate(iso: string | null | undefined) {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return d && m && y ? `${d}/${m}/${y}` : iso;
}

function statusTag(m: DossierModule, t: (vi: string, en: string) => string) {
  if (m.status === "need_data") return t("thiếu dữ liệu", "no data");
  if (m.status === "out_of_scope") return t("không áp dụng", "not applicable");
  return m.is_real ? t("đo thật", "measured") : t("ước lượng", "estimated");
}

export default function DossierPage() {
  const params = useParams();
  const id = String(Array.isArray(params.id) ? params.id[0] : params.id ?? "");
  const { t, lang } = useLang();
  const [d, setD] = useState<Dossier | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [fileCheck, setFileCheck] = useState<DossierFileCheck | null>(null);
  const [fileErr, setFileErr] = useState<string | null>(null);
  const [tok, setTok] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    // ?d=… = chuỗi tiết lộ chọn lọc chủ hồ sơ đưa (vd họ tên) — máy chủ đối chiếu với cam kết đã ký.
    const token = new URLSearchParams(window.location.search).get("d");
    setTok(token);
    getDossier(id, token).then((x) => live && setD(x)).catch((e) => live && setErr(e.message));
    return () => { live = false; };
  }, [id, lang]);

  function download() {
    if (!d) return;
    // facts_canonical: đúng chuỗi đã băm → trang /kiem kiểm offline được.
    const doc = { id: d.id, seq: d.seq, issued_at: d.issued_at, facts: d.facts, facts_canonical: d.facts_canonical, proof: d.proof };
    const url = URL.createObjectURL(new Blob([JSON.stringify(doc, null, 2)], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `terratwin-ho-so-${d.id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function checkFile(f: File | undefined) {
    setFileCheck(null);
    setFileErr(null);
    if (!f) return;
    try {
      setFileCheck(await verifyDossierFile(JSON.parse(await f.text())));
    } catch (e) {
      setFileErr(e instanceof SyntaxError
        ? t("Tệp không phải JSON hợp lệ.", "The file is not valid JSON.")
        : (e as Error).message);
    }
  }

  const f = d?.facts;
  const v = d?.verification;
  const lu = f?.land_use;
  const hist = f?.history_10y ? Object.entries(f.history_10y) : [];
  const cr = f?.current_risk;
  const isEudr = f?.kind === "eudr_plot";
  const isLot = (f as { kind?: string } | undefined)?.kind === "lot_certificate";

  return (
    <AppShell extra={d ? <span className="dos-noprint tt-dos-actions">
        <button className="doc-link-btn" onClick={download}>{t("Tải JSON đã ký", "Download signed JSON")}</button>
        <button className="doc-link-btn" onClick={() => window.print()}>{t("In", "Print")}</button>
      </span> : null}>
      <div className="dos">
        {d && <div className="dos-noprint tt-dos-mobile">
          <button className="bat-btn ghost" onClick={download}>{t("Tải JSON đã ký", "Download signed JSON")}</button>
        </div>}

      <main className="dos-wrap">
        {err && <p className="doc-note">{err}</p>}
        {!d && !err && <p className="doc-note">{t("Đang tải và kiểm chứng hồ sơ…", "Loading and verifying the dossier…")}</p>}

        {d && f && v && (
          <article className="dos-paper">
            <div className="dos-head">
              <div>
                <p className="dos-eyebrow">{isLot ? t("CHỨNG THƯ LÔ HÀNG · TERRATWIN", "LOT CERTIFICATE · TERRATWIN") : isEudr
                  ? t("HỒ SƠ VƯỜN CHUẨN EUDR · TERRATWIN", "EUDR PLOT DOSSIER · TERRATWIN")
                  : t("HỒ SƠ ĐẤT SỐ · TERRATWIN", "DIGITAL LAND DOSSIER · TERRATWIN")}</p>
                <h1>{isLot ? ((f as unknown as LotCertificateFacts).lot.ref || t("Lô hàng", "Lot"))
                  : isEudr ? f.plot!.ref : <>{t("Thửa", "Plot")} {f.location.lat.toFixed(5)}, {f.location.lon.toFixed(5)}</>}</h1>
                <p className="dos-meta">
                  {t("Phát hành", "Issued")} {fmtTime(d.issued_at)} · {t("Số", "No.")} {String(d.seq).padStart(6, "0")} ·{" "}
                  {t("Mã", "ID")} <code>{d.id}</code>
                  {isLot ? null : isEudr ? <> · {f.plot!.area_ha} ha</> : f.location.area_ha ? <> · {f.location.area_ha} ha</> : null}
                </p>
              </div>
              {d.qr && (
                <figure className="dos-qr">
                  <img src={d.qr} alt={t("Mã QR tới trang kiểm chứng", "QR code to the verification page")} width={112} height={112} />
                  <figcaption>{t("Quét để kiểm bản gốc", "Scan to verify the original")}</figcaption>
                </figure>
              )}
            </div>

            <section className={`dos-verify ${v.valid ? "ok" : "bad"}`} aria-live="polite">
              <b>{v.valid
                ? t("✓ Bản gốc — đã kiểm chứng", "✓ Original — verified")
                : t("✗ KHÔNG qua kiểm chứng — đừng tin nội dung dưới đây", "✗ FAILED verification — do not trust the content below")}</b>
              <ul>
                {v.checks.map((c) => <li key={c.id} className={c.ok ? "ok" : "bad"}>{c.ok ? "✓" : "✗"} {c.label}</li>)}
              </ul>
              <small>{t("Máy chủ vừa chạy lại bốn phép kiểm này khi bạn mở trang.",
                        "The server re-ran these four checks when you opened this page.")}</small>
            </section>

            {d.monitor && (
              <section className={`dos-live ${d.monitor.changed ? "bad" : "ok"}`}>
                <b>{d.monitor.changed
                  ? t("Giám sát sau phát hành: vườn đã XẤU ĐI so với lúc phát hành", "Post-issuance monitoring: the plot has WORSENED since issuance")
                  : t("Giám sát sau phát hành: chưa thấy thay đổi", "Post-issuance monitoring: no change found")}</b>
                <span>{t("Kiểm lại", "Re-checked")} {fmtTime(d.monitor.checked_at)} · {t("lúc phát hành", "at issuance")}: {d.monitor.issued_level} → {t("nay", "now")}: {d.monitor.level}
                  {d.monitor.s2_after ? ` · ${t("ảnh mới nhất", "latest image")} ${fmtDate(d.monitor.s2_after)}` : ""}</span>
                <small>{t("Kết quả SỐNG — không phải nội dung đã ký (hồ sơ đã ký là bất biến).", "LIVE result — not signed content (the signed dossier is immutable).")}</small>
              </section>
            )}

            {isEudr && <EudrDossierView f={f as unknown as EudrDossierFacts} revealed={d.revealed} />}
            {isEudr && tok && <DeliveryConfirm id={d.id} token={tok} />}
            {isLot && <LotCertificateView f={f as unknown as LotCertificateFacts} certId={d.id} />}

            {!isEudr && !isLot && <>
            <div className="dos-grid">
              <section>
                <h2>{t("Loại đất", "Land type")}</h2>
                {lu ? (
                  <>
                    <div className="lu-bar dos-bar" aria-hidden="true">
                      {lu.classes.map((c) => <span key={c.code} className={`lu-${c.group}`} style={{ width: `${c.pct}%` }} />)}
                    </div>
                    <ul className="dos-list">
                      {lu.classes.map((c) => <li key={c.code}><span>{c.name}</span><b>{c.pct.toFixed(0)}%</b></li>)}
                    </ul>
                    <p className="dos-src">{lu.source} · {lu.pixels} {t("điểm ảnh 10 m", "10 m pixels")}</p>
                  </>
                ) : <p className="dos-miss">{t("Không lấy được lúc phát hành.", "Not available at issuance.")}</p>}
              </section>

              <section>
                <h2>{t("Địa hình", "Terrain")}</h2>
                {f.terrain ? (
                  <>
                    <ul className="dos-list">
                      <li><span>{t("Cao độ", "Elevation")}</span><b>{f.terrain.elevation_m} m</b></li>
                      <li><span>{t(`Thấp hơn đất trong ${f.terrain.radius_km} km`, `Lower than land within ${f.terrain.radius_km} km`)}</span><b>{f.terrain.lower_than_pct}%</b></li>
                      <li><span>{t("Độ dốc", "Slope")}</span><b>{f.terrain.slope_deg ?? "—"}°</b></li>
                    </ul>
                    <p className="dos-note">{f.terrain.meaning}</p>
                  </>
                ) : <p className="dos-miss">{t("Không lấy được lúc phát hành.", "Not available at issuance.")}</p>}
              </section>
            </div>

            <section>
              <h2>{t("Mười năm hiểm hoạ tại chính thửa này", "Ten years of hazards at this exact plot")}</h2>
              {hist.length ? (
                <div className="dos-table-wrap">
                  <table className="dos-table">
                    <thead><tr>
                      <th>{t("Hiểm hoạ", "Hazard")}</th><th>{t("Số đợt vượt ngưỡng", "Episodes over threshold")}</th>
                      <th>{t("Tháng nhiều nhất", "Peak month")}</th><th>{t("Nặng nhất", "Most severe")}</th><th>{t("Gần nhất", "Latest")}</th>
                    </tr></thead>
                    <tbody>
                      {hist.map(([mid, h]) => (
                        <tr key={mid}>
                          <td>{h.name}</td><td className="num">{h.events}</td>
                          <td className="num">{h.peak_month ?? "—"}</td>
                          <td className="num">{fmtDate(h.worst_date)}</td>
                          <td className="num">{fmtDate(h.latest)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : <p className="dos-miss">{t("Không lấy được lúc phát hành.", "Not available at issuance.")}</p>}
              {f.history_caveat && <p className="dos-src">{f.history_caveat}</p>}
            </section>

            {!cr && f.predictions_note && (
              <section>
                <h2>{t("Dự báo không nằm trong hồ sơ", "Forecasts are not in this dossier")}</h2>
                <p className="dos-note">{f.predictions_note}</p>
              </section>
            )}

            {cr && <section>
              <h2>{t("Hiện trạng rủi ro lúc phát hành", "Risk status at issuance")}</h2>
              {cr ? (
                <>
                  <p className="dos-score">
                    <b>{cr.terrascore.score}/100 · {cr.terrascore.grade}</b> {cr.terrascore.summary}
                  </p>
                  <ul className="dos-mods">
                    {cr.modules.map((m) => {
                      const lv = levelOf(m.risk_level, m.threat);
                      return (
                        <li key={m.id} title={m.headline}>
                          <span className="dos-dot" style={{ background: lv.color }} />
                          <span className="dos-mname">{m.name}</span>
                          <span className="dos-mlv">{lang === "en" ? lv.en : lv.vi}</span>
                          <span className="dos-mtag">{statusTag(m, t)}</span>
                        </li>
                      );
                    })}
                  </ul>
                  <p className="dos-src">
                    {t("Đánh giá lúc", "Assessed at")} {fmtTime(cr.assessed_at)} · {t("tỉ lệ dữ liệu thật", "real-data ratio")} {Math.round(cr.real_data_ratio * 100)}%
                    {cr.not_assessed_in_dossier.length > 0 && <> · {t(`${cr.not_assessed_in_dossier.length} mô-đun ảnh vệ tinh không chạy trong hồ sơ`,
                      `${cr.not_assessed_in_dossier.length} satellite-image modules not run for the dossier`)}</>}
                  </p>
                </>
              ) : <p className="dos-miss">{t("Không lấy được lúc phát hành.", "Not available at issuance.")}</p>}
            </section>}

            {f.land_change && (
              <section>
                <h2>{t("Đất có đổi khác sau 2021?", "Has the land changed since 2021?")}</h2>
                <p className={`dos-score ${f.land_change.changed ? "dos-flag" : ""}`}><b>{f.land_change.headline}</b></p>
                <div className="dos-table-wrap">
                  <table className="dos-table">
                    <thead><tr>
                      <th>{t("Nhóm lớp phủ", "Cover group")}</th>
                      <th>2021 (WorldCover)</th>
                      <th>{f.land_change.now.image.date} ({t("mô hình", "model")})</th>
                      <th>{t("Chênh", "Change")}</th>
                    </tr></thead>
                    <tbody>
                      {(["built", "crop", "tree", "water", "open"] as const).map((g) => (
                        <tr key={g}>
                          <td>{{ built: t("Xây dựng", "Built-up"), crop: t("Trồng trọt", "Cropland"),
                                 tree: t("Cây xanh", "Trees"), water: t("Mặt nước", "Water"),
                                 open: t("Đất trống / cỏ", "Open land") }[g]}</td>
                          <td className="num">{(f.land_change!.before.groups_pct[g] ?? 0).toFixed(0)}%</td>
                          <td className="num">{(f.land_change!.now.groups_pct[g] ?? 0).toFixed(0)}%</td>
                          <td className="num">{f.land_change!.delta_pts[g] > 0 ? "+" : ""}{f.land_change!.delta_pts[g].toFixed(0)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="dos-src">
                  {f.land_change.now.source} · {t("ảnh quang mây tại thửa", "cloud-free at plot")} {f.land_change.now.image.clear_pct_at_plot}%
                  {f.land_change.model.miou_holdout != null && <> · {t("mIoU trên tỉnh mô hình chưa từng thấy", "mIoU on provinces the model never saw")} {f.land_change.model.miou_holdout.toFixed(2)}</>}
                  {" · "}{f.land_change.caveat}
                </p>
              </section>
            )}

            {f.field_evidence && f.field_evidence.length > 0 && (
              <section>
                <h2>{t("Ảnh thực địa đã kiểm", "Verified field photos")}</h2>
                <div className="dos-photos">
                  {f.field_evidence.map((e) => (
                    <figure key={e.id} className={`dos-photo ${e.verdict}`}>
                      <img src={evidenceThumbSrc(e)} alt={t("Ảnh thực địa", "Field photo")} loading="lazy" />
                      <figcaption>
                        <b className="dos-photo-v">{e.verdict_label}</b>
                        <ul>
                          {e.checks.map((c) => (
                            <li key={c.id} className={c.ok === false ? "bad" : c.ok === null ? "unk" : "ok"}>
                              {c.ok === false ? "✗" : c.ok === null ? "?" : "✓"} {c.label}
                            </li>
                          ))}
                        </ul>
                        <code title={t("SHA-256 của ảnh gốc", "SHA-256 of the original photo")}>{e.sha256.slice(0, 16)}…</code>
                      </figcaption>
                    </figure>
                  ))}
                </div>
                <p className="dos-src">{f.field_evidence[0].caveat}</p>
              </section>
            )}

            {f.track_record && (
              <section>
                <h2>{t("Độ tin cậy của chính TerraTwin", "TerraTwin's own track record")}</h2>
                <p className="dos-note">{f.track_record.headline ?? t("Không lấy được lúc phát hành.", "Not available at issuance.")}</p>
              </section>
            )}
            </>}

            {!isLot && <section>
              <h2>{t("Nguồn dữ liệu", "Data sources")}</h2>
              <ul className="dos-bullets">{(f.sources ?? []).map((s) => <li key={s}>{s}</li>)}</ul>
              {(f.missing?.length ?? 0) > 0 && (
                <p className="dos-miss">{t("Thiếu lúc phát hành:", "Missing at issuance:")} {f.missing.join(", ")}</p>
              )}
              <p className="dos-disclaimer">{f.disclaimer}</p>
            </section>}

            {d.transparency && (
              <section>
                <h2>{t("Sổ minh bạch (RFC 6962)", "Transparency log (RFC 6962)")}</h2>
                <p className="dos-src">{t(
                  `Hồ sơ này là lá #${d.transparency.seq} của cây Merkle gồm ${d.transparency.tree_size} hồ sơ; đầu cây đã ký lúc ${fmtTime(d.transparency.head.timestamp)}. Mỗi ngày một tác vụ độc lập trên GitHub lưu đầu cây và kiểm cây chỉ được thêm, không bị sửa (nhánh transparency-log).`,
                  `This dossier is leaf #${d.transparency.seq} of a Merkle tree of ${d.transparency.tree_size} dossiers; tree head signed at ${fmtTime(d.transparency.head.timestamp)}. Every day an independent GitHub job stores the tree head and checks the tree is append-only (branch transparency-log).`)}</p>
                <p className="dos-src"><code className="eu-hash">{d.transparency.root_hash}</code></p>
              </section>
            )}

            <section className="dos-proof">
              <h2>{t("Bằng chứng kỹ thuật", "Technical proof")}</h2>
              <dl>
                <dt>{t("Mã băm nội dung (SHA-256)", "Content hash (SHA-256)")}</dt><dd><code>{d.proof.facts_hash}</code></dd>
                <dt>{t("Mục sổ đăng ký", "Registry entry")}</dt><dd><code>{d.proof.entry_hash}</code></dd>
                <dt>{t("Nối vào mục trước", "Links to previous entry")}</dt><dd><code>{d.proof.prev_hash}</code></dd>
                <dt>{t("Chữ ký", "Signature")} ({d.proof.algorithm}, {t("khoá", "key")} {d.proof.key_id})</dt><dd><code>{d.proof.signature}</code></dd>
              </dl>
              <p className="dos-src">
                {t("Tự kiểm không cần tin máy chủ: tải ", "Verify without trusting the server: download ")}
                <a href={`${process.env.NEXT_PUBLIC_API ?? "http://localhost:8000"}/api/dossiers/keys`} target="_blank" rel="noreferrer">{t("khoá công khai", "the public key")}</a>
                {t(" và ", " and ")}
                <a href={`${process.env.NEXT_PUBLIC_API ?? "http://localhost:8000"}/api/dossiers/log`} target="_blank" rel="noreferrer">{t("sổ đăng ký công khai", "the public registry")}</a>
                {t(" (chỉ mã băm, không nội dung hay toạ độ của ai), kiểm chữ ký Ed25519 trên entry_hash và từng mắt xích prev_hash.",
                   " (hashes only — nobody's content or coordinates), then check the Ed25519 signature over entry_hash and every prev_hash link.")}
              </p>
            </section>

            <section className="dos-noprint dos-check">
              <h2>{t("Kiểm một tệp hồ sơ ai đó gửi bạn", "Check a dossier file someone sent you")}</h2>
              <label className="dos-file">
                <input id="dossier-file" type="file" accept="application/json,.json" onChange={(e) => checkFile(e.target.files?.[0])} />
                <span>{t("Chọn tệp .json đã tải từ TerraTwin", "Choose a .json file downloaded from TerraTwin")}</span>
              </label>
              {fileErr && <p className="dos-miss">{fileErr}</p>}
              {fileCheck && <p className={`dos-verify-inline ${fileCheck.valid ? "ok" : "bad"}`}>{fileCheck.valid ? "✓" : "✗"} {fileCheck.message}</p>}
            </section>
          </article>
        )}
      </main>
      </div>
    </AppShell>
  );
}
