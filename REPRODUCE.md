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

## 7. Lịch sử nước nhìn xuyên mây (radar Sentinel-1) — CỔNG GĐ2 ĐẠT 9/10/2026

```bash
python ops/water_gate.py      # ~5 phút: đọc ~300 cảnh/điểm qua Planetary Computer, ghi backend/data/water_gate.json
```

Quy tắc (viết trước khi chạy, `services/water_history.py`): một quỹ đạo cố định, ảnh Sentinel-1 RTC; cảnh có nước khi
phân vị VV < −18 dB **và** thấp hơn nền của chính thửa ≥ 3 dB; cảnh cách nhau ≤ 24 ngày ghép thành một đợt.

| Điểm | Cảnh đọc được | Kỳ vọng | Kết quả |
|---|---|---|---|
| Đồng lúa Quảng Điền, Huế (16,575; 107,495) | 325 (2017-01 → 2026-09, quỹ đạo giảm #18) | có nước tuần lũ 06–20/10/2020 và 25/10–10/11/2025 | **đạt** — 10/10/2020 (phủ 25–50%), 01–19/11/2025 (25–50%); tổng 7 đợt |
| Đất cao Đà Lạt (11,940; 108,458) | 291 | 0 đợt | **đạt** — 0 |
| Đồi thông Thiên An, Huế (16,428; 107,563) | 325 | 0 đợt | **đạt** — 0 |

Giới hạn: đô thị (phản xạ kép), rừng rậm, sườn dốc, mặt rất phẳng; chu kỳ 6–12 ngày có thể lọt đợt ngập ngắn
(lũ đỉnh 27–30/10/2025 được thấy ở cảnh 01/11 khi nước còn đọng). Đây là số đo radar, không phải số liệu ngập chính thức.

**Thời gian đọc một thửa MỚI trên production (Render gói miễn phí), 18/10/2026** — cổng kế hoạch tổng "hồ sơ đầy đủ < 60 giây":

| Bản | 459 cảnh | Ghi chú |
|---|---|---|
| 4 luồng, mỗi cảnh một kết nối TLS mới | ~181 s | |
| 8 luồng | 71,6 s | 12 luồng 77,7 s — không nhanh hơn: MỌI lượt gọi ra ngoài chung trần 6 (`jobs._UPSTREAM_LIMIT`, đặt cho Open-Meteo) |
| **Trần riêng Planetary Computer 16 + kết nối giữ mở + 12 luồng** (2bb66bb) | **35,0 s** (người dùng chờ 39 s) | 0 cảnh lỗi; 5/5 cảnh so với đường cũ khớp tuyệt đối |

Hộ chiếu thửa (địa hình + ERA5 10 năm) cho toạ độ mới: 10,3 s, chạy song song khi mở thửa → hồ sơ đầy đủ ≈ 40–50 s,
**đạt cổng < 60 s** khi Open-Meteo không chặn IP dùng chung của Render. Bị chặn thì hồ sơ vẫn phát hành và ghi mục thiếu.

### 7b. Lớp diễn giải MÙA LŨ (trong / ngoài mùa) — CỔNG ĐẠT 17/10/2026

Vì sao: bộ phát hiện ở trên (không đổi) đếm cả nước cho vào ruộng/ao theo vụ. Đo production: Cà Mau 9,18; 105,09 có
13 đợt, tháng bắt đầu 3–5 và 8–9; Hà Nội 21,12; 105,89 có 6 đợt tháng 2–3 và 7. Lớp này chỉ GẮN NHÃN từng đợt.

```bash
cd backend && python ../ops/flood_season_gate.py   # ghi backend/data/eval/flood_season_result.json
```

Quy tắc v1 + 4 ca + tiêu chí đạt đăng ký TRƯỚC khi chạy (`backend/data/eval/flood_season_protocol.json`, commit 6de80c3;
mã `backend/app/services/flood_season.py`): mưa ngày ERA5 2016–2025 tại chính điểm → mưa trung bình từng tháng;
**lõi** = các tháng mưa nhiều nhất, lấy dần tới khi cộng dồn ≥ 50% tổng năm; **mùa lũ** = lõi + tháng liền sau mỗi tháng
lõi. Đợt "trong mùa lũ" nếu tháng bắt đầu thuộc mùa lũ. Đợt ngoài mùa trên ruộng (WorldCover Trồng trọt ≥ 50%) hoặc có mặt
nước nhỏ → "thường là nước tưới / nuôi trồng theo vụ". Kiểm tin đăng: chỉ đợt TRONG mùa lũ làm "không ngập" thành
"mâu thuẫn"; chỉ có đợt ngoài mùa → "không đủ dữ liệu".

| Ca | Mùa lũ tính ra (lõi) | Đợt được chọn | Yêu cầu | Kết quả |
|---|---|---|---|---|
| Lũ Huế 10–11/2020 — Quảng Điền (16,5751; 107,4952) | tháng 10–1 (lõi 10, 11, 12) | 10/10/2020, 09/11/2020 | trong | **đạt** |
| Lũ miền Trung 11/2025 — Quảng Điền | tháng 10–1 | 01/11/2025 | trong | **đạt** |
| Cà Mau (9,18; 105,09) — các đợt tháng 3–5 | tháng 7–11 (lõi 7–10) | 10 đợt (2017-05 … 2026-05) | ngoài | **đạt** 10/10 |
| Hà Nội (21,12; 105,89) — các đợt tháng 2–3 | tháng 7–10 (lõi 7–9) | 4 đợt (2018-03, 2020-02, 2022-03, 2023-02) | ngoài | **đạt** 4/4 |

Các đợt NGOÀI cổng (công bố đủ, không chỉnh quy tắc theo chúng): Quảng Điền 7 trong / 0 ngoài; Cà Mau 3 trong (08/2020,
08/2021, 09/2026) / 10 ngoài; Hà Nội 2 trong (07/2020, 07/2021) / 4 ngoài; đồng lúa Huế 16,52; 107,59: 5 trong / 1 ngoài —
**đợt 19/09/2024 bị xếp "ngoài mùa lũ" dù trùng ngày bão Soulik đổ bộ miền Trung**: lũ sớm đầu mùa là giới hạn đã biết
của quy tắc v1 (muốn sửa phải đăng ký v2 với ca mới, không chạy lại trên 4 ca này).

### 7c. Lớp mùa lũ v2 — bắt lũ sớm/muộn bằng MƯA CỰC ĐOAN — CỔNG TRƯỢT 17/10/2026 (giữ v1, không bật)

```bash
cd backend && python ../ops/flood_season_v2_gate.py   # ghi backend/data/eval/flood_season_v2_result.json
```

Đăng ký trước (commit 2683146, `backend/data/eval/flood_season_v2_protocol.json`): với mỗi đợt NGOÀI mùa lũ v1, cửa sổ
từ ngày sau cảnh radar khô liền trước tới ngày cảnh ướt đầu tiên (tối đa 12 ngày); tổng mưa 3 ngày ERA5 lớn nhất trong
cửa sổ ≥ P97 của mọi tổng 3 ngày tại điểm (2016–2025) → "ngoài mùa nhưng ngay sau mưa cực đoan". P97 và 12 ngày chốt
trước; bộ phát hiện và quy tắc v1 không đổi.

| Ca | Chiều | Đợt | Mưa 3 ngày / P97 | Yêu cầu | Kết quả |
|---|---|---|---|---|---|
| Bão Soulik 19/09/2024 — ruộng lúa Huế (16,52; 107,59) | dương tính | 19/09/2024 | 125,7 / 125,2 mm | cực đoan | **đạt** (sát nút, hơn 0,5 mm) |
| Bão Noru 28/09/2022 — lưới 20 điểm Vu Gia – Thu Bồn, giữ 3 điểm ruộng | dương tính | — | — | ≥ 1 đợt cực đoan | **trượt — không đánh giá được**: năm 2022 chỉ còn Sentinel-1A (12 ngày/lần), cảnh 25/09 và 07/10; 3 điểm ruộng không có đợt nước nào tháng 8–11/2022 |
| Cà Mau (9,18; 105,09) — 10 đợt tháng 3–5 | âm tính | 9 đợt "out"; **05/04/2025 "cực đoan"** | 70,4 / 69,6 mm | nước tưới / nuôi trồng | **trượt** 9/10 |
| Hà Nội (21,12; 105,89) — 4 đợt tháng 2–3 | âm tính | 4 đợt "out" | 5,9–61,7 / 88,9 mm | nước tưới / nuôi trồng | **đạt** 4/4 |
| Lũ Huế 10–11/2020 — Quảng Điền | giữ v1 | 10/10/2020, 09/11/2020 | — | trong mùa | **đạt** |
| Lũ miền Trung 11/2025 — Quảng Điền | giữ v1 | 01/11/2025 | — | trong mùa | **đạt** |

Kết luận: trượt cả hai chiều (Noru không có cảnh radar đúng tuần; Cà Mau bị bắt nhầm một đợt cho nước theo vụ) → **giữ
v1**. Mưa ERA5 lưới ~25 km tách lũ sớm khỏi mưa đầu mùa rất kém: Soulik chỉ hơn ngưỡng 0,5 mm, đợt Cà Mau sai chỉ hơn 0,8 mm.
Không chỉnh P97 / cửa sổ / ô lưới rồi chạy lại trên 6 ca này; muốn thử tiếp phải đăng ký phiên bản mới với tín hiệu độc lập
và ca mới.

### 7d. Lớp mùa lũ v3 — lưu lượng sông GloFAS (R-a, R-b) — CỔNG TRƯỢT 17/10/2026 (giữ v1, không bật)

```bash
cd backend && python ../ops/flood_season_v3_select.py   # chọn ca (chỉ phép kiểm được phép) → data/eval/flood_season_v3_cases.json
cd backend && python ../ops/flood_season_v3_gate.py     # chấm R-a và R-b → data/eval/flood_season_v3_result.json
```

Đăng ký trước, theo thứ tự: quy tắc + cách chọn ca + cách chấm (59837ec) → bổ sung một lần 4 ứng viên (A2, e80bd09, trước
mọi kết quả cổng) → danh sách ca chốt (3a812f6) → chạy cổng. Ô sông = ô GloFAS 0,05° có lưu lượng TB 2016–2025 lớn nhất
trong 5 km, chỉ áp dụng khi TB ≥ 10 m³/s. R-a: lưu lượng lớn nhất trong cửa sổ ≥ P97 của ô. R-b: ≥ P90 VÀ mưa 3 ngày ERA5
≥ P97 của điểm. Chọn ca chỉ dùng WorldCover, mùa v1, lưu lượng TB 10 năm và NGÀY cảnh radar (≤ 6 ngày sau lũ).

Chọn ca: 12 trận bão có ngày công khai → **3 đủ điều kiện** (cần ≥ 4): Hà Tĩnh – Nghệ An có mùa lũ v1 tháng 7–11 nên bão
tháng 8–9 ở đó đã TRONG mùa; Noul 2020, Podul 2019, Noru 2022, Sơn Ca 2017 có ruộng hợp lệ nhưng quỹ đạo radar không có cảnh
≤ 6 ngày sau lũ. Âm tính: Cà Mau và Hà Nội NGOÀI phạm vi (không có ô sông ≥ 10 m³/s trong 5 km) nên giữ nhãn v1.

| Ca | R-a (lưu lượng / P97) | R-b (lưu lượng / P90 · mưa 3 ngày / P97) | Kết quả |
|---|---|---|---|
| Soulik 19/09/2024 — ruộng Huế 16,52; 107,59 (ô sông TB 44,8 m³/s, cách 3,8 km) | 45,2 / 248,5 m³/s (−81,8%) | 45,2 / 103,9 (−56,5%) · 125,7 / 125,2 mm (+0,4%, **biên mỏng**) | trượt cả hai |
| Conson 12/09/2021 — ruộng 15,88; 108,20 (ô sông TB 591,7 m³/s) | — | — | trượt: radar không thấy nước trong [ngày lũ − 3, + 6] |
| Bualoi 29/09/2025 — ruộng Quảng Trị 16,66; 107,30 (ô sông TB 75,3 m³/s) | — | — | trượt: radar không thấy nước trong [ngày lũ − 3, + 6] |
| Âm tính: 17 đợt (Cà Mau 10, Hà Nội 4 — ngoài phạm vi; Phan Rang 3 — trong phạm vi) | 0 bắt nhầm, biên an toàn nhỏ nhất 51% | 0 bắt nhầm, biên an toàn nhỏ nhất 78% | đạt |
| Giữ v1: Huế 10–11/2020, 11/2025 | giữ "trong mùa" | giữ "trong mùa" | đạt |

Kết luận: **trượt cả R-a và R-b** (dương tính 0/3, thiếu ca) → giữ v1. Ở ruộng Huế, sông không lên mức hiếm trong đợt Soulik —
ruộng ngập do mưa tại chỗ, nên lưu lượng sông không phải tín hiệu đúng cho loại ngập này; hai trận còn lại radar không thấy
nước ở điểm ruộng. Ca thật cho phiên bản sau lấy từ người dùng: mỗi câu trả lời "ruộng có ngập thật" rơi vào đợt ngoài mùa
được lưu vào bảng `season_cases` (xem `services/season_cases.py`, `GET /api/admin/season-cases`).

### 7e. Xác nhận TỪNG đợt nước từ người dùng (17/10/2026) — nguồn ca thật, không phải mô hình

Dưới mỗi đợt nước trong "Lịch sử nước nhìn xuyên mây", người đã đăng nhập trả lời **"Ruộng có ngập đợt này không?"**
(Có ngập / Không / Không rõ; một người một câu mỗi đợt ở mỗi ô ~100 m, bấm lại là sửa). Ai cũng thấy số đếm, không ai thấy
người khác trả lời gì (`GET /api/water/confirmations`).

- Lưu ở bảng riêng `water_confirms`, **không** ghi vào bảng quan sát — bảng quan sát nuôi phần hiệu chuẩn ngưỡng cảnh báo
  theo vùng (`services/federated.py`); trộn vào sẽ làm lệch phần đó.
- "Có ngập" ở đợt mà lớp mùa lũ v1 xếp "ngoài mùa" → thêm một ca vào `season_cases` (nguồn `event`) — ca dương tính cho v4.
- "Không" ở một đợt radar → ứng viên báo nhầm của bộ phát hiện đợt nước.
- Quản trị xem tổng hợp (toạ độ làm tròn 0,01°) ở `/admin` → "Xác nhận thực địa"
  (`GET /api/admin/water-confirms`, `GET /api/admin/season-cases`).

**Kiểm thực địa bộ phát hiện — ĐĂNG KÝ TRƯỚC 17/10/2026, trước khi đọc câu trả lời nào**
([`backend/data/eval/water_field_protocol.json`](backend/data/eval/water_field_protocol.json)):

| Bước | Chốt trước |
|---|---|
| Đơn vị | một đợt radar ở một ô ~100 m |
| Câu tính | "có" / "không" (bỏ "không rõ"); bỏ tài khoản quản trị và tài khoản thử; mỗi người tối đa 20 đợt đầu |
| Nhãn đợt | đa số; hoà → loại |
| Cỡ mẫu tối thiểu | ≥ 30 đợt có nhãn, ≥ 10 người, ≥ 3 ô 1° |
| Thước đo | độ chính xác P = đợt "ngập thật" / đợt có nhãn, khoảng Wilson 95% |
| Kết luận | cận dưới ≥ 0,60 → "đã kiểm thực địa"; P < 0,50 → công bố "nhiều báo nhầm", sửa phải đăng ký bản mới; còn lại → chưa kết luận |

```bash
cd backend && python ../ops/water_field_gate.py --status   # tiến độ (không bao giờ ghi)
cd backend && python ../ops/water_field_gate.py            # đủ cỡ mẫu → chấm MỘT lần, ghi data/eval/water_field_result.json
```

Tiến độ công khai: `GET /api/water/field-check` và dòng cuối thẻ "Lịch sử nước" ở `/mo-hinh`. Test:
`backend/tests/test_field_truth.py`.

## 7f. Tổ hợp dự báo mưa best_match + ECMWF AIFS — CỔNG ĐẠT 18/10/2026 (đã bật)

Kế hoạch tổng GĐ5 mục 3. Đăng ký trước [`backend/data/eval/aifs_blend_protocol.json`](backend/data/eval/aifs_blend_protocol.json)
(commit a6950c1, trước khi đọc giá trị mưa nào), script [`ops/aifs_blend_gate.py`](ops/aifs_blend_gate.py) commit trước khi
chạy (ff0aa9e), chấm một lần → `backend/data/eval/aifs_blend_result.json` (kèm từng dòng điểm × ngày để tự tính lại).

```bash
cd backend && python ../ops/aifs_blend_gate.py     # từ chối chạy lại khi tệp kết quả đã có
```

Mưa 3 ngày D+1..D+3 do dự báo phát hành ngày D (Open-Meteo Previous Runs, `precipitation_previous_day1..3`) so với ERA5;
sự kiện = ERA5 ≥ P97 của chính điểm (2016–2025). 9 điểm, ngày phát hành 01/03–28/12/2025, 303 ngày mỗi điểm.

| Mưa 3 ngày ≥ P97 (128 ngày-sự kiện) | POD | FAR | CSI | Sai số TB |
|---|---|---|---|---|
| best_match (trước đây) | 0,289 | 0,439 | 0,236 | 12,7 mm |
| **Tổ hợp (đã bật)** | **0,477** | **0,322** | **0,389** | **9,3 mm** |
| AIFS một mình (tham khảo) | 0,539 | 0,425 | 0,385 | 10,7 mm |

Cổng: FAR giảm VÀ POD không giảm, ≥ 30 ngày-sự kiện trên ≥ 3 điểm → **đạt**. Bật trong `services/realdata.py`
(`weather_7d`, `weather_multi`): một lượt gọi `models=best_match,ecmwf_aifs025_single`, mưa = trung bình (ngày AIFS thiếu →
best_match); ET0, nhiệt độ giữ best_match.

Giới hạn (ghi cả trên thẻ mô hình): sự thật là ERA5, không phải trạm đo; chấm ở mức mưa, chưa ở mức cảnh báo. Ngày-sự kiện
liền nhau không độc lập — gộp thành **50 đợt riêng biệt** (chỉ để mô tả, không quyết định cổng) thì best_match bắt được 17,
tổ hợp 22: **cả hai vẫn bắt chưa tới một nửa** số đợt mưa cực đoan trước 1–3 ngày. Một năm dữ liệu.

## 8. Kiểm một hồ sơ mà không cần tin TerraTwin — CỔNG GĐ4

Một tệp duy nhất, không import mã máy chủ: [`ops/verify_dossier.py`](ops/verify_dossier.py).

```bash
pip install cryptography opentimestamps jsonschema   # opentimestamps chỉ cần cho bước 5, jsonschema cho bước 0
python ops/verify_dossier.py <mã hồ sơ>       # hoặc dán cả đường dẫn https://…/h/<mã>
python ops/verify_dossier.py --file terratwin-ho-so-<mã>.json --offline   # tệp đã tải, không mạng
python ops/verify_dossier.py --file terratwin-ho-so-<mã>.json --offline        --schema backend/data/schema/terratwin-document-1.schema.json        # thêm bước 0 khi không mạng
```

**Định dạng tệp — lược đồ JSON công khai** (draft 2020-12):
[`backend/data/schema/terratwin-document-1.schema.json`](backend/data/schema/terratwin-document-1.schema.json)
(máy chủ phát lại đúng tệp đó ở `GET /api/dossiers/schema`). Một phong bì chung (`id`, `seq`, `issued_at`, `facts`,
`facts_canonical`, `proof`) cho ba loại nội dung: Hồ sơ đất số `terratwin.dossier/1`, Hồ sơ vườn EUDR
`terratwin.eudr-plot/1`, Chứng thư lô hàng `terratwin.lot/1`. Bất biến ghi trong lược đồ: `predictions_included`
luôn là `false`; mỗi mục ghi loại bằng chứng (`measured` / `derived` / `declared` / `predicted`). Hồ sơ đất phát hành
trước 03/10/2026 còn `current_risk` / `track_record` (ảnh chụp dự báo lúc đó) — vẫn đúng định dạng, lược đồ ghi rõ.
Bước 0 của script (tuỳ chọn) lấy lược đồ THẲNG từ GitHub; lệch định dạng chỉ là cảnh báo — bản gốc hay không do các
phép 1–5 quyết định. Đã kiểm 26/26 hồ sơ trong CSDL phát triển (8 hồ sơ đất, 11 hồ sơ vườn, 7 chứng thư) khớp lược đồ;
test `backend/tests/test_doc_schema.py` (+ kiểm trong `test_eudr.py`, `test_trust_infra.py`) bắt tệp sai định dạng.

Năm phép kiểm: (1) SHA-256 nội dung = `facts_hash` và nội dung hiển thị = nội dung đã ký; (2) mục sổ
`terratwin.dossier/1|seq|id|issued_at|facts_hash|prev_hash` băm ra `entry_hash`; (3) chữ ký Ed25519 bằng
khoá ở `/api/dossiers/keys`; (4) chữ ký đầu cây + bằng chứng bao hàm RFC 9162 từ lá của hồ sơ lên gốc
Merkle; (5) neo Bitcoin: mục lục `anchors.json` đọc THẲNG từ nhánh `transparency-log` trên GitHub, hồ sơ
nằm trong gốc cây đã neo, bằng chứng OpenTimestamps tới gốc Merkle của khối Bitcoin (đối chiếu
blockstream.info / mempool.space).

Neo hằng ngày: `.github/workflows/transparency.yml` → `ops/ots_anchor.py` ghi `sth/<n>.txt` (đúng chuỗi đầu
cây đã ký) + `sth/<n>.txt.ots`. Tự kiểm bằng công cụ chuẩn: `ots verify sth/<n>.txt.ots` hoặc tải hai tệp
lên https://opentimestamps.org.

Cổng (test `backend/tests/test_gd4_evidence.py`, chạy trong CI): sửa một ký tự bản hồ sơ → máy chủ và
script độc lập đều báo hỏng; con số bịa trong lời LLM → cả câu bị loại, giữ câu mẫu; mỗi câu mẫu chỉ dùng
số có trong bằng chứng nó dẫn; inclusion proof kiểm bằng thuật toán viết lại độc lập; gốc đã neo lệch sổ
hiện tại → trang hồ sơ báo đỏ.

## 9. Canh đất mỗi ngày — nhật ký thửa, so sánh thửa, cảm biến (GĐ6)

Nhật ký thửa (`backend/app/services/plot_journal.py`, `GET /api/plots/{id}/journal`) dựng khi mở từ dữ liệu
sẵn có: cảnh báo + kết quả chấm, câu trả lời/quan sát, ảnh thực địa, số đo cảm biến đã ký, mưa ngày
(Open-Meteo), cảnh radar Sentinel-1 mới (so với nền của chính thửa nếu đã đọc lịch sử nước). Chỉ bật cờ
"thay đổi thật" khi: mưa ≥ 50 mm/ngày, radar thấy nước, cảnh báo mới/kết quả chấm, câu trả lời/ảnh của
người dùng, cảm biến vượt ngưỡng nhắc (đất khô < 20%, mặn ≥ 4‰). Ngưỡng cố định trong mã.

Phát lại 7 ngày trên dữ liệu thật — `cd backend && python ../ops/journal_gate.py 7`. Chạy 9/10/2026, 6 thửa
(Huế, Cần Thơ, Hà Nội, Lâm Đồng, Cà Mau, Quảng Nam): **1 sự kiện bật cờ** (mưa rất to 95 mm ở Điện Bàn
ngày 8/10), 14 sự kiện bối cảnh (mưa to 16–50 mm, ảnh radar mới), **0 sự kiện rác**. Đây là phát lại, chưa
phải 7 ngày chạy sống. Lượt SỐNG hằng ngày chạy từ 10/10/2026 trong `.github/workflows/journal-live.yml`, ghi từng
ngày vào nhánh `journal-log` (`journal.jsonl` + `SUMMARY.txt`); `python ../ops/journal_gate.py --summary journal.jsonl`
báo ĐẠT khi đủ 7 ngày sống, 0 rác.

Cảm biến: số đo đã ký Ed25519 hiện trên nhật ký ở lượt gọi nhanh kế tiếp (giao diện gọi `?fast=1` mỗi 5 giây
khi thẻ đang mở) — test `test_so_do_cam_bien_hien_ngay_tren_nhat_ky_va_man_vuot_nguong`. Trình diễn cốc nước
muối không cần phần cứng: `python ops/iot_simulator.py --email … --password … --lat … --lon … --count 1
--salinity 35`.

So sánh 2–4 thửa: `/so-sanh` (`POST /api/compare`), mỗi tiêu chí đánh dấu giá trị thuận lợi nhất theo riêng
tiêu chí đó; không điểm tổng. Đối chiếu ba chiều: câu trả lời "ruộng có ngập" ↔ radar ±6 ngày ↔ mưa 3 ngày →
khớp / khớp một phần / lệch / chưa đủ dữ liệu. Nhận nước trong ẢNH bằng SegFormer cần mô hình qua cổng GĐ5 —
chưa bật.

## 10. Loại đất bằng AlphaEarth — CỔNG GĐ5 (mục 1) ĐẠT 10/10/2026

Giao thức đăng ký trước: `backend/data/ml/aef_landcover_protocol.json` (commit 0f1997d, TRƯỚC khi tải vectơ). Cùng
nhãn ESA WorldCover 2021 (213 ô của U-Net lần 2) và cùng chia tỉnh: kiểm tra Cần Giờ, Cần Thơ, Hà Giang, Đà Nẵng ·
kiểm định Buôn Ma Thuột, Huế.

```bash
cd backend
python -m app.dl.fetch --seasons 2 --out data/dl2        # nếu chưa có bộ nhãn (xem app/dl/fetch.py)
python -m app.ml.aef_landcover extract                    # ~1 giờ, tiếp tục được nếu đứt
python -m app.ml.aef_landcover train                      # chọn L2 trên kiểm định, chấm kiểm tra MỘT lần
```

Kết quả (ghi trong `backend/data/landcover_runs.json`, lần 3): **mIoU 0,420** trên tỉnh giữ lại (ngưỡng 0,35; U-Net
0,232 và 0,314), kiểm định 0,463, đúng 84% điểm ảnh; IoU từng lớp: mặt nước 0,975 · tán cây 0,773 · xây dựng 0,638 ·
**trồng trọt 0,578** · đất trống 0,367 · đồng cỏ 0,342 · rừng ngập mặn 0,106 · cây bụi 0 · đất ngập nước 0. Chấm trên
1.024 điểm ảnh ngẫu nhiên mỗi ô (49.152 điểm ảnh kiểm tra). 4 tỉnh kiểm tra đã dùng cho U-Net lần 1–2; đây là lần
chấm cuối trên bộ tỉnh này. Bật: `GET /api/landcover/change` (2021 so với năm mới nhất, nhóm đổi ≥ 25 điểm % mới
gọi là đổi khác) — dự đoán, không vào hồ sơ ký.

## 11. Nước trên ảnh radar bằng học sâu (U-Net, Sen1Floods11) — CỔNG GĐ5 (mục 2) ĐẠT 18/10/2026, CHƯA bật

Giao thức đăng ký trước 09/10/2026 cùng commit với script (6d9cfb4): [`backend/data/ml/gd5_protocol.json`](backend/data/ml/gd5_protocol.json)
mục `s1_water`. Chạy đúng một lần trên GPU Kaggle (2× Tesla T4, 40 vòng, 1.124,6 s), script tải theo đúng commit và kiểm
SHA-256 `c48956dc…31cf6f` trước khi chạy. Kết quả chép nguyên văn: [`backend/data/ml/s1_water_result.json`](backend/data/ml/s1_water_result.json).

```bash
# trên notebook Kaggle (GPU T4, Internet bật) — đúng ô lệnh đã chạy
!wget -q -O s1_water_seg.py https://raw.githubusercontent.com/annguyen210/TerraTwin/6d9cfb45085dca995bdc027b7892f41be3ee7f2a/ml/kaggle/s1_water_seg.py \
  && echo "c48956dcc673acf450e92762ccbba40e0444e7fec7076e45d80fa8b52731cf6f  s1_water_seg.py" | sha256sum -c \
  && pip -q install rasterio onnx && nvidia-smi -L && python s1_water_seg.py --out /kaggle/working/s1_water_result.json
```

Chọn mô hình CHỈ bằng tập valid (tốt nhất vòng 31, IoU 0,6457); test, Bolivia, Mekong chấm một lần ở cuối:

| IoU lớp nước | U-Net | Ngưỡng −18 dB (đang dùng ở GĐ2) | Otsu theo ô |
|---|---|---|---|
| Test (90 ô) | **0,668** | 0,443 | 0,209 |
| Bolivia (15 ô — sự kiện giữ lại hoàn toàn) | **0,681** | 0,324 | 0,307 |
| Mekong (6 ô — gần Việt Nam nhất) | **0,851** | 0,696 | 0,299 |

Cổng (mô hình > ngưỡng −18 dB trên CẢ BA) → **đạt**. Theo đúng giao thức, đạt mới là bước 1: **chưa bật**. Lịch sử nước của
thửa hiện đọc THỐNG KÊ phân vị từng cảnh trên khung thửa (Planetary Computer `/item/statistics`), không đọc ảnh điểm ảnh;
muốn dùng mô hình phải đọc ảnh VV/VH của khung thửa cho từng cảnh, chạy mô hình, rồi qua lại cổng GĐ2 (`ops/water_gate.py`:
lũ Huế 10/2020, miền Trung 10/2025 thấy nước đúng tuần; đất cao 0 đợt). Lượt Kaggle đầu (Version 1) bị kẹt hàng đợi GPU
38 phút và được huỷ khi CHƯA chạy dòng nào; Version 2 là lượt duy nhất được chấm. Xuất ONNX lỗi (thiếu `onnxscript` trên
ảnh Kaggle) — không ảnh hưởng kết quả; trọng số `s1_water_unet.pt` nằm trong Output của notebook.

## 12. Nước trong ẢNH THỰC ĐỊA (SegFormer-b0) — CỔNG ĐẠT 18/10/2026, CHƯA bật

Giao thức đăng ký trước khi huấn luyện, cùng commit với script (2e44cb0):
[`backend/data/ml/field_water_protocol.json`](backend/data/ml/field_water_protocol.json). Dữ liệu: Kaggle
`faizalkarim/flood-area-segmentation` v1 (CC0), 290 ảnh lũ + mặt nạ nhãn tay; chia cố định 70/15/15 theo hạt giống 20261018
(204 · 43 · 43, danh sách tên tệp từng tập nằm trong kết quả). Chạy đúng một lần trên GPU Kaggle (2× T4, 40 vòng, 520,8 s),
script tải theo commit và kiểm SHA-256 `91813015…4a42d655`. Kết quả chép nguyên văn:
[`backend/data/ml/field_water_result.json`](backend/data/ml/field_water_result.json) — danh sách chia tập đã được kiểm lại
bằng cách chạy lại đúng phép chia của script.

```bash
# trên notebook Kaggle (GPU T4, Internet bật, gắn dataset flood-area-segmentation) — đúng ô lệnh đã chạy
!wget -q -O field_water_seg.py https://raw.githubusercontent.com/annguyen210/TerraTwin/2e44cb094bd1bbad8c17e25a8f74eb594e72b16c/ml/kaggle/field_water_seg.py   && echo "918130157568b66e9385e5585b005df4c77d86134ffb17839ed4f1594a42d655  field_water_seg.py" | sha256sum -c   && pip -q install onnx onnxscript && nvidia-smi -L && python field_water_seg.py --out /kaggle/working/field_water_result.json
```

| IoU lớp nước trên TEST (43 ảnh, chấm một lần) | Giá trị | Cổng |
|---|---|---|
| SegFormer-b0 (chọn bằng valid: vòng 38, IoU valid 0,8437) | **0,816** | ≥ 0,70 |
| Đường cơ sở màu HSV (không học) | 0,4285 | mô hình phải hơn |

Cổng → **đạt**. Theo giao thức: nếu bật thì chỉ là tín hiệu THAM KHẢO (tỉ lệ điểm ảnh nước trong ảnh thực địa) trong đối chiếu
ba chiều, không vào nội dung ký, không thay câu trả lời của người dùng. Giới hạn đã viết trước: ảnh lũ nhiều nước, nhiều ảnh
chụp từ trên cao — đạt cổng không chứng minh đúng trên ruộng Việt Nam. Lượt Kaggle đầu (Version 1) kẹt hàng đợi GPU và được
huỷ khi CHƯA chạy dòng nào; Version 2 là lượt duy nhất được chấm. Trọng số `.pt` và `.onnx` nằm trong Output của notebook.

## 13. Kiểm tin đăng (cổng GĐ3) trên tin đất THẬT — trượt 2 lần (18/10), ĐẠT lần 3 (19/10/2026)

Nguồn: bộ công khai Hugging Face `tinixai/vietnam-real-estates` (CC BY-NC 4.0, số điện thoại đã bị xoá sẵn), revision
`ca3fedcb…`. Mỗi lần: đăng ký trước một shard + hạt giống + quy tắc gán nhãn + ngưỡng (F1 trung bình ≥ 0,80), lấy 40 tin
"Đất", **Claude gán nhãn theo uỷ quyền chủ dự án — không phải nhãn người** — commit nhãn TRƯỚC khi chạy bộ tách câu, chấm
một lần. Repo chỉ giữ chỉ số hàng + SHA-256 mô tả + nhãn (không chép nguyên văn tin).

```bash
pip install pyarrow
# tải shard_0000.parquet / shard_0001.parquet tại revision ca3fedcbb089bf65f7e4cfb03316cce4bd0d779f
python ops/listing_gate_hf.py score shard_0000.parquet 1    # cần luật của commit d1c8940
python ops/listing_gate_hf.py score shard_0001.parquet 2    # luật của commit d751942
python ops/listing_gate_hf.py score shard_0002.parquet 3    # luật của commit dbd1c85
```

| Lần | Giao thức → nhãn → chấm | F1 trung bình | Từng loại (F1) |
|---|---|---|---|
| 1 — shard_0000, hạt giống 20261019 | c974060 → d1c8940 | **0,58** (trượt) | thổ cư 0,90 · gần biển 0,40 · gần sông 0 · cao ráo 1,0 |
| 2 — shard_0001, hạt giống 20261020, luật sửa theo lỗi lần 1 | d751942 → c810876 | **0,72** (trượt) | thổ cư 1,0 (8/8, 0 bắt nhầm) · gần sông 0,67 · gần biển 0,50 |
| 3 — shard_0002, hạt giống 20261021, thêm cách nói vòng theo lỗi lần 2 | dbd1c85 → 02ba524 | **0,99** (ĐẠT) | gần biển 1,0 (7/7) · thổ cư 0,97 (15/15, 1 bắt nhầm) · gần sông, cao ráo, bằng phẳng 1,0 nhưng mỗi loại chỉ 1 câu |

Đọc kết quả: luật từ khoá gần như **không bắt nhầm** (độ chính xác 1,0 mọi loại ở lần 2) nhưng **sót cách nói vòng** ("gió
sông rất mát", "đi biển 10 phút", "bên bờ vịnh"). Mẫu ngẫu nhiên rất ít câu "không ngập / gần sông" nên F1 các loại hiếm dao
động mạnh. Lần 3 thêm cách nói vòng theo lỗi lần 2 và đạt trên mẫu mới. Cần đọc đúng mức: đây là lần thử THỨ BA (nguy cơ "thử tới khi đạt"),
nhãn do AI gán, và các loại hiếm mỗi loại chỉ 1 câu — muốn chắc hơn phải có nhãn người ở /admin → Tin đăng GĐ3 hoặc mẫu lớn hơn. Lần chạy thử luật lần 2 trên mẫu lần 1 từng ghi đè nhầm tệp kết quả lần 1;
tệp đã được tạo lại bằng đúng luật d1c8940 (số liệu trùng lần chấm đầu) và ghi chú trong tệp.

## Nếu một bước không ra kết quả

- **Gọi mạng hụt / rate-limit Open-Meteo**: các endpoint mục 1–3 gọi API thời
  tiết công khai; nếu bị giới hạn tần suất, chờ rồi chạy lại. `GET /api/health`
  cho biết nguồn nào đang bị chặn vì quá hạn mức.
- **Sổ điểm trống**: đúng như mục 4 — không phải lỗi.
- **Test đỏ vì mạng**: hiếm; CI có `--reruns` cho các test cố ý gọi API thật.
  Bộ test lõi chạy offline và phải xanh 100%.
