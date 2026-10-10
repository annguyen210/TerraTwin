import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Thẻ mô hình AI",
  description: "Mọi mô hình và quy tắc AI của TerraTwin, kể cả cái đã trượt: dữ liệu, cách chia tập, điểm trên tập giữ lại, giới hạn, mã nguồn.",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
