"""Ảnh THẬT của thửa đất — thứ TerraTwin thiếu suốt từ đầu.

VẤN ĐỀ NÀY LỚN HƠN MỘT TÍNH NĂNG THIẾU. Người dùng thử phần mềm rồi nói "sơ
sài, chẳng có gì". Sửa điều hướng không hết, thêm dữ liệu không hết. Đọc lại
mới thấy: cả sản phẩm là MỘT BẢNG CHỮ bên phải màn hình. Bản đồ nhiệt là những
ô màu trừu tượng. TerraTwin chưa bao giờ CHO NGƯỜI TA THẤY mảnh đất của họ — nó
chỉ KỂ về mảnh đất bằng câu văn.

Chữ "Twin" hứa một bản sao của vật thật. Không có hình ảnh nào của vật thật thì
lời hứa đó rỗng, và người dùng cảm nhận được điều đó ngay cả khi không gọi tên
ra được.

Nay sửa được, vì Planetary Computer phục vụ cả ẢNH chứ không riêng con số —
công khai, không khoá, đo được 3,2 giây cho một ô 512×512.

BA LỚP ẢNH, mỗi lớp trả lời một câu hỏi khác nhau:
  màu thật   "thửa của tôi trông thế nào"      — ai cũng đọc được, không cần học
  sức sống   "chỗ nào cây yếu"                  — NDVI tô màu đỏ-vàng-xanh
  đối chiếu  "một năm qua đổi thế nào"          — cùng tháng, cách nhau một năm

VÌ SAO ĐỐI CHIẾU PHẢI CÙNG THÁNG. Lấy ảnh tháng 3 so với ảnh tháng 9 thì khác
biệt nhìn thấy gần như hoàn toàn là MÙA VỤ, không phải thay đổi thật. Người xem
sẽ kết luận sai một cách rất tự tin. Nên hàm ở đây ép cùng tháng, cách đúng một
năm, và nếu không tìm được ảnh quang mây trong cửa sổ đó thì nói không có —
không lấy bừa ảnh tháng khác cho đủ cặp.

KHÔNG TẢI ẢNH QUA MÁY CHỦ NÀY. Chỉ trả về đường dẫn để trình duyệt tự lấy: mỗi
ảnh nửa megabyte, đẩy qua máy chủ gói free là tự bóp cổ mình, mà chẳng được lợi
gì vì nguồn vốn đã công khai.
"""
from __future__ import annotations

import urllib.parse
from datetime import date, timedelta

from app.services import mpc

DATA = "https://planetarycomputer.microsoft.com/api/data/v1/item/bbox"

# Công thức màu cho ảnh thật. Ảnh Sentinel-2 thô rất tối và xám; không chỉnh thì
# người dùng tưởng vệ tinh chụp hỏng. Các tham số này là bộ Planetary Computer
# dùng cho chính bản xem trước của họ.
_TRUE_COLOR = ("assets=visual&asset_bidx=visual%7C1%2C2%2C3&nodata=0")

# Thang màu NDVI: đỏ (cây yếu / đất trống) → vàng → xanh (cây khoẻ).
# Chặn ở -0,2…0,9 vì ngoài khoảng đó gần như chỉ có mặt nước và mây.
_NDVI = ("expression=(B08-B04)%2F(B08%2BB04)&asset_as_band=true"
         "&rescale=-0.2%2C0.9&colormap_name=rdylgn")

SIZE = 512
# Không có ngưỡng quang mây ở đây — xem lý do trong _pick(). Ảnh nhiều mây vẫn
# được đưa ra kèm con số độ mây, để người xem tự quyết; giấu nó đi thì người ta
# tưởng vệ tinh không bay qua, trong khi thực tế là bay qua nhưng trời nhiều mây.


def _url(item_id: str, box: list[float], layer: str) -> str:
    bb = ",".join(f"{v:.5f}" for v in box)
    q = (f"collection={mpc.COLLECTION}&item={urllib.parse.quote(item_id)}"
         f"&width={SIZE}&height={SIZE}&{layer}")
    return f"{DATA}/{bb}.png?{q}"


