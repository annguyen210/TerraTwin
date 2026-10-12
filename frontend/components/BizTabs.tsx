"use client";

/** Thanh phụ của mục "Doanh nghiệp": Hồ sơ EUDR · Lô hàng · Sàng lọc hàng loạt · Bên mua kiểm. */
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useLang } from "@/lib/i18n";

const TABS = [
  { href: "/eudr", vi: "Hồ sơ EUDR", en: "EUDR dossier" },
  { href: "/lo", vi: "Lô hàng", en: "Lots" },
  { href: "/batch", vi: "Sàng lọc hàng loạt", en: "Batch screening" },
  { href: "/buyer", vi: "Bên mua kiểm", en: "Buyer check" },
];

export default function BizTabs() {
  const { t } = useLang();
  const path = usePathname() || "";
  return (
    <nav className="biz-tabs" aria-label={t("Mục doanh nghiệp", "Business section")}>
      <span className="biz-tabs-k">{t("Doanh nghiệp", "Business")}</span>
      {TABS.map((x) => (
        <Link key={x.href} href={x.href} className={path.startsWith(x.href) ? "on" : ""} aria-current={path.startsWith(x.href) ? "page" : undefined}>
          {t(x.vi, x.en)}</Link>
      ))}
    </nav>
  );
}
