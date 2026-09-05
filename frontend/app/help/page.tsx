"use client";

import Link from "next/link";
import { LangToggle, useLang } from "@/lib/i18n";

export default function HelpPage() {
  const { t } = useLang();
  const FAQ: [string, string, string, string][] = [
    [
      "TerraTwin là gì?", "What is TerraTwin?",
      "Bản sao số của đất đai Việt Nam. Chọn đúng thửa của bạn, phần mềm kiểm toàn bộ rủi ro (mặn, hạn, lũ, sạt lở, cháy…) trong 7 ngày tới bằng dữ liệu vệ tinh & khí hậu thật, rồi cho biết nên làm gì.",
      "A digital twin of Vietnam's land. Pick your plot and it checks every risk (salinity, drought, flood, landslide, fire…) over the next 7 days using real satellite & climate data, then tells you what to do.",
    ],
    [
      "Có mất phí không?", "Is it free?",
      "Toàn bộ 18 mũi nhọn chạy miễn phí ngay, không cần thẻ. Gói trả phí chỉ thêm hạn mức và tính năng cho hợp tác xã / doanh nghiệp — và hiện chưa thu tiền.",
      "All 18 spearheads run free right now, no card needed. Paid plans only add quota and features for co-ops / enterprises — and there are no charges yet.",
    ],
    [
      "Cần cài đặt gì không?", "Do I need to install anything?",
      "Không. TerraTwin chạy trên trình duyệt. Trên điện thoại, bạn có thể 'Thêm vào màn hình chính' để dùng như một ứng dụng, kể cả khi mạng yếu.",
      "No. TerraTwin runs in the browser. On a phone you can 'Add to Home Screen' to use it like an app, even on a weak connection.",
    ],
    [
      "Cảnh báo chính xác đến đâu?", "How accurate are the alerts?",
      "Ngưỡng được hiệu chuẩn theo khí hậu 10 năm của CHÍNH điểm bạn chọn nên báo động giả chỉ ~3% (so với 46–61% của ngưỡng chung). Phần mềm tự chấm điểm công khai (bắt được / báo bừa / bỏ sót) — bạn xem được trên trang chính.",
      "Thresholds are calibrated to the exact point's 10-year climatology, so false alarms are ~3% (vs 46–61% for a shared threshold). The app scores itself publicly (caught / false / missed) — visible on the home page.",
    ],
    [
      "Làm sao nhận cảnh báo khi không mở app?", "How do I get alerts when the app is closed?",
      "Đăng nhập → lưu thửa → vào Khu làm việc → Kênh cảnh báo, thêm email hoặc webhook (nối Zalo/Telegram). TerraTwin tự quét nền 6 giờ/lần và gửi khi có rủi ro.",
      "Sign in → save a plot → Workspace → Alert channels, add email or a webhook (to Zalo/Telegram). TerraTwin scans in the background every 6 hours and notifies you when there's risk.",
    ],
    [
      "Dữ liệu của tôi có an toàn không?", "Is my data safe?",
      "Chúng tôi không bán hay chia sẻ dữ liệu cá nhân. Quan sát thực địa dùng để hiệu chỉnh được ẩn danh và làm tròn về ô ~55 km. Xem chi tiết ở trang Quyền riêng tư.",
      "We don't sell or share personal data. Field observations used for calibration are anonymized and rounded to a ~55 km cell. See the Privacy page for details.",
    ],
    [
      "Sổ tay thửa dùng để làm gì?", "What is the Land Passport for?",
      "Là hồ sơ dữ liệu chia sẻ được của một thửa (địa hình + 10 năm hiểm hoạ) — có thể đưa ngân hàng, bảo hiểm, hay người mua như một chứng thư đáng tin về mảnh đất.",
      "A shareable data record of a plot (terrain + 10-year hazard history) — you can give it to a bank, insurer, or buyer as a credible credential for the land.",
    ],
  ];

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
        <h1>{t("Trợ giúp & Câu hỏi thường gặp", "Help & FAQ")}</h1>
        <div className="faq">
          {FAQ.map(([qv, qe, av, ae]) => (
            <details key={qv} className="faq-item">
              <summary>{t(qv, qe)}</summary>
              <p>{t(av, ae)}</p>
            </details>
          ))}
        </div>

        <div className="doc-cta">
          <Link href="/" className="doc-btn">{t("Bắt đầu với thửa của bạn", "Start with your plot")}</Link>
        </div>

        <footer className="doc-foot">
          <Link href="/about">{t("Cách hoạt động", "How it works")}</Link>
          <span>·</span>
          <Link href="/pricing">{t("Bảng giá", "Pricing")}</Link>
          <span>·</span>
          <Link href="/privacy">{t("Quyền riêng tư", "Privacy")}</Link>
          <span>·</span>
          <span>© {new Date().getFullYear()} TerraTwin</span>
        </footer>
      </article>
    </div>
  );
}
