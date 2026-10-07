import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Quản trị",
  description: "Trang vận hành cho quản trị viên và hợp tác xã.",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
