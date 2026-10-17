// Test đọc toạ độ (lib/geo.ts) — chạy thẳng bằng Node 22 (bỏ kiểu TypeScript), không cần thư viện test.
// Lỗi thật 17/10/2026: link "địa điểm" Google Maps đọc ra (1, 1), link OpenStreetMap ra (17, 16.57).
import assert from "node:assert/strict";
import { findCoordInText, isListingSite, looksLikeUrl, parseCoord, parseMapLink } from "../lib/geo.ts";

const r4 = (c) => (c ? `${+c.lat.toFixed(4)},${+c.lon.toFixed(4)}` : null);
const cases = [
  ["https://www.google.com/maps/place/Hu%E1%BA%BF,+Th%E1%BB%ABa+Thi%C3%AAn+Hu%E1%BA%BF/@16.4637,107.5909,15z/data=!3m1!4b1!4m6!3m5!1s0x3141a115e1866a41:0x2d6d1e4a54e0!8m2!3d16.4498!4d107.5623",
   "16.4498,107.5623", "ghim địa điểm, không phải tâm khung nhìn"],
  ["https://maps.google.com/?q=10.0452,105.7469", "10.0452,105.7469", "?q="],
  ["https://www.google.com/maps?q=16.4637%2C107.5909", "16.4637,107.5909", "?q= mã hoá"],
  ["https://www.google.com/maps/@21.0278,105.8342,17z", "21.0278,105.8342", "@lat,lon"],
  ["https://www.google.com/maps/search/16.4637,+107.5909?entry=tts", "16.4637,107.5909", "/search/"],
  ["https://www.openstreetmap.org/#map=17/16.57510/107.49520", "16.5751,107.4952", "OSM #map"],
  ["https://www.openstreetmap.org/?mlat=16.5751&mlon=107.4952#map=17/16.5/107.4", "16.5751,107.4952", "OSM mlat"],
  ["https://maps.app.goo.gl/AbCdEf123", null, "link rút gọn: không đoán"],
  ["https://batdongsan.com.vn/ban-dat-hue/ban-lo-dat-123-pr456789", null, "trang rao: không đọc số trong link"],
  ["21.0278, 105.8342", "21.0278,105.8342", "thập phân"],
  ["21°01'40\"N 105°50'03\"E", "21.0278,105.8342", "độ-phút-giây"],
  ["21,0278; 105,8342", "21.0278,105.8342", "dấu phẩy thập phân"],
  ["105.8342, 21.0278", "21.0278,105.8342", "dán ngược"],
];
for (const [input, want, why] of cases) assert.equal(r4(parseCoord(input)), want, `${why}: ${input}`);
assert.deepEqual(parseMapLink("https://maps.app.goo.gl/AbCdEf123"), { short: true });
assert.ok(isListingSite("https://batdongsan.com.vn/x") && isListingSite("https://www.chotot.com/y") && !isListingSite("https://www.google.com/maps/@1,2"));
assert.ok(looksLikeUrl("https://x.vn/a") && looksLikeUrl("maps.app.goo.gl/x") && !looksLikeUrl("21.0278, 105.8342"));

// Toạ độ trong nội dung tin đăng — không bắt nhầm giá, diện tích, số điện thoại
assert.equal(r4(findCoordInText("Bán đất 300m2 cao ráo, giá 1,2 tỷ, sđt 0905123456. Toạ độ 16.5751, 107.4952 gần sông.")), "16.5751,107.4952");
assert.equal(r4(findCoordInText("Xem vị trí https://www.google.com/maps/@10.2341,106.3755,18z nhé")), "10.2341,106.3755");
assert.equal(findCoordInText("Bán đất 5x20m giá 1.250 triệu, sổ hồng riêng, 0905.123.456, ngang 12.500 dài 30.000"), null);

console.log(`OK — đọc toạ độ: ${cases.length} kiểu dán + tin đăng.`);
