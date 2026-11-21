"use client";

/**
 * "ĐANG ĐÁNH THỨC MÁY CHỦ" (kiểm A–Z 21/11/2026, P0-2). Render miễn phí ngủ sau 15 phút vắng, thức mất 30–60 giây; người
 * được mời gần như chắc chắn gặp lúc đó. Thay vì "Không kết nối được máy chủ", hiện một dòng nói rõ đang chờ và yêu cầu sẽ
 * tự chạy tiếp. Hai nguồn: (1) mở trang là gọi /api/live — quá 2,5 giây chưa xong thì coi như máy chủ đang thức;
 * (2) mọi yêu cầu đang trong lịch chờ của lib/retry.ts (sự kiện WAKE_EVENT).
 */
import { useEffect, useState } from "react";
import { wakeServer } from "@/lib/api";
import { useLang } from "@/lib/i18n";
import { WAKE_EVENT, wakingCount, wakingMessage } from "@/lib/retry";

const SLOW_MS = 2500;

export default function WakeBanner() {
  const { lang } = useLang();
  const [waiting, setWaiting] = useState(0);
  const [slowPing, setSlowPing] = useState(false);

  useEffect(() => {
    const on = (e: Event) => setWaiting(Number((e as CustomEvent).detail) || 0);
    window.addEventListener(WAKE_EVENT, on);
    setWaiting(wakingCount());
    let done = false;
    const timer = setTimeout(() => { if (!done) setSlowPing(true); }, SLOW_MS);
    void wakeServer().finally(() => { done = true; clearTimeout(timer); setSlowPing(false); });
    return () => { window.removeEventListener(WAKE_EVENT, on); clearTimeout(timer); };
  }, []);

  if (!waiting && !slowPing) return null;
  return (
    <div className="tt-wake" role="status" aria-live="polite">
      <span className="tt-wake-dot" aria-hidden="true" />
      {wakingMessage(lang)}
    </div>
  );
}
