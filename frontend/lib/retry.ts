// ĐỌC (GET) CÓ THỬ LẠI. Máy chủ miễn phí khởi động lại, hoặc proxy Render trả 502–504 KHÔNG kèm header CORS, thì
// trình duyệt chỉ thấy "Failed to fetch" — E2E production 21/10/2026: 32 lỗi CORS trong một phút, danh sách công cụ
// trống, người xem không biết làm gì. GET chỉ đọc nên lặp lại an toàn: thử thêm 2 lần (sau 2 s, 5 s) rồi mới báo, bằng
// câu người đọc hiểu được. Lệnh ghi (POST…) KHÔNG đi qua đây — gửi lại có thể làm hai lần.

export const RETRY_MS = [2000, 5000];
const RETRY_STATUS = [502, 503, 504];

export class NetworkError extends Error {}

export function offlineMessage(lang: string): string {
  return lang === "en"
    ? "Can't reach the server — it may be restarting (the free tier sleeps when idle). Try again in a few seconds."
    : "Không kết nối được máy chủ — có thể đang khởi động lại (bản miễn phí ngủ khi vắng). Thử lại sau ít giây.";
}

// timeoutMs (kiểm 18/11/2026): khi Render đang đánh thức máy chủ, yêu cầu có thể TREO cả phút mà không lỗi — ô sổ điểm
// kẹt "Đang tải…" mãi. Có timeoutMs thì mỗi lần thử bị cắt sau ngần ấy và tính như lỗi mạng (thử lại, hết lượt thì báo).
type Opt = { fetchFn?: typeof fetch; sleep?: (ms: number) => Promise<void>; lang?: string; timeoutMs?: number };

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

export async function getRetry(url: string, init?: RequestInit, opt: Opt = {}): Promise<Response> {
  const f = opt.fetchFn ?? fetch;
  const sleep = opt.sleep ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)));
  for (let i = 0; ; i++) {
    let r: Response | null = null;
    try {
      r = await once(f, url, init, opt.timeoutMs);
    } catch (e) {
      if ((e as Error)?.name === "AbortError") throw e;      // người gọi tự huỷ — không thử lại
      if (i >= RETRY_MS.length) throw new NetworkError(offlineMessage(opt.lang ?? "vi"));
    }
    if (r && (!RETRY_STATUS.includes(r.status) || i >= RETRY_MS.length)) return r;
    await sleep(RETRY_MS[i]);
  }
}
