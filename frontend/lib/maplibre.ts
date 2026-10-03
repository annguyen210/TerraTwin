/**
 * MapLibre dùng chung cho mọi bản đồ: trỏ web worker về /public/maplibre (xem
 * scripts/copy-maplibre-worker.mjs). Import maplibregl TỪ ĐÂY, không trực tiếp.
 */
import * as maplibregl from "maplibre-gl";

if (typeof window !== "undefined") {
  maplibregl.setWorkerUrl("/maplibre/maplibre-gl-worker.mjs");
}

export default maplibregl;
