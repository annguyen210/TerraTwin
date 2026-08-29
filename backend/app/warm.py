"""Hâm nóng trước đường hiệu chuẩn — xoá 13 giây chờ của người dùng đầu tiên.

    python -m app.warm --demo          # 8 nơi trong màn hình chọn nhanh, ~2 phút
    python -m app.warm --provinces     # phủ cả nước, ~30-60 phút
    python -m app.warm --lat 16.46 --lon 107.59

VÌ SAO CẦN. Lần đầu mở một toạ độ, TerraTwin phải tải 10 năm ERA5 của đúng điểm
đó về để dựng đường hiệu chuẩn phân vị — chính thứ làm tỉ lệ báo động giả tụt
từ 46–61% xuống 3%. Đo được: 13,2 giây. Sau đó phân bố nằm trong cache bền, nên
lần sau chỉ 2,2 giây, và 4,1 giây kể cả sau khi khởi động lại máy chủ.

Nghĩa là 13 giây ấy chỉ chạm ĐÚNG NGƯỜI ĐẦU TIÊN mở một toạ độ. Chạy tệp này
trước khi mở cho người dùng, hoặc trước khi lên bục thi, thì không ai phải chờ.

Hâm nóng ở đây là CHẠY ĐÚNG LƯỢT QUÉT THẬT, không phải nạp riêng phần hiệu
chuẩn — bản đầu làm thế và hoàn toàn vô tác dụng, xem chú thích ở warm_one().

KHÔNG PHẢI MẸO GIẤU CHẬM. Dữ liệu hâm nóng là dữ liệu thật, tính bằng đúng
đường mà lượt quét dùng; chỉ khác thời điểm tính. Nếu một điểm không tải được
thì nó vẫn chậm khi có người mở — và bản in ở cuối nói rõ điểm nào đã hỏng.
"""
from __future__ import annotations

import argparse
import sys
import time

from app.services import calibration as cal

MODULES = ("flood", "landslide", "drought", "wildfire")

# Tám nơi trong màn hình chọn nhanh — chạy trước buổi thi thì demo không lag.
DEMO = [
    (10.24, 106.37, "Bến Tre"),
    (9.18, 105.15, "Cà Mau"),
    (15.33, 108.05, "Trà Leng, Quảng Nam"),
    (16.46, 107.59, "Huế"),
    (11.56, 108.99, "Phan Rang"),
    (12.67, 108.05, "Buôn Ma Thuột"),
    (21.03, 105.85, "Hà Nội"),
    (22.40, 103.47, "Lai Châu"),
]

# Trung tâm các tỉnh/thành. Toạ độ xấp xỉ, đủ để hâm nóng ô lưới khí hậu quanh
# đó — KHÔNG dùng để tra cứu hành chính, và cố ý không gắn nhãn đơn vị hành
# chính nào, vì bản đồ hành chính Việt Nam vừa thay đổi lớn và một danh sách sai
# còn tệ hơn không có danh sách.
PROVINCES = [
    (22.82, 104.98), (22.40, 103.47), (22.34, 103.84), (22.66, 106.26),
    (21.85, 106.76), (21.59, 105.85), (21.30, 105.60), (21.03, 105.85),
    (20.86, 106.68), (20.95, 105.75), (20.44, 106.17), (20.25, 106.15),
    (20.13, 105.93), (19.81, 105.78), (19.23, 105.36), (18.68, 105.68),
    (17.98, 105.78), (17.47, 106.62), (16.82, 107.10), (16.46, 107.59),
    (16.05, 108.21), (15.87, 108.33), (15.33, 108.05), (15.12, 108.80),
    (14.35, 108.99), (13.78, 109.22), (13.98, 108.00), (13.08, 109.30),
    (12.67, 108.05), (12.24, 109.19), (11.94, 108.44), (11.56, 108.99),
    (11.32, 106.10), (11.05, 107.07), (10.95, 106.82), (10.82, 106.63),
    (10.60, 107.10), (10.36, 105.44), (10.24, 106.37), (10.03, 105.78),
    (10.45, 105.63), (9.60, 105.97), (9.29, 105.72), (9.18, 105.15),
    (8.62, 104.90), (10.23, 103.96), (20.72, 107.05), (21.77, 104.90),
]


def warm_one(lat: float, lon: float) -> tuple[int, int]:
    """Chạy ĐÚNG lượt quét thật để mọi tầng cache được nạp.

    BẢN ĐẦU CỦA HÀM NÀY KHÔNG CÓ TÁC DỤNG, và tôi chỉ biết vì đã đo lại. Nó chỉ
    gọi climatology() — tức là hâm nóng đường hiệu chuẩn. Nhưng hiệu chuẩn chỉ
    là MỘT trong bảy lượt gọi mạng của một lần quét; sáu cái còn lại là dự báo
    7 ngày, cao độ, độ dốc, nhiệt mặt biển, lưu lượng sông và bức xạ mặt trời.
    Hâm xong Phan Rang rồi quét lại vẫn mất 14,7 giây — y như chưa hâm.

    Cách đúng là chạy chính lượt quét: nó chạm mọi thứ mà một yêu cầu thật chạm,
    theo đúng thứ tự đó. Không có cách nào ngắn hơn mà vẫn đúng.
    """
    from app.services import scan
    from app.schemas import Location
    try:
        d = scan.scan(Location(lat=lat, lon=lon))
    except Exception:
        return 0, 1
    # `pending` KHÔNG phải hỏng: đó là các mũi nhọn cần ảnh vệ tinh, được hoãn
    # có chủ ý khỏi lượt quét nhanh. Đếm chúng là thất bại thì mọi điểm đều báo
    # "11/18" và bản in cuối nói dối về tình trạng thật.
    thieu = sum(1 for m in d.modules if m.status == "need_data")
    return len(d.modules) - thieu, len(d.modules)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="8 nơi trong màn hình chọn nhanh")
    ap.add_argument("--provinces", action="store_true", help="trung tâm các tỉnh")
    ap.add_argument("--lat", type=float)
    ap.add_argument("--lon", type=float)
    a = ap.parse_args()

    if a.lat is not None and a.lon is not None:
        diem = [(a.lat, a.lon, f"{a.lat},{a.lon}")]
    elif a.provinces:
        diem = [(la, lo, f"{la:.2f},{lo:.2f}") for la, lo in PROVINCES]
    else:
        diem = DEMO

    from app.db import init_db
    init_db()

    print(f"Hâm nóng {len(diem)} điểm · mỗi điểm 10 năm ERA5 cho {len(MODULES)} hiểm hoạ")
    print("Điểm nào đã có trong cache sẽ xong tức thì.\n")

    t0 = time.time()
    hong = []
    for i, (la, lo, ten) in enumerate(diem, 1):
        t = time.time()
        ok, tong = warm_one(la, lo)
        dt = time.time() - t
        dau = "✓" if ok == tong else ("~" if ok else "✗")
        print(f"  {dau} {i:3}/{len(diem)}  {ten:24} {ok}/{tong}  {dt:5.1f}s")
        if ok < tong:
            hong.append((ten, ok, tong))

    print(f"\nXong {len(diem) - len(hong)}/{len(diem)} điểm trong "
          f"{(time.time() - t0) / 60:.1f} phút")
    if hong:
        print("\nChưa hâm nóng được (những điểm này vẫn chậm ở lần mở đầu):")
        for ten, ok, tong in hong:
            print(f"  {ten:24} {ok}/{tong}")
        print("Thường là do nguồn dữ liệu đang chặn vì gọi quá nhiều — "
              "chờ mươi phút rồi chạy lại, phần đã xong sẽ được bỏ qua.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
