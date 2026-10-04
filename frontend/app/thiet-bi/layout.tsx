import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Thiết bị tại vườn",
  description: "IoT ký số: trạm đo ẩm đất, mưa, nhiệt tự ký từng số đo bằng Ed25519 — chống giả mạo, chống phát lại.",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
