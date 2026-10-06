"use client";

/**
 * GÁN NHÃN kiểm định EUDR v3 — người nhìn ảnh năm 2020 làm thước đo (xem
 * backend/app/services/label_v3.py vì sao). Trang này CỐ Ý không hiện bất cứ kết quả
 * nào của máy: người gán phải mù với bản đồ, mô hình và nhãn của người kia.
 */

import AppShell from "@/components/AppShell";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  getToken, labelCell, labelMe, labelNext, labelSave,
  type LabelBox, type LabelCover, type LabelIn, type LabelNext, type LabelView,
} from "@/lib/api";
import { useLang } from "@/lib/i18n";

const COVERS: [LabelCover, string, string, string][] = [
  ["natural_forest", "1", "Rừng tự nhiên", "Natural forest"],
  ["planted_forest", "2", "Rừng trồng lấy gỗ (keo, bạch đàn, thông)", "Timber plantation (acacia, eucalyptus, pine)"],
  ["tree_crop", "3", "Cây trồng lâu năm (cà phê, cao su, điều, tiêu, cây ăn quả)", "Tree crop (coffee, rubber, cashew, pepper, orchard)"],
  ["no_trees", "4", "Không có tán cây (lúa, hoa màu, cỏ, đất trống, nhà, nước)", "No tree cover (rice, annual crops, grass, bare, buildings, water)"],
  ["unclear", "5", "Không xác định được", "Cannot tell"],
];
const LOSSES: [LabelIn["loss"], string, string, string][] = [
  ["no", "q", "Không mất", "No loss"], ["yes", "w", "Có mất tán cây", "Tree cover lost"], ["unclear", "e", "Không rõ", "Unclear"],
];

function Frame({ box }: { box: LabelBox }) {
  return <span className="gn-frame" style={{ left: `${box.left}%`, top: `${box.top}%`, width: `${box.width}%`, height: `${box.height}%` }} />;
}

function Mosaic({ tiles, box, alt }: { tiles: string[][]; box: LabelBox; alt: string }) {
  return (
    <div className="gn-img gn-mosaic" role="img" aria-label={alt}>
      {tiles.flat().map((u) => <img key={u} src={u} alt="" loading="eager" draggable={false} />)}
      <Frame box={box} />
    </div>
  );
}

function Panel({ title, sub, children }: { title: string; sub: string; children: React.ReactNode }) {
  return (
    <figure className="gn-panel">
      {children}
      <figcaption><b>{title}</b><span>{sub}</span></figcaption>
    </figure>
  );
}

function Views({ v }: { v: LabelView }) {
  const { t } = useLang();
  const wb = v.wayback;
  const shot = (w: typeof wb.before) => w.acquired
    ? t(`chụp ${w.acquired}${w.resolution_m ? ` · ${w.resolution_m} m` : ""}${w.source ? ` · ${w.source}` : ""}`,
        `taken ${w.acquired}${w.resolution_m ? ` · ${w.resolution_m} m` : ""}${w.source ? ` · ${w.source}` : ""}`)
    : t("chưa rõ ngày chụp", "capture date unknown");
  const old = wb.before.acquired && wb.before.acquired < "2018-01-01";
  const staleAfter = wb.after.acquired && wb.after.acquired <= "2020-12-31";
  return (
    <>
      {staleAfter && <p className="doc-note">{t(
        `Ảnh chi tiết "gần đây" thực ra chụp ${wb.after.acquired} — TRƯỚC mốc, nên không dùng để xét mất cây. Hãy so hai ảnh Sentinel-2 (2020 và 2026).`,
        `The "recent" detailed image was actually taken ${wb.after.acquired} — BEFORE the cutoff, so don't use it for loss. Compare the two Sentinel-2 images (2020 vs 2026).`)}</p>}
      {old && <p className="doc-note">{t(
        `Ảnh chi tiết "trước mốc" chụp từ ${wb.before.acquired} — có thể đã cũ so với 31/12/2020. Đối chiếu ảnh Sentinel-2 năm 2020; vẫn không chắc thì chọn "Không xác định được".`,
        `The detailed "before" image was taken ${wb.before.acquired} — possibly outdated for 31/12/2020. Check the 2020 Sentinel-2 image; if still unsure pick "Cannot tell".`)}</p>}
      <div className="gn-grid">
        <Panel title={t("Trước mốc — ảnh chi tiết", "Before cutoff — detailed")} sub={shot(wb.before)}>
          <Mosaic tiles={wb.before.tiles} box={v.mosaic_box} alt={t("Ảnh vệ tinh chi tiết trước mốc 2020", "Detailed imagery before 2020 cutoff")} />
        </Panel>
        <Panel title={t("Gần đây — ảnh chi tiết", "Recent — detailed")} sub={shot(wb.after)}>
          <Mosaic tiles={wb.after.tiles} box={v.mosaic_box} alt={t("Ảnh vệ tinh chi tiết gần đây", "Recent detailed imagery")} />
        </Panel>
        {(["2020", "2026"] as const).map((y) => {
          const s = v.s2[y];
          return (
            <Panel key={y} title={`Sentinel-2 · ${t("mùa khô", "dry season")} ${y}`}
                   sub={s ? t(`chụp ${s.date} · 10 m · mây ${s.cloud_pct}%`, `taken ${s.date} · 10 m · cloud ${s.cloud_pct}%`) : t("không có ảnh ít mây", "no cloud-free image")}>
              {s ? <div className="gn-img"><img src={s.url} alt={`Sentinel-2 ${y}`} draggable={false} /><Frame box={s.box} /></div>
                 : <div className="gn-img gn-empty">—</div>}
            </Panel>
          );
        })}
      </div>
    </>
  );
}

