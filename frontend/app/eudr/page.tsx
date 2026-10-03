"use client";

/**
 * HỒ SƠ VƯỜN CHUẨN EUDR — sản phẩm chính của TerraTwin từ 3/10/2026.
 *
 * Ba việc, đúng thứ tự người ta phải làm trước 30/12/2026:
 *   1. Lấy ranh vườn đúng chuẩn GeoJSON của EU (vẽ / đi bộ GPS / tải tệp) và sửa lỗi
 *      TRƯỚC khi nộp — hệ thống EU từ chối ranh hở, tự cắt, có lỗ, thửa > 4 ha chỉ
 *      khai một điểm.
 *   2. Sàng lọc phá rừng sau 31/12/2020 bằng ba bản đồ rừng 2020 độc lập + ảnh cùng mùa.
 *   3. Phát hành Hồ sơ vườn ký số (nông hộ giữ, ai cũng tự kiểm) / xuất GeoJSON nộp EU.
 * Tab "Cả lô" cho doanh nghiệp, hợp tác xã: cả danh sách nhà cung cấp một lần.
 */

import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { Copy, Download, FileCheck2, FileSignature, MessageCircleQuestion, Package, ScanSearch, Upload } from "lucide-react";
import Account from "@/components/Account";
import EudrResult, { IssueList, LevelBadge } from "@/components/EudrResult";
import LandDocForm from "@/components/LandDocForm";
import {
  eudrDeleteSet, eudrDownloadSet, eudrExport, eudrGetSet, eudrIssueDossier, eudrListSets, eudrMethod, eudrScreen,
  eudrAsk, eudrSetDossiers, eudrSubmitSet, eudrValidate, fetchMe, getToken,
  type AskCitation, type AuthUser, type Dossier, type LandDocInput, type EudrLevel, type EudrMethod, type EudrPlot, type EudrScreening, type EudrSet, type EudrSetInfo,
  type EudrValidation, type GeoGeometry,
} from "@/lib/api";
import { LangToggle, useLang } from "@/lib/i18n";

const PlotDraw = dynamic(() => import("@/components/PlotDraw"), { ssr: false });

type Tab = "one" | "set" | "ask" | "method";
const COMMODITIES: [string, string, string][] = [
  ["coffee", "Cà phê", "Coffee"], ["rubber", "Cao su", "Rubber"], ["wood", "Gỗ", "Wood"],
  ["cocoa", "Ca cao", "Cocoa"], ["other", "Khác", "Other"],
];
const LEVEL_RANK: Record<string, number> = { high: 0, review: 1, unknown: 2, low: 3 };

const TEMPLATE = "ma,chu_ho,vi_do,kinh_do,dien_tich,wkt\n" +
  "V-001,Nguyễn Văn A,12.712345,108.061234,1.2,\n" +
  "V-002,Trần Thị B,,,,\"POLYGON((108.050000 12.700000, 108.051000 12.700000, 108.051000 12.701000, 108.050000 12.701000, 108.050000 12.700000))\"\n";

function readFile(f: File): Promise<string> { return f.text(); }

export default function EudrPage() {
  const { t, lang } = useLang();
  const [tab, setTab] = useState<Tab>("one");
  const [user, setUser] = useState<AuthUser | null>(null);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("tab");
    if (q === "lo" || q === "set") setTab("set");
    else if (q === "phuong-phap" || q === "method") setTab("method");
    else if (q === "hoi-dap" || q === "ask") setTab("ask");
    if (getToken()) fetchMe().then(setUser).catch(() => setUser(null));
  }, []);

  function go(k: Tab) {
    setTab(k);
    const slug = k === "set" ? "lo" : k === "method" ? "phuong-phap" : k === "ask" ? "hoi-dap" : "";
    window.history.replaceState(null, "", slug ? `/eudr?tab=${slug}` : "/eudr");
  }

  return (
    <div className="doc">
      <header className="doc-top">
        <Link href="/" className="doc-brand">◵ TerraTwin</Link>
        <div className="doc-actions"><LangToggle /><Account user={user} onAuth={setUser} /></div>
      </header>
      <main className="bat-wrap eu-wrap">
        <div>
          <p className="eu-eyebrow">{t("EUDR · Quy định chống phá rừng của EU · áp dụng 30/12/2026", "EUDR · EU Deforestation Regulation · applies 30/12/2026")}</p>
          <h1>{t("Hồ sơ vườn chuẩn EUDR", "EUDR-ready plot dossier")}</h1>
          <p className="doc-lede">{t(
            "Lấy ranh vườn đúng chuẩn tệp của EU, sàng lọc phá rừng sau 31/12/2020 bằng ba bản đồ rừng độc lập và ảnh vệ tinh, rồi phát hành hồ sơ có chữ ký số mà nông hộ giữ và bất kỳ người mua nào cũng tự kiểm được.",
            "Capture the plot boundary in the EU file format, screen for deforestation after 31/12/2020 with three independent forest maps and satellite imagery, then issue a digitally signed dossier the farmer keeps and any buyer can verify.")}</p>
        </div>
        <nav className="eu-tabs" role="tablist">
          {([["one", t("Một vườn", "One plot")], ["set", t("Cả lô (doanh nghiệp, HTX)", "Whole set (exporters, co-ops)")],
             ["ask", t("Hỏi đáp EUDR", "EUDR Q&A")], ["method", t("Phương pháp & kiểm định", "Method & validation")]] as [Tab, string][]).map(([k, label]) => (
            <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""} onClick={() => go(k)}>{label}</button>
          ))}
        </nav>
        {tab === "one" && <OnePlot />}
        {tab === "set" && <WholeSet user={user} />}
        {tab === "ask" && <Ask />}
        {tab === "method" && <Method lang={lang} />}
      </main>
    </div>
  );
}

