"use client";

/**
 * THANH LỆNH Ctrl+K (GĐ1 kế hoạch tổng) — một chỗ để đi tới mọi nơi: gõ tên trang (có dấu hay
 * không dấu đều được) hoặc DÁN TOẠ ĐỘ để mở thẳng thửa đó. Dùng trọn bằng bàn phím:
 * ↑/↓ chọn, Enter mở, Esc đóng; đóng thì trả tiêu điểm về chỗ cũ.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Search } from "lucide-react";
import { inVietnam, parseCoord } from "@/lib/geo";
import { useLang } from "@/lib/i18n";

type Item = { href: string; vi: string; en: string; hint?: string };

const ITEMS: Item[] = [
  { href: "/hom-nay", vi: "Hôm nay", en: "Today" },
  { href: "/", vi: "Thửa đất — bản đồ", en: "Land — map" },
  { href: "/eudr", vi: "EUDR — hồ sơ một vườn", en: "EUDR — one plot dossier" },
  { href: "/eudr?tab=lo", vi: "EUDR — kiểm cả lô (doanh nghiệp, HTX)", en: "EUDR — whole set (exporters, co-ops)" },
  { href: "/eudr?tab=hoi-dap", vi: "Hỏi đáp EUDR", en: "EUDR Q&A" },
  { href: "/eudr?tab=phuong-phap", vi: "Phương pháp & kiểm định", en: "Method & validation" },
  { href: "/lo", vi: "Lô hàng — cân bằng khối lượng", en: "Lots — mass balance" },
  { href: "/kiem", vi: "Kiểm hồ sơ (cả khi không có mạng)", en: "Verify a dossier (works offline)" },
  { href: "/so-sanh", vi: "So sánh 2–4 thửa đất", en: "Compare 2–4 plots" },
  { href: "/mo-hinh", vi: "Thẻ mô hình AI (kể cả cái trượt)", en: "AI model cards (incl. failures)" },
  { href: "/thi-diem", vi: "Bộ thí điểm cho hợp tác xã", en: "Pilot kit for co-operatives" },
  { href: "/gan-nhan", vi: "Gán nhãn kiểm định v3", en: "Label validation v3" },
  { href: "/thiet-bi", vi: "Thiết bị IoT tại vườn", en: "IoT devices" },
  { href: "/batch", vi: "Thẩm định hàng loạt", en: "Batch appraisal" },
  { href: "/pricing", vi: "Bảng giá", en: "Pricing" },
  { href: "/help", vi: "Trợ giúp", en: "Help" },
  { href: "/privacy", vi: "Quyền riêng tư", en: "Privacy" },
  { href: "/status", vi: "Trạng thái hệ thống", en: "System status" },
  { href: "/admin", vi: "Quản trị", en: "Admin" },
];

const fold = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d").replace(/Đ/g, "D").toLowerCase();

export function openCommandPalette() {
  window.dispatchEvent(new Event("tt-open-palette"));
}

export default function CommandPalette() {
  const { t } = useLang();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const back = useRef<Element | null>(null);

  const show = useCallback(() => {
    back.current = document.activeElement;
    setQ(""); setSel(0); setOpen(true);
  }, []);
  const hide = useCallback(() => {
    setOpen(false);
    (back.current as HTMLElement | null)?.focus?.();
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); show(); }
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("tt-open-palette", show);
    return () => { window.removeEventListener("keydown", onKey); window.removeEventListener("tt-open-palette", show); };
  }, [show]);
  useEffect(() => { if (open) setTimeout(() => input.current?.focus(), 0); }, [open]);

  const results = useMemo(() => {
    const out: { href: string; label: string }[] = [];
    const c = q.trim() ? parseCoord(q) : null;
    if (c && inVietnam(c.lat, c.lon)) {
      out.push({ href: `/plot/${c.lat.toFixed(5)},${c.lon.toFixed(5)}`,
                 label: t(`Mở thửa tại ${c.lat.toFixed(5)}, ${c.lon.toFixed(5)}`, `Open the plot at ${c.lat.toFixed(5)}, ${c.lon.toFixed(5)}`) });
    }
    const f = fold(q.trim());
    for (const it of ITEMS) {
      const label = t(it.vi, it.en);
      if (!f || fold(label).includes(f) || fold(it.vi).includes(f) || fold(it.en).includes(f)) out.push({ href: it.href, label });
    }
    return out;
  }, [q, t]);

  const go = (i: number) => {
    const r = results[i];
    if (!r) return;
    setOpen(false);
    router.push(r.href);
  };

  if (!open) return null;
  return (
    <div className="cp-back" onMouseDown={(e) => { if (e.target === e.currentTarget) hide(); }}>
      <div className="cp" role="dialog" aria-modal="true" aria-label={t("Thanh lệnh", "Command palette")}>
        <div className="cp-in">
          <Search size={18} aria-hidden="true" />
          <input ref={input} value={q} placeholder={t("Gõ tên trang hoặc dán toạ độ (vd 12.68, 108.05)…", "Type a page name or paste coordinates (e.g. 12.68, 108.05)…")}
                 aria-label={t("Tìm trang hoặc toạ độ", "Search pages or coordinates")} role="combobox" aria-expanded="true"
                 aria-controls="cp-list" aria-activedescendant={results[sel] ? `cp-${sel}` : undefined}
                 onChange={(e) => { setQ(e.target.value); setSel(0); }}
                 onKeyDown={(e) => {
                   if (e.key === "Escape") { e.preventDefault(); hide(); }
                   else if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(s + 1, results.length - 1)); }
                   else if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
                   else if (e.key === "Enter") { e.preventDefault(); go(sel); }
                 }} />
          <kbd>Esc</kbd>
        </div>
        <ul id="cp-list" role="listbox" className="cp-list">
          {results.length === 0 && <li className="cp-empty">{t("Không có kết quả", "No results")}</li>}
          {results.map((r, i) => (
            <li key={r.href} id={`cp-${i}`} role="option" aria-selected={i === sel} className={i === sel ? "on" : ""}
                onMouseEnter={() => setSel(i)} onMouseDown={(e) => { e.preventDefault(); go(i); }}>
              {r.label}<span>{r.href}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
