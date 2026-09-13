/* TerraTwin service worker — chỉ đủ để cài được lên màn hình chính.

   NGUYÊN TẮC: KHÔNG cache phản hồi /api/. Đây là ứng dụng cảnh báo thiên tai;
   phục vụ lại một cảnh báo cũ từ cache còn nguy hiểm hơn là báo lỗi mạng.
   Chỉ cache vỏ ứng dụng (tài nguyên tĩnh) để mở nhanh và hiện được trang
   offline tử tế.
*/
const CACHE = "terratwin-shell-v1";
const OFFLINE_URL = "/offline.html";
// P3 — đệm TILE bản đồ (cross-origin, ArcGIS World Imagery). Người dùng mở lại
// quanh thửa đã lưu thì bản đồ hiện ngay, không tải lại từng ô — quan trọng với
// sóng yếu. Bucket riêng, giữ trần ~300 ô để không phình vô hạn.
const TILE_CACHE = "terratwin-tiles-v1";
const TILE_MAX = 300;
const TILE_HOSTS = ["server.arcgisonline.com"];

async function _cap(cacheName, max) {
  const c = await caches.open(cacheName);
  const keys = await c.keys();
  // FIFO: xoá cái cũ nhất khi vượt trần.
  for (let i = 0; i < keys.length - max; i++) await c.delete(keys[i]);
}

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((c) => c.addAll([OFFLINE_URL, "/manifest.webmanifest"])),
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  const keep = new Set([CACHE, TILE_CACHE]);
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => !keep.has(k)).map((k) => caches.delete(k))),
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

  // P3 — TILE bản đồ: cache-first, bucket riêng có trần. Ô đã xem hiện ngay khi
  // mở lại; ô mới vẫn tải mạng rồi lưu. Không đụng nguyên tắc "không cache /api/".
  if (TILE_HOSTS.includes(url.hostname)) {
    event.respondWith(
      caches.open(TILE_CACHE).then((c) =>
        c.match(req).then((hit) =>
          hit ||
          fetch(req).then((res) => {
            if (res.ok) { c.put(req, res.clone()); _cap(TILE_CACHE, TILE_MAX); }
            return res;
          }).catch(() => hit),
        ),
      ),
    );
    return;
  }

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
