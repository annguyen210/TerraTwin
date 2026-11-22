// Có ĐẾM sự kiện phễu (trackEvent → /api/events) hay không — kiểm A–Z lần 2 (22/11/2026): phễu bị thổi phồng bởi máy chạy
// thử (E2E, rà soát trang tự động) và chính quản trị viên. Bỏ qua khi:
//   · trình duyệt tự động (navigator.webdriver === true — Playwright, Selenium);
//   · có cờ E2E: localStorage "tt_e2e" hoặc ?e2e=1 trên URL;
//   · đang đăng nhập bằng tài khoản quản trị (cờ "tt_admin" ghi lúc fetchMe trả role=admin).
// Hàm thuần — nhận môi trường qua tham số để test được bằng Node.
export type TrackEnv = { webdriver?: boolean; search?: string; flags?: Record<string, string | null> };

export function shouldTrack(env: TrackEnv): boolean {
  if (env.webdriver) return false;
  if (/(^|[?&])e2e=1(&|$)/.test(env.search ?? "")) return false;
  const f = env.flags ?? {};
  if (f["tt_e2e"]) return false;
  if (f["tt_admin"]) return false;
  return true;
}

/** Môi trường thật của trình duyệt (bọc try: localStorage có thể bị chặn). */
export function browserTrackEnv(): TrackEnv {
  const get = (k: string) => { try { return localStorage.getItem(k); } catch { return null; } };
  return {
    webdriver: typeof navigator !== "undefined" && navigator.webdriver === true,
    search: typeof location !== "undefined" ? location.search : "",
    flags: { tt_e2e: get("tt_e2e"), tt_admin: get("tt_admin") },
  };
}

/** Ghi / xoá cờ quản trị sau khi biết vai trò (gọi từ fetchMe). */
export function rememberRole(role: string | undefined | null): void {
  try {
    if (role === "admin") localStorage.setItem("tt_admin", "1");
    else localStorage.removeItem("tt_admin");
  } catch { /* localStorage bị chặn — không sao */ }
}
