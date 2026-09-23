"use client";

/**
 * G4 — đường vào riêng cho người ĐANG ĐỊNH MUA/THUÊ đất, không phải người đã
 * sở hữu thửa. Trang chính (Start.tsx) mặc định khung "thửa CỦA BẠN" — sai
 * ngữ cảnh cho người còn đang cân nhắc trả tiền cho một mảnh đất chưa phải
 * của mình. Kết quả đổ về đúng "Sổ tay thửa" (/plot/[coord]) — trang đó đã
 * viết sẵn cho ba đối tượng gồm cả "người mua thẩm định trước khi mua đất",
 * chỉ thiếu một cửa vào riêng dẫn tới đó.
 */

import { useRouter } from "next/navigation";
import Link from "next/link";
import Start from "@/components/Start";
import { LangToggle, useLang } from "@/lib/i18n";

export default function BuyerPage() {
  const { t } = useLang();
  const router = useRouter();

  function goToPlot(lat: number, lon: number) {
    router.push(`/plot/${lat.toFixed(6)},${lon.toFixed(6)}`);
  }

  return (
    <div className="doc">
      <header className="doc-top">
        <Link href="/" className="doc-brand">◵ TerraTwin</Link>
        <div className="doc-actions"><LangToggle /><Link href="/" className="doc-home">{t("← Về trang chính", "← Home")}</Link></div>
      </header>

      <main className="doc-body" style={{ maxWidth: 640 }}>
        <div className="pp-badge">{t("TRƯỚC KHI KÝ", "BEFORE YOU SIGN")}</div>
        <h1>{t("Định mua hay thuê đất?", "Planning to buy or rent land?")}</h1>
        <p className="doc-lede">
          {t(
            "Kiểm rủi ro lũ, hạn, sạt lở của MẢNH ĐẤT ĐÓ trước khi trả tiền — không phải lời người bán nói, mà dữ liệu vệ tinh & khí hậu 10 năm, hiệu chuẩn riêng cho đúng toạ độ đó.",
            "Check flood, drought, and landslide risk for THAT EXACT PLOT before you pay — not the seller's word, but 10 years of satellite & climate data calibrated to that exact spot.",
          )}
        </p>
        <p className="doc-note">
          {t(
            "Kết quả là một Sổ tay thửa công khai, có thể gửi cho người bán, ngân hàng, hay giữ lại làm bằng chứng nếu sau này có tranh chấp.",
            "The result is a public Land Passport you can send to the seller, the bank, or keep as evidence if a dispute comes up later.",
          )}
        </p>

        <div style={{ marginTop: 24 }}>
          <Start onPick={goToPlot} />
        </div>
      </main>
    </div>
  );
}