export default function LabelPage() {
  const { t } = useLang();
  const [me, setMe] = useState<{ can_label: boolean; n_cells: number; done: number; sample_ready: boolean } | null>(null);
  const [signedIn, setSignedIn] = useState<boolean | null>(null);
  const [cur, setCur] = useState<LabelNext | null>(null);
  const [cover, setCover] = useState<LabelCover | null>(null);
  const [loss, setLoss] = useState<LabelIn["loss"] | null>(null);
  const [conf, setConf] = useState(2);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [history, setHistory] = useState<number[]>([]);
  const started = useRef<number>(Date.now());

  const show = useCallback((r: LabelNext) => {
    setCur(r);
    setCover(r.mine?.cover2020 ?? null);
    setLoss(r.mine?.loss ?? null);
    setConf(r.mine?.confidence ?? 2);
    setNote(r.mine?.note ?? "");
    started.current = Date.now();
    window.scrollTo({ top: 0 });
  }, []);

  useEffect(() => {
    const ok = !!getToken();
    setSignedIn(ok);
    if (!ok) return;
    labelMe().then((m) => {
      setMe(m);
      if (m.can_label && m.sample_ready) labelNext().then(show).catch((e) => setErr(e.message));
    }).catch((e) => setErr(e.message));
  }, [show]);

  const need = cover && (cover === "unclear" || cover === "no_trees" || cover === "tree_crop" || loss);
  const save = useCallback(async () => {
    const v = cur?.view;
    if (!v || !cover || busy) return;
    const lossVal = loss ?? (cover === "unclear" ? "unclear" : "no");
    if ((cover === "natural_forest" || cover === "planted_forest") && !loss) return;
    setBusy(true); setErr(null);
    try {
      const r = await labelSave(v.cell, { cover2020: cover, loss: lossVal, confidence: conf, note,
                                          seconds: Math.round((Date.now() - started.current) / 1000) });
      setMe((m) => m && { ...m, done: r.labeled });
      setHistory((h) => [...h, v.cell]);
      show(await labelNext(v.cell));
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, [cur, cover, loss, conf, note, busy, show]);

  const skip = async () => { if (cur?.view) show(await labelNext(cur.view.cell)); };
  const back = async () => {
    const k = history[history.length - 1];
    if (k == null) return;
    setHistory((h) => h.slice(0, -1));
    show(await labelCell(k));
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === "INPUT" || (e.target as HTMLElement)?.tagName === "TEXTAREA") return;
      const c = COVERS.find((x) => x[1] === e.key);
      if (c) { setCover(c[0]); return; }
      const l = LOSSES.find((x) => x[1] === e.key.toLowerCase());
      if (l) { setLoss(l[0]); return; }
      if (e.key === "Enter") { e.preventDefault(); save(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [save]);

  const v = cur?.view;
  const forestPicked = cover === "natural_forest" || cover === "planted_forest";

  return (
    <AppShell>
      <main className="gn-wrap">
        <header className="gn-head">
          <div>
            <p className="eu-eyebrow">{t("Kiểm định EUDR v3 · giải đoán ảnh năm 2020", "EUDR validation v3 · 2020 image interpretation")}</p>
            <h1>{t("Gán nhãn: ngày 31/12/2020, ô này là gì?", "Label: what was this plot on 31/12/2020?")}</h1>
          </div>
          {me?.can_label && <div className="gn-progress" aria-label={t("Tiến độ", "Progress")}>
            <b>{me.done}</b>/{me.n_cells}
            <span className="gn-bar"><i style={{ width: `${me.n_cells ? (me.done / me.n_cells) * 100 : 0}%` }} /></span>
          </div>}
        </header>

        {signedIn === false && <p className="doc-note">{t("Cần đăng nhập. ", "Sign in first. ")}<Link href="/">{t("Về trang chính để đăng nhập", "Go home to sign in")}</Link></p>}
        {me && !me.can_label && <p className="doc-note">{t(
          "Tài khoản này chưa được cấp quyền gán nhãn. Gán nhãn tạo ra THƯỚC ĐO cho cả hệ thống nên chỉ người được quản trị viên thêm email mới làm được.",
          "This account may not label yet. Labels become the yardstick for the whole system, so only people an administrator has added can label.")}</p>}
        {me?.can_label && !me.sample_ready && <p className="doc-note">{t("Mẫu v3 đang được tạo — quay lại sau.", "The v3 sample is being generated — come back later.")}</p>}
        {err && <p className="bat-err" role="alert">{err}</p>}

        <details className="gn-guide" open={!!me?.can_label && me.done === 0}>
          <summary>{t("Hướng dẫn (đọc trước khi gán ô đầu tiên)", "Guide (read before the first plot)")}</summary>
          <ul>
            <li>{t("Chỉ nhìn phần TRONG KHUNG ĐỎ (~1,2 ha). Trả lời theo đa số diện tích trong khung.",
                   "Look only INSIDE THE RED FRAME (~1.2 ha). Answer for the majority of its area.")}</li>
            <li>{t("Theo EUDR: rừng tự nhiên và rừng trồng lấy gỗ (keo, bạch đàn) LÀ rừng. Cao su, cà phê, điều, tiêu, cây ăn quả, nông lâm kết hợp KHÔNG phải rừng.",
                   "Under the EUDR: natural forest and timber plantations (acacia, eucalyptus) ARE forest. Rubber, coffee, cashew, pepper, orchards and agroforestry are NOT.")}</li>
            <li>{t("Dấu hiệu vườn cây: hàng lối đều, khoảng cách cây đều, đường lô, nhà kho/sân phơi gần đó. Cao su: hàng thẳng dài, tán đồng đều, rụng lá mùa khô. Rừng tự nhiên: tán lổn nhổn nhiều kích cỡ, không hàng lối.",
                   "Tree-crop signs: regular rows and spacing, plantation tracks, nearby drying yards. Rubber: long straight rows, even canopy, leaf drop in the dry season. Natural forest: uneven mixed canopy, no rows.")}</li>
            <li>{t("Ảnh chi tiết \"trước mốc\" là bản lưu cuối 2020 nhưng NGÀY CHỤP có thể sớm hơn — xem dòng \"chụp …\". Ảnh Sentinel-2 năm 2020 thô (10 m) nhưng đúng năm.",
                   "The \"before\" detailed image is the late-2020 archive but its CAPTURE date may be earlier — see \"taken …\". The 2020 Sentinel-2 image is coarse (10 m) but from the right year.")}</li>
            <li>{t("\"Mất tán cây\": từ khoảng 1/4 khung trở lên bị chặt, đốt, chuyển sang trồng khác sau 31/12/2020. Thay cây cao su già trồng lại cũng ghi là có mất.",
                   "\"Tree cover lost\": roughly 1/4 of the frame or more cleared, burned or converted after 31/12/2020. Replanting old rubber also counts as loss.")}</li>
            <li>{t("Không chắc thì chọn \"Không xác định được\" — một nhãn sai làm hỏng thước đo hơn một ô bị bỏ. Không tra bản đồ rừng, không bàn với người gán kia.",
                   "If unsure choose \"Cannot tell\" — a wrong label harms the yardstick more than a skipped plot. Don't consult forest maps, don't discuss with the other labeler.")}</li>
            <li>{t("Phím tắt: 1–5 chọn loại, Q/W/E chọn mất cây, Enter lưu và sang ô tiếp.", "Shortcuts: 1–5 cover, Q/W/E loss, Enter save and next.")}</li>
          </ul>
        </details>

        {cur?.done && <p className="eu-ok-line">{t(`Xong cả ${cur.n_cells} ô — cảm ơn bạn!`, `All ${cur.n_cells} plots done — thank you!`)}</p>}

        {v && (
          <>
            <p className="gn-meta">{t("Ô", "Plot")} #{cur?.position} · {v.center.lat.toFixed(5)}, {v.center.lon.toFixed(5)} · ~{v.area_ha} ha</p>
            <Views v={v} />
            <section className="gn-form" aria-label={t("Nhãn", "Label")}>
              <fieldset>
                <legend>{t("Ngày 31/12/2020, phần lớn khung đỏ là", "On 31/12/2020, most of the red frame was")}</legend>
                {COVERS.map(([k, key, vi, en]) => (
                  <button key={k} type="button" className={`gn-opt ${cover === k ? "on" : ""}`} aria-pressed={cover === k}
                          onClick={() => setCover(k)}><kbd>{key}</kbd>{t(vi, en)}</button>
                ))}
              </fieldset>
              <fieldset disabled={!cover || cover === "unclear"}>
                <legend>{t("Sau 31/12/2020, khung đỏ có mất tán cây không?", "After 31/12/2020, did the frame lose tree cover?")}
                  {forestPicked && <small> {t("(bắt buộc với ô rừng)", "(required for forest)")}</small>}</legend>
                {LOSSES.map(([k, key, vi, en]) => (
                  <button key={k} type="button" className={`gn-opt ${loss === k ? "on" : ""}`} aria-pressed={loss === k}
                          onClick={() => setLoss(k)}><kbd>{key.toUpperCase()}</kbd>{t(vi, en)}</button>
                ))}
              </fieldset>
              <fieldset>
                <legend>{t("Độ chắc chắn", "Confidence")}</legend>
                {[[1, t("Đoán", "Guess")], [2, t("Khá chắc", "Fairly sure")], [3, t("Chắc", "Sure")]].map(([n, l]) => (
                  <button key={n as number} type="button" className={`gn-opt ${conf === n ? "on" : ""}`} aria-pressed={conf === n}
                          onClick={() => setConf(n as number)}>{l}</button>
                ))}
              </fieldset>
              <label className="pk-field">{t("Ghi chú (không bắt buộc)", "Note (optional)")}
                <input type="text" maxLength={300} value={note} onChange={(e) => setNote(e.target.value)} />
              </label>
              <div className="gn-actions">
                <button className="doc-btn" type="button" disabled={!need || busy} onClick={save}>
                  {busy ? t("Đang lưu…", "Saving…") : t("Lưu & ô tiếp (Enter)", "Save & next (Enter)")}</button>
                <button className="doc-btn pk-btn2" type="button" onClick={skip} disabled={busy}>{t("Bỏ qua ô này", "Skip")}</button>
                <button className="doc-btn pk-btn2" type="button" onClick={back} disabled={busy || history.length === 0}>{t("← Ô vừa gán", "← Previous")}</button>
              </div>
            </section>
          </>
        )}
        <p className="eu-src">{t(
          "Ảnh chi tiết: Esri World Imagery Wayback (bản 16/12/2020 và 05/08/2026). Ảnh 10 m: Sentinel-2 L2A qua Microsoft Planetary Computer. Giao thức kiểm định ghi trước khi gán nhãn: ",
          "Detailed imagery: Esri World Imagery Wayback (16/12/2020 and 05/08/2026 releases). 10 m imagery: Sentinel-2 L2A via Microsoft Planetary Computer. Validation protocol registered before labeling: ")}
          <code>backend/data/eudr_validation_protocol_v3.json</code></p>
      </main>
    </AppShell>
  );
}
