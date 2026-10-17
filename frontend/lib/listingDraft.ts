/**
 * Nội dung tin đăng người dùng dán ở trang đầu → giữ TRONG TRÌNH DUYỆT (sessionStorage) để ô "Kiểm chứng tin đăng"
 * điền sẵn khi họ chọn thửa. Không gửi lên máy chủ cho tới khi họ bấm kiểm. Mất phiên / chặn lưu trữ thì thôi.
 */
const KEY = "tt-listing-draft";

export function saveListingDraft(text: string): void {
  try { sessionStorage.setItem(KEY, text.slice(0, 5000)); } catch { /* chế độ riêng tư / bị chặn */ }
}

export function takeListingDraft(): string {
  try { return sessionStorage.getItem(KEY) ?? ""; } catch { return ""; }
}

export function clearListingDraft(): void {
  try { sessionStorage.removeItem(KEY); } catch { /* bỏ qua */ }
}
