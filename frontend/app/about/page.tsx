"use client";

/**
 * TRANG GIỚI THIỆU — "TerraTwin hoạt động thế nào & vì sao tin được".
 *
 * Trang công khai cho giám khảo, người dùng, báo chí. Song ngữ VI/EN. Không
 * marketing rỗng: mọi câu gắn với một cơ chế đang chạy thật trong phần mềm, và nói
 * rõ cả những gì CHƯA làm được.
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
          "TerraTwin là hạ tầng niềm tin cho đất nông nghiệp Việt Nam: biến một mảnh vườn thành bằng chứng mà ngân hàng, doanh nghiệp xuất khẩu, nhà nhập khẩu châu Âu tự kiểm được — không cần tin TerraTwin. Việc cấp bách nhất: Quy định chống phá rừng của EU (EUDR) áp dụng từ 30/12/2026.",
          "TerraTwin is trust infrastructure for Vietnam's farmland: it turns a farm into evidence that banks, exporters and EU importers can verify themselves — without trusting TerraTwin. The most urgent job: the EU Deforestation Regulation (EUDR) applies from 30/12/2026.")}</p>

        <h2>{t("1. Ranh thửa đúng chuẩn EU", "1. Plot boundaries in the EU format")}</h2>
        <p>{t(
          "Vẽ trên ảnh vệ tinh, đi bộ quanh vườn bằng GPS điện thoại (mất sóng vẫn lưu), hoặc tải tệp GeoJSON, KML, Excel. TerraTwin kiểm đúng các quy tắc EU từ chối: toạ độ ít hơn 6 chữ số, thửa trên 4 ha chỉ khai một điểm, ranh hở, tự cắt, có lỗ, hai hộ khai chồng nhau. Lỗi chắc chắn thì tự sửa; lỗi còn lại chỉ đúng toạ độ chỗ sai.",
          "Draw on satellite imagery, walk the boundary with a phone (saved offline), or upload GeoJSON, KML or Excel. TerraTwin checks the rules the EU rejects: under 6 decimals, plots over 4 ha declared as a point, open, self-crossing or holed rings, overlapping producers. Certain errors are auto-fixed; the rest are pinpointed.")}</p>

        <h2>{t("2. Sàng lọc phá rừng sau 31/12/2020", "2. Deforestation screening after 31/12/2020")}</h2>
        <p>{t(
          "Ba bản đồ rừng quanh năm 2020 độc lập nhau bỏ phiếu: ESA WorldCover (quang học), JAXA ALOS (radar), Impact Observatory (trung bình 2018–2020). Thêm quỹ đạo tán cây từng năm, NDVI Sentinel-2 cùng mùa trước và sau mốc, khu bảo tồn theo OpenStreetMap. Bỏ phiếu vì một bản đồ đơn lẻ hay sai: đo thật ở vườn cà phê Buôn Ma Thuột, WorldCover vẽ 76% \"tán cây\" trong khi radar và Impact Observatory đều 0% rừng — và EUDR không coi vườn cây nông nghiệp là rừng.",
          "Three independent forest maps around 2020 vote: ESA WorldCover (optical), JAXA ALOS (radar), Impact Observatory (2018–2020 average). Plus yearly tree-cover trajectory, same-season Sentinel-2 NDVI before and after the cutoff, and protected areas from OpenStreetMap. Voting, because single maps err: at a Buôn Ma Thuột coffee farm WorldCover shows 76% \"tree cover\" while radar and Impact Observatory show 0% forest — and the EUDR does not count tree crops as forest.")}</p>
        <p>{t("Đây là SÀNG LỌC, không phải chứng nhận. Quy tắc công khai, số liệu đo trên đúng ranh thửa, ai cũng tính lại được.",
          "This is SCREENING, not certification. The rule is public and the numbers are measured on the exact boundary — anyone can recompute them.")}</p>

        <h2>{t("3. Hồ sơ ký số và sổ minh bạch", "3. Signed dossiers and a transparency log")}</h2>
        <p>{t(
          "Mỗi vườn có một hồ sơ ký Ed25519 kèm QR. Mọi hồ sơ là lá của một cây Merkle theo chuẩn RFC 6962 (như Certificate Transparency); mỗi ngày một tác vụ độc lập trên GitHub giữ đầu cây và kiểm cây chỉ được thêm, không bị sửa. Tải tệp hồ sơ về là kiểm được ngay trong trình duyệt, kể cả khi tắt mạng (trang Kiểm).",
          "Each plot gets an Ed25519-signed dossier with a QR code. Every dossier is a leaf of an RFC 6962 Merkle tree (like Certificate Transparency); every day an independent GitHub job keeps the tree head and checks the tree is append-only. A downloaded dossier can be verified in the browser, even offline (Verify page).")}</p>
        <p>{t(
          "Hồ sơ chỉ chứa số ĐO và số TÍNH LẠI ĐƯỢC — không chứa dự báo. Tên chủ hộ mặc định ẩn bằng cam kết băm có muối; nông hộ giữ đường link đầy đủ để chứng minh khi cần.",
          "Dossiers hold only MEASURED and RECOMPUTABLE figures — no forecasts. The producer's name is hidden by default behind a salted hash commitment; the farmer keeps a full link to prove it when needed.")}</p>

        <h2>{t("4. Lô hàng không thể bị rửa", "4. Lots that can't be laundered")}</h2>
        <p>{t(
          "Doanh nghiệp ghép lô từ các đợt nhập của từng vườn. TerraTwin chặn vườn chưa đạt sàng lọc và vườn khai vượt năng suất trần — cộng dồn mọi lô cùng vụ của MỌI doanh nghiệp. Nông hộ tự xác nhận hoặc từ chối từng đợt giao hàng bằng đường link của mình. Lô đạt nhận chứng thư Merkle đã ký và tờ khai DDS nháp.",
          "Exporters build lots from each plot's deliveries. TerraTwin blocks plots that failed screening and plots declared above the yield cap — summed across every lot in the season from EVERY company. Farmers confirm or reject each delivery via their own link. Passing lots get a signed Merkle certificate and a draft DDS.")}</p>

        <h2>{t("5. Giám sát sau phát hành", "5. Post-issuance monitoring")}</h2>
        <p>{t(
          "Mỗi tuần, hồ sơ vườn đã phát hành được sàng lọc lại; radar Sentinel-1 nhìn xuyên mây thấy mất tán cây cả trong mùa mưa. Vườn xấu đi thì lô hàng chứa nó bị chặn, và trang Hôm nay báo cho chủ vườn. Radar đang ở mức thử nghiệm cho tới khi kiểm định xong với cảnh báo RADD.",
          "Every week, issued plot dossiers are re-screened; Sentinel-1 radar sees canopy loss through rainy-season clouds. Worsening plots block the lots that contain them, and the Today page tells the owner. Radar is experimental until validated against RADD alerts.")}</p>

        <h2>{t("6. Tự kiểm định, công bố cả lần trượt", "6. Self-validation, failures published")}</h2>
        <p>{t(
          "Mọi mô hình chỉ được bật khi qua ngưỡng đặt trước, commit lên GitHub TRƯỚC khi chạy. Hai lần huấn luyện U-Net phân loại lớp phủ đều trượt và được công bố; phân tích mức lỗi nén ảnh (ELA) không tách được ảnh ghép nên không bật. Kết quả kiểm định sàng lọc EUDR và mô hình \"rừng hay vườn cây\" hiện ở trang Phương pháp.",
          "Every model is enabled only after passing a bar committed to GitHub BEFORE it runs. Two U-Net land-cover runs failed and were published; error level analysis couldn't separate spliced photos, so it isn't enabled. EUDR screening validation and the \"forest or tree crop\" model results appear on the Method page.")}</p>

        <h2>{t("7. Công cụ thẩm định thửa đất", "7. Land appraisal tools")}</h2>
        <p>{t(
          "Ngoài EUDR, TerraTwin có công cụ cho một thửa bất kỳ: loại đất, địa hình, mười năm hiểm hoạ, theo dõi thời tiết. Cảnh báo thiên tai chỉ để tham khảo — bản tin chính thức do Trung tâm Dự báo KTTV quốc gia phát (nchmf.gov.vn).",
          "Beyond the EUDR, TerraTwin has tools for any plot: land type, terrain, ten years of hazards, weather watch. Disaster alerts are reference only — official bulletins come from Vietnam's national forecasting centre (nchmf.gov.vn).")}</p>

        <h2>{t("Nguồn dữ liệu", "Data sources")}</h2>
        <p>{t(
          "Copernicus Sentinel-1 và Sentinel-2, ESA WorldCover 2020/2021, JAXA ALOS PALSAR, Impact Observatory/Esri Annual Land Cover — qua Microsoft Planetary Computer; Hansen Global Forest Change (đối chiếu kiểm định); OpenStreetMap; Open-Meteo/ERA5, GloFAS.",
          "Copernicus Sentinel-1 and Sentinel-2, ESA WorldCover 2020/2021, JAXA ALOS PALSAR, Impact Observatory/Esri Annual Land Cover — via Microsoft Planetary Computer; Hansen Global Forest Change (validation reference); OpenStreetMap; Open-Meteo/ERA5, GloFAS.")}</p>

        <div className="doc-cta">
          <Link href="/eudr" className="doc-btn">{t("Bắt đầu với một vườn", "Start with a plot")}</Link>
        </div>
        <div className="doc-foot">
          <Link href="/eudr?tab=phuong-phap">{t("Phương pháp & kiểm định", "Method & validation")}</Link>
          <Link href="/pricing">{t("Bảng giá", "Pricing")}</Link>
          <Link href="/help">{t("Trợ giúp", "Help")}</Link>
          <Link href="/privacy">{t("Quyền riêng tư", "Privacy")}</Link>
          <Link href="/terms">{t("Điều khoản", "Terms")}</Link>
        </div>
      </main>
    </AppShell>
  );
}
