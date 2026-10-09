"use client";

/**
 * HOÃN NẠP thành phần nặng (bản đồ MapLibre ~ hàng trăm KB JS) cho tới khi nó SẮP HIỆN trên màn
 * hình VÀ người dùng đã thao tác lần đầu. Đo Lighthouse điện thoại 9/10/2026: /eudr hiệu năng
 * 57 vì bản đồ dựng ngay lúc mở trang. Khung giữ chỗ cùng chiều cao → không nhảy bố cục; có nút
 * "Mở ngay" cho người dùng bàn phím/đọc màn hình.
 */
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useLang } from "@/lib/i18n";

export default function WhenVisible({ children, minHeight, label }: { children: ReactNode; minHeight: number | string; label: string }) {
  const { t } = useLang();
  const [on, setOn] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (on) return;
    // Dựng khi khung ĐÃ HIỆN và người dùng ĐÃ THAO TÁC (chạm, cuộn bằng tay, gõ phím) — đo 9/10/2026:
    // dựng ngay lúc rảnh vẫn rơi vào cửa sổ tải trang (TBT 2,7 s, CLS 0,22 trên /eudr điện thoại).
    let seen = false, acted = false;
    const tryOn = () => { if (seen && acted) setOn(true); };
    const io = new IntersectionObserver((es) => {
      if (es.some((e) => e.isIntersecting)) { seen = true; io.disconnect(); tryOn(); }
    }, { rootMargin: "200px" });
    if (ref.current) io.observe(ref.current);
    const evs = ["pointerdown", "keydown", "touchstart", "wheel"] as const;
    const onAct = () => { acted = true; evs.forEach((e) => window.removeEventListener(e, onAct)); tryOn(); };
    evs.forEach((e) => window.addEventListener(e, onAct, { passive: true }));
    return () => { io.disconnect(); evs.forEach((e) => window.removeEventListener(e, onAct)); };
  }, [on]);

  if (on) return <>{children}</>;
  return (
    <div ref={ref} className="wv-ph" style={{ minHeight }}>
      <span>{label}</span>
      <button type="button" className="bat-btn ghost" onClick={() => setOn(true)}>{t("Mở ngay", "Open now")}</button>
    </div>
  );
}
