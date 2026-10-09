# GĐ5 trên GPU Kaggle — mô hình nước trên radar (Sen1Floods11)

Giao thức đã đăng ký TRƯỚC khi huấn luyện: [`backend/data/ml/gd5_protocol.json`](../../backend/data/ml/gd5_protocol.json)
(mục `s1_water`). Chạy đúng một lần; không đạt thì kết quả trượt vẫn được công bố.

## Bác làm (khoảng 10 phút thao tác, 1–2 giờ máy chạy)

1. Tạo tài khoản tại kaggle.com và xác minh số điện thoại (bắt buộc để bật GPU và Internet).
2. **Create → New Notebook**. Cột phải: **Accelerator → GPU T4 x2** (hoặc P100), **Internet → On**.
3. **File → Upload** tệp `s1_water_seg.py` trong thư mục này (hoặc dán nội dung vào một ô mã và lưu thành tệp).
4. Chạy hai ô:

   ```
   !pip -q install rasterio onnx
   !python s1_water_seg.py --out /kaggle/working/s1_water_result.json
   ```

   Script tự tải Sen1Floods11 (~1 GB) từ kho công khai của Google Cloud, huấn luyện 40 vòng, chọn mô hình bằng
   tập valid, rồi chấm MỘT lần trên test, Bolivia và Mekong.
5. Tab **Output**: tải về `s1_water_result.json` (bắt buộc), `s1_water_unet.onnx` và `s1_water_unet.pt`.
   Gửi lại cho phiên làm mã hoặc chép vào `backend/data/ml/`.

## Kết quả được đọc thế nào

- `results.test / bolivia / mekong`: IoU lớp nước của mô hình, của ngưỡng −18 dB và của Otsu.
- `passed: true` chỉ khi mô hình hơn ngưỡng −18 dB trên **cả ba**.
- Đạt mới là bước 1: muốn thay phương pháp ngưỡng trong lịch sử nước của từng thửa, mô hình còn phải qua lại cổng
  GĐ2 (`ops/water_gate.py`: lũ Huế 10/2020, miền Trung 10/2025, đất cao 0 đợt).

## Thử máy trước (không cần GPU)

```
python s1_water_seg.py --baseline-only --limit 3      # chỉ đọc dữ liệu + chấm phương pháp ngưỡng
python s1_water_seg.py --limit 2 --epochs 1 --width 8 # chạy thông cả vòng huấn luyện trên CPU
```

`--limit` chỉ để thử máy — không bao giờ là kết quả kiểm định (`passed` luôn là `false`).

## Loại đất (Prithvi) — không cần Kaggle nữa

Mục loại đất của GĐ5 dùng **AlphaEarth Foundations** (mô hình nền địa không gian của Google DeepMind, cùng loại với
Prithvi-EO-2.0) + bộ phân loại tuyến tính, chạy trên CPU: `backend/app/ml/aef_landcover.py`, giao thức
`backend/data/ml/aef_landcover_protocol.json`, kết quả ghi vào `backend/data/landcover_runs.json`.

## PhoBERT tách câu khẳng định — chờ dữ liệu

Cần ~1.000 câu tin đăng tự thu thập và gán nhãn (không cào trang bất động sản). Trước đó là cổng GĐ3: 20 tin thật
trong `backend/data/listings_gold.json` (mẫu: `listings_gold.example.json`).
