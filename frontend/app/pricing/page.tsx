"use client";

/**
 * BẢNG GIÁ — lấy từ /api/plans (nguồn thật). Ghi RÕ đang thử nghiệm, chưa thu
 * tiền — đúng nguyên tắc trung thực, không giả vờ có doanh thu.
 */

import AppShell from "@/components/AppShell";
import { useEffect, useState } from "react";
import Link from "next/link";
import { getPlans, type PlanCatalogue } from "@/lib/api";
import { useLang } from "@/lib/i18n";

const vnd = (n: number) => (n === 0 ? "0đ" : `${n.toLocaleString("vi-VN")}đ`);

export default function PricingPage() {
  const { t } = useLang();
  const [cat, setCat] = useState<PlanCatalogue | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    getPlans().then(setCat).catch((e) => setErr(e.message));
  }, []);

  return (
    <AppShell>

      <main className="doc-body">
        <h1>{t("Bảng giá", "Pricing")}</h1>
        <p className="doc-lede">{t(
          "Đang thử nghiệm: mọi tính năng MIỄN PHÍ tới hạn EUDR 30/12/2026. Nông hộ luôn miễn phí. Giá cho doanh nghiệp sẽ công bố trước khi hết thử nghiệm — không thu tiền khi chưa báo trước.",
          "In trial: every feature is FREE until the EUDR deadline, 30/12/2026. Farmers are always free. Business pricing will be published before the trial ends — no charge without notice.")}</p>
        <div className="price-grid">
          <div className="price-card">
            <h3>{t("Nông hộ, hợp tác xã", "Farmers, co-ops")}</h3>
            <div className="price-amt">0đ<small>{t(" · mãi mãi", " · always")}</small></div>
            <p className="price-for">{t("Có hồ sơ để bán được cho đại lý xuất EU", "A dossier to sell to EU-bound traders")}</p>
            <ul>
              <li>{t("Lấy ranh: vẽ, đi bộ GPS, tải tệp", "Boundaries: draw, GPS walk, upload")}</li>
              <li>{t("Kiểm chuẩn EU + sàng lọc phá rừng", "EU format check + deforestation screening")}</li>
              <li>{t("Hồ sơ ký số + QR, tên chủ hộ ẩn", "Signed dossier + QR, name hidden")}</li>
              <li>{t("Xác nhận / từ chối đợt giao hàng", "Confirm / reject deliveries")}</li>
              <li>{t("Trang Hôm nay, hỏi đáp EUDR", "Today page, EUDR Q&A")}</li>
            </ul>
          </div>
          <div className="price-card featured">
            <span className="price-tag">{t("Cho hạn 30/12/2026", "For the 30/12/2026 deadline")}</span>
            <h3>{t("Doanh nghiệp xuất khẩu", "Exporters")}</h3>
            <div className="price-amt">{t("Theo thửa/năm", "Per plot/year")}<small>{t(" · miễn phí khi thử nghiệm", " · free during trial")}</small></div>
            <p className="price-for">{t("Nộp tờ khai thẩm định cho từng lô hàng", "File a due diligence statement per lot")}</p>
            <ul>
              <li>{t("Kiểm cả lô nhà cung cấp (GeoJSON, KML, Excel)", "Check whole supplier sets (GeoJSON, KML, Excel)")}</li>
              <li>{t("Giám sát hằng tuần + radar xuyên mây", "Weekly monitoring + cloud-piercing radar")}</li>
              <li>{t("Lô hàng: cân bằng khối lượng, chứng thư Merkle", "Lots: mass balance, Merkle certificate")}</li>
              <li>{t("Tờ khai DDS nháp + GeoJSON nộp EU", "Draft DDS + EU GeoJSON")}</li>
              <li>{t("Bảng tổng quan vùng nguyên liệu", "Sourcing overview dashboard")}</li>
            </ul>
          </div>
          <div className="price-card">
            <h3>{t("Ngân hàng, bảo hiểm", "Banks, insurers")}</h3>
            <div className="price-amt">{t("Theo lượt API", "Per API call")}<small>{t(" · liên hệ", " · contact us")}</small></div>
            <p className="price-for">{t("Tín dụng xanh, rủi ro tài sản bảo đảm", "Green credit, collateral risk")}</p>
            <ul>
              <li>{t("API hồ sơ thửa đã kiểm, đã ký", "API for verified, signed plot dossiers")}</li>
              <li>{t("Kiểm chữ ký + sổ minh bạch tự động", "Automatic signature + log verification")}</li>
              <li>{t("Thẩm định cả danh mục từ CSV", "Portfolio appraisal from CSV")}</li>
            </ul>
          </div>
        </div>

        {/* GĐ7 kế hoạch tổng — ba gói cho người mua đất, chủ đất, tổ chức. Giá DỰ KIẾN, đang kiểm chứng bằng
            phỏng vấn; chưa thu tiền khi chưa có pháp nhân và cổng thanh toán. */}
        <h2>{t("Đất ở, đất nông nghiệp — mua bán và canh đất", "Residential & farm land — buying and watching")}</h2>
        <p className="doc-note">{t("Giá DỰ KIẾN, đang hỏi ý kiến người mua đất, môi giới và cán bộ tín dụng. Hiện mọi tính năng miễn phí; sẽ báo trước khi thu.",
                                   "INDICATIVE prices, being validated with land buyers, brokers and loan officers. Everything is free for now; we will announce before charging.")}</p>
        <div className="price-grid">
          <div className="price-card">
            <h3>{t("Hồ sơ lẻ", "Single dossier")}</h3>
            <div className="price-amt">{t("50–100 nghìn đ", "VND 50–100k")}<small>{t(" / hồ sơ · dự kiến", " / dossier · indicative")}</small></div>
            <p className="price-for">{t("Người sắp mua, thuê đất — kiểm trước khi đặt cọc", "About to buy or rent land — check before the deposit")}</p>
            <ul>
              <li>{t("Lịch sử nước radar 2017 → nay", "Radar water history 2017 → now")}</li>
              <li>{t("Kiểm chứng tin đăng bán đất từng câu", "Sentence-by-sentence listing check")}</li>
              <li>{t("Hồ sơ ký số, QR, neo Bitcoin", "Signed dossier, QR, Bitcoin anchor")}</li>
            </ul>
          </div>
          <div className="price-card featured">
            <span className="price-tag">{t("Mở mỗi sáng", "Every morning")}</span>
            <h3>{t("Canh đất", "Land watch")}</h3>
            <div className="price-amt">{t("Theo tháng", "Monthly")}<small>{t(" · miễn phí 1–3 thửa", " · free for 1–3 plots")}</small></div>
            <p className="price-for">{t("Chủ đất, nông hộ, hợp tác xã nhiều thửa", "Landowners, farmers, co-ops with many plots")}</p>
            <ul>
              <li>{t("Nhật ký thửa: chỉ báo khi có thay đổi thật", "Plot journal: only real changes")}</li>
              <li>{t("Cảnh báo đẩy, bản tin sáng", "Push alerts, morning brief")}</li>
              <li>{t("So sánh thửa, cảm biến IoT ký số", "Plot comparison, signed IoT sensors")}</li>
            </ul>
          </div>
          <div className="price-card">
            <h3>{t("Doanh nghiệp", "Business")}</h3>
            <div className="price-amt">{t("Hợp đồng", "Contract")}<small>{t(" · liên hệ", " · contact us")}</small></div>
            <p className="price-for">{t("Ngân hàng, bảo hiểm, sàn môi giới", "Banks, insurers, brokerages")}</p>
            <ul>
              <li>{t("Thẩm định hàng loạt từ CSV", "Batch appraisal from CSV")}</li>
              <li>{t("API có khoá, có hạn mức, xác thực hai lớp", "Keyed, metered API with two-factor login")}</li>
              <li>{t("Cam kết mức dịch vụ (SLA) khi lên gói trả phí", "Service-level agreement on paid plans")}</li>
            </ul>
          </div>
        </div>

        <h2>{t("Công cụ thẩm định & theo dõi thửa đất", "Land appraisal & monitoring tools")}</h2>
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
            <p className="doc-note">{cat.disclaimer}</p>
          </>
        )}

        <div className="doc-cta">
          <Link href="/eudr" className="doc-btn">{t("Dùng thử miễn phí", "Try it free")}</Link>
        </div>

        <footer className="doc-foot">
          <Link href="/about">{t("Cách hoạt động", "How it works")}</Link>
          <span>·</span>
          <Link href="/help">{t("Trợ giúp", "Help")}</Link>
          <span>·</span>
          <span>© {new Date().getFullYear()} TerraTwin</span>
        </footer>
      </main>
    </AppShell>
  );
}
