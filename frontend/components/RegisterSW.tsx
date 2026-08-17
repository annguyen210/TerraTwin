"use client";

import { useEffect } from "react";

/** Đăng ký service worker để cài được lên màn hình chính (PWA).
 *
 *  Chỉ chạy ở production: khi `next dev`, service worker sẽ cache nhầm các
 *  chunk HMR và làm hỏng hot-reload.
 */
export default function RegisterSW() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production") return;
    if (!("serviceWorker" in navigator)) return;
    const onLoad = () => {
      navigator.serviceWorker.register("/sw.js").catch(() => {
        /* PWA là tiện ích thêm — hỏng thì app vẫn chạy bình thường */
      });
    };
    window.addEventListener("load", onLoad);
    return () => window.removeEventListener("load", onLoad);
  }, []);
  return null;
}
