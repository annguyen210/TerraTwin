"use client";

/**
 * TRANG GIỚI THIỆU — "TerraTwin hoạt động thế nào & vì sao tin được".
 *
 * Trang công khai cho giám khảo, người dùng, báo chí. Song ngữ VI/EN. Không
 * marketing rỗng: mọi câu gắn với một cơ chế đang chạy thật trong phần mềm, và nói
 * rõ cả những gì CHƯA làm được. Trục chính là HỒ SƠ ĐẤT cho người có đất / người mua đất;
 * EUDR là một mục cho doanh nghiệp xuất khẩu (báo cáo kiểm toàn bộ 12/10/2026, mục 9).
 */

import Link from "next/link";
import AppShell from "@/components/AppShell";
import { useLang } from "@/lib/i18n";

export default function AboutPage() {
  const { t } = useLang();
  return (
    <AppShell>
      <main className="doc-body tt-reveal">
        <h1>{t("TerraTwin hoạt động thế nào — và vì sao tin được", "How TerraTwin works — and why to trust it")}</h1>
        <p className="doc-lede">{t(
          "TerraTwin là hồ sơ sự thật về một mảnh đất ở Việt Nam: nước đã phủ thửa bao nhiêu lần từ 2017, đất đang dùng làm gì, tin đăng bán nói có đúng không — bằng số ĐO từ vệ tinh, ký số, ai cũng tự kiểm lại được mà không cần tin TerraTwin. Người mua đất, chủ đất, ngân hàng thẩm định dùng cùng một hồ sơ.",
          "TerraTwin is a record of the facts about a piece of land in Vietnam: how many times water has covered the plot since 2017, what the land is used for, whether a sale listing tells the truth — with MEASURED satellite figures, digitally signed, verifiable by anyone without trusting TerraTwin. Buyers, owners and bank appraisers use the same dossier.")}</p>

        <h2>{t("1. Lịch sử nước nhìn xuyên mây, 2017 → nay", "1. Water history through clouds, 2017 → now")}</h2>
        <p>{t(
          "Đọc toàn bộ ảnh radar Sentinel-1 của đúng thửa (vài trăm cảnh, một quỹ đạo cố định). Mặt nước phẳng làm tán xạ VV tụt dưới −18 dB; một cảnh có nước khi phân vị VV dưới ngưỡng VÀ thấp hơn nền của chính thửa ≥ 3 dB — nên ruộng ngập theo vụ hay ao hồ thường trực không bị tính là lũ. Quy tắc chỉ bật sau khi qua cổng kiểm chứng đặt trước: thấy đúng lũ Huế 10/2020 và miền Trung 10/2025, 0 đợt ở đất cao. Mở thửa là tự đọc; kéo thanh năm để xem ảnh radar trên bản đồ.",
          "Reads every Sentinel-1 radar image of the exact plot (hundreds of scenes, one fixed orbit). Flat water drops VV backscatter below −18 dB; a scene has water when a VV percentile is below that AND ≥ 3 dB below the plot's own baseline — so seasonal paddy flooding or permanent ponds aren't counted as floods. The rule was enabled only after a pre-registered gate: it finds the Huế flood of 10/2020 and central Vietnam 10/2025, and 0 events on high ground. Opening a plot reads it automatically; drag the year slider to see radar images on the map.")}</p>

        <h2>{t("2. Đất đang dùng làm gì — và đổi từ khi nào", "2. What the land is used for — and since when")}</h2>
        <p>{t(
          "Loại đất từ đặc trưng vệ tinh AlphaEarth (Google DeepMind) qua bộ phân loại chỉ được bật khi vượt ngưỡng đăng ký trước trên tập giữ lại; so 2021 với năm mới nhất để thấy đất đã đổi mục đích. Loại đất PHÁP LÝ (thổ cư, đất ở) chỉ có trên sổ đỏ — vệ tinh không kiểm được, và TerraTwin nói thẳng như vậy.",
          "Land cover from AlphaEarth satellite embeddings (Google DeepMind) through a classifier enabled only after beating a pre-registered bar on held-out data; 2021 is compared with the latest year to show changes of use. LEGAL land type (residential) exists only on the land-use certificate — satellites can't check it, and TerraTwin says so.")}</p>

        <h2>{t("3. Kiểm tin đăng bán đất", "3. Checking a land sale listing")}</h2>
        <p>{t(
          "Dán tin đăng (\"đất cao ráo, không bao giờ ngập, gần sông\"): từng câu khẳng định được tách ra, trích đúng vế của nó, và đặt cạnh số đo — Khớp / Mâu thuẫn / Không đủ dữ liệu — kèm con số, ngày, nguồn. TerraTwin không cào trang bất động sản và không lưu nội dung tin đăng.",
          "Paste a listing (\"high ground, never floods, near the river\"): each claim is split out, quoted by its own clause, and placed next to measurements — Consistent / Contradicted / Not enough data — with the figure, date and source. TerraTwin doesn't scrape property sites and doesn't store listing text.")}</p>

        <h2>{t("4. Hồ sơ đất ký số, sổ minh bạch, neo Bitcoin", "4. Signed land dossiers, transparency log, Bitcoin anchoring")}</h2>
        <p>{t(
          "Mỗi hồ sơ được ký Ed25519 và là lá của một cây Merkle theo chuẩn RFC 6962 (như Certificate Transparency). Mỗi ngày một tác vụ độc lập trên GitHub giữ đầu cây, kiểm cây chỉ được thêm, và neo gốc cây vào Bitcoin qua OpenTimestamps — từ lúc khối được đào, không ai (kể cả TerraTwin) lùi ngày phát hành được. Tải tệp hồ sơ về là kiểm được ngay trong trình duyệt, kể cả khi tắt mạng; sửa bất kỳ trường nào — số liệu, lời diễn giải, ngày, số thứ tự — đều bị báo đỏ.",
          "Each dossier is Ed25519-signed and is a leaf of an RFC 6962 Merkle tree (like Certificate Transparency). Every day an independent GitHub job keeps the tree head, checks it is append-only, and anchors the root in Bitcoin via OpenTimestamps — once the block is mined, nobody (TerraTwin included) can backdate an issuance. A downloaded dossier verifies in the browser, even offline; editing any field — figures, narrative, date, sequence — turns it red.")}</p>
        <p>{t(
          "Hồ sơ chỉ chứa số ĐO và số TÍNH LẠI ĐƯỢC — không chứa dự báo. Mỗi câu diễn giải trỏ tới đúng bằng chứng của nó.",
          "Dossiers hold only MEASURED and RECOMPUTABLE figures — no forecasts. Every narrative sentence points to its own evidence.")}</p>

        <h2>{t("5. Canh đất khi bạn ngủ", "5. Watching your land while you sleep")}</h2>
        <p>{t(
          "Lưu thửa thì có nhật ký riêng: từ lần mở trước có gì đổi — mưa rất to, ảnh radar mới thấy nước, cảnh báo, cảm biến tại vườn (số đo ký số), câu trả lời và ảnh thực địa của bạn được đối chiếu ba chiều với radar và mưa. Chỉ báo khi có thay đổi thật. Các thửa mẫu được canh công khai mỗi ngày trên nhánh journal-log của kho mã. Cảnh báo thiên tai chỉ để tham khảo — bản tin chính thức do Trung tâm Dự báo KTTV quốc gia phát (nchmf.gov.vn).",
          "Save a plot for its own journal: what changed since your last visit — very heavy rain, a new radar image showing water, alerts, field sensors (signed readings), your answers and field photos reconciled three ways with radar and rain. Only real changes are reported. Sample plots are watched publicly every day on the repository's journal-log branch. Disaster alerts are reference only — official bulletins come from Vietnam's national forecasting centre (nchmf.gov.vn).")}</p>

        <h2>{t("6. So sánh thửa", "6. Comparing plots")}</h2>
        <p>{t(
          "Đặt 2–4 thửa cạnh nhau bằng cùng một bộ số đo: số đợt nước, địa hình, loại đất, khoảng cách tới sông/kênh. Mỗi hàng đánh dấu giá trị thuận lợi nhất theo RIÊNG tiêu chí đó; không có điểm tổng, không khuyên mua.",
          "Put 2–4 plots side by side with the same measurements: water events, terrain, land cover, distance to a river/canal. Each row marks the most favourable value on THAT criterion only; no total score, no buying advice.")}</p>

        <h2>{t("7. Cho doanh nghiệp xuất khẩu: EUDR", "7. For exporters: the EUDR")}</h2>
        <p>{t(
          "Quy định chống phá rừng của EU áp dụng từ 30/12/2026. Mục Doanh nghiệp: ranh thửa đúng chuẩn EU (vẽ, đi bộ GPS, GeoJSON/KML/Excel; kiểm và tự sửa lỗi EU từ chối), sàng lọc phá rừng sau 31/12/2020 bằng ba bản đồ rừng độc lập bỏ phiếu (ESA WorldCover, JAXA ALOS, Impact Observatory), ghép lô hàng chặn vườn chưa đạt và vượt năng suất trần, nông hộ tự xác nhận từng đợt giao, giám sát lại mỗi tuần sau phát hành. Đây là SÀNG LỌC, không phải chứng nhận.",
          "The EU Deforestation Regulation applies from 30/12/2026. The Business section: EU-format plot boundaries (draw, GPS walk, GeoJSON/KML/Excel; checks and auto-fixes what the EU rejects), deforestation screening after 31/12/2020 by three independent forest maps voting (ESA WorldCover, JAXA ALOS, Impact Observatory), lots that block failed and over-yield plots, farmers confirming each delivery, weekly re-screening after issuance. This is SCREENING, not certification.")}</p>

        <h2>{t("8. Tự kiểm định, công bố cả lần trượt", "8. Self-validation, failures published")}</h2>
        <p>{t(
          "Mọi mô hình và quy tắc chỉ được bật khi qua ngưỡng đặt trước, commit lên GitHub TRƯỚC khi chạy, chấm một lần. Hai lần huấn luyện U-Net lớp phủ đều trượt và được công bố; phân tích mức lỗi nén ảnh (ELA) không tách được ảnh ghép nên không bật. Thẻ mô hình của từng mô hình — kể cả cái trượt — ở trang Mô hình.",
          "Every model and rule is enabled only after passing a bar committed to GitHub BEFORE it runs, scored once. Two U-Net land-cover runs failed and were published; error level analysis couldn't separate spliced photos, so it isn't enabled. Every model's card — including the failed ones — is on the Models page.")}</p>

        <h2>{t("Nguồn dữ liệu", "Data sources")}</h2>
        <p>{t(
          "Copernicus Sentinel-1 RTC và Sentinel-2, ESA WorldCover 2020/2021, JAXA ALOS PALSAR, Impact Observatory/Esri Annual Land Cover — qua Microsoft Planetary Computer; AlphaEarth Foundations (Google DeepMind); Hansen Global Forest Change (đối chiếu kiểm định); OpenStreetMap (© những người đóng góp, ODbL); Open-Meteo/ERA5, GloFAS.",
          "Copernicus Sentinel-1 RTC and Sentinel-2, ESA WorldCover 2020/2021, JAXA ALOS PALSAR, Impact Observatory/Esri Annual Land Cover — via Microsoft Planetary Computer; AlphaEarth Foundations (Google DeepMind); Hansen Global Forest Change (validation reference); OpenStreetMap (© contributors, ODbL); Open-Meteo/ERA5, GloFAS.")}</p>

        <div className="doc-cta">
          <Link href="/" className="doc-btn">{t("Mở hồ sơ một thửa đất", "Open a land dossier")}</Link>
          <Link href="/eudr" className="doc-btn ghost">{t("Doanh nghiệp: EUDR", "Business: EUDR")}</Link>
        </div>
        <div className="doc-foot">
          <Link href="/mo-hinh">{t("Mô hình & kiểm định", "Models & validation")}</Link>
          <Link href="/eudr?tab=phuong-phap">{t("Phương pháp EUDR", "EUDR method")}</Link>
          <Link href="/pricing">{t("Bảng giá", "Pricing")}</Link>
          <Link href="/help">{t("Trợ giúp", "Help")}</Link>
          <Link href="/privacy">{t("Quyền riêng tư", "Privacy")}</Link>
          <Link href="/terms">{t("Điều khoản", "Terms")}</Link>
        </div>
      </main>
    </AppShell>
  );
}
