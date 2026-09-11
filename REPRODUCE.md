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

## Nếu một bước không ra kết quả

- **Gọi mạng hụt / rate-limit Open-Meteo**: các endpoint mục 1–3 gọi API thời
  tiết công khai; nếu bị giới hạn tần suất, chờ rồi chạy lại. `GET /api/health`
  cho biết nguồn nào đang bị chặn vì quá hạn mức.
- **Sổ điểm trống**: đúng như mục 4 — không phải lỗi.
- **Test đỏ vì mạng**: hiếm; CI có `--reruns` cho các test cố ý gọi API thật.
  Bộ test lõi chạy offline và phải xanh 100%.
