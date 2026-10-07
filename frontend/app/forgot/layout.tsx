import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Quên mật khẩu",
  description: "Đặt lại mật khẩu tài khoản TerraTwin.",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
