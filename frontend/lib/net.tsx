"use client";

/**
 * P2 — CHẾ ĐỘ TIẾT KIỆM DỮ LIỆU.
 *
 * Người dùng nông thôn thường trả tiền theo dung lượng và sóng yếu. Ảnh vệ tinh
 * ~0,5 MB mỗi tấm là gánh nặng thật. Tôn trọng cờ Save-Data của trình duyệt
 * (bật trong Chrome Android "Lite mode", hoặc khi mạng chậm): khi bật, hoãn tải
 * ảnh nặng sau một cú chạm thay vì tự tải.
 *
 * Người dùng cũng tự bật/tắt được (localStorage), ghi đè phát hiện tự động.
 */
import { useEffect, useState } from "react";

const KEY = "tt_datasaver";

export function isDataSaver(): boolean {
  if (typeof window === "undefined") return false;
  try {
    const manual = localStorage.getItem(KEY);
    if (manual === "1") return true;
    if (manual === "0") return false;
  } catch { /* */ }
  // Tự phát hiện: cờ Save-Data hoặc mạng 2g/chậm.
  const c = (navigator as unknown as { connection?: { saveData?: boolean; effectiveType?: string } }).connection;
  if (!c) return false;
  return Boolean(c.saveData) || /(^|-)2g$/.test(c.effectiveType ?? "");
}

export function setDataSaver(on: boolean | null): void {
  try {
    if (on === null) localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, on ? "1" : "0");
  } catch { /* */ }
}

/**
 * P2 — công tắc TỰ TAY, đặt cạnh LangToggle. Trước đây isDataSaver/setDataSaver
 * đã có sẵn trong lib này nhưng KHÔNG có chỗ nào trong giao diện gọi
 * setDataSaver() — công tắc tồn tại trong code nhưng người dùng không bấm được.
 */
export function DataSaverToggle() {
  const [on, setOn] = useState(false);
  useEffect(() => { setOn(isDataSaver()); }, []);

  function toggle() {
    const next = !on;
    setDataSaver(next);
    setOn(next);
  }

  return (
    <button
      className={`ds-toggle${on ? " on" : ""}`}
      onClick={toggle}
      aria-pressed={on}
      title={on
        ? "Tiết kiệm dữ liệu đang BẬT — ảnh vệ tinh & mục nặng chờ bạn bấm mới tải"
        : "Bật tiết kiệm dữ liệu — hoãn tải ảnh vệ tinh & mục nặng tới khi bạn bấm"}
    >
      📶 {on ? "Tiết kiệm: BẬT" : "Tiết kiệm dữ liệu"}
    </button>
  );
}
