// MapLibre 6 chạy web worker dưới dạng MODULE ES riêng (maplibre-gl-worker.mjs, kéo theo
// maplibre-gl-shared.mjs). Webpack không phân giải được URL worker đó ("Worker failed to
// load") → chép hai tệp vào public/maplibre/ sau mỗi lần cài, và lib/maplibre.ts trỏ
// setWorkerUrl về đó. Chạy tự động qua "postinstall" — luôn khớp đúng phiên bản đã cài.
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const src = join(root, "node_modules", "maplibre-gl", "dist");
const dst = join(root, "public", "maplibre");
mkdirSync(dst, { recursive: true });
for (const f of ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"]) copyFileSync(join(src, f), join(dst, f));
console.log("maplibre worker → public/maplibre/");
