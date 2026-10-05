/**
 * Toạ độ: kiểm khung Việt Nam và đọc mọi kiểu người dùng hay dán.
 *
 * Khung bao KHỚP máy chủ (backend/app/schemas.py): vĩ độ 7.5–24, kinh độ 101.5–115.
 * Mọi đường đưa toạ độ vào khu làm việc (ô dán, nút GPS, tìm địa danh, bản đồ, đường
 * link) đều phải qua inVietnam() trước khi gọi API — lỗi thật 4/10/2026: trình duyệt
 * máy tính đoán vị trí theo mạng (Wi-Fi/IP/VPN) ra Singapore, toạ độ đi thẳng tới máy
 * chủ và người dùng ở FPT Bắc Ninh nhận câu "Vĩ độ phải trong khoảng 7.5–24".
 */

export const VN = { latMin: 7.5, latMax: 24, lonMin: 101.5, lonMax: 115 };

export function inVietnam(lat: number, lon: number): boolean {
  return Number.isFinite(lat) && Number.isFinite(lon)
    && lat >= VN.latMin && lat <= VN.latMax && lon >= VN.lonMin && lon <= VN.lonMax;
}

/** Độ-phút-giây → độ thập phân. Nhận 21°11'08.6"N, 21° 11' 8.6'' N, 21 11 8.6 N… */
function dms(deg: string, min?: string, sec?: string, hemi?: string): number {
  const v = Math.abs(parseFloat(deg)) + (min ? parseFloat(min) / 60 : 0) + (sec ? parseFloat(sec) / 3600 : 0);
  const neg = deg.trim().startsWith("-") || /[SWT]/i.test(hemi ?? "");   // T = Tây (VN)
  return neg ? -v : v;
}

export type ParsedCoord = { lat: number; lon: number; swapped: boolean };

/**
 * Đọc toạ độ người dùng dán. Trả null nếu không đọc được 2 số.
 *  · "21.1857, 106.0738" · "21.1857 106.0738" · "21.1857°N 106.0738°E"
 *  · độ-phút-giây Google Maps: 21°11'08.6"N 106°04'25.9"E
 *  · dấu phẩy thập phân kiểu Việt Nam: "21,1857; 106,0738" hoặc "21,1857 106,0738"
 *  · dán ngược (kinh độ trước) → tự hoán đổi nếu chỉ thứ tự ngược mới nằm trong Việt Nam.
 */
export function parseCoord(input: string): ParsedCoord | null {
  const s = input.trim().replace(/[″”“]/g, '"').replace(/[′’‘]/g, "'");
  let a: number | null = null;
  let b: number | null = null;

  const DMS = /(-?\d+(?:[.,]\d+)?)\s*[°º]\s*(?:(\d+(?:[.,]\d+)?)\s*['m]\s*)?(?:(\d+(?:[.,]\d+)?)\s*(?:"|''|s)\s*)?([NSEWBĐT])?/gi;
  const parts = [...s.matchAll(DMS)];
  if (parts.length >= 2) {
    const n = (x?: string) => (x ? x.replace(",", ".") : undefined);
    const v = parts.slice(0, 2).map((m) => ({ val: dms(n(m[1])!, n(m[2]), n(m[3]), m[4]), h: (m[4] ?? "").toUpperCase() }));
    // Bán cầu nói rõ thì theo bán cầu: E/W/Đ/T là kinh độ.
    const isLon = (h: string) => ["E", "W", "Đ", "T"].includes(h);
    if (isLon(v[0].h) && !isLon(v[1].h)) { a = v[1].val; b = v[0].val; } else { a = v[0].val; b = v[1].val; }
  } else {
    const commaDecimal = /^\s*(-?\d+),(\d+)\s*[;\s]\s*(-?\d+),(\d+)\s*$/.exec(s)
      ?? /^\s*(-?\d+),(\d+)\s*,\s+(-?\d+),(\d+)\s*$/.exec(s);
    if (commaDecimal) {
      a = parseFloat(`${commaDecimal[1]}.${commaDecimal[2]}`);
      b = parseFloat(`${commaDecimal[3]}.${commaDecimal[4]}`);
    } else {
      const nums = s.replace(/[^\d.,\-\s]/g, " ").match(/-?\d+(\.\d+)?/g);
      if (!nums || nums.length < 2) return null;
      a = parseFloat(nums[0]);
      b = parseFloat(nums[1]);
    }
  }
  if (a == null || b == null || !Number.isFinite(a) || !Number.isFinite(b)) return null;
  if (!inVietnam(a, b) && inVietnam(b, a)) return { lat: b, lon: a, swapped: true };
  return { lat: a, lon: b, swapped: false };
}

/** Câu giải thích khi một toạ độ nằm ngoài Việt Nam — nói rõ toạ độ đã nhận. */
export function outsideMessage(lat: number, lon: number, source: "gps" | "other" = "other"): string {
  const at = `${lat.toFixed(4)}, ${lon.toFixed(4)}`;
  if (source === "gps") {
    return `Trình duyệt báo bạn đang ở ${at} — ngoài Việt Nam. Máy tính không có GPS thường ĐOÁN vị trí theo mạng (Wi-Fi, IP, VPN, mạng trường/công ty) nên có thể lệch hàng trăm km. ` +
      `Hãy gõ tên xã, dán toạ độ từ Google Maps, hoặc mở TerraTwin trên điện thoại có GPS.`;
  }
  return `Toạ độ ${at} nằm ngoài Việt Nam (vĩ độ 7.5–24, kinh độ 101.5–115). Kiểm tra lại thứ tự vĩ độ, kinh độ.`;
}
