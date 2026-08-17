/* TerraTwin service worker — chỉ đủ để cài được lên màn hình chính.

   NGUYÊN TẮC: KHÔNG cache phản hồi /api/. Đây là ứng dụng cảnh báo thiên tai;
   phục vụ lại một cảnh báo cũ từ cache còn nguy hiểm hơn là báo lỗi mạng.
   Chỉ cache vỏ ứng dụng (tài nguyên tĩnh) để mở nhanh và hiện được trang
   offline tử tế.
*/
const CACHE = "terratwin-shell-v1";
const OFFLINE_URL = "/offline.html";

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((c) => c.addAll([OFFLINE_URL, "/manifest.webmanifest"])),
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))),
    ),
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);

  // Dữ liệu cảnh báo: LUÔN đi mạng, không bao giờ lấy từ cache.
  if (url.pathname.startsWith("/api/")) return;

  // Điều hướng trang: thử mạng trước, hỏng thì hiện trang offline.
  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req).catch(() => caches.match(OFFLINE_URL)),
    );
    return;
  }

  // Tài nguyên tĩnh cùng nguồn: cache-first cho nhẹ mạng.
  if (url.origin === self.location.origin) {
    event.respondWith(
      caches.match(req).then(
        (hit) =>
          hit ||
          fetch(req).then((res) => {
            if (res.ok && res.type === "basic") {
              const copy = res.clone();
              caches.open(CACHE).then((c) => c.put(req, copy));
            }
            return res;
          }),
      ),
    );
  }
});
