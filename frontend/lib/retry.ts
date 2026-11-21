// ĐỌC (GET) CÓ THỬ LẠI. Máy chủ miễn phí khởi động lại, hoặc proxy Render trả 502–504 KHÔNG kèm header CORS, thì
// trình duyệt chỉ thấy "Failed to fetch" — E2E production 21/10/2026: 32 lỗi CORS trong một phút, danh sách công cụ
// trống, người xem không biết làm gì. GET chỉ đọc nên lặp lại an toàn.
//
// CHỜ MÁY CHỦ THỨC (kiểm A–Z 21/11/2026, P0-2): Render miễn phí ngủ sau 15 phút vắng và thức mất 30–60 giây. Bản cũ chỉ
// thử lại GET sau 2 s rồi 5 s, nên người được mời bấm "Đối chiếu với số đo" (POST) lần đầu là gặp ngay "Không kết nối
// được máy chủ". Nay: lịch chờ ~75 giây, và trong lúc chờ phát sự kiện WAKE_EVENT để giao diện hiện "Đang đánh thức máy
// chủ miễn phí…". POST CHỈ TÍNH TOÁN (danh sách COMPUTE_POST — đã soát phía máy chủ: không ghi CSDL) dùng cùng lịch; POST
// GHI dữ liệu vẫn KHÔNG thử lại — gửi lại có thể làm hai lần.

export const WAKE_MS = [3000, 5000, 7000, 10000, 12000, 15000, 15000];   // tổng chờ 67 s + thời gian các lượt gọi ≈ 75 s
export const RETRY_MS = WAKE_MS;
// Trần TỔNG thời gian (cả lúc chờ lẫn lúc mỗi lần gọi treo tới timeoutMs) — sổ điểm cắt mỗi lần 25 s, không có trần thì máy
// chủ treo hẳn sẽ bắt người dùng chờ 8 × 25 s + 67 s ≈ 4,5 phút mới thấy báo lỗi.
export const MAX_TOTAL_MS = 90_000;
const RETRY_STATUS = [502, 503, 504];
export const WAKE_EVENT = "terratwin:waking";

export class NetworkError extends Error {}

export function offlineMessage(lang: string): string {
  return lang === "en"
    ? "Can't reach the server — it may be restarting (the free tier sleeps when idle). Try again in a few seconds."
    : "Không kết nối được máy chủ — có thể đang khởi động lại (bản miễn phí ngủ khi vắng). Thử lại sau ít giây.";
}

export function wakingMessage(lang: string): string {
  return lang === "en"
    ? "Waking the free server… usually 30–60 seconds. Your request will continue by itself."
    : "Đang đánh thức máy chủ miễn phí… thường 30–60 giây. Yêu cầu của bạn sẽ tự chạy tiếp.";
}

// POST chỉ tính toán, không ghi — gửi lại an toàn. Đường dẫn kết thúc bằng "/" là tiền tố (/api/assess/flood…), còn lại
// khớp đúng (để /api/genome/warm, /api/anomaly-ml… không lọt theo tiền tố ngoài ý muốn).
export const COMPUTE_POST = [
  "/api/listing/check", "/api/scan", "/api/assess/", "/api/terrascore", "/api/passport", "/api/compare", "/api/contrast",
  "/api/copilot", "/api/whatif/", "/api/explain/", "/api/goalseek/", "/api/timemachine/", "/api/heatmap/",
  "/api/probability/", "/api/timelapse/", "/api/future/", "/api/anomaly", "/api/anomaly-ml", "/api/genome", "/api/design",
  "/api/plan",
  // xếp việc đọc radar, nhưng máy chủ tự gộp việc trùng cùng thửa (routes_water.water_history_start) → gửi lại an toàn
  "/api/water/history",
];

export function isComputePost(url: string, method?: string): boolean {
  if ((method || "GET").toUpperCase() !== "POST") return false;
  let path: string;
  try { path = new URL(url, "http://x").pathname; } catch { return false; }
  return COMPUTE_POST.some((p) => (p.endsWith("/") ? path.startsWith(p) && path.length > p.length : path === p));
}

