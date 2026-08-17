# 🛰️ TerraTwin

**Bản sao số (digital twin) của đất đai Việt Nam** — nhìn đất thật từ vệ tinh → mô phỏng → dự đoán kiểm chứng được → khuyến nghị hành động. Một lõi Twin, phủ 14 mũi nhọn.

Ba chữ cốt lõi: **CỦA MÌNH** (từng thửa) · **BIẾT TRƯỚC** (kịp hành động) · **BẰNG CHỨNG THẬT** (vệ tinh/thời tiết, kiểm chứng được — không phỏng đoán).

> Phạm vi phục vụ: **lãnh thổ Việt Nam**. Toạ độ ngoài vùng bị từ chối (HTTP 422).

---

## Trạng thái dữ liệu (minh bạch)

Mỗi kết quả gắn cờ rõ ràng 🛰️ **Dữ liệu thật** hoặc 🧪 **Ước lượng/chờ dữ liệu**, kèm khoảng tin cậy. **Không hứa 100%.**

| Nhóm | Module | Nguồn |
|---|---|---|
| 🛰️ Dữ liệu thật (8) | hạn, cháy rừng, **lũ/ngập**, sạt lở, rủi ro mua đất, bảo hiểm tham số, điện mặt trời, **ao nuôi** | Open-Meteo (mưa/ET₀/nhiệt/cao độ/**độ dốc DEM**), **GloFAS lưu lượng sông**, **Open-Meteo Marine**, NASA POWER |
| 🧪 Ước lượng vật lý (1) | xâm nhập mặn | bờ biển VN (34 điểm) + cao độ DEM + **chu kỳ mùa khô/mùa lũ** + triều (**chờ hiệu chỉnh MRC**) |
| ⏳ Chờ ảnh Sentinel (5) | sâu bệnh, năng suất, carbon, thiệt hại bão, xây dựng trái phép | kiến trúc sẵn sàng — KHÔNG bịa số khi chưa có ảnh |

**Hai nguồn thật mới (miễn phí, không cần API key):**
- **GloFAS lưu lượng sông** (Open-Meteo Flood API) — mưa là *nguyên nhân*, lưu lượng sông mới là thứ trực tiếp gây ngập. Đây là tín hiệu đối chứng **độc lập** cho module Lũ; API trả sẵn cả trung bình khí hậu nên tỉ số `discharge/mean` đã chuẩn hoá theo từng con sông. Hai nguồn độc lập cùng chỉ một hướng ⇒ độ tin cậy 0,75 → 0,83.
- **Open-Meteo Marine** — nhiệt mặt nước & sóng, đưa module **Ao nuôi** từ ⏳ lên dữ liệu thật, dùng ngưỡng tôm sú/thẻ chân trắng (tối ưu 28–32 °C · stress ≥33,5 °C · chậm lớn ≤25 °C · sóng ≥2 m đe dọa lồng bè). Ao nội đồng không có dữ liệu biển → vẫn báo thật là chưa đủ dữ liệu, không bịa số.

> **Phạm vi module Mặn:** xâm nhập mặn *nông nghiệp* ở **ĐBSCL** và **ĐB sông Hồng**.
> Ngoài hai vùng đó (Đà Nẵng, Nha Trang, Hạ Long…) module trả `out_of_scope` thay vì
> áp ngưỡng mặn của cây lúa. Mô hình có **mùa vụ**: đỉnh ~15/3 (mùa khô, sông cạn),
> đáy ~15/9 (lũ đẩy mặn ra biển) — tỉ lệ khô/mưa ở Bến Tre ≈ **6,2×**.

**Tính năng thật đã có:** TerraScore (chỉ chấm từ hiểm họa dữ liệu thật) · Quét toàn cảnh 14 module · **Backtest lịch sử ERA5** (đo lead time 4 thiên tai VN có thật) · **What-If / Parallel Futures** · **Causal Explain** · **Goal-Seek** · **Time Machine** · **Anomaly** · Danh mục thửa đất + xuất báo cáo · Copilot (rule-based, bật LLM nếu có key) · bản đồ nền ảnh vệ tinh thật.

### Phân tích sâu — 4 luồng nâng cao (mới)

| Luồng | Trả lời câu hỏi | Cách làm |
|---|---|---|
| 🧠 **S07 Causal Explain** | *Vì sao chỉ số cao?* | Mô hình là hàm thuần → tắt từng yếu tố, chạy lại, chênh lệch **chính là** đóng góp. Leave-one-out chính xác, không xấp xỉ kiểu SHAP |
| 🎯 **S03 Goal-Seek** | *Cần gì để an toàn? Còn chịu được bao nhiêu?* | Tìm kiếm nhị phân 40 vòng đảo ngược chính mô hình cảnh báo; có phương án **kết hợp** khi không đòn bẩy đơn lẻ nào đủ |
| ⏳ **S02 Time Machine** | *Xác suất vượt ngưỡng là bao nhiêu?* | **Analog ensemble**: cùng cửa sổ lịch của 10 năm THẬT (ERA5) tại chính toạ độ đó — mỗi con số truy ngược được về một năm có thật, không có phân phối giả định |
| 📈 **C10 Anomaly** | *Tuần này có bất thường không?* | z-score so với khí hậu nền ERA5 cùng ngày/tháng, 10 năm, tại chính toạ độ đó |

Cả 4 đều đi qua lõi chung `services/hazard.py` nên chạy **đúng mô hình** đang dùng cho dự báo — không có model thứ hai lệch pha.

---

## Độ chính xác — công bố cả hai chiều

Lead time một mình là **vô nghĩa**: một model luôn hét "nguy hiểm" cũng bắt trúng
mọi thảm họa nổi tiếng. Vì vậy TerraTwin công bố lead time **kèm tỉ lệ báo động**.

**Bệnh đã tìm ra và đã sửa.** Thang tuyệt đối cũ bão hòa ở vùng mưa nhiều
(`min(100, …)` chạm trần), khiến mức nguy hiểm nổ gần như quanh năm:

| Điểm | Module | Tỉ lệ báo NGUY HIỂM (năm 2022) | Sau hiệu chuẩn |
|---|---|---|---|
| Huế | flood | **45,8%** | **3,0%** |
| Quảng Nam | flood | **60,6%** | **3,0%** |
| Trà Leng | landslide | 13,7% | 3,0% |
| Bến Tre | drought | 0,0% | 3,0% |

**Cách sửa** (`services/calibration.py`): tách động lực vật lý thô (không chặn trần)
khỏi việc chấm điểm, rồi quy về **phân vi so với khí hậu 10 năm của chính điểm đó**
(ERA5), ánh xạ về thang 0–100 quen thuộc — P90→40, P97→70. Tỉ lệ báo động vì thế
là **thuộc tính thiết kế**, không phải may rủi. Kèm **chốt tuyệt đối**: phân vi cao
mà động lực vật lý quá nhỏ thì vẫn an toàn (tránh "cực đoan so với hư không" ở
vùng khô). Đây chính là moat §13: ngưỡng bản địa hóa tới từng thửa.

**Kết quả kiểm chứng trên 4 thiên tai VN có thật** (Open-Meteo Archive / ERA5):

| Sự kiện | Cảnh báo (P90) | Nguy hiểm (P97) |
|---|---|---|
| Lũ lịch sử Huế 10/2020 | báo trước **4 ngày** | trước 3 ngày |
| Lũ Quảng Nam – Đà Nẵng 10/2022 | báo trước **4 ngày** | trước 0 ngày |
| Sạt lở Trà Leng 10/2020 | báo trước **8 ngày** | trước 0 ngày |
| Hạn – mặn Bến Tre mùa khô 2020 | báo trước **12 ngày** | trước 12 ngày |
| **Tỉ lệ báo động** | **~10%** số cửa sổ | **~3%** |

> Hai tầng có vai trò khác nhau: **Cảnh báo** cho lead time để chuẩn bị;
> **Nguy hiểm** nổ sát sự kiện, nghĩa là "hành động ngay". So với bản trước
> (lead 5/5/8/10 nhưng báo động 46–61% số ngày), bản này lead ngắn hơn chút
> nhưng **ít báo động giả hơn ~15–20 lần** — và mọi con số đều kiểm chứng lại được.

---

## Tài khoản & dữ liệu người dùng

Đăng ký/đăng nhập bằng email + mật khẩu (bcrypt có salt, JWT). **Danh mục thửa
đất nay nằm trong database, không còn localStorage** — đồng bộ đa thiết bị,
không mất khi xóa trình duyệt, và phân tách theo từng người dùng nên bán được B2B.

| Endpoint | Việc |
|---|---|
| `POST /api/auth/register` · `POST /api/auth/login` · `GET /api/auth/me` | Tài khoản |
| `GET/POST /api/plots` · `DELETE /api/plots/{id}` | Danh mục thửa đất |
| `GET/POST /api/keys` · `DELETE /api/keys/{id}` | Khóa Twin API (C12) |
| `POST /api/datasets` · `POST /api/datasets/{id}/score` | Tải CSV/GeoJSON của bạn lên, chấm rủi ro hàng loạt (C11) |
| `POST /api/radar/run` · `GET /api/alerts` | Quét lại mọi thửa đã lưu, sinh cảnh báo mới (C05/S08) |
| `POST /api/heatmap/{id}` | Lưới rủi ro quanh thửa (C06) |

### Cài lên điện thoại (PWA)

Mở `http://…` trên điện thoại → menu trình duyệt → **Thêm vào màn hình chính**.
Ứng dụng chạy toàn màn hình như app thật, có icon riêng.

Service worker **cố ý KHÔNG cache phản hồi `/api/`** — đây là hệ thống cảnh báo
thiên tai, phục vụ lại một cảnh báo cũ còn nguy hiểm hơn là báo mất mạng. Chỉ
vỏ ứng dụng được cache; mất mạng thì hiện trang offline giải thích rõ lý do.

**Twin API cho bên thứ ba:** tạo khóa rồi gọi mọi endpoint bằng header
`X-API-Key: tt_…` thay cho JWT. Khóa chỉ lưu **hash** — lộ database vẫn không
dùng lại được; bản rõ chỉ hiện đúng một lần lúc tạo; thu hồi có hiệu lực ngay.

**Đã xử lý trong phần bảo mật:**
- Mật khẩu băm bcrypt, không bao giờ lưu bản rõ; mật khẩu >72 byte được SHA-256
  trước khi băm để bcrypt không cắt cụt (nếu không, hai mật khẩu dài khác nhau
  có thể đăng nhập lẫn cho nhau).
- Đăng nhập sai trả **cùng một thông báo** cho email không tồn tại và mật khẩu
  sai — không để dò xem email nào đã đăng ký.
- Thao tác lên tài nguyên của người khác trả **404 chứ không phải 403** — không
  xác nhận ID đó có tồn tại.
- Secret JWT lấy từ `TERRATWIN_SECRET`; thiếu thì sinh ngẫu nhiên mỗi lần chạy
  và **in cảnh báo**, thay vì hardcode một giá trị mặc định.

> Database mặc định là SQLite (chạy ngay, không cần cài gì). Đổi sang PostgreSQL
> chỉ bằng `TERRATWIN_DATABASE_URL` — code không đổi.

---

## Kiến trúc: 1 Lõi + 14 Module
```
terratwin/
├── backend/                      # Python + FastAPI
│   └── app/
│       ├── main.py               # API + CORS/rate-limit theo env
│       ├── schemas.py            # kiểu dữ liệu + validate Location
│       ├── db.py                 # SQLAlchemy: users, plots, api_keys,
│       │                         #   datasets, kv_cache, alerts
│       ├── auth.py               # bcrypt + JWT + API key
│       ├── routes_account.py     # đăng ký/đăng nhập, thửa đất, khóa API
│       ├── services/             # realdata, datasources, calibration, hazard,
│       │                         #   terrascore, scan, whatif, explain,
│       │                         #   goalseek, timemachine, anomaly,
│       │                         #   backtest, copilot, twin
│       └── modules/              # base + util + 14 module + registry
│   └── tests/                    # pytest (114 test, offline & tất định)
├── frontend/                     # Next.js 14 + MapLibre
│   └── components/               # MapView, ResultsPanel, Overview, WhatIf,
│                                 #   Backtest, Portfolio, Copilot
├── .github/workflows/ci.yml      # CI: pytest + tsc + next build
└── docker-compose.yml
```
Mô hình chỉ số (`flood_index`/`drought_index`/`landslide_index`/`wildfire_index`) là **hàm thuần dùng chung** cho cả forecast, what-if và backtest — đây là lý do backtest kiểm chứng được đúng model đang chạy.

---

## Chạy nhanh

### Cách A — Docker (khuyến nghị)
```bash
docker compose up --build
# Frontend: http://localhost:1825  ·  API docs: http://localhost:8000/docs
```

### Cách B — Local
```bash
# Backend (Python 3.12)
cd backend
python -m venv .venv && .venv\Scripts\activate      # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --port 8000

# Frontend (Node 18+) — cửa sổ khác
cd frontend
npm install
npm run dev -- -p 1825      # http://localhost:1825
```

### Test
```bash
cd backend
pip install -r requirements-dev.txt
pytest                      # 114 test, chạy offline & tất định
```

---

## Cấu hình (biến môi trường — xem `.env.example`)
| Biến | Ý nghĩa | Mặc định |
|---|---|---|
| `TERRATWIN_CORS` | origin cho CORS (phân tách dấu phẩy) | `*` |
| `TERRATWIN_RATE_LIMIT` | request/phút mỗi IP (0 = tắt) | `120` |
| `TERRATWIN_SECRET` | **bắt buộc khi deploy** — khóa ký JWT | (ngẫu nhiên mỗi lần chạy + cảnh báo) |
| `TERRATWIN_TOKEN_HOURS` | hạn token đăng nhập | `72` |
| `TERRATWIN_DATABASE_URL` | chuỗi kết nối database | `sqlite:///./terratwin.db` |
| `ANTHROPIC_API_KEY` | bật Copilot LLM thật | (trống → rule-based) |
| `NEXT_PUBLIC_API` | URL backend cho frontend | `http://localhost:8000` |

## API (cổng 8000)
`GET /api/health` · `GET /api/modules` · `POST /api/assess/{id}` · `POST /api/terrascore` · `POST /api/scan` · `POST /api/whatif/{id}` · `POST /api/explain/{id}` · `POST /api/goalseek/{id}` · `POST /api/timemachine/{id}` · `POST /api/anomaly` · `POST /api/copilot` · `POST /api/twin` · `GET /api/backtest[/{event}]` · `/docs`

> 4 endpoint `explain` / `goalseek` / `timemachine` / `whatif` chỉ nhận module hiểm
> họa thời tiết: `drought`, `flood`, `wildfire`, `landslide` (khác → HTTP 404).

## Thêm module mới
1. Tạo lớp con `TwinModule` trong `backend/app/modules/`, viết `assess()`.
2. Đăng ký ở `registry.py`. Frontend tự hiện.

## Lộ trình
- **Đã có:** 8 module dữ liệu thật · hiệu chuẩn theo khí hậu từng điểm (FAR ~3%) ·
  backtest hai tầng · what-if · explain · goal-seek · time machine · anomaly ·
  **database + đăng nhập** · danh mục thửa đất trên máy chủ · Twin API key.
- **Tiếp theo:** tích hợp ảnh Sentinel (bật 5 module còn lại) · cắm dữ liệu mặn
  MRC để hiệu chỉnh module Mặn · heatmap & Twin Genome (dùng `kv_cache` đã dựng) ·
  Proactive Radar gửi cảnh báo Zalo/email (bảng `alerts` đã dựng) · deploy cloud.

## License
MIT — xem [LICENSE](LICENSE).
