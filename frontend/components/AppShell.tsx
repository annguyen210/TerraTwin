"use client";

/**
 * KHUNG ỨNG DỤNG — một thanh điều hướng cho MỌI trang (thay cho mỗi trang một kiểu đầu
 * trang), và trên điện thoại một THANH TAB DƯỚI ĐÁY như ứng dụng dùng hằng ngày:
 * Hôm nay · Thửa đất · So sánh · Kiểm · Doanh nghiệp. Trang nào đang mở thì sáng lên.
 *
 * Trục chính là HỒ SƠ ĐẤT (báo cáo kiểm toàn bộ 12/10/2026, mục 9): trước đây 2/5 mục là EUDR + Lô hàng nên
 * người dùng đất tưởng đây là phần mềm xuất khẩu cà phê. EUDR, lô hàng, sàng lọc hàng loạt gom vào "Doanh nghiệp".
 */

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Building2, CalendarCheck, Columns2, LayoutDashboard, Map as MapIcon, Search, ShieldCheck } from "lucide-react";
import CommandPalette, { openCommandPalette } from "@/components/CommandPalette";
import Account from "@/components/Account";
import { fetchMe, getToken, type AuthUser } from "@/lib/api";
import { LangToggle, useLang } from "@/lib/i18n";

const NAV = [
  { href: "/hom-nay", vi: "Hôm nay", en: "Today", icon: CalendarCheck },
  { href: "/", vi: "Thửa đất", en: "Land", icon: MapIcon },
  { href: "/so-sanh", vi: "So sánh", en: "Compare", icon: Columns2 },
  { href: "/kiem", vi: "Kiểm", en: "Verify", icon: ShieldCheck },
  { href: "/eudr", vi: "Doanh nghiệp", en: "Business", icon: Building2 },
];
/** Các trang thuộc mục "Doanh nghiệp" (EUDR, lô hàng, sàng lọc hàng loạt, bên mua, thí điểm). */
export const BIZ_PATHS = ["/eudr", "/lo", "/batch", "/buyer", "/thi-diem"];

function active(path: string, href: string) {
  if (href === "/") return path === "/" || path.startsWith("/plot");
  if (href === "/eudr") return BIZ_PATHS.some((p) => path.startsWith(p));
  return path.startsWith(href);
}

export default function AppShell({ children, user: userProp, onAuth, extra, wide = false }: {
  children: ReactNode;
  user?: AuthUser | null;
  onAuth?: (u: AuthUser | null) => void;
  extra?: ReactNode;
  wide?: boolean;
}) {
  const { t } = useLang();
  const path = usePathname() || "/";
  const [ownUser, setOwnUser] = useState<AuthUser | null>(null);
  const controlled = userProp !== undefined;
  useEffect(() => {
    if (!controlled && getToken()) fetchMe().then(setOwnUser).catch(() => setOwnUser(null));
  }, [controlled]);
  const user = controlled ? userProp : ownUser;
  const setUser = (u: AuthUser | null) => { if (onAuth) onAuth(u); if (!controlled) setOwnUser(u); };

  return (
    <div className="tt-app">
      <header className="tt-top">
        <div className={`tt-top-in ${wide ? "wide" : ""}`}>
          <Link href="/" className="tt-brand" aria-label="TerraTwin">
            <span className="tt-logo" aria-hidden="true"><span /></span>
            <b>TerraTwin</b>
          </Link>
          <nav className="tt-nav" aria-label={t("Điều hướng chính", "Main navigation")}>
            {NAV.map((n) => (
              <Link key={n.href} href={n.href} className={active(path, n.href) ? "on" : ""} aria-current={active(path, n.href) ? "page" : undefined}>
                <n.icon size={16} strokeWidth={2} aria-hidden="true" /> {t(n.vi, n.en)}
              </Link>
            ))}
          </nav>
          <div className="tt-actions">
            {extra}
            {(user?.role === "admin" || user?.role === "coop") && (
              <Link href="/admin" className={`tt-admin ${path.startsWith("/admin") ? "on" : ""}`} title={t("Trang quản trị", "Admin page")}>
                <LayoutDashboard size={15} aria-hidden="true" /> <span>{t("Quản trị", "Admin")}</span>
              </Link>
            )}
            <button type="button" className="tt-cmdk" onClick={openCommandPalette}
                    aria-label={t("Mở thanh lệnh (Ctrl+K)", "Open command palette (Ctrl+K)")} title="Ctrl+K">
              <Search size={15} aria-hidden="true" /><kbd>Ctrl K</kbd>
            </button>
            <LangToggle />
            <Account user={user} onAuth={setUser} />
          </div>
        </div>
      </header>
      <div className="tt-page">{children}</div>
      <CommandPalette />
      <nav className="tt-tabbar" aria-label={t("Điều hướng", "Navigation")}>
        {NAV.map((n) => (
          <Link key={n.href} href={n.href} className={active(path, n.href) ? "on" : ""} aria-current={active(path, n.href) ? "page" : undefined}>
            <n.icon size={20} strokeWidth={2} aria-hidden="true" />
            <span>{t(n.vi, n.en)}</span>
          </Link>
        ))}
      </nav>
    </div>
  );
}
