"use client";

/**
 * TRANG GIỚI THIỆU — "TerraTwin hoạt động thế nào & vì sao tin được".
 *
 * Đây là trang công khai cho giám khảo / người dùng / báo chí đọc để hiểu sản
 * phẩm mà không cần đăng nhập. Song ngữ VI/EN. Không marketing rỗng — mọi tuyên
 * bố đều gắn với cơ chế thật trong phần mềm.
 */

import Link from "next/link";
import { LangToggle, useLang } from "@/lib/i18n";

export default function AboutPage() {
  const { t } = useLang();
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
        <h1>{t("TerraTwin hoạt động thế nào — và vì sao tin được",
               "How TerraTwin works — and why to trust it")}</h1>
        <p className="doc-lede">
          {t("TerraTwin là bản sao số của đất đai Việt Nam: chọn đúng thửa của bạn, phần mềm kiểm toàn bộ rủi ro trong 7 ngày tới bằng dữ liệu vệ tinh và khí hậu thật, hiệu chuẩn riêng cho chính điểm đó, rồi cho biết nên làm gì.",
             "TerraTwin is a digital twin of Vietnam's land: pick your exact plot and it checks every risk over the next 7 days using real satellite and climate data, calibrated to that precise point, then tells you what to do.")}
        </p>

        <h2>{t("1. Hiệu chuẩn tới từng thửa — cái lõi độc quyền",
               "1. Calibrated to each plot — the exclusive core")}</h2>
        <p>
          {t("Đa số cảnh báo dùng một ngưỡng chung cho cả nước nên kêu oan hơn nửa số ngày ở miền Trung. TerraTwin tải 10 năm khí hậu ERA5 của CHÍNH điểm bạn chọn để dựng ngưỡng riêng — báo động giả tụt từ 46–61% xuống khoảng 3%. Không ai làm được điều này bằng một ngưỡng chung.",
             "Most alerts use one nationwide threshold and cry wolf over half the days in central Vietnam. TerraTwin loads 10 years of ERA5 climatology for the exact point you pick to build a local threshold — false alarms drop from 46–61% to about 3%. No one achieves this with a single shared threshold.")}
        </p>

        <h2>{t("2. Dữ liệu THẬT, kiểm chứng được", "2. Real, verifiable data")}</h2>
        <p>
          {t("Nguồn: Open-Meteo/ERA5 (khí hậu), GloFAS (lũ), NASA POWER (bức xạ), Sentinel-2 qua Microsoft Planetary Computer (ảnh vệ tinh), OpenStreetMap (hạ tầng). Mỗi kết luận gắn cờ 🛰️ đo được hay 🧪 ước lượng, kèm khoảng tin cậy. Chỗ nào chưa đủ dữ liệu, phần mềm nói thẳng — không bịa số.",
             "Sources: Open-Meteo/ERA5 (climate), GloFAS (floods), NASA POWER (radiation), Sentinel-2 via Microsoft Planetary Computer (satellite), OpenStreetMap (infrastructure). Every conclusion is flagged 🛰️ measured or 🧪 estimated, with a confidence range. Where data is insufficient, it says so — no made-up numbers.")}
        </p>

        <h2>{t("3. Bằng chứng, không phải lời hứa", "3. Evidence, not promises")}</h2>
        <p>
          {t("Mô hình được kiểm chứng ngược trên thiên tai thật (lũ Huế 2020, sạt lở Trà Leng): báo trước mấy ngày, kèm tỉ lệ báo bừa. Và phần mềm tự chấm điểm về chính mình công khai (POD/FAR/CSI) — không sửa được từ giao diện. Bạn xem được ngay trên trang chính.",
             "The model is backtested on real disasters (Huế 2020 flood, Trà Leng landslide): days of lead time, with the false-alarm rate shown. And it scores itself publicly (POD/FAR/CSI) — not editable from the UI. You can see it on the home page.")}
        </p>

        <h2>{t("4. Trí tuệ AI — đúng chỗ, trung thực", "4. AI — applied where it truly helps")}</h2>
        <p>
          {t("TerraTwin dùng cả một ngăn xếp AI: học máy hiệu chuẩn theo phân vị, học sâu phân đoạn lớp phủ (thị giác máy), chỉ số quang học NDVI/NDBI, xử lý ngôn ngữ tự nhiên cho câu hỏi what-if, trợ lý LLM có DẪN NGUỒN (chỉ trả lời dựa dữ liệu đo được + lịch sử thửa, cấm bịa số), mô hình độ hiếm tổ hợp, và học liên kết từ quan sát thực địa. Mỗi mô hình chỉ được bật khi qua ngưỡng kiểm định.",
             "TerraTwin runs a full AI stack: percentile-calibration machine learning, deep-learning land-cover segmentation (computer vision), NDVI/NDBI optical indices, natural-language processing for what-if questions, a source-cited LLM assistant (answers only from measured data + plot history, never invents numbers), a combinatorial-rarity model, and federated learning from field observations. Each model only turns on after it passes a held-out check.")}
        </p>

        <h2>{t("5. Vì sao người dùng cần TerraTwin", "5. Why users need TerraTwin")}</h2>
        <p>
          {t("Nó không chỉ báo rủi ro — nó cho một KẾ HOẠCH: việc cần làm có ngày, ngày an toàn để làm đồng, giá trị đang chịu rủi ro, và tự canh nền để báo trước qua Zalo/email. Càng nhiều nông dân xác nhận thực địa bằng một chạm, ngưỡng càng khớp với đất Việt Nam — một tài sản không ai tải được từ vệ tinh, chỉ TerraTwin có.",
             "It doesn't just flag risk — it gives a PLAN: dated to-dos, safe days for fieldwork, the value at stake, and background guarding that warns you early via Zalo/email. The more farmers confirm outcomes with one tap, the better the thresholds fit Vietnamese land — an asset no one can download from satellites, unique to TerraTwin.")}
        </p>

        <div className="doc-cta">
          <Link href="/" className="doc-btn">{t("Thử ngay với thửa của bạn", "Try it on your plot")}</Link>
        </div>

        <footer className="doc-foot">
          <Link href="/privacy">{t("Quyền riêng tư", "Privacy")}</Link>
          <span>·</span>
          <Link href="/terms">{t("Điều khoản", "Terms")}</Link>
          <span>·</span>
          <span>© {new Date().getFullYear()} TerraTwin</span>
        </footer>
      </article>
    </div>
  );
}