// ------------------------------------------------------------------ một vườn

function OnePlot() {
  const { t } = useLang();
  const [geom, setGeom] = useState<GeoGeometry | null>(null);
  const [initial, setInitial] = useState<GeoGeometry | null>(null);
  const [gpsAcc, setGpsAcc] = useState<number | null>(null);
  const [ref, setRef] = useState("");
  const [producer, setProducer] = useState("");
  const [commodity, setCommodity] = useState("coffee");
  const [busy, setBusy] = useState<"" | "screen" | "issue" | "export">("");
  const [err, setErr] = useState<string | null>(null);
  const [res, setRes] = useState<{ plot: EudrPlot; screening: EudrScreening | null } | null>(null);
  const [hideProducer, setHideProducer] = useState(true);
  const [landDoc, setLandDoc] = useState<LandDocInput | null>(null);
  const [issued, setIssued] = useState<Dossier | null>(null);

  const onDraw = useCallback(({ geometry, gpsAccuracy }: { geometry: GeoGeometry | null; gpsAccuracy: number | null }) => {
    setGeom(geometry); setGpsAcc(gpsAccuracy); setRes(null); setIssued(null);
  }, []);

  async function importFile(f: File | undefined) {
    if (!f) return;
    setErr(null);
    try {
      const v = await eudrValidate(await readFile(f), f.name);
      const p = v.plots.find((x) => x.geometry && x.kind === "polygon") ?? v.plots[0];
      if (!p?.geometry) throw new Error(v.file_errors[0]?.message ?? t("Tệp không có ranh thửa nào đọc được.", "No readable boundary in the file."));
      if (p.geometry.type !== "Polygon") throw new Error(t("Mục này nhận một đa giác (Polygon). Tệp nhiều thửa hoặc điểm: dùng tab \"Cả lô\".",
        "This tab takes one Polygon. Files with many plots or points: use the \"Whole set\" tab."));
      setInitial(p.geometry);
      if (p.ref && !p.ref.startsWith("#")) setRef(p.ref);
      if (p.producer) setProducer(p.producer);
    } catch (e) { setErr((e as Error).message); }
  }

  const input = () => ({ geometry: geom!, ref, producer, gps_accuracy_m: gpsAcc });

  async function screen() {
    setBusy("screen"); setErr(null);
    try { setRes(await eudrScreen(input())); } catch (e) { setErr((e as Error).message); } finally { setBusy(""); }
  }
  async function issue() {
    setBusy("issue"); setErr(null);
    try {
      setIssued(await eudrIssueDossier({ ...input(), commodity, hide_producer: hideProducer, land_document: landDoc }));
    } catch (e) { setErr((e as Error).message); } finally { setBusy(""); }
  }
  async function exportGeo() {
    setBusy("export"); setErr(null);
    try { await eudrExport({ geometry: geom!, ref, producer }); } catch (e) { setErr((e as Error).message); } finally { setBusy(""); }
  }

  return (
    <>
      <section className="bat-card">
        <h2>1 · {t("Ranh vườn", "Plot boundary")}</h2>
        <PlotDraw initial={initial} onChange={onDraw} />
        <div className="bat-row">
          <label className="bat-btn ghost">
            <Upload size={15} aria-hidden="true" className="ui-ic" /> {t("Hoặc tải tệp ranh (GeoJSON, KML)", "Or upload a boundary file (GeoJSON, KML)")}
            <input type="file" hidden accept=".geojson,.json,.kml,application/geo+json,application/vnd.google-earth.kml+xml"
                   onChange={(e) => importFile(e.target.files?.[0])} />
          </label>
        </div>
        <div className="eu-fields">
          <label>{t("Tên / mã vườn", "Plot name / ID")}<input className="bat-input" value={ref} maxLength={80} onChange={(e) => setRef(e.target.value)} placeholder={t("vd: Vườn rẫy Ea Tu 2", "e.g. Ea Tu farm 2")} /></label>
          <label>{t("Chủ hộ", "Producer")}<input className="bat-input" value={producer} maxLength={120} onChange={(e) => setProducer(e.target.value)} placeholder={t("Họ tên chủ hộ", "Producer name")} /></label>
          <label>{t("Nông sản", "Commodity")}
            <select className="bat-input" value={commodity} onChange={(e) => setCommodity(e.target.value)}>
              {COMMODITIES.map(([k, vi, en]) => <option key={k} value={k}>{t(vi, en)}</option>)}
            </select>
          </label>
        </div>
        <div className="bat-row">
          <button className="bat-btn" disabled={!geom || !!busy} onClick={screen}>
            <ScanSearch size={15} aria-hidden="true" className="ui-ic" />{" "}
            {busy === "screen" ? t("Đang kiểm và sàng lọc… (10–30 giây)", "Checking and screening… (10–30 s)") : t("Kiểm chuẩn EU + sàng lọc phá rừng", "Check EU format + screen deforestation")}
          </button>
          {!geom && <small>{t("Cần ít nhất 3 điểm ranh.", "At least 3 boundary points are needed.")}</small>}
        </div>
        {err && <p className="bat-err">{err}</p>}
      </section>

      {res && (
        <section className="bat-card">
          <h2>2 · {t("Chuẩn tệp EU", "EU file format")} {res.plot.valid
            ? <span className="eu-badge eu-low"><FileCheck2 size={15} aria-hidden="true" /> {t("Đạt", "Pass")}</span>
            : <span className="eu-badge eu-high">{t("Có lỗi", "Has errors")}</span>}</h2>
          <p className="eu-src">{res.plot.area_ha != null && <>{t("Diện tích tính từ ranh", "Area from boundary")} <b>{res.plot.area_ha} ha</b> · </>}
            {res.plot.n_vertices} {t("đỉnh", "vertices")} · {t("toạ độ làm tròn 6 chữ số (~0,1 m), ranh ngược chiều kim đồng hồ", "coordinates rounded to 6 decimals (~0.1 m), counter-clockwise ring")}</p>
          <IssueList issues={res.plot.issues} />
        </section>
      )}

      {res?.screening && (
        <section className="bat-card">
          <h2>3 · {t("Sàng lọc phá rừng sau 31/12/2020", "Deforestation screening after 31/12/2020")}</h2>
          <EudrResult s={res.screening} geometry={res.plot.geometry} areaHa={res.plot.area_ha} />
        </section>
      )}

      {res?.plot.valid && (
        <section className="bat-card">
          <h2>4 · {t("Giấy tờ đất (tuỳ chọn, nên có)", "Land documents (optional, recommended)")}</h2>
          <p className="eu-src">{t("EUDR đòi cả tính HỢP PHÁP: quyền sử dụng đất đúng mục đích. Ảnh vệ tinh không trả lời được câu này — giấy chứng nhận thì có.",
            "The EUDR also requires LEGALITY: land-use rights for the right purpose. Satellite imagery can't answer that — the certificate can.")}</p>
          <LandDocForm areaHa={res.plot.area_ha} producer={producer} onChange={setLandDoc} />
        </section>
      )}

      {res?.plot.valid && (
        <section className="bat-card">
          <h2>5 · {t("Hồ sơ & tệp nộp EU", "Dossier & EU file")}</h2>
          <label className="eu-check">
            <input id="hide-producer" type="checkbox" checked={hideProducer} onChange={(e) => setHideProducer(e.target.checked)} />
            {t("Ẩn tên chủ hộ trên trang công khai (khuyên dùng — dữ liệu cá nhân). Nông hộ giữ đường link đầy đủ để chứng minh khi cần.",
               "Hide the producer's name on the public page (recommended — personal data). The farmer keeps a full link to prove it when needed.")}
          </label>
          <div className="bat-row">
            <button className="bat-btn" disabled={!!busy} onClick={issue}>
              <FileSignature size={15} aria-hidden="true" className="ui-ic" />{" "}
              {busy === "issue" ? t("Đang phát hành…", "Issuing…") : t("Phát hành Hồ sơ vườn ký số", "Issue signed plot dossier")}
            </button>
            <button className="bat-btn ghost" disabled={!!busy} onClick={exportGeo}>
              <Download size={15} aria-hidden="true" className="ui-ic" /> {t("Tải GeoJSON chuẩn EU", "Download EU GeoJSON")}
            </button>
          </div>
          {issued && <IssuedCard d={issued} />}
          <p className="eu-src">{t(
            "Hồ sơ có mã + QR, chữ ký Ed25519, nối vào sổ đăng ký công khai móc xích. Nông hộ in ra giữ; đại lý, doanh nghiệp, ngân hàng quét QR là kiểm được bản gốc — không cần tài khoản, không cần tin TerraTwin. Hồ sơ chỉ chứa số ĐO và số TÍNH LẠI ĐƯỢC, không chứa dự báo.",
            "The dossier has an ID + QR, an Ed25519 signature and a link in a hash-chained public registry. The farmer prints and keeps it; traders, exporters and banks scan the QR to verify the original — no account, no need to trust TerraTwin. It holds only MEASURED and RECOMPUTABLE figures, no forecasts.")}</p>
        </section>
      )}
    </>
  );
}

