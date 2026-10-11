import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Tài khoản của tôi",
  description: "Thông tin tài khoản, vai trò, dữ liệu đang có, lịch sử hoạt động, bảo mật và quyền với dữ liệu cá nhân.",
  robots: { index: false },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
