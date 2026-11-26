import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Bản đồ công nghệ",
  description: "Đủ 413 mục khoa học máy tính, dữ liệu, AI, kỹ thuật phần mềm — mục nào TerraTwin đang dùng ở đâu, mục nào không dùng và vì sao.",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
