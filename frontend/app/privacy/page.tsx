"use client";

import AppShell from "@/components/AppShell";
import Link from "next/link";
import { useLang } from "@/lib/i18n";

export default function PrivacyPage() {
  const { t } = useLang();
  return (
    <AppShell>

      <main className="doc-body">
        <h1>{t("Chính sách quyền riêng tư", "Privacy Policy")}</h1>
        <p className="doc-note">
          {t("Soạn theo Luật Bảo vệ dữ liệu cá nhân số 91/2025/QH15 (hiệu lực 01/01/2026) và Nghị định 356/2025/NĐ-CP hướng dẫn. BẢN NHÁP — chờ luật sư duyệt trước khi phát hành thương mại chính thức.",
             "Drafted under Vietnam's Personal Data Protection Law No. 91/2025/QH15 (in force 1 January 2026) and guiding Decree 356/2025/ND-CP. DRAFT — pending legal review before a formal commercial release.")}
        </p>

        <h2>{t("Dữ liệu chúng tôi lưu", "Data we store")}</h2>
        <ul>
          <li>{t("Tài khoản: email và mật khẩu (đã băm bcrypt — chúng tôi KHÔNG thấy mật khẩu gốc).",
                 "Account: email and password (bcrypt-hashed — we never see the raw password).")}</li>
          <li>{t("Thửa đất bạn lưu: toạ độ GPS, diện tích, tên bạn đặt.",
                 "Plots you save: GPS coordinates, area, the name you give.")}</li>
          <li>{t("Quan sát thực địa bạn gửi (vd 'ruộng có ngập'): dùng để hiệu chỉnh ngưỡng cảnh báo.",
                 "Field observations you submit (e.g. 'the field flooded'): used to calibrate alert thresholds.")}</li>
          <li>{t("Kênh nhận cảnh báo bạn cấu hình (email/webhook Zalo/Telegram).",
                 "Alert channels you configure (email / Zalo / Telegram webhook).")}</li>
          <li>{t("Phiếu góp ý thí điểm (/thi-diem): vai trò, điểm đánh giá, số phút, góp ý và huyện/tỉnh nếu bạn ghi. Không lưu địa chỉ IP, không bắt buộc tên. Số điện thoại hoặc email chỉ được lưu khi bạn đánh dấu đồng ý cho liên hệ lại; chỉ quản trị viên xem được.",
                 "Pilot feedback (/thi-diem): role, ratings, minutes, comment and district if given. No IP address stored, no name required. Phone or email is stored only if you tick consent to be contacted; only administrators can see it.")}</li>
        </ul>

        <h2>{t("Hồ sơ vườn EUDR, giấy tờ đất và sổ minh bạch", "EUDR plot dossiers, land documents and the transparency log")}</h2>
        <ul>
          <li>{t("Hồ sơ vườn chứa RANH THỬA (toạ độ) và kết quả sàng lọc. Ai có mã hồ sơ hoặc quét QR đều xem được — đó là mục đích của hồ sơ (người mua tự kiểm). Chỉ chia sẻ mã/QR với người bạn muốn.",
                 "A plot dossier contains the BOUNDARY (coordinates) and the screening result. Anyone with the dossier ID or QR can view it — that's its purpose (buyers verify it themselves). Share the ID/QR only with whom you choose.")}</li>
          <li>{t("Họ tên chủ hộ và tên trên sổ đỏ mặc định KHÔNG công khai: nội dung đã ký chỉ chứa mã băm có muối. Muối và tên thật (\"phần riêng\") chỉ nằm trong đường link đầy đủ bạn giữ, và trong tài khoản của người phát hành nếu đã đăng nhập.",
                 "The producer's name and the name on the land certificate are NOT public by default: signed content holds only a salted hash. The salt and real name (the \"private part\") live only in the full link you keep, and in the issuer's account if signed in.")}</li>
          <li>{t("Ảnh sổ đỏ KHÔNG được lưu: chỉ lưu các trường đã đọc và mã SHA-256 của ảnh. Khi dùng AI đọc ảnh, ảnh được gửi tới nhà cung cấp mô hình đã cấu hình để trích trường, rồi bỏ đi.",
                 "Land certificate photos are NOT stored: only the extracted fields and the photo's SHA-256. When AI reading is used, the photo is sent to the configured model provider to extract fields, then discarded.")}</li>
          <li>{t("Ảnh thực địa: chỉ lưu ảnh thu nhỏ đã XOÁ EXIF (toạ độ, máy ảnh) cùng mã băm của ảnh gốc.",
                 "Field photos: only an EXIF-STRIPPED thumbnail (no coordinates, no camera data) plus the original's hash are stored.")}</li>
          <li>{t("Sổ minh bạch công khai chỉ chứa mã băm, chữ ký và thời điểm — không có nội dung, toạ độ hay tên.",
                 "The public transparency log holds only hashes, signatures and timestamps — no content, coordinates or names.")}</li>
          <li>{t("Lô hàng: danh sách nhà cung cấp chỉ doanh nghiệp tạo lô xem được; chứng thư lô công khai chỉ có gốc Merkle, tổng khối lượng, số vườn.",
                 "Lots: the supplier list is visible only to the company that built the lot; the public certificate shows only the Merkle root, total quantity and plot count.")}</li>
          <li>{t("HỒ SƠ ĐÃ PHÁT HÀNH LÀ BẤT BIẾN: không xoá hay sửa được khỏi sổ (xoá một hồ sơ là gãy cả chuỗi). Vì thế tên luôn ẩn mặc định. Xoá tài khoản sẽ xoá phần riêng (tên thật, muối), lô thửa, lô hàng nháp — hồ sơ chỉ còn mã băm, không dò ngược ra tên được.",
                 "ISSUED DOSSIERS ARE IMMUTABLE: they can't be deleted or edited from the log (removing one breaks the chain). That's why names are hidden by default. Deleting your account erases the private part (real names, salts), supplier sets and draft lots — dossiers keep only hashes that can't be reversed to a name.")}</li>
        </ul>

        <h2>{t("Chúng tôi KHÔNG làm gì", "What we do NOT do")}</h2>
        <ul>
          <li>{t("KHÔNG bán, cho thuê, hay chia sẻ dữ liệu cá nhân của bạn cho bên thứ ba.",
                 "We do NOT sell, rent, or share your personal data with third parties.")}</li>
          <li>{t("KHÔNG gửi email, toạ độ hay bí mật của bạn ra dịch vụ ngoài.",
                 "We do NOT send your email, coordinates, or secrets to external services.")}</li>
          <li>{t("Quan sát dùng cho hiệu chỉnh được ẩn danh và làm tròn về ô lưới ~55 km — không lộ vị trí thửa.",
                 "Observations used for calibration are anonymized and rounded to a ~55 km grid cell — your plot location is never exposed.")}</li>
        </ul>

        <h2>{t("Nguồn dữ liệu bên ngoài", "External data sources")}</h2>
        <p>
          {t("Để phân tích một toạ độ hay ranh thửa, phần mềm gọi các dịch vụ công khai (Microsoft Planetary Computer, Open-Meteo, GloFAS, NASA POWER, OpenStreetMap). Chỉ toạ độ điểm được gửi đi để lấy dữ liệu thời tiết/ảnh — không kèm danh tính của bạn.",
             "To analyze a coordinate or boundary, the app calls public services (Microsoft Planetary Computer, Open-Meteo, GloFAS, NASA POWER, OpenStreetMap). Only the point coordinate is sent to fetch weather/imagery — never your identity.")}
        </p>

        <h2>{t("Đồng ý theo mục đích", "Purpose-separated consent")}</h2>
        <p>
          {t("Trong Khu làm việc, bạn bật/tắt riêng ba mục đích: nhận cảnh báo, góp quan sát (được hỏi một-chạm), và phục vụ nghiên cứu (dữ liệu ẩn danh cải thiện mô hình chung — mặc định TẮT, bạn chủ động bật). Tắt một mục đích không ảnh hưởng hai mục còn lại.",
             "In the Workspace, you toggle three purposes independently: receiving alerts, contributing observations (one-tap prompts), and research use (anonymized data to improve the shared model — OFF by default, opt-in only). Turning one off does not affect the others.")}
        </p>

        <h2>{t("Thời gian lưu trữ", "Retention")}</h2>
        <p>
          {t("Dữ liệu tài khoản/thửa/quan sát/cảnh báo được giữ trong lúc tài khoản còn hoạt động. Xoá tài khoản xoá NGAY khỏi ứng dụng đang chạy. Vì hệ thống có sao lưu mã hoá định kỳ để chống mất dữ liệu do sự cố, một bản sao có thể còn tồn tại thêm tối đa 7 ngày (sao lưu hằng ngày) hoặc 4 tuần (sao lưu hằng tuần) trước khi tự động bị ghi đè/hết hạn.",
             "Account/plot/observation/alert data is kept while the account is active. Deleting your account removes it from the running app IMMEDIATELY. Because the system keeps encrypted periodic backups to protect against data loss, a copy may persist for up to 7 days (daily backups) or 4 weeks (weekly backups) before being automatically overwritten/expired.")}
        </p>

        <h2>{t("Quyền của bạn theo Luật 91/2025/QH15 — và cách thực hiện ngay trong ứng dụng", "Your rights under Law 91/2025/QH15 — and how to exercise them in the app")}</h2>
        <ul>
          <li>{t("Được biết: trang này liệt kê đủ loại dữ liệu, mục đích, nơi gửi đi và thời hạn lưu.",
                 "To be informed: this page lists every data type, purpose, where it is sent and how long it is kept.")}</li>
          <li>{t("Đồng ý và rút lại đồng ý: ba công tắc mục đích trong Khu làm việc (cảnh báo, góp quan sát, nghiên cứu — mặc định TẮT). Rút lại không làm mất dữ liệu đã xử lý trước đó một cách hợp lệ.",
                 "To consent and withdraw consent: three purpose toggles in the Workspace (alerts, observations, research — OFF by default). Withdrawal does not undo processing lawfully done before.")}</li>
          <li>{t("Truy cập, sao chép: nút \"Tải toàn bộ dữ liệu của tôi (JSON)\" trong Khu làm việc trả mọi bảng thuộc tài khoản, gồm cả góp ý thí điểm và nhãn kiểm định.",
                 "To access and copy: the \"Download all my data (JSON)\" button in the Workspace returns every table tied to your account, including pilot feedback and validation labels.")}</li>
          <li>{t("Chỉnh sửa: sửa tên, ranh, ghi chú thửa trong Khu làm việc. Hồ sơ đã ký số không sửa được (sửa là gãy chữ ký) — phát hành hồ sơ mới thay thế.",
                 "To correct: edit names, boundaries and notes in the Workspace. A signed dossier cannot be edited (that would break the signature) — issue a new one instead.")}</li>
          <li>{t("Xoá: nút \"Xoá tài khoản\" xoá ngay phần riêng (tên thật, muối, thửa, lô nháp, góp ý của bạn). Hồ sơ đã phát hành chỉ còn mã băm trong sổ công khai — không dò ngược ra tên.",
                 "To erase: the \"Delete account\" button immediately removes your private data (real name, salts, plots, draft lots, your feedback). Issued dossiers keep only hashes in the public log — they cannot be traced back to your name.")}</li>
          <li>{t("Không mua bán dữ liệu cá nhân — điều luật cấm và TerraTwin không làm.",
                 "No buying or selling of personal data — prohibited by law and never done by TerraTwin.")}</li>
        </ul>
        <p>
          {t("Yêu cầu khác (khiếu nại, hỏi về xử lý dữ liệu): gửi qua phiếu góp ý tại /thi-diem và đánh dấu đồng ý liên hệ lại. Đầu mối bảo vệ dữ liệu chính thức sẽ được ghi tại đây khi TerraTwin có pháp nhân.",
             "Other requests (complaints, questions about processing): send them via the feedback form at /thi-diem with consent to be contacted. An official data-protection contact will be listed here once TerraTwin is a legal entity.")}
        </p>

        <footer className="doc-foot">
          <Link href="/about">{t("Giới thiệu", "About")}</Link>
          <span>·</span>
          <Link href="/terms">{t("Điều khoản", "Terms")}</Link>
          <span>·</span>
          <span>© {new Date().getFullYear()} TerraTwin</span>
        </footer>
      </main>
    </AppShell>
  );
}
