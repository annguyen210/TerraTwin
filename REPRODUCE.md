# Tái lập kết quả — TerraTwin

Tài liệu này để **người ngoài kiểm chứng** những tuyên bố chính của TerraTwin
bằng chính mã nguồn, không phải tin lời. Mỗi mục ghi rõ: chạy gì, thấy gì, và
con số đó nghĩa là gì.

> Nguyên tắc: chỗ nào chưa đủ dữ liệu thì phần mềm nói thẳng. Nếu một bước dưới
> đây trả về "chưa đủ mẫu" thì đó là hành vi ĐÚNG, không phải lỗi — xem ghi chú
> ở từng mục.

## 0. Cài đặt (một lần)

```bash
# Backend (Python 3.12)
cd backend
python -m venv .venv && . .venv/Scripts/activate   # Linux/Mac: . .venv/bin/activate
pip install -r requirements-dev.txt
pytest                       # toàn bộ test, chạy OFFLINE & tất định

# Frontend (Node 20)
cd ../frontend
npm ci
npm run build
```

Test chạy được **không cần mạng và không cần khoá API** — đó là điều kiện để kết
quả tái lập được ở máy khác. CI (`.github/workflows/ci.yml`) chạy đúng bộ test
này trên **cả SQLite lẫn PostgreSQL** mỗi lần đẩy mã.

## 1. Tuyên bố "biết trước" — kiểm trên thiên tai lịch sử THẬT

Đây là bằng chứng cốt lõi: chạy đúng mô hình cảnh báo trên dữ liệu thời tiết
QUÁ KHỨ (Open-Meteo Archive / ERA5) tại đúng toạ độ và thời điểm một trận thiên
tai đã xảy ra, xem model có báo trước không và trước mấy ngày.

```bash
uvicorn app.main:app --port 8000        # Windows: KHÔNG dùng --reload
# Cửa sổ khác:
curl http://localhost:8000/api/backtest                 # danh sách sự kiện
curl http://localhost:8000/api/backtest/hue_flood_2020  # lũ Huế 10/2020
```

Sự kiện có sẵn gồm: lũ lịch sử Thừa Thiên Huế 10/2020, lũ Quảng Nam–Đà Nẵng
10/2022, sạt lở Trà Leng 28/10/2020, hạn–mặn ĐBSCL (Bến Tre) mùa khô 2020.
Kết quả trả về **số ngày báo trước** và chuỗi chỉ số so với ngưỡng đã hiệu chuẩn
— dữ liệu đầu vào là ERA5 công khai, ai chạy lại cũng ra cùng con số.

## 2. Tuyên bố "báo động giả ~3%" — hiệu chuẩn TỪNG THỬA

Con số báo động giả thấp đến từ việc so ngưỡng với **10 năm khí hậu của chính
điểm đó**, thay vì một ngưỡng chung cả nước. Xem đối chứng trực tiếp:

```bash
# Ngưỡng chung cả nước vs hiệu chuẩn theo chính thửa này:
curl -X POST http://localhost:8000/api/contrast \
  -H "Content-Type: application/json" \
  -d '{"location":{"lat":16.46,"lon":107.59}}'

# Thẻ mô hình — CÔNG BỐ CẢ CHỖ MÔ HÌNH KHÔNG THẮNG (bảng comparison):
curl http://localhost:8000/api/model
```

`/api/model` cố tình giữ nguyên **mọi mức báo động đã thử**, kể cả mức mô hình
chỉ hoà với cách cũ — để người đọc tự kiểm, không phải tin một con số đã chọn
sẵn. Đây là điểm trung thực quan trọng nhất: không giấu chỗ thua.

## 3. Hiệu chuẩn từng thửa nhìn thấy được — "Sổ tay thửa"

```bash
curl -X POST http://localhost:8000/api/passport \
  -H "Content-Type: application/json" \
  -d '{"location":{"lat":10.24,"lon":106.38}}'
```

Trả về địa hình tương đối + **10 năm hiểm hoạ đo từ ERA5** của riêng thửa đó.
Ghi chú trung thực đi kèm: số lần trong lịch sử đếm theo ngưỡng đã hiệu chuẩn,
**KHÔNG phải số trận được ghi nhận chính thức** — hai thứ khác nhau, và phần mềm
nói rõ.

## 4. Cơ chế trung thực — sổ điểm tự chấm

```bash
curl http://localhost:8000/api/scorecard
```

Phần mềm **tự chấm về chính mình** (POD/FAR/CSI), không sửa được từ giao diện.
Trên một cơ sở dữ liệu mới, mục này trả `"enough": false` và headline *"chưa có
cảnh báo prod nào tới hạn chấm"* — ĐÚNG như thiết kế: sổ điểm chỉ hiện tỉ lệ khi
có cảnh báo thật đủ 13 ngày tuổi để chấm lại bằng số đo thực tế. Nó KHÔNG bịa số
để trông đẹp.

Nhãn nguồn trên mọi kết luận: 🛰️ = đo được · 🧪 = ước lượng vật lý · "chưa đủ dữ
liệu" khi chưa đủ. Không có con số nào không gắn được về nguồn.

## 5. (Tuỳ chọn) Huấn luyện lại mô hình

```bash
python -m app.ml.train        # mô hình chấm bất thường tổ hợp (A-series)
# U-Net lớp phủ (A1) cần GPU — xem backend/app/dl/train.py; chưa có landcover.onnx
# thì lớp học sâu IM LẶNG trả None, phần còn lại của phần mềm vẫn chạy bình thường.
```

## 6. A7 (biến động tán cây) — đã kiểm bằng dữ liệu tổng hợp, CHƯA bằng sự kiện thật

