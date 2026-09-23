"use client";

import Link from "next/link";
import { LangToggle, useLang } from "@/lib/i18n";

export default function PrivacyPage() {
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
        <h1>{t("Chính sách quyền riêng tư", "Privacy Policy")}</h1>
        <p className="doc-note">
          {t("Bản tóm tắt trung thực về dữ liệu TerraTwin thu thập và cách dùng. Cần rà soát pháp lý trước khi phát hành thương mại chính thức.",
             "An honest summary of what TerraTwin collects and how it is used. Requires legal review before a formal commercial release.")}
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
          {t("Để phân tích một toạ độ, phần mềm gọi các dịch vụ công khai (Open-Meteo, GloFAS, NASA POWER, Microsoft Planetary Computer, OpenStreetMap). Chỉ toạ độ điểm được gửi đi để lấy dữ liệu thời tiết/ảnh — không kèm danh tính của bạn.",
             "To analyze a coordinate, the app calls public services (Open-Meteo, GloFAS, NASA POWER, Microsoft Planetary Computer, OpenStreetMap). Only the point coordinate is sent to fetch weather/imagery — never your identity.")}
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

        <h2>{t("Quyền của bạn", "Your rights")}</h2>
        <p>
          {t("Bạn có thể xoá thửa và tài khoản bất cứ lúc nào trong Khu làm việc. Yêu cầu xuất hoặc xoá toàn bộ dữ liệu: liên hệ qua repo/kênh hỗ trợ của phần mềm.",
             "You can delete plots and your account anytime in the Workspace. To export or erase all your data, contact us via the app's support channel.")}
        </p>

        <footer className="doc-foot">
          <Link href="/about">{t("Giới thiệu", "About")}</Link>
          <span>·</span>
          <Link href="/terms">{t("Điều khoản", "Terms")}</Link>
          <span>·</span>
          <span>© {new Date().getFullYear()} TerraTwin</span>
        </footer>
      </article>
    </div>
  );
}
