// onnxruntime-web (WebAssembly) cho kiểm ảnh ruộng NGAY TRÊN MÁY (25/11/2026, public/fieldcheck.js) — chép runtime vào
// public/ort/ sau mỗi lần cài, cùng cách copy-maplibre-worker.mjs: tự host (chạy được khi mất mạng, không phụ thuộc CDN),
// luôn khớp đúng phiên bản đã cài. Chỉ bản WASM SIMD (không JSEP/WebGPU) để nhẹ: ~11 MB, tải khi người dùng bấm lần đầu.
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const src = join(root, "node_modules", "onnxruntime-web", "dist");
const dst = join(root, "public", "ort");
mkdirSync(dst, { recursive: true });
for (const f of ["ort.wasm.min.js", "ort-wasm-simd-threaded.mjs", "ort-wasm-simd-threaded.wasm"]) copyFileSync(join(src, f), join(dst, f));
console.log("onnxruntime-web → public/ort/");