```bash
curl -X POST "http://localhost:8000/api/change-detect?months=24" \
  -H "Content-Type: application/json" \
  -d '{"lat":16.4637,"lon":107.5909}'
```

**Đã chứng minh, tái lập được ngay:**
- `pytest tests/test_change_detect.py` — dữ liệu NDVI tổng hợp có kiểm soát:
  lúa ba vụ (dao động mùa vụ đều, không xu hướng) KHÔNG bị báo mất tán; một đợt
  phá rừng dựng sẵn ở một THÁNG biết trước THÌ bị báo đúng khoảng đó.
- Trên dữ liệu thật (không mock): chạy tại Huế, Đắk Lắk, Trà Leng, An Giang —
  mọi nơi đều `available: true` với 9–19 tháng ảnh quang mây trong 24–36 tháng.
  Tại An Giang (ruộng lúa ba vụ thật) `change_detected: false`, `test_statistic
  0.33` dưới hẳn ngưỡng `1.36` — đúng như tiêu chí "không báo giả ở ruộng lúa
  ba vụ".

**CHƯA chứng minh được — chưa có một sự kiện phá rừng THẬT, đã xác minh độc
lập, được A7 báo đúng tháng.** Đã thử nghiêm túc trong phạm vi công cụ không
cần tài khoản nào, bốn hướng đều không ra kết quả dùng được, ghi lại đây để
không ai phải tin lời suông:

1. **Sân bay Long Thành**, Đồng Nai (10.7725, 107.04528 — nguồn: Wikipedia,
   bàn giao mặt bằng 25/8/2023). NDVI thấp (0,01–0,06) suốt CẢ cửa sổ 36
   tháng — san nền thật đã bắt đầu từ 2021, trước cả mốc xa nhất A7 với tới
   (giới hạn `months<=36` tính lùi từ hôm chạy). Không có mốc trước/sau nào
   để so — đây là giới hạn tầm với của cửa sổ, không phải lỗi thuật toán.
2. **KCN Sông Công II giai đoạn 2**, Thái Nguyên (21.5072382, 105.8438183 —
   toạ độ OSM cho tên "Khu công nghiệp Sông Công II"; khởi công 3/2025, giải
   phóng 120ha trong 9 tháng theo báo Thái Nguyên). Cùng triệu chứng: NDVI
   thấp (0,08–0,16) suốt cửa sổ, kể cả điểm đầu tiên (10/2023) — nhiều khả
   năng toạ độ rơi vào phần đã xây từ giai đoạn trước, không phải mảnh đất
   MỚI giải phóng năm 2025.
3. **Hầm Bình Đê**, cao tốc Quảng Ngãi–Hoài Nhơn (hai cửa hầm theo OSM:
   14.6743472/109.0028425 và 14.6745070/109.0033681; khởi công tuyến
   1/1/2023). NDVI ổn định 0,38–0,58 suốt 36 tháng, không có đợt giảm bền
   vững nào.
4. **Quét lưới tự động** — 200 điểm cách nhau 500m tại hai vùng áp lực phá
   rừng (Đắk Nông huyện Tuy Đức/Đắk Song, Quảng Nam huyện Nam Trà My), sàng
   lọc bằng so sánh NDVI hai lát cắt nhanh (không lọc mây theo pixel). Kết
   quả ban đầu: một cụm 14 điểm liền kề ở Đắk Nông (quanh 12,25–12,27°N
   107,42–107,47°Đ) có vẻ giảm mạnh (tới −0,39). Kiểm lại bằng đúng hàm
   `mpc.monthly_index_series()` mà A7 thật sự dùng (có lọc `clear_fraction`
   theo lớp SCL) tại chính các toạ độ đó thì KHÔNG thấy đợt giảm nào — NDVI
   ổn định 0,33–0,53 suốt 36 tháng. Kết luận: cụm "giảm mạnh" ban đầu là SAI
   — do phép sàng lọc nhanh chỉ chọn cảnh theo % mây CẢ CẢNH mà bỏ qua lọc
   mây THEO ĐÚNG ĐIỂM ẢNH, nên bị một cảnh có mây/sương mù cục bộ đánh lừa.
   Đây cũng là bằng chứng gián tiếp cho thấy bước lọc `clear_fraction` trong
   pipeline thật đang làm đúng việc của nó — nó đã tự loại bỏ chính cái tín
   hiệu giả này.

**Vì sao vẫn chưa xong**: cả bốn hướng trên đều cần biết TRƯỚC toạ độ và
khoảng thời gian một mảnh đất THẬT SỰ mất tán — thứ duy nhất cung cấp đúng dữ
liệu đó (toạ độ điểm ảnh + ngày, đã xác minh) là các dịch vụ cảnh báo vệ tinh
chuyên dụng (vd Global Forest Watch GLAD/RADD), và các dịch vụ đó cần tài
khoản/API key — ngoài phạm vi "không cần gì từ chủ dự án" của việc này. Cách
đóng nốt: (a) chủ dự án cung cấp một toạ độ + tháng mình biết chắc đã mất
rừng, hoặc (b) tạo tài khoản GFW Data API rồi truy vấn toạ độ cảnh báo thật.

## Nếu một bước không ra kết quả

- **Gọi mạng hụt / rate-limit Open-Meteo**: các endpoint mục 1–3 gọi API thời
  tiết công khai; nếu bị giới hạn tần suất, chờ rồi chạy lại. `GET /api/health`
  cho biết nguồn nào đang bị chặn vì quá hạn mức.
- **Sổ điểm trống**: đúng như mục 4 — không phải lỗi.
- **Test đỏ vì mạng**: hiếm; CI có `--reruns` cho các test cố ý gọi API thật.
  Bộ test lõi chạy offline và phải xanh 100%.
