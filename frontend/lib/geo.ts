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

export type ParsedCoord = { lat: number; lon: number; swapped: boolean; source?: string };

/** Chuỗi trông như một đường link (có giao thức, www., hoặc tên miền bản đồ quen). */
export function looksLikeUrl(input: string): boolean {
  const s = input.trim();
  return /^(https?:\/\/|www\.)\S+$/i.test(s) || /^(maps\.app\.goo\.gl|goo\.gl|maps\.google\.|google\.[a-z.]+\/maps|(www\.)?openstreetmap\.org)\S*$/i.test(s);
}

export type MapLink = { lat: number; lon: number; source: string } | { short: true } | null;

const NUM = "(-?\\d{1,3}(?:\\.\\d+)?)";
// Thứ tự = độ ưu tiên: GHIM trước tâm khung nhìn. Google "địa điểm" có cả ghim (!3d…!4d…) lẫn tâm (@…); OSM có ghim
// (mlat/mlon) lẫn tâm (#map=…). Ghim mới là chỗ người ta chọn.
const MAP_PATTERNS: [RegExp, string][] = [
  [new RegExp(`!3d${NUM}!4d${NUM}`), "Google Maps"],
  [new RegExp(`[?&]mlat=${NUM}&mlon=${NUM}`), "OpenStreetMap"],
  [new RegExp(`[?&](?:q|query|ll|sll|center|destination|daddr)=(?:loc:)?\\s*${NUM}\\s*,\\s*\\+?${NUM}`), "link bản đồ"],
  [new RegExp(`/search/${NUM}\\s*,\\s*\\+?${NUM}`), "Google Maps"],
  [new RegExp(`/place/${NUM}\\s*,\\s*\\+?${NUM}`), "Google Maps"],
  [new RegExp(`#map=\\d+(?:\\.\\d+)?/${NUM}/${NUM}`), "OpenStreetMap"],
  [new RegExp(`@${NUM},${NUM}`), "Google Maps"],
];

/**
 * Toạ độ nằm TRONG một link bản đồ (Google Maps, OpenStreetMap, Apple Maps). Không tải trang nào.
 * Lỗi thật 17/10/2026: link "địa điểm" Google Maps (…/place/Hu%E1%BA%BF/@16.46,107.59…!3d16.4498!4d107.5623) bị cách
 * đọc số chung đọc ra (1, 1) vì "%E1"; link OpenStreetMap #map=17/16.57/107.49 ra (17, 16.57).
 * Link rút gọn (maps.app.goo.gl) không chứa toạ độ → { short: true } để báo người dùng cách lấy.
 */
export function parseMapLink(input: string): MapLink {
  let s = input.trim();
  try { s = decodeURIComponent(s); } catch { /* giữ nguyên chuỗi nếu mã hoá hỏng */ }
  for (const [re, source] of MAP_PATTERNS) {
    const m = re.exec(s);
    if (m) {
      const lat = parseFloat(m[1]);
      const lon = parseFloat(m[2]);
      if (Number.isFinite(lat) && Number.isFinite(lon)) return { lat, lon, source };
    }
  }
  if (/(maps\.app\.goo\.gl|goo\.gl\/maps)/i.test(s)) return { short: true };
  return null;
}

/** Trang tin rao bất động sản: TerraTwin KHÔNG tải nội dung các trang này (điều khoản + rủi ro pháp lý). */
export function isListingSite(input: string): boolean {
  return /(batdongsan\.com\.vn|chotot\.com|nhatot\.com|alonhadat\.com\.vn|muaban\.net|homedy\.com|mogi\.vn|nhadat24h\.net|nhadat247\.com\.vn|rongbay\.com|dothi\.net|facebook\.com\/(groups|marketplace))/i.test(input);
}

/**
 * Tìm toạ độ trong một đoạn chữ dài (vd nội dung tin đăng có "Toạ độ: 16.4637, 107.5909" hoặc kèm link Google Maps).
 * Chỉ nhận cặp số có ≥ 3 chữ số thập phân nằm trong Việt Nam — tránh bắt nhầm giá tiền, diện tích, số điện thoại.
 */
