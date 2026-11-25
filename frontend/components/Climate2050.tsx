"use client";

/**
 * KHÍ HẬU 2050 CỦA VÙNG QUANH THỬA (nâng cấp 24/11/2026) — services/climate_2050.py.
 * 5 chỉ số 2041–2050 so với 1995–2014, mỗi mô hình so với CHÍNH NÓ (delta), trung vị + dải giữa 3 mô hình CMIP6
 * HighResMIP; mô hình không cùng chiều thì nói "chưa chắc chiều". Thửa ven biển và thấp: nước biển dâng IPCC AR6.
 * Tự chạy khi mở thửa; vùng mới lần đầu ~15–30 s, mỗi vùng chỉ tính một lần.
 */
import { useEffect, useRef, useState } from "react";
import { ThermometerSun } from "lucide-react";
import { climate2050, type Climate2050 as C } from "@/lib/api";
import { useLang } from "@/lib/i18n";

export default function Climate2050({ lat, lon }: { lat: number; lon: number }) {
  const { t, lang } = useLang();
  const [r, setR] = useState<C | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [gone, setGone] = useState(false);     // máy chủ chưa có endpoint này (bản cũ) → ẩn thẻ, không hiện lỗi đỏ
  const gen = useRef(0);

  async function run() {
    const my = ++gen.current;
    setBusy(true); setErr(null);
    try {
      const x = await climate2050(lat, lon);
      if (my === gen.current) setR(x);
    } catch (e) {
      if (my === gen.current) {
        if ((e as { status?: number }).status === 404) setGone(true);
        else setErr((e as Error).message);
      }
    } finally {
      if (my === gen.current) setBusy(false);
    }
  }

  useEffect(() => {
    setR(null); setErr(null);
    run();
    return () => { gen.current++; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lat, lon, lang]);

  const ok = r?.available && r.indicators?.length;
  if (gone) return null;
  return (
    <section className="lc2 cl50">
      <div className="wh-head">
        <ThermometerSun size={18} aria-hidden="true" />
        <h3>{t("Khí hậu 2050 của vùng quanh thửa", "2050 climate of the area around the plot")}</h3>
        <span className="wh-badge lc2-badge">{t("mô phỏng CMIP6", "CMIP6 simulation")}</span>
      </div>
      {!r && busy && (
        <div className="wh-start" aria-live="polite">
          <p>{t("Đang tính khí hậu 2041–2050 so với 1995–2014 từ 3 mô hình khí hậu độ phân giải cao (CMIP6 HighResMIP). Vùng mới lần đầu ~15–30 giây; mỗi vùng chỉ tính một lần.",
                "Computing 2041–2050 climate vs 1995–2014 from 3 high-resolution climate models (CMIP6 HighResMIP). A new region takes ~15–30 s the first time; each region is computed once.")}</p>
        </div>
      )}
      {(err || (r && !r.available)) && (
        <div className="wh-start">
          <p className="bat-err">{err ?? r?.message}</p>
          <button type="button" className="bat-btn ghost" onClick={run} disabled={busy}>{t("Thử lại", "Try again")}</button>
        </div>
      )}
      {ok && (
        <>
          <p className="cl50-sub">
            {t(`${r.future?.[0]?.slice(0, 4)}–${r.future?.[1]?.slice(0, 4)} so với ${r.base?.[0]?.slice(0, 4)}–${r.base?.[1]?.slice(0, 4)}`,
               `${r.future?.[0]?.slice(0, 4)}–${r.future?.[1]?.slice(0, 4)} vs ${r.base?.[0]?.slice(0, 4)}–${r.base?.[1]?.slice(0, 4)}`)}
            {" · "}{r.scenario}{" · "}{(r.model_names ?? []).join(", ")}
          </p>
          <div className="bat-table-wrap">
            <table className="bat-table cl50-t">
              <thead><tr>
                <th>{t("Chỉ số", "Indicator")}</th><th>{t("1995–2014", "1995–2014")}</th><th>{t("2041–2050", "2041–2050")}</th>
                <th>{t("Thay đổi (dải 3 mô hình)", "Change (3-model range)")}</th>
              </tr></thead>
              <tbody>
                {r.indicators!.map((i) => (
                  <tr key={i.id} className={i.agree ? "" : "cl50-unsure"}>
                    <td>{i.name}</td>
                    <td className="num">{i.base_txt}</td>
                    <td className="num"><b>{i.future_txt}</b></td>
                    <td>{i.change}<small>{i.trend}</small></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {r.sea_level && <p className="cl50-sea">🌊 {r.sea_level.text}</p>}
          <details className="cl50-why">
            <summary>{t("Đọc số này thế nào — và giới hạn", "How to read this — and its limits")}</summary>
            <ul>{(r.caveats ?? []).map((c) => <li key={c}>{c}</li>)}</ul>
            <p className="eu-src">{t("Nguồn: ", "Sources: ")}{(r.sources ?? []).join(" · ")}</p>
          </details>
        </>
      )}
    </section>
  );
}
