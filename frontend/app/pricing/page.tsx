"use client";

/**
 * BẢNG GIÁ — lấy từ /api/plans (nguồn thật). Ghi RÕ đang thử nghiệm, chưa thu
 * tiền — đúng nguyên tắc trung thực, không giả vờ có doanh thu.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { getPlans, type PlanCatalogue } from "@/lib/api";
import { LangToggle, useLang } from "@/lib/i18n";

const vnd = (n: number) => (n === 0 ? "0đ" : `${n.toLocaleString("vi-VN")}đ`);

export default function PricingPage() {
  const { t } = useLang();
  const [cat, setCat] = useState<PlanCatalogue | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    getPlans().then(setCat).catch((e) => setErr(e.message));
  }, []);

  return (
    <div className="doc">
      <header className="doc-top">
        <Link href="/" className="doc-brand">◵ TerraTwin</Link>
        <div className="doc-actions">
          <LangToggle />
          <Link href="/" className="doc-home">{t("← Về trang chính", "← Home")}</Link>
        </div>
      </header>

      <article className="doc-body">
        <h1>{t("Bảng giá", "Pricing")}</h1>
        <p className="doc-lede">
          {t("Toàn bộ 18 mũi nhọn chạy MIỄN PHÍ ngay. Gói trả phí thêm hạn mức và tính năng cho hợp tác xã / doanh nghiệp.",
             "All 18 spearheads run FREE right now. Paid plans add quota and features for co-ops / enterprises.")}
        </p>

        {err && <p className="doc-note">{err}</p>}
        {cat && (
          <>
            <div className="price-grid">
              {cat.plans.map((p) => (
                <div key={p.id} className={`price-card${p.id === "pro" ? " featured" : ""}`}>
                  {p.id === "pro" && <span className="price-tag">{t("Phổ biến", "Popular")}</span>}
                  <h3>{p.name}</h3>
                  <div className="price-amt">{vnd(p.price_vnd)}<small>{p.price_vnd ? t("/tháng", "/mo") : ""}</small></div>
                  <p className="price-for">{p.for}</p>
                  <div className="price-quota">{p.quota.toLocaleString("vi-VN")} {t("lượt quét/tháng", "scans/mo")}</div>
                  <ul>
                    {p.features.map((f) => <li key={f}>{f}</li>)}
                  </ul>
                </div>
              ))}
            </div>
            <p className="doc-note">🧪 {cat.disclaimer}</p>
          </>
        )}

        <div className="doc-cta">
          <Link href="/" className="doc-btn">{t("Dùng thử miễn phí", "Try it free")}</Link>
        </div>

        <footer className="doc-foot">
          <Link href="/about">{t("Cách hoạt động", "How it works")}</Link>
          <span>·</span>
          <Link href="/help">{t("Trợ giúp", "Help")}</Link>
          <span>·</span>
          <span>© {new Date().getFullYear()} TerraTwin</span>
        </footer>
      </article>
    </div>
  );
}