def _pick(box: list[float], start: date, end: date) -> dict | None:
    """Ảnh ít mây nhất trong cửa sổ. Một lời gọi tìm kiếm, KHÔNG dò từng tấm.

    ĐÂY LÀ CHỖ TÔI THIẾT KẾ SAI MỘT LẦN RỒI SỬA. Bản đầu dò lớp SCL cho tới 12
    tấm để chọn hộ người dùng tấm quang nhất tại thửa — mất 80–140 giây, không
    dùng được, và có lúc còn bỏ sót tấm tốt vì nguồn quá tải giữa chừng.

    Nhìn lại thì việc dò đó là thừa Ở ĐÂY. Lọc SCL theo từng thửa là cần cho
    CON SỐ — không ai nhìn ra mây lẫn trong một giá trị NDVI trung bình, nên
    máy phải lọc hộ. Nhưng với ẢNH thì mắt người thấy mây ngay lập tức, tốt hơn
    mọi thuật toán. Việc của phần mềm chỉ là đưa tấm gần đây ít mây nhất và NÓI
    RÕ độ mây, rồi để người xem tự đánh giá.

    Kết quả: từ 80–140 giây xuống còn một lời gọi.
    """
    items = mpc.search(box, start, end, max_cloud=mpc.MAX_CLOUD, limit=30)
    if not items:
        return None
    items.sort(key=lambda it: float(it["properties"].get("eo:cloud_cover") or 100.0))
    it = items[0]
    return {
        "item": it["id"],
        "date": it["properties"]["datetime"][:10],
        "cloud_scene_pct": round(float(it["properties"].get("eo:cloud_cover") or 0.0), 1),
    }


def plot_view(lat: float, lon: float, buffer_m: float = 500.0) -> dict:
    """Ba lớp ảnh cho một thửa. Luôn trả dict — không bao giờ ném lỗi lên API."""
    from app.services import cache_store
    key = cache_store.make_key("imagery", round(lat, 4), round(lon, 4), int(buffer_m))
    hit = cache_store.get(key)
    if hit is not None:
        return hit

    box = mpc.bbox_around(lat, lon, buffer_m)
    today = date.today()

    now = _pick(box, today - timedelta(days=120), today)
    if now is None:
        kq = {
            "available": False,
            "message": ("Chưa có ảnh quang mây cho thửa này trong 4 tháng qua. "
                        "Mùa mưa ở Việt Nam mây che gần như liên tục — vệ tinh "
                        "quang học không nhìn xuyên mây được. Thử lại sau vài "
                        "ngày, phần mềm tự lấy tấm gần nhất."),
            "reason": "cloud",
        }
        # Cache cả trường hợp KHÔNG có ảnh — nếu không thì mỗi lần mở lại phải
        # chờ hết chu trình tìm kiếm để nhận cùng một câu trả lời.
        cache_store.put(key, kq, ttl_seconds=6 * 3600)
        return kq

    # Đối chiếu: CÙNG THÁNG, cách một năm. Xem lý do ở đầu tệp.
    d_now = date.fromisoformat(now["date"])
    try:
        anchor = d_now.replace(year=d_now.year - 1)
    except ValueError:                       # 29/02
        anchor = d_now.replace(year=d_now.year - 1, day=28)
    then = _pick(box, anchor - timedelta(days=60), anchor + timedelta(days=60))

    out = {
        "available": True,
        "center": {"lat": lat, "lon": lon},
        "bbox": box,
        "span_m": round(buffer_m * 2),
        "now": {
            **now,
            "true_color": _url(now["item"], box, _TRUE_COLOR),
            "ndvi": _url(now["item"], box, _NDVI),
        },
        "source": "Sentinel-2 L2A · Microsoft Planetary Computer (không cần khoá)",
        "resolution_m": 10,
        "caveat": (
            f"Ảnh chụp ngày {now['date']} (mây toàn cảnh {now['cloud_scene_pct']}%), "
            f"không phải hôm nay — Sentinel-2 bay "
            f"qua mỗi ~5 ngày và mùa mưa thường bị mây che. Mỗi điểm ảnh là một "
            f"ô 10×10 m, nên vật nhỏ hơn thế không nhìn thấy được."),
    }

    if then:
        out["then"] = {
            **then,
            "true_color": _url(then["item"], box, _TRUE_COLOR),
            "ndvi": _url(then["item"], box, _NDVI),
        }
        out["compare_note"] = (
            f"Hai ảnh cách nhau khoảng một năm và CÙNG MÙA "
            f"({then['date']} so với {now['date']}). Cùng mùa mới so được: lấy "
            f"ảnh mùa khô đặt cạnh ảnh mùa mưa thì khác biệt nhìn thấy chủ yếu "
            f"là mùa vụ, không phải thay đổi thật.")
    else:
        out["compare_note"] = (
            "Không tìm được ảnh quang mây cùng mùa năm ngoái, nên chưa so được "
            "hai kỳ. Cố ý không lấy ảnh tháng khác thay thế — khác biệt khi đó "
            "sẽ là mùa vụ chứ không phải thay đổi thật.")

    # Giữ 12 giờ: Sentinel-2 bay qua mỗi ~5 ngày nên trong một ngày không có
    # tấm nào mới, và mỗi lần dựng lại tốn hàng chục giây.
    cache_store.put(key, out, ttl_seconds=12 * 3600)
    return out
