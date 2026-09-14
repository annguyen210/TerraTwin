"use client";

/**
 * M1 — bật WEB PUSH ở phía trình duyệt.
 *
 * Lấy khoá công khai VAPID từ máy chủ (không hardcode), xin quyền thông báo,
 * đăng ký PushManager, rồi gửi subscription về máy chủ. Máy chủ đẩy cảnh báo
 * vào đây kể cả khi app đóng. Không cần nhà cung cấp nào — VAPID tự sinh.
 */
import { getPushKey, subscribePush } from "@/lib/api";

function urlB64ToBytes(base64: string): ArrayBuffer {
  const pad = "=".repeat((4 - (base64.length % 4)) % 4);
  const b64 = (base64 + pad).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(b64);
  const buf = new ArrayBuffer(raw.length);
  const view = new Uint8Array(buf);
  for (let i = 0; i < raw.length; i++) view[i] = raw.charCodeAt(i);
  return buf;
}

export function pushSupported(): boolean {
  return typeof window !== "undefined"
    && "serviceWorker" in navigator
    && "PushManager" in window
    && "Notification" in window;
}

/** Trả trạng thái: "on" đã bật · "unsupported" · "denied" · "unconfigured" · "off". */
export async function pushState(): Promise<string> {
  if (!pushSupported()) return "unsupported";
  if (Notification.permission === "denied") return "denied";
  const key = await getPushKey().catch(() => null);
  if (!key || !key.configured) return "unconfigured";
  const reg = await navigator.serviceWorker.getRegistration();
  const sub = reg ? await reg.pushManager.getSubscription() : null;
  return sub ? "on" : "off";
}

/** Bật push. Trả "on" nếu thành công, hoặc mã lỗi để giao diện giải thích. */
export async function enablePush(): Promise<string> {
  if (!pushSupported()) return "unsupported";
  const key = await getPushKey().catch(() => null);
  if (!key || !key.configured || !key.public_key) return "unconfigured";

  const perm = await Notification.requestPermission();
  if (perm !== "granted") return "denied";

  const reg = await navigator.serviceWorker.register("/sw.js");
  await navigator.serviceWorker.ready;
  let sub = await reg.pushManager.getSubscription();
  if (!sub) {
    sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlB64ToBytes(key.public_key),
    });
  }
  await subscribePush(sub.toJSON());
  return "on";
}
