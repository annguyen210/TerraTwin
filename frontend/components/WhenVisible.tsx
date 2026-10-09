"use client";

/**
 * HOÃN NẠP thành phần nặng (bản đồ MapLibre ~ hàng trăm KB JS) cho tới khi nó SẮP HIỆN trên màn
 * hình VÀ trình duyệt đã rảnh sau khi tải trang. Đo Lighthouse điện thoại 9/10/2026: /eudr hiệu năng
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
    let seen = false, idle = false, cancelled = false;
    const tryOn = () => { if (seen && idle && !cancelled) setOn(true); };
    const io = new IntersectionObserver((es) => {
      if (es.some((e) => e.isIntersecting)) { seen = true; io.disconnect(); tryOn(); }
    }, { rootMargin: "200px" });
    if (ref.current) io.observe(ref.current);
    const markIdle = () => {
      const ric = (window as Window & { requestIdleCallback?: (cb: () => void, o?: { timeout: number }) => number }).requestIdleCallback;
      if (ric) ric(() => { idle = true; tryOn(); }, { timeout: 2500 });
      else setTimeout(() => { idle = true; tryOn(); }, 600);
    };
    if (document.readyState === "complete") markIdle();
    else window.addEventListener("load", markIdle, { once: true });
    return () => { cancelled = true; io.disconnect(); window.removeEventListener("load", markIdle); };
  }, [on]);

  if (on) return <>{children}</>;
  return (
    <div ref={ref} className="wv-ph" style={{ minHeight }}>
      <span>{label}</span>
      <button type="button" className="bat-btn ghost" onClick={() => setOn(true)}>{t("Mở ngay", "Open now")}</button>
    </div>
  );
}