// ------------------------------------------------------------------ cả lô

function WholeSet({ user }: { user: AuthUser | null }) {
  const { t, lang } = useLang();
  const [text, setText] = useState("");
  const [filename, setFilename] = useState("");
  const [val, setVal] = useState<EudrValidation | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [commodity, setCommodity] = useState("coffee");
  const [producer, setProducer] = useState("");
  const [cur, setCur] = useState<EudrSet | null>(null);
  const [sets, setSets] = useState<EudrSetInfo[]>([]);
  const [warn, setWarn] = useState<string | null>(null);
  const [issued, setIssued] = useState<{ ref: string; id: string; url: string; full_url?: string | null }[]>([]);
  const [open, setOpen] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const r = await eudrListSets();
    setSets(r.sets);
    return r;
  }, []);

  useEffect(() => {
    if (!user) return;
    refresh().then((r) => { if (r.sets[0]) eudrGetSet(r.sets[0].id).then(setCur).catch(() => {}); }).catch(() => {});
  }, [user, refresh]);

  useEffect(() => {
    if (!cur || cur.state === "done") return;
    const id = setInterval(async () => {
      try {
        const s = await eudrGetSet(cur.id);
        setCur(s);
        if (s.state === "done") refresh().catch(() => {});
      } catch { /* thử lại nhịp sau */ }
    }, 4000);
    return () => clearInterval(id);
  }, [cur, refresh]);

  async function validate() {
    setBusy(true); setErr(null);
    try { setVal(await eudrValidate(text, filename)); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }
  async function submit() {
    setBusy(true); setErr(null); setWarn(null); setIssued([]);
    try {
      const r = await eudrSubmitSet({ text, filename, title, commodity, producer });
      setWarn(r.warning);
      setCur(await eudrGetSet(r.set_id));
      refresh().catch(() => {});
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }

  const rows = useMemo(() => {
    if (!cur) return [];
    return [...cur.plots].sort((a, b) => {
      const ra = a.valid ? LEVEL_RANK[cur.results[String(a.index)]?.level ?? "unknown"] ?? 2 : -1;
      const rb = b.valid ? LEVEL_RANK[cur.results[String(b.index)]?.level ?? "unknown"] ?? 2 : -1;
      return ra - rb;
    });
  }, [cur]);

  return (
    <>
      <section className="bat-card">
        <h2>1 · {t("Tệp ranh thửa của cả lô", "Boundary file for the whole set")}</h2>
        <p className="eu-src">{t(
          "Nhận GeoJSON (kể cả tệp xuất từ hệ thống EU), KML (Google Earth, ứng dụng đo đất), CSV/Excel: mỗi dòng một thửa — toạ độ điểm (vi_do, kinh_do, dien_tich) hoặc cột ranh dạng WKT. Kiểm chuẩn EU không cần đăng nhập, không lưu gì.",
          "Accepts GeoJSON (including files exported from the EU system), KML (Google Earth, field-measuring apps), CSV/Excel: one plot per row — point coordinates (lat, lon, area) or a WKT boundary column. The EU format check needs no account and stores nothing.")}</p>
        <div className="bat-row">
          <label className="bat-btn ghost">
            <Upload size={15} aria-hidden="true" className="ui-ic" /> {t("Chọn tệp", "Choose file")}
            <input type="file" hidden accept=".geojson,.json,.kml,.csv,.txt"
                   onChange={async (e) => { const f = e.target.files?.[0]; if (f) { setText(await readFile(f)); setFilename(f.name); setVal(null); } }} />
          </label>
          <a className="bat-btn ghost" download="terratwin-eudr-mau.csv"
             href={`data:text/csv;charset=utf-8,${encodeURIComponent("﻿" + TEMPLATE)}`}>{t("Tải tệp mẫu CSV", "Download CSV template")}</a>
          {filename && <small>{filename} · {(text.length / 1024).toFixed(0)} KB</small>}
        </div>
        <textarea className="bat-csv" rows={6} spellCheck={false} value={text} placeholder={TEMPLATE}
                  onChange={(e) => { setText(e.target.value); setFilename(""); setVal(null); }} />
        <div className="bat-row">
          <button className="bat-btn" disabled={busy || !text.trim()} onClick={validate}>
            <FileCheck2 size={15} aria-hidden="true" className="ui-ic" /> {t("Kiểm chuẩn EU", "Check EU format")}
          </button>
          {val && val.summary.n_valid > 0 && (
            <button className="bat-btn ghost" onClick={() => eudrExport({ text, filename }).catch((e) => setErr(e.message))}>
              <Download size={15} aria-hidden="true" className="ui-ic" /> {t(`Tải GeoJSON chuẩn EU (${val.summary.n_valid} thửa đúng)`, `Download EU GeoJSON (${val.summary.n_valid} valid plots)`)}
            </button>
          )}
        </div>
        {err && <p className="bat-err">{err}</p>}
        {val && <ValidationTable v={val} />}
      </section>

      <section className="bat-card">
        <h2>2 · {t("Sàng lọc phá rừng cả lô", "Screen the whole set for deforestation")}</h2>
        {!user ? (
          <p className="doc-note">{t("Đăng nhập (nút trên cùng) để sàng lọc cả lô — kết quả là danh sách nhà cung cấp của bạn, chỉ bạn xem được, lưu lại để mở lần sau.",
                                     "Sign in (top button) to screen a whole set — results are your supplier list, visible only to you and saved for later.")}</p>
        ) : (
          <>
            <div className="eu-fields">
              <label>{t("Tên lô", "Set name")}<input className="bat-input" value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} placeholder={t("vd: Thu mua vụ 2026/27 — HTX Ea Tu", "e.g. 2026/27 harvest — Ea Tu co-op")} /></label>
              <label>{t("Nông sản", "Commodity")}
                <select className="bat-input" value={commodity} onChange={(e) => setCommodity(e.target.value)}>
                  {COMMODITIES.map(([k, vi, en]) => <option key={k} value={k}>{t(vi, en)}</option>)}
                </select>
              </label>
              <label>{t("Tên nhà sản xuất mặc định (ProducerName)", "Default producer name (ProducerName)")}<input className="bat-input" value={producer} maxLength={120} onChange={(e) => setProducer(e.target.value)} /></label>
            </div>
            <div className="bat-row">
              <button className="bat-btn" disabled={busy || !text.trim() || (cur != null && cur.state !== "done")} onClick={submit}>
                <ScanSearch size={15} aria-hidden="true" className="ui-ic" /> {t("Sàng lọc cả lô", "Screen the set")}
              </button>
              <small>{t("Mỗi thửa ~10–20 giây. Thửa lỗi chuẩn EU không được sàng lọc.", "~10–20 s per plot. Plots with EU format errors are not screened.")}</small>
            </div>
            {warn && <p className="doc-note">{warn}</p>}
          </>
        )}
      </section>

      {cur && cur.state !== "done" && (
        <section className="bat-card">
          <b>{t("Đang sàng lọc…", "Screening…")} {cur.title}</b>
          <div className="bat-bar"><span style={{ width: `${cur.progress?.total ? (100 * cur.progress.done) / cur.progress.total : 3}%` }} /></div>
          <small>{cur.progress?.done ?? 0}/{cur.progress?.total ?? "?"} {t("thửa", "plots")}{cur.progress?.current ? ` · ${cur.progress.current}` : ""}</small>
          <p className="bat-keepopen">{t(
            "Giữ trang mở tới khi xong. Máy chủ gói miễn phí ngủ sau 15 phút không ai truy cập; đóng trang thì lô tạm dừng và tự chạy tiếp từ thửa dở khi bạn mở lại.",
            "Keep this page open until it finishes. The free-tier server sleeps after 15 minutes with no visitors; if you close the page the set pauses and resumes from the last plot when you come back.")}</p>
        </section>
      )}

      {cur && cur.state === "done" && (
        <section className="bat-card">
          <div className="bat-row bat-between">
            <h2>{cur.title || t("Kết quả sàng lọc", "Screening result")}</h2>
            <div className="bat-row">
              <button className="bat-btn ghost" onClick={() => eudrDownloadSet(cur.id, "csv").catch((e) => setErr(e.message))}>{t("Báo cáo CSV", "CSV report")}</button>
              <button className="bat-btn ghost" onClick={() => eudrDownloadSet(cur.id, "geojson-passed").catch((e) => setErr(e.message))}>{t("GeoJSON thửa đạt sàng lọc", "GeoJSON of passed plots")}</button>
              <button className="bat-btn ghost" onClick={() => eudrDownloadSet(cur.id, "geojson-valid").catch((e) => setErr(e.message))}>{t("GeoJSON mọi thửa đúng chuẩn", "GeoJSON of all valid plots")}</button>
              <button className="bat-btn ghost danger" onClick={async () => {
                await eudrDeleteSet(cur.id).catch((e) => setErr(e.message)); setCur(null); refresh().catch(() => {});
              }}>{t("Xoá", "Delete")}</button>
            </div>
          </div>
          <p className="bat-head">{cur.summary.headline}</p>
          <div className="bat-tiles">
            {(["low", "review", "high", "unknown"] as EudrLevel[]).map((k) => (
              <div key={k} className={`eu-tile eu-${k}`}><b>{cur.summary.by_level[k] ?? 0}</b>
                <span>{{ low: t("đạt sàng lọc", "passed"), review: t("cần xem lại", "need review"), high: t("rủi ro phá rừng", "deforestation risk"), unknown: t("chưa đủ dữ liệu", "insufficient data") }[k]}
                  {" · "}{cur.summary.ha_by_level[k] ?? 0} ha</span></div>
            ))}
          </div>
          <div className="bat-row">
            <button className="bat-btn" onClick={async () => {
              try { const r = await eudrSetDossiers(cur.id); setIssued(r.issued); setCur(await eudrGetSet(cur.id)); } catch (e) { setErr((e as Error).message); }
            }}>
              <FileSignature size={15} aria-hidden="true" className="ui-ic" /> {t("Phát hành hồ sơ ký số cho từng vườn", "Issue a signed dossier for every plot")}
            </button>
            {issued.length > 0 && <small>{t(`Đã phát hành ${issued.length} hồ sơ — mã từng vườn ở cột cuối bảng và trong báo cáo CSV. Tên chủ hộ được ẩn; đường link đầy đủ của từng vườn lưu trong tài khoản của bạn.`, `Issued ${issued.length} dossiers — each plot's ID is in the last column and in the CSV report. Producer names are hidden; each plot's full link is stored in your account.`)}</small>}
            {Object.values(cur.results).some((r) => r.dossier_id) && (
              <Link className="bat-btn ghost" href={`/lo?set=${cur.id}`}><Package size={15} aria-hidden="true" className="ui-ic" /> {t("Ghép lô hàng từ các vườn này", "Build a lot from these plots")}</Link>
            )}
          </div>
          <div className="bat-table-wrap">
            <table className="bat-table">
              <thead><tr>
                <th>{t("Thửa", "Plot")}</th><th>{t("Chuẩn EU", "EU format")}</th><th>{t("Sàng lọc", "Screening")}</th>
                <th>WorldCover</th><th>ALOS</th><th>IO 18–20</th><th>{t("Hồ sơ", "Dossier")}</th>
              </tr></thead>
              <tbody>
                {rows.map((p) => {
                  const r = cur.results[String(p.index)];
                  const m = Object.fromEntries((r?.forest_2020 ?? []).map((x) => [x.id, x.pct]));
                  const k = String(p.index);
                  return (
                    <Fragment key={k}>
                      <tr className={p.valid ? "" : "bat-failed"}>
                        <td><b>{p.ref}</b><small>{p.producer ?? ""}{p.area_ha != null ? ` · ${p.area_ha} ha` : ""}{p.kind === "point" ? ` · ${t("điểm", "point")}` : ""}</small></td>
                        <td>{p.valid ? t("Đúng", "Valid") : <span className="eu-err-txt">{p.issues.find((i) => i.level === "error")?.message}</span>}</td>
                        <td>{r ? <button className="doc-link-btn" onClick={() => setOpen(open === k ? null : k)}><LevelBadge level={r.level} label={r.label} /></button> : "—"}</td>
                        <td className="num">{m.wc2020 != null ? `${(m.wc2020 as number).toFixed(0)}%` : "—"}</td>
                        <td className="num">{m.alos2020 != null ? `${(m.alos2020 as number).toFixed(0)}%` : "—"}</td>
                        <td className="num">{m.io != null ? `${(m.io as number).toFixed(0)}%` : "—"}</td>
                        <td>{r?.dossier_id ? <Link href={`/h/${r.dossier_id}`}>{r.dossier_id}</Link> : "—"}</td>
                      </tr>
                      {open === k && r && (
                        <tr className="eu-detail"><td colSpan={7}><EudrResult s={r} geometry={p.geometry} areaHa={p.area_ha} /></td></tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {sets.length > 1 && (
        <section className="bat-card">
          <h2>{t("Các lô trước", "Previous sets")}</h2>
          <ul className="bat-runs">
            {sets.map((s) => (
              <li key={s.id}>
                <button className="doc-link-btn" onClick={() => eudrGetSet(s.id).then(setCur).catch((e) => setErr(e.message))}>{s.title || s.id.slice(0, 8)}</button>
                <small>{new Date(s.created_at).toLocaleString(lang === "en" ? "en-GB" : "vi-VN")} · {s.n_plots} {t("thửa", "plots")}{s.headline ? ` · ${s.headline}` : ""}</small>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}

function ValidationTable({ v }: { v: EudrValidation }) {
  const { t } = useLang();
  return (
    <>
      <p className={`bat-head ${v.summary.eu_ready ? "eu-ok-line" : ""}`}>{v.summary.headline}</p>
      {v.file_errors.length > 0 && <ul className="bat-rowerr">{v.file_errors.map((e, i) => <li key={i}>{e.message}</li>)}</ul>}
      <p className="eu-src">{v.summary.n} {t("thửa", "plots")} · {v.summary.n_polygons} {t("đa giác", "polygons")} · {v.summary.n_points} {t("điểm", "points")} ·{" "}
        {t("tổng diện tích thửa đúng chuẩn", "total area of valid plots")} {v.summary.total_ha} ha</p>
      <div className="bat-table-wrap">
        <table className="bat-table">
          <thead><tr><th>{t("Thửa", "Plot")}</th><th>{t("Loại", "Type")}</th><th>{t("Diện tích", "Area")}</th><th>{t("Vấn đề", "Issues")}</th></tr></thead>
          <tbody>
            {[...v.plots].sort((a, b) => Number(a.valid) - Number(b.valid)).slice(0, 300).map((p) => (
              <tr key={p.index} className={p.valid ? "" : "bat-failed"}>
                <td><b>{p.ref}</b><small>{p.src}</small></td>
                <td>{p.kind === "polygon" ? t("Đa giác", "Polygon") : p.kind === "point" ? t("Điểm", "Point") : "—"}</td>
                <td className="num">{p.area_ha != null ? `${p.area_ha} ha` : "—"}</td>
                <td><IssueList issues={p.issues} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

// ------------------------------------------------------------------ phương pháp

function Method({ lang }: { lang: string }) {
  const { t } = useLang();
  const [m, setM] = useState<EudrMethod | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { eudrMethod().then(setM).catch((e) => setErr(e.message)); }, [lang]);
  if (err) return <p className="bat-err">{err}</p>;
  if (!m) return <p className="doc-note">{t("Đang tải…", "Loading…")}</p>;
  const v = m.validation;
  const P = m.validation_protocol;
  const metricName: Record<string, string> = {
    M1_detect_lost: t("Bắt được thửa mất rừng 2021–2024", "Catches plots deforested 2021–2024"),
    M2_flag_forest: t("Không cho rừng lọt qua", "Does not let forest through"),
    M3_pass_clean: t("Cho qua đất chưa từng là rừng", "Passes land that was never forest"),
  };
  return (
    <>
      <section className="bat-card">
        <h2>{t("Kiểm định độc lập — ngưỡng đặt trước, công bố kể cả khi thấp", "Independent validation — pre-set bar, published even if low")}</h2>
        {P && <p className="eu-src">{t("Đối chiếu", "Reference")}: {P.reference} · {P.region.note} · {P.per_set} {t("thửa mỗi nhóm", "plots per group")} ·{" "}
          {t("giao thức đăng ký ngày", "protocol registered on")} {P.registered}</p>}
        {!v ? <p className="doc-note">{t("Chưa chạy xong — kết quả sẽ hiện ở đây.", "Not finished yet — results will appear here.")}</p> : (
          <>
            <p className={`bat-head ${v.passed ? "eu-ok-line" : "eu-err-txt"}`}>{v.passed
              ? t(`ĐẠT cả ba ngưỡng đặt trước (${v.n} thửa).`, `PASSED all three pre-set bars (${v.n} plots).`)
              : t(`KHÔNG ĐẠT ngưỡng đặt trước (${v.n} thửa) — công bố nguyên trạng, không chấm lại trên mẫu này.`,
                  `Did NOT pass the pre-set bar (${v.n} plots) — published as is, not re-scored on this sample.`)}</p>
            <div className="bat-table-wrap">
              <table className="bat-table">
                <thead><tr><th>{t("Chỉ số", "Metric")}</th><th>{t("Kết quả", "Result")}</th><th>{t("Ngưỡng", "Bar")}</th><th></th></tr></thead>
                <tbody>
                  {Object.entries(v.pass_thresholds).map(([k, th]) => {
                    const val = v.metrics[k];
                    return (
                      <tr key={k}>
                        <td>{metricName[k] ?? k}{P?.sets && <small>{Object.values(P.sets)[["M1_detect_lost", "M2_flag_forest", "M3_pass_clean"].indexOf(k)]?.criteria}</small>}</td>
                        <td className="num"><b>{val != null ? `${Math.round(val * 100)}%` : "—"}</b></td>
                        <td className="num">≥ {Math.round(th * 100)}%</td>
                        <td>{val != null && val >= th ? t("đạt", "pass") : t("không đạt", "fail")}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="eu-src">{t("Phân bố kết luận theo nhóm", "Verdicts by group")}: {Object.entries(v.counts).map(([g, c]) =>
              `${g}: ${c.low} ${t("đạt", "low")} / ${c.review} ${t("xem lại", "review")} / ${c.high} ${t("rủi ro", "high")} / ${c.unknown} ${t("thiếu", "unknown")}`).join(" · ")}</p>
          </>
        )}
      </section>
      <section className="bat-card">
        <h2>{t("Quy tắc sàng lọc", "Screening rule")} <code>{m.rule_version}</code></h2>
        <ul className="eu-reasons">
          <li>{t(`"Phiếu rừng": một bản đồ năm 2020 có ≥${m.thresholds.forest_vote_pct}% diện tích thửa là rừng (ngưỡng tán 10% của định nghĩa rừng EU/FAO); "phiếu mạnh": ≥${m.thresholds.forest_strong_pct}%.`,
                 `"Forest vote": a 2020 map shows ≥${m.thresholds.forest_vote_pct}% of the plot as forest (the EU/FAO 10% canopy threshold); "strong vote": ≥${m.thresholds.forest_strong_pct}%.`)}</li>
          <li>{t(`"Mất cây": tán cây Impact Observatory trung bình 2022–2023 thấp hơn 2018–2020 ≥${m.thresholds.loss_pts} điểm %, hoặc NDVI cùng mùa giảm ≥${m.thresholds.ndvi_drop} từ mức rừng ≥${m.thresholds.ndvi_forest}.`,
                 `"Tree loss": Impact Observatory tree cover averaged 2022–2023 is ≥${m.thresholds.loss_pts} pts below 2018–2020, or same-season NDVI fell ≥${m.thresholds.ndvi_drop} from a forest level ≥${m.thresholds.ndvi_forest}.`)}</li>
          <li><b>{m.levels.high}</b>: {t("≥2 phiếu mạnh và mất cây.", "≥2 strong votes and tree loss.")}</li>
          <li><b>{m.levels.review}</b>: {t("≥2 phiếu rừng; hoặc 1 phiếu kèm mất cây; hoặc chỉ 2 bản đồ và chúng bất đồng; hoặc tâm thửa trong khu bảo tồn.",
                                           "≥2 forest votes; or 1 vote plus tree loss; or only 2 maps that disagree; or the plot centre is in a protected area.")}</li>
          <li><b>{m.levels.low}</b>: {t("0 phiếu, hoặc 1/3 phiếu (thường là cây lâu năm che bóng) và không mất cây.",
                                        "0 votes, or 1/3 votes (usually shaded tree crops) and no tree loss.")}</li>
          <li><b>{m.levels.unknown}</b>: {t("lấy được dưới 2/3 bản đồ.", "fewer than 2 of 3 maps available.")}</li>
        </ul>
        <p className="eu-src">{t("Vì sao bỏ phiếu: đo thật ở vườn cà phê Buôn Ma Thuột và vườn cây ăn trái Cần Thơ, WorldCover vẽ 76–78% \"tán cây\" trong khi radar ALOS và Impact Observatory đều 0% rừng — mà EUDR không coi đất nông nghiệp có cây là rừng.",
          "Why voting: measured at a Buôn Ma Thuột coffee farm and a Cần Thơ orchard, WorldCover maps 76–78% \"tree cover\" while ALOS radar and Impact Observatory both show 0% forest — and the EUDR does not count agricultural land with trees as forest.")}</p>
      </section>
      <section className="bat-card">
        <h2>{t("Chuẩn tệp EU được kiểm", "EU file rules checked")}</h2>
        <ul className="eu-reasons">
          <li>{t(`Toạ độ ít nhất ${m.eu_rules.min_decimals} chữ số thập phân — Quy định (EU) 2023/1115 Điều 2(28).`, `Coordinates with at least ${m.eu_rules.min_decimals} decimals — Regulation (EU) 2023/1115 Art. 2(28).`)}</li>
          <li>{t(`Thửa trên ${m.eu_rules.point_max_ha} ha phải khai bằng đa giác — Điều 9(1)(d). Điểm không khai diện tích: EU mặc định ${m.eu_rules.default_point_ha} ha.`,
                 `Plots over ${m.eu_rules.point_max_ha} ha must be polygons — Art. 9(1)(d). Points without an area: the EU assumes ${m.eu_rules.default_point_ha} ha.`)}</li>
          <li>{t(`Theo mô tả tệp GeoJSON của TRACES: chỉ Point/MultiPoint/Polygon/MultiPolygon WGS84; ranh khép kín; không lỗ thủng, không tự cắt; tệp tối đa ${m.eu_rules.max_file_mb} MB.`,
                 `Per the TRACES GeoJSON description: only Point/MultiPoint/Polygon/MultiPolygon in WGS84; closed rings; no holes, no self-intersections; files up to ${m.eu_rules.max_file_mb} MB.`)}</li>
          <li>{t("Thêm: hai hộ khai chồng lên nhau, khai trùng một thửa hai lần, GPS nhảy điểm, diện tích khai lệch ranh đo.", "Plus: two producers declaring overlapping land, the same plot twice, GPS jumps, declared area vs measured boundary.")}</li>
        </ul>
      </section>
      <section className="bat-card">
        <h2>{t("Nguồn dữ liệu (đều công khai, ai cũng tính lại được)", "Data sources (all public, anyone can recompute)")}</h2>
        <ul className="eu-reasons">{m.sources.map((s) => <li key={s}>{s}</li>)}</ul>
        <p className="eu-src">{t("Giới hạn: đây là sàng lọc, không phải chứng nhận tuân thủ EUDR; TerraTwin không xác nhận quyền sử dụng đất hay tính hợp pháp của sản xuất. Kết luận cuối cùng thuộc về người nộp tờ khai thẩm định (DDS).",
          "Limits: this is screening, not EUDR compliance certification; TerraTwin does not confirm land rights or production legality. The final call rests with whoever files the due diligence statement (DDS).")}</p>
      </section>
    </>
  );
}


function CopyLine({ label, value }: { label: string; value: string }) {
  const { t } = useLang();
  const [done, setDone] = useState(false);
  return (
    <div className="eu-copy">
      <small>{label}</small>
      <div className="bat-row">
        <code>{value}</code>
        <button className="bat-btn ghost" onClick={() => navigator.clipboard?.writeText(value).then(() => setDone(true)).catch(() => setDone(false))}>
          <Copy size={14} aria-hidden="true" className="ui-ic" /> {done ? t("Đã chép", "Copied") : t("Chép", "Copy")}
        </button>
      </div>
    </div>
  );
}

function IssuedCard({ d }: { d: Dossier }) {
  const { t } = useLang();
  return (
    <div className="eu-issued">
      {d.qr && <img src={d.qr} alt={t("Mã QR hồ sơ", "Dossier QR code")} width={120} height={120} />}
      <div>
        <b>{t(`Đã phát hành hồ sơ số ${String(d.seq).padStart(6, "0")} · mã ${d.id}`, `Issued dossier no. ${String(d.seq).padStart(6, "0")} · ID ${d.id}`)}</b>
        <CopyLine label={t("Link công khai (in QR, gửi người mua)", "Public link (print the QR, send to buyers)")} value={d.url} />
        {d.disclosure && (
          <CopyLine label={t("Link ĐẦY ĐỦ có tên chủ hộ — nông hộ tự giữ, chỉ đưa khi cần chứng minh" + (d.disclosure.stored ? "" : " (KHÔNG lưu trên máy chủ vì chưa đăng nhập — chép lại ngay)"),
                             "FULL link with the producer name — the farmer keeps it and shares only when needed" + (d.disclosure.stored ? "" : " (NOT stored on the server because you're not signed in — copy it now)"))}
                    value={d.disclosure.url} />
        )}
        <a className="bat-btn" href={`/h/${d.id}`}>{t("Mở hồ sơ", "Open the dossier")}</a>
      </div>
    </div>
  );
}

const SAMPLE_Q = ["Vườn 3 ha có phải vẽ ranh không?", "Cà phê trồng xen cây rừng có bị coi là rừng không?",
                  "Vi phạm EUDR bị phạt bao nhiêu?", "Đất rừng phòng hộ trồng cà phê được không?"];

function Ask() {
  const { t } = useLang();
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [r, setR] = useState<{ mode: string; answer: string; citations: AskCitation[] } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  async function go(question: string) {
    setQ(question); setBusy(true); setErr(null);
    try { setR(await eudrAsk(question)); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }
  return (
    <section className="bat-card">
      <h2><MessageCircleQuestion size={18} aria-hidden="true" className="ui-ic" /> {t("Hỏi về EUDR — trả lời kèm điều khoản", "Ask about the EUDR — answers cite the article")}</h2>
      <p className="eu-src">{t("Tìm trong kho đoạn trích quy định có nguồn (tìm kiếm BM25 tiếng Việt). Có khoá AI thì diễn giải, nhưng chỉ dựa trên đoạn tìm được; không tìm thấy thì nói thẳng. Không thay cho tư vấn pháp lý.",
        "Searches a sourced library of regulation passages (Vietnamese BM25 search). With an AI key it paraphrases, but only from the passages found; if nothing matches it says so. Not legal advice.")}</p>
      <form className="bat-row" onSubmit={(e) => { e.preventDefault(); if (q.trim().length > 1) go(q.trim()); }}>
        <input id="eudr-ask" className="bat-input" value={q} maxLength={500} onChange={(e) => setQ(e.target.value)} placeholder={t("vd: thửa dưới 4 ha khai một điểm được không?", "e.g. can a plot under 4 ha be a single point?")} />
        <button className="bat-btn" disabled={busy || q.trim().length < 2}>{busy ? t("Đang tìm…", "Searching…") : t("Hỏi", "Ask")}</button>
      </form>
      <div className="bat-row">{SAMPLE_Q.map((s) => <button key={s} className="eu-chip" onClick={() => go(s)}>{s}</button>)}</div>
      {err && <p className="bat-err">{err}</p>}
      {r && (
        <div className="eu-answer">
          <p>{r.answer}</p>
          <small>{r.mode === "llm" ? t("Diễn giải bằng AI, chỉ từ các đoạn dưới đây.", "Paraphrased by AI, only from the passages below.")
            : r.mode === "extractive" ? t("Trích nguyên văn đoạn liên quan nhất (chưa cấu hình AI diễn giải).", "Quoting the most relevant passage (AI paraphrase not configured).")
              : t("Không có đoạn nào đủ khớp.", "No passage matched well enough.")}</small>
          {r.citations.length > 0 && (
            <ol className="eu-cites">
              {r.citations.map((c) => (
                <li key={c.id}><b>{c.title}</b> — <a href={c.url} target="_blank" rel="noreferrer">{c.source}</a>
                  <span>{c.text}</span></li>
              ))}
            </ol>
          )}
        </div>
      )}
    </section>
  );
}
