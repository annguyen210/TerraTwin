/**
 * MapLibre dùng chung cho mọi bản đồ: trỏ web worker về /public/maplibre (xem
 * scripts/copy-maplibre-worker.mjs). Import maplibregl TỪ ĐÂY, không trực tiếp.
 */
import * as maplibregl from "maplibre-gl";

if (typeof window !== "undefined") {
  maplibregl.setWorkerUrl("/maplibre/maplibre-gl-worker.mjs");
}

export default maplibregl;

// Bản đồ đã bắn "load" (nguồn/lớp tự thêm lúc nạp đã có). KHÔNG dùng map.isStyleLoaded() để hỏi việc này:
// ở MapLibre 6 nó trả false cả khi chỉ còn ô ảnh nền đang tải (Style.loaded() kiểm mọi nguồn), mà "load" chỉ
// bắn MỘT lần — nên `isStyleLoaded() ? fn() : map.once("load", fn)` sau lần nạp đầu không bao giờ chạy fn.
// Kiểm 24/11/2026: lớp radar "Ảnh radar ngày 12/9/2024" báo đã hiện nhưng bản đồ trống, khung thửa mất.
const READY = new WeakSet<object>();

/** Gọi NGAY sau `new maplibregl.Map(...)`, trước mọi map.on("load"). */
export function trackReady(map: maplibregl.Map): void {
  map.once("load", () => READY.add(map));
}

/** Chạy fn khi bản đồ đã nạp xong kiểu (bất kể ô ảnh nền còn đang tải hay không). */
export function whenStyleReady(map: maplibregl.Map, fn: () => void): void {
  if (READY.has(map)) fn();
  else map.once("load", fn);
}