export function findCoordInText(text: string): ParsedCoord | null {
  for (const w of text.split(/\s+/)) {
    if (/maps|goo\.gl|openstreetmap/i.test(w)) {
      const m = parseMapLink(w);
      if (m && "lat" in m && inVietnam(m.lat, m.lon)) return { lat: m.lat, lon: m.lon, swapped: false, source: m.source };
    }
  }
  const re = /(-?\d{1,3}\.\d{3,})\s*[,;]?\s+(-?\d{1,3}\.\d{3,})|(-?\d{1,3}\.\d{3,}),(-?\d{1,3}\.\d{3,})/g;
  for (const m of text.matchAll(re)) {
    const a = parseFloat(m[1] ?? m[3]);
    const b = parseFloat(m[2] ?? m[4]);
    if (inVietnam(a, b)) return { lat: a, lon: b, swapped: false, source: "trong nội dung" };
    if (inVietnam(b, a)) return { lat: b, lon: a, swapped: true, source: "trong nội dung" };
  }
  return null;
}

/**
 * Đọc toạ độ người dùng dán. Trả null nếu không đọc được 2 số.
 *  · "21.1857, 106.0738" · "21.1857 106.0738" · "21.1857°N 106.0738°E"
 *  · độ-phút-giây Google Maps: 21°11'08.6"N 106°04'25.9"E
 *  · dấu phẩy thập phân kiểu Việt Nam: "21,1857; 106,0738" hoặc "21,1857 106,0738"
 *  · dán ngược (kinh độ trước) → tự hoán đổi nếu chỉ thứ tự ngược mới nằm trong Việt Nam.
 */
export function parseCoord(input: string): ParsedCoord | null {
  if (looksLikeUrl(input)) {                       // link: chỉ đọc toạ độ theo mẫu link, KHÔNG đọc số đại khái
    const m = parseMapLink(input);
    if (!m || !("lat" in m)) return null;
    if (!inVietnam(m.lat, m.lon) && inVietnam(m.lon, m.lat)) return { lat: m.lon, lon: m.lat, swapped: true, source: m.source };
    return { lat: m.lat, lon: m.lon, swapped: false, source: m.source };
  }
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

// geo.ts giữ THUẦN (không import api.ts) để test chạy thẳng bằng Node (scripts/test-geo.mjs). Cùng khoá với curLang().
function isEn(): boolean {
  try { return typeof window !== "undefined" && localStorage.getItem("terratwin_lang") === "en"; } catch { return false; }
}

/** Câu giải thích khi một toạ độ nằm ngoài Việt Nam — nói rõ toạ độ đã nhận. */
export function outsideMessage(lat: number, lon: number, source: "gps" | "other" = "other"): string {
  const at = `${lat.toFixed(4)}, ${lon.toFixed(4)}`;
  const en = isEn();
  if (source === "gps") {
    return en
      ? `Your browser reports ${at} — outside Viet Nam. Computers without GPS GUESS the location from the network (Wi-Fi, IP, VPN, school/office network) and can be hundreds of km off. `
        + `Type a commune, paste coordinates from Google Maps, or open TerraTwin on a phone with GPS.`
      : `Trình duyệt báo bạn đang ở ${at} — ngoài Việt Nam. Máy tính không có GPS thường ĐOÁN vị trí theo mạng (Wi-Fi, IP, VPN, mạng trường/công ty) nên có thể lệch hàng trăm km. `
        + `Hãy gõ tên xã, dán toạ độ từ Google Maps, hoặc mở TerraTwin trên điện thoại có GPS.`;
  }
  return en
    ? `Coordinates ${at} are outside Viet Nam (latitude 7.5–24, longitude 101.5–115). Check the latitude/longitude order.`
    : `Toạ độ ${at} nằm ngoài Việt Nam (vĩ độ 7.5–24, kinh độ 101.5–115). Kiểm tra lại thứ tự vĩ độ, kinh độ.`;
}