// Đếm số yêu cầu đang chờ máy chủ thức — nhiều yêu cầu cùng chờ thì thông báo chỉ tắt khi yêu cầu CUỐI xong.
let waiting = 0;
export function wakingCount(): number { return waiting; }
function notify(delta: number) {
  waiting = Math.max(0, waiting + delta);
  try {
    if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent(WAKE_EVENT, { detail: waiting }));
  } catch { /* không có window (Node test) */ }
}

// timeoutMs (kiểm 18/11/2026): khi Render đang đánh thức máy chủ, yêu cầu có thể TREO cả phút mà không lỗi — ô sổ điểm
// kẹt "Đang tải…" mãi. Có timeoutMs thì mỗi lần thử bị cắt sau ngần ấy và tính như lỗi mạng (thử lại, hết lượt thì báo).
type Opt = { fetchFn?: typeof fetch; sleep?: (ms: number) => Promise<void>; lang?: string; timeoutMs?: number;
  schedule?: number[]; now?: () => number };

async function once(f: typeof fetch, url: string, init: RequestInit | undefined, timeoutMs?: number): Promise<Response> {
  if (!timeoutMs) return f(url, init);
  const ctl = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; ctl.abort(); }, timeoutMs);
  const outer = init?.signal;
  const relay = () => ctl.abort();
  if (outer) { if (outer.aborted) ctl.abort(); else outer.addEventListener("abort", relay); }
  try {
    return await f(url, { ...init, signal: ctl.signal });
  } catch (e) {
    if (timedOut) throw new TypeError("timeout");          // hết giờ = lỗi mạng (thử lại), KHÔNG phải người gọi huỷ
    throw e;
  } finally {
    clearTimeout(timer);
    outer?.removeEventListener("abort", relay);
  }
}

// 502–504 của PROXY (trang HTML của Render lúc máy chủ đang thức) thì chờ; 503 JSON là lỗi THẬT của chính máy chủ
// (vd. "mô hình chưa bật") — trả ngay, không bắt người dùng chờ 75 giây để rồi vẫn thấy đúng lỗi đó.
function proxyHiccup(r: Response): boolean {
  return RETRY_STATUS.includes(r.status) && !(r.headers.get("content-type") || "").includes("application/json");
}

export async function getRetry(url: string, init?: RequestInit, opt: Opt = {}): Promise<Response> {
  const f = opt.fetchFn ?? fetch;
  const sleep = opt.sleep ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)));
  const plan = opt.schedule ?? WAKE_MS;
  const now = opt.now ?? Date.now;
  const t0 = now();
  let counted = false;
  try {
    for (let i = 0; ; i++) {
      let r: Response | null = null;
      try {
        r = await once(f, url, init, opt.timeoutMs);
      } catch (e) {
        if ((e as Error)?.name === "AbortError") throw e;      // người gọi tự huỷ — không thử lại
      }
      // hết lượt, hoặc chờ thêm + một lần gọi nữa (có thể treo tới timeoutMs) sẽ vượt trần
      const het = i >= plan.length || now() - t0 + plan[i] + (opt.timeoutMs ?? 0) > MAX_TOTAL_MS;
      if (r && (!proxyHiccup(r) || het)) return r;
      if (het) throw new NetworkError(offlineMessage(opt.lang ?? "vi"));
      if (!counted) { counted = true; notify(+1); }
      await sleep(plan[i]);
    }
  } finally {
    if (counted) notify(-1);
  }
}

/** Cùng lịch chờ cho POST chỉ tính toán (isComputePost). Gọi với POST ghi dữ liệu là lỗi lập trình — từ chối luôn. */
export async function computeRetry(url: string, init: RequestInit, opt: Opt = {}): Promise<Response> {
  if (!isComputePost(url, init.method)) throw new Error(`computeRetry chỉ dùng cho POST tính toán: ${url}`);
  return getRetry(url, init, opt);
}
