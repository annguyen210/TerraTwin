"use client";

import AppShell from "@/components/AppShell";
import Link from "next/link";
import { useLang } from "@/lib/i18n";

export default function HelpPage() {
  const { t } = useLang();
  const LAND: [string, string, string, string][] = [
    ["TerraTwin là gì?", "What is TerraTwin?",
     "Hồ sơ sự thật về một mảnh đất ở Việt Nam: nước đã phủ thửa bao nhiêu lần từ 2017 (radar Sentinel-1 nhìn xuyên mây), đất đang dùng làm gì, tin đăng bán nói có đúng không — bằng số đo vệ tinh, ký số, ai cũng tự kiểm lại được. Doanh nghiệp xuất khẩu có thêm mục EUDR.",
     "A record of the facts about a piece of land in Vietnam: how many times water covered the plot since 2017 (Sentinel-1 radar sees through clouds), what the land is used for, whether a sale listing tells the truth — with satellite measurements, signed, verifiable by anyone. Exporters also get an EUDR section."],
    ["Bắt đầu thế nào?", "How do I start?",
     "Trang chủ → “Xem ngay” một thửa mẫu, hoặc kéo bản đồ cho thửa của bạn vào giữa ô ngắm rồi bấm nút xanh. Thẻ thửa có ba tab: Hồ sơ (lịch sử nước tự đọc, loại đất, phát hành hồ sơ ký số), Canh đất (nhật ký), Kiểm chứng (dán tin đăng bán đất).",
     "Home → “Try now” on a sample plot, or drag the map so your plot sits in the crosshair and press the green button. The plot card has three tabs: Dossier (water history loads by itself, land cover, issue a signed dossier), Watch (journal), Verify (paste a sale listing)."],
    ["“Đợt nước phủ” nghĩa là gì? Có phải số liệu ngập chính thức?", "What is a “water event”? Is it an official flood record?",
     "Một hoặc nhiều cảnh radar (cách nhau ≤ 24 ngày) mà phân vị tán xạ VV của thửa dưới −18 dB VÀ thấp hơn nền của chính thửa ≥ 3 dB. Đây là SỐ ĐO radar, không phải số liệu ngập chính thức; đô thị, rừng rậm, sườn dốc có thể làm sai, và đợt ngập ngắn hơn chu kỳ chụp 6–12 ngày có thể bị lọt — trang thửa luôn ghi rõ giới hạn này.",
     "One or more radar scenes (≤ 24 days apart) where the plot's VV backscatter percentile is below −18 dB AND ≥ 3 dB below the plot's own baseline. It is a radar MEASUREMENT, not an official flood record; cities, dense forest and slopes can mislead, and floods shorter than the 6–12 day revisit can be missed — the plot page always states these limits."],
    ["Kiểm tin đăng bán đất có lưu nội dung tin không?", "Does the listing check store the listing text?",
     "Không. Bạn tự dán chữ vào; TerraTwin tách câu khẳng định, đối chiếu với số đo rồi bỏ nội dung. Khi phát hành hồ sơ kèm kết quả kiểm tin đăng, hồ sơ chỉ giữ loại câu, kết quả, số đo, nguồn — không giữ nguyên văn. TerraTwin không cào trang bất động sản.",
     "No. You paste the text yourself; TerraTwin splits out the claims, checks them against measurements and discards the text. A dossier that includes a listing check keeps only claim type, verdict, figures and source — never the wording. TerraTwin doesn't scrape property sites."],
    ["Hồ sơ đất của TerraTwin có thay sổ đỏ không?", "Does a TerraTwin dossier replace the land-use certificate?",
     "Không. Loại đất PHÁP LÝ, ranh pháp lý, chủ sở hữu chỉ có trên sổ đỏ và hồ sơ địa chính. TerraTwin ghi những gì đo được từ vệ tinh và dữ liệu mở — bằng chứng bổ sung cho người mua, ngân hàng thẩm định, không phải giấy tờ pháp lý.",
     "No. LEGAL land type, legal boundary and ownership exist only on the certificate and cadastral records. TerraTwin records what satellites and open data measure — supporting evidence for buyers and bank appraisers, not a legal document."],
    ["Canh đất là gì?", "What is Land watch?",
     "Lưu thửa (tab Canh đất) để có nhật ký riêng: từ lần mở trước có gì đổi — mưa rất to, ảnh radar mới thấy nước, cảnh báo, cảm biến tại vườn, câu trả lời và ảnh thực địa của bạn. Chỉ báo khi có thay đổi thật; bật thông báo đẩy ở trang Hôm nay. Chưa đăng nhập vẫn xem được nhật ký công khai 7 ngày của toạ độ đang xem và của 6 thửa mẫu.",
     "Save a plot (Watch tab) for its own journal: what changed since your last visit — very heavy rain, a new radar image showing water, alerts, field sensors, your answers and field photos. Only real changes are reported; turn on push on the Today page. Signed out, you still see the public 7-day journal of the spot and of 6 sample plots."],
    ["Người nhận kiểm hồ sơ của tôi thế nào?", "How does a recipient verify my dossier?",
     "Quét QR trên hồ sơ (hoặc mở mã hồ sơ) là thấy bản gốc kèm các phép kiểm: nội dung, mục sổ, chữ ký, mắt xích, neo Bitcoin. Nhận tệp .json thì thả vào trang Kiểm: trình duyệt tự kiểm, kể cả khi không có mạng. Sửa bất kỳ trường nào — số liệu, lời diễn giải, ngày, số thứ tự — đều bị báo đỏ.",
     "Scan the QR (or open the dossier ID) to see the original with its checks: content, registry entry, signature, chain link, Bitcoin anchor. With the .json file, drop it on the Verify page: the browser checks it, even offline. Editing any field — figures, narrative, date, sequence — turns it red."],
    ["Có mất phí không? Tài khoản miễn phí có bị khoá tính năng?", "Is it free? Are features locked on free accounts?",
     "Đang thử nghiệm: mọi tính năng miễn phí. MỌI tài khoản có ĐỦ MỌI tính năng; gói chỉ khác HẠN MỨC (số hồ sơ, lượt quét, lượt API) — gửi yêu cầu ở Tài khoản của tôi, quản trị cấp. Giá sẽ công bố trước khi thu.",
     "In trial: everything is free. EVERY account has EVERY feature; plans differ only in QUOTA (dossiers, scans, API calls) — request in My account and an admin grants it. Prices will be published before any charge."],
    ["Cảnh báo thiên tai của TerraTwin có chính thức không?", "Are TerraTwin's disaster alerts official?",
     "Không. Cảnh báo chỉ để tham khảo; bản tin chính thức do Trung tâm Dự báo Khí tượng Thủy văn quốc gia phát (nchmf.gov.vn). Tỉ lệ đúng / báo bừa / bỏ sót của TerraTwin được chấm công khai.",
     "No. Alerts are reference only; official bulletins come from Vietnam's national forecasting centre (nchmf.gov.vn). TerraTwin's hit / false-alarm / miss rates are scored publicly."],
  ];
  const FAQ: [string, string, string, string][] = [
    ["Khi nào EUDR áp dụng?", "When does the EUDR apply?",
     "30/12/2026 với doanh nghiệp lớn và vừa; 30/6/2027 với doanh nghiệp nhỏ và siêu nhỏ. Ủy ban châu Âu xác nhận tháng 5/2026 là không hoãn nữa. Áp dụng cho cà phê, cao su, gỗ, ca cao, dầu cọ, đậu tương, gia súc và sản phẩm từ chúng.",
     "30/12/2026 for large and medium operators; 30/6/2027 for micro and small. The European Commission confirmed in May 2026 there will be no further delay. It covers coffee, rubber, wood, cocoa, palm oil, soy, cattle and derived products."],
    ["Vườn của tôi dưới 4 ha có phải vẽ ranh không?", "My plot is under 4 ha — do I need a boundary?",
     "Không bắt buộc: thửa từ 4 ha trở xuống có thể khai bằng một điểm (6 chữ số thập phân). Nhưng nên vẽ ranh: sàng lọc trên ranh thật sát hơn nhiều so với hình tròn giả định quanh một điểm. Thửa trên 4 ha thì bắt buộc vẽ ranh.",
     "Not required: plots up to 4 ha can be a single point (6 decimals). But draw it anyway: screening on the real boundary is far closer than an assumed circle around a point. Plots over 4 ha must have a boundary."],
    ["Lấy ranh vườn bằng cách nào?", "How do I capture the boundary?",
     "Vào EUDR → Một vườn: bấm các góc vườn trên ảnh vệ tinh, hoặc chọn \"Đi bộ quanh vườn (GPS)\" rồi đi chậm sát mép vườn — điểm GPS kém hơn ±25 m tự bị bỏ, mất sóng vẫn lưu trong máy. Cũng có thể tải tệp GeoJSON hoặc KML.",
     "Go to EUDR → One plot: tap the corners on the satellite image, or pick \"Walk the boundary (GPS)\" and walk slowly along the edge — GPS points worse than ±25 m are dropped, and it's saved offline. You can also upload GeoJSON or KML."],
    ["\"Đạt sàng lọc\", \"Cần xem lại\", \"Rủi ro\" nghĩa là gì?", "What do \"Passed\", \"Review\", \"Risk\" mean?",
     "Ba bản đồ rừng năm 2020 bỏ phiếu. Đạt: không bản đồ nào (hoặc chỉ 1/3) thấy rừng và không có dấu hiệu mất cây. Cần xem lại: ≥2 bản đồ thấy rừng, hoặc một bản đồ kèm dấu hiệu mất cây, hoặc nằm trong khu bảo tồn — cần người xem ảnh, giấy tờ. Rủi ro: ≥2 bản đồ thấy rừng rõ VÀ có dấu hiệu mất cây sau mốc. Đây là sàng lọc, không phải chứng nhận.",
     "Three 2020 forest maps vote. Passed: no map (or only 1/3) sees forest and no tree-loss sign. Review: ≥2 maps see forest, or one map plus tree loss, or inside a protected area — a person must check imagery and documents. Risk: ≥2 maps clearly see forest AND tree loss after the cutoff. This is screening, not certification."],
    ["Vườn cà phê có cây che bóng có bị coi là rừng không?", "Is shaded coffee counted as forest?",
     "Theo EUDR thì không: vườn cây nông nghiệp (kể cả nông lâm kết hợp) là đất nông nghiệp. Bản đồ vệ tinh đơn lẻ hay vẽ nhầm thành \"tán cây\" — vì vậy TerraTwin cho ba bản đồ bỏ phiếu, và hiện cả ảnh trước/sau để người xem tự nhìn.",
     "Under the EUDR, no: agricultural plantations (including agroforestry) are agricultural land. Single satellite maps often mislabel them as \"tree cover\" — that's why TerraTwin lets three maps vote and shows before/after imagery."],
    ["Người mua kiểm hồ sơ của tôi thế nào?", "How does a buyer verify my dossier?",
     "Quét QR trên hồ sơ (hoặc mở mã hồ sơ) là thấy bản gốc kèm bốn phép kiểm: nội dung, mục sổ, chữ ký, mắt xích. Nhận tệp .json thì thả vào trang Kiểm: trình duyệt tự kiểm, kể cả khi không có mạng.",
     "Scan the QR (or open the dossier ID) to see the original with four checks: content, registry entry, signature, chain link. With the .json file, drop it on the Verify page: the browser checks it, even offline."],
    ["Tên của tôi có bị công khai không?", "Is my name public?",
     "Mặc định KHÔNG. Hồ sơ chỉ chứa mã băm có muối của tên. Bạn giữ \"đường link đầy đủ\" và tự quyết đưa cho ai; người có link thấy tên kèm dấu \"đã chứng minh\".",
     "Not by default. The dossier only holds a salted hash of your name. You keep the \"full link\" and decide who gets it; whoever has it sees your name marked \"proven\"."],
    ["Doanh nghiệp khai hàng từ vườn tôi, tôi biết bằng cách nào?", "How do I know a company declared goods from my plot?",
     "Mở đường link đầy đủ của hồ sơ vườn: mục \"Đợt giao hàng khai cho vườn của bạn\" liệt kê mọi lô có vườn bạn, kèm số kg. Bấm Xác nhận hoặc Từ chối — đợt bị từ chối bị chặn khỏi lô.",
     "Open your dossier's full link: \"Deliveries declared from your plot\" lists every lot containing your plot, with kg. Press Confirm or Reject — rejected deliveries are blocked from the lot."],
    ["Cân bằng khối lượng là gì?", "What is mass balance?",
     "Tổng số kg mọi lô hàng cùng vụ khai từ một vườn không được vượt diện tích × năng suất trần (cà phê 6 tấn/ha — gấp khoảng hai lần bình quân). Vượt thì bị chặn: vườn không thể làm ra chừng ấy hàng, dấu hiệu \"rửa\" hàng từ vùng phá rừng.",
     "The total kg declared from one plot across all lots in a season can't exceed area × yield cap (coffee 6 t/ha — about twice the average). Above it, delivery is blocked: the plot can't produce that much — a sign of laundering from deforested land."],
  ];

  return (
    <AppShell>
      <main className="doc-body">
        <h1>{t("Trợ giúp & Câu hỏi thường gặp", "Help & FAQ")}</h1>
        <div className="faq">
          {LAND.map(([qv, qe, av, ae]) => (
            <details key={qv} className="faq-item">
              <summary>{t(qv, qe)}</summary>
              <p>{t(av, ae)}</p>
            </details>
          ))}
        </div>
        <h2>{t("Doanh nghiệp xuất khẩu — EUDR", "Exporters — EUDR")}</h2>
        <div className="faq">
          {FAQ.map(([qv, qe, av, ae]) => (
            <details key={qv} className="faq-item">
              <summary>{t(qv, qe)}</summary>
              <p>{t(av, ae)}</p>
            </details>
          ))}
        </div>

        <div className="doc-cta">
          <Link href="/" className="doc-btn">{t("Mở hồ sơ một thửa đất", "Open a land dossier")}</Link>
        </div>
        <p className="doc-note">{t("Hợp tác xã tổ chức tập huấn? ", "Running a co-op training session? ")}
          <Link href="/thi-diem">{t("Bộ thí điểm: tờ hướng dẫn in được và phiếu góp ý", "Pilot kit: printable guides and feedback form")}</Link></p>

        <footer className="doc-foot">
          <Link href="/about">{t("Cách hoạt động", "How it works")}</Link>
          <span>·</span>
          <Link href="/pricing">{t("Bảng giá", "Pricing")}</Link>
          <span>·</span>
          <Link href="/thi-diem">{t("Bộ thí điểm", "Pilot kit")}</Link>
          <span>·</span>
          <Link href="/privacy">{t("Quyền riêng tư", "Privacy")}</Link>
          <span>·</span>
          <span>© {new Date().getFullYear()} TerraTwin</span>
        </footer>
      </main>
    </AppShell>
  );
}
