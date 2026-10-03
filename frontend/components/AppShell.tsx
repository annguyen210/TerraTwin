"use client";

/**
 * KHUNG ỨNG DỤNG — một thanh điều hướng cho MỌI trang (thay cho mỗi trang một kiểu đầu
 * trang), và trên điện thoại một THANH TAB DƯỚI ĐÁY như ứng dụng dùng hằng ngày:
 * Hôm nay · Thửa đất · EUDR · Lô hàng · Kiểm. Trang nào đang mở thì sáng lên.
 */

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { CalendarCheck, Map as MapIcon, Package, ShieldCheck, TreePine } from "lucide-react";
import Account from "@/components/Account";
import { fetchMe, getToken, type AuthUser } from "@/lib/api";
import { LangToggle, useLang } from "@/lib/i18n";

const NAV = [
  { href: "/hom-nay", vi: "Hôm nay", en: "Today", icon: CalendarCheck },
  { href: "/", vi: "Thửa đất", en: "Land", icon: MapIcon },
  { href: "/eudr", vi: "EUDR", en: "EUDR", icon: TreePine },
  { href: "/lo", vi: "Lô hàng", en: "Lots", icon: Package },
  { href: "/kiem", vi: "Kiểm", en: "Verify", icon: ShieldCheck },
];

function active(path: string, href: string) {
  return href === "/" ? path === "/" || path.startsWith("/plot") : path.startsWith(href);
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
            <LangToggle />
            <Account user={user} onAuth={setUser} />
          </div>
        </div>
      </header>
      <div className="tt-page">{children}</div>
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
