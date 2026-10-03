"use client";

import AppShell from "@/components/AppShell";
import Link from "next/link";
import { useLang } from "@/lib/i18n";

export default function TermsPage() {
  const { t } = useLang();
  return (
    <AppShell>

      <main className="doc-body">
        <h1>{t("Điều khoản sử dụng", "Terms of Use")}</h1>
        <p className="doc-note">
          {t("Bản tóm tắt cho giai đoạn thử nghiệm. Cần rà soát pháp lý trước khi phát hành thương mại.",
             "A summary for the trial phase. Requires legal review before commercial release.")}
        </p>

        <h2>{t("TerraTwin là công cụ HỖ TRỢ quyết định", "TerraTwin is a decision-SUPPORT tool")}</h2>
        <p>
          {t("Cảnh báo và dự báo dựa trên dữ liệu và mô hình thật, nhưng thiên nhiên có bất định. TerraTwin cung cấp thông tin để bạn quyết định tốt hơn — KHÔNG thay thế phán đoán của bạn, cơ quan phòng chống thiên tai địa phương, hay chuyên gia. Trong tình huống khẩn cấp, luôn tuân theo hướng dẫn của chính quyền.",
             "Alerts and forecasts are based on real data and models, but nature is uncertain. TerraTwin provides information to help you decide better — it does NOT replace your judgment, local disaster authorities, or experts. In an emergency, always follow official guidance.")}
        </p>

        <h2>{t("Sàng lọc EUDR không phải chứng nhận", "EUDR screening is not certification")}</h2>
        <p>
          {t("Kết quả sàng lọc phá rừng là sàng lọc từ bản đồ và ảnh vệ tinh công khai theo quy tắc công khai — KHÔNG phải chứng nhận tuân thủ Quy định (EU) 2023/1115. TerraTwin không xác nhận quyền sử dụng đất hay tính hợp pháp của sản xuất; giấy tờ đất được đối chiếu, không được xác minh với văn phòng đăng ký đất đai. Tờ khai thẩm định (DDS) do TerraTwin sinh là BẢN NHÁP; người nộp tờ khai chịu trách nhiệm về nội dung. Khối lượng trong lô hàng do doanh nghiệp khai.",
             "Deforestation screening is screening from public satellite maps and imagery under a public rule — NOT certification of compliance with Regulation (EU) 2023/1115. TerraTwin does not confirm land rights or production legality; land documents are cross-checked, not verified with the land registry. The due diligence statement (DDS) TerraTwin produces is a DRAFT; the filer is responsible for its content. Lot quantities are declared by the operator.")}
        </p>
        <h2>{t("Hồ sơ đã phát hành", "Issued dossiers")}</h2>
        <p>
          {t("Hồ sơ và chứng thư đã phát hành được ghi vào sổ chỉ-được-thêm và không thể xoá hay sửa. Nội dung là ảnh chụp tại thời điểm phát hành; kết quả giám sát sau phát hành được hiện kèm như dữ liệu sống. Bạn chịu trách nhiệm về ranh thửa và thông tin mình khai.",
             "Issued dossiers and certificates are written to an append-only log and cannot be deleted or edited. Content is a snapshot at issuance; post-issuance monitoring is shown alongside as live data. You are responsible for the boundary and information you declare.")}
        </p>
        <h2>{t("Cảnh báo thiên tai", "Disaster alerts")}</h2>
        <p>
          {t("Cảnh báo trong công cụ theo dõi thửa đất chỉ để tham khảo, không thay thế bản tin chính thức của Trung tâm Dự báo Khí tượng Thủy văn quốc gia (nchmf.gov.vn) và chỉ đạo của cơ quan phòng chống thiên tai địa phương.",
             "Alerts in the land tools are for reference only and do not replace official bulletins from Vietnam's national forecasting centre (nchmf.gov.vn) or local disaster-prevention authorities.")}
        </p>

        <h2>{t("Độ chính xác & trung thực", "Accuracy & honesty")}</h2>
        <p>
          {t("Chúng tôi gắn cờ rõ 🛰️ đo được / 🧪 ước lượng / chưa đủ dữ liệu, và công bố sổ điểm tự chấm gồm cả tỉ lệ báo bừa lẫn số lần bỏ sót. Chúng tôi không đảm bảo mọi cảnh báo đều đúng, và cam kết không tô hồng số liệu.",
             "We clearly flag 🛰️ measured / 🧪 estimated / insufficient data, and publish a self-scorecard including both the false-alarm rate and the miss count. We do not guarantee every alert is correct, and we commit to never gloss over the numbers.")}
        </p>

        <h2>{t("Tài khoản của bạn", "Your account")}</h2>
        <p>
          {t("Bạn chịu trách nhiệm giữ an toàn thông tin đăng nhập. Không dùng phần mềm để lạm dụng nguồn dữ liệu bên thứ ba (có giới hạn tần suất để bảo vệ các nguồn miễn phí).",
             "You are responsible for keeping your credentials safe. Do not use the app to abuse third-party data sources (rate limits protect the free upstreams).")}
        </p>

        <h2>{t("Gói cước", "Plans")}</h2>
        <p>
          {t("Bảng giá là ĐỀ XUẤT trong giai đoạn thử nghiệm — hiện chưa có cổng thanh toán và chưa thu tiền. Mọi thay đổi sẽ được thông báo trước.",
             "Pricing is PROPOSED during the trial phase — there is no payment gateway yet and no charges. Any changes will be announced in advance.")}
        </p>

        <footer className="doc-foot">
          <Link href="/about">{t("Giới thiệu", "About")}</Link>
          <span>·</span>
          <Link href="/privacy">{t("Quyền riêng tư", "Privacy")}</Link>
          <span>·</span>
          <span>© {new Date().getFullYear()} TerraTwin</span>
        </footer>
      </main>
    </AppShell>
  );
}
