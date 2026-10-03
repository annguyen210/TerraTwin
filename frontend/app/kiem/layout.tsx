import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Kiểm hồ sơ offline",
  description: "Kiểm chữ ký Ed25519 và bằng chứng Merkle ngay trong trình duyệt, không cần mạng.",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
