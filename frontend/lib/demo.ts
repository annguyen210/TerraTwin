/**
 * THỬA + TIN MẪU cho luồng chính "kiểm đất trước khi mua" (trang đầu, kịch bản demo đi thi docs/KICH_BAN_DEMO.md).
 *
 * Thửa: ruộng xã Tuệ Tĩnh, Hải Phòng (Cẩm Giàng, Hải Dương cũ) — bản đồ ngập UNOSAT ngày 10/9/2024 (bão Yagi) ghi
 * điểm này ngập; lịch sử nước radar có đợt 12/9/2024. Giữ khớp backend/app/services/demo_plots.py (DEMO_PLOTS[0],
 * hâm nóng radar + ý kiến U-Net mỗi 6 giờ) và ô "thua" mặc định của .github/workflows/keepwarm.yml.
 *
 * Tin: do TerraTwin SOẠN để minh hoạ, KHÔNG phải tin rao thật — ô kiểm tin luôn ghi rõ như vậy khi chữ trùng tin
 * này. backend/tests/test_listing_check.py đọc chuỗi dưới đây và kiểm máy tách đủ 5 loại câu.
 */
export const DEMO_PLOT = { lat: 20.9716, lon: 106.2834, label: "Ruộng xã Tuệ Tĩnh, Hải Phòng — bão Yagi 9/2024" };

export const DEMO_LISTING =
  "Bán lô đất 250m2 thổ cư 100%, sổ đỏ chính chủ. Đất cao ráo, không bao giờ ngập, mặt bằng bằng phẳng, gần sông mát mẻ. Giá thương lượng.";

export function isDemoListing(text: string): boolean {
  return text.trim() === DEMO_LISTING;
}
