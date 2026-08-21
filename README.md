# 🛰️ TerraTwin

**Bản sao số (digital twin) của đất đai Việt Nam** — nhìn đất thật từ vệ tinh → mô phỏng → dự đoán kiểm chứng được → khuyến nghị hành động. Một lõi Twin, **18 mũi nhọn phủ đủ 12/12 ngành**.

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

**Tính năng thật đã có:** TerraScore (chỉ chấm từ hiểm họa dữ liệu thật) · Quét toàn cảnh mọi mũi nhọn trong ~2,5 giây · **Backtest lịch sử ERA5** (đo lead time 4 thiên tai VN có thật) · **What-If / Parallel Futures** · **Causal Explain** · **Goal-Seek** · **Time Machine** · **Anomaly** · Danh mục thửa đất + xuất báo cáo · Copilot (rule-based, bật LLM nếu có key) · bản đồ nền ảnh vệ tinh thật.

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
| `POST /api/ask` · `GET /api/llm` | Hỏi What-If bằng lời (C03) · trạng thái LLM |
| `POST /api/genome` · `POST /api/genome/warm` | Tìm vùng "song sinh" (S04) |
| `POST /api/twin` · `GET/POST /api/twins` | Dựng & lưu bản sao số đầy đủ (C01) |
| `GET/POST /api/channels` · `POST /api/channels/{id}/test` | Kênh nhận cảnh báo: webhook, email (U01) |
| `GET /api/roadmap` | **Trạng thái thật của 26 luồng** — sinh từ mã nguồn |

### 🧬 S04 Twin Genome — tìm vùng giống thửa của bạn

Mỗi vị trí có một **bộ gen** 7 đặc trưng đo được: cao độ · độ dốc · cách biển ·
mưa cả năm · tỉ lệ mưa mùa khô · nhiệt tối đa · **biên độ nhiệt mùa**. Lưới tham
chiếu 180 ô đất liền phủ Việt Nam, dựng từ ERA5 — chuẩn hoá rồi tìm láng giềng
gần nhất.

> Bến Tre (6 m, biên độ 4,8 °C) → khớp Kiên Giang 1 m · Bạc Liêu 1 m · Cần Thơ 6 m
> Sa Pa (1563 m, biên độ **11,2 °C**) → khớp núi phía Bắc, **không** phải Đà Lạt

Đặc trưng **biên độ nhiệt mùa** là thứ phân biệt Bắc/Nam: Sa Pa và Đà Lạt cao gần
bằng nhau nhưng biên độ 11,2 °C so với 5,5 °C, nên thuật toán không lẫn.

Cao độ · độ dốc · cách biển được **log-hoá** trước khi chuẩn hoá. Nếu không, trên
thang 0–3000 m thì 6 m và 52 m gần như bằng nhau — trong khi với nông dân ĐBSCL
đó là khác biệt sống còn về ngập.

> ⚠️ Lưới ~0,75° (≈80 km) nên tìm được **vùng** tương đồng, không phải thửa giống
> hệt. Khí hậu lấy từ **một năm tham chiếu (2023)**, không phải chuẩn 30 năm.
> Lần dựng lưới đầu mất ~2–3 phút; gọi `POST /api/genome/warm` để dựng sẵn (cache 30 ngày).

### Trợ lý LLM — cắm key nào cũng chạy

TerraTwin **không phụ thuộc một nhà cung cấp AI nào**. Đặt `TERRATWIN_LLM_API_KEY`
(và `TERRATWIN_LLM_BASE_URL` nếu không dùng OpenAI) là xong — hỗ trợ **OpenAI ·
Gemini · DeepSeek · Groq · OpenRouter · Together · xAI · Qwen · Mistral ·
Anthropic**, và cả **Ollama chạy trên máy** (miễn phí, không cần key). Xem
[.env.example](.env.example) để có sẵn URL từng nhà cung cấp.

**Không có key vẫn dùng được đầy đủ** — chỉ khác ở phần diễn đạt:

| Tính năng | Không key | Có key |
|---|---|---|
| 🗣️ **C03 What-If bằng lời** | Bộ luật tiếng Việt bắt các mẫu hỏi thông dụng ("mưa gấp đôi", "giảm 60%", "nóng thêm 3 độ") — có dấu hoặc không dấu | Hiểu thêm câu hỏi tự do |
| 💬 Copilot | Trả lời bám sát dữ liệu module | Diễn đạt tự nhiên hơn |

> **Ranh giới quan trọng:** LLM **chỉ được dịch câu hỏi thành tham số mô phỏng**.
> Mọi con số đều do mô hình vật lý tính trên nền thời tiết thật — có test chứng
> minh rằng một LLM cố tình trả về con số bịa cũng **không** chèn được vào kết quả.

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
│       └── modules/              # base + util + 18 mũi nhọn (nhóm A–D) + registry
│   └── tests/                    # pytest (217 test, offline & tất định)
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
pytest                      # 217 test, chạy offline & tất định
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

## Chạy song song — nguyên lý 02 của bản thiết kế

Bản thiết kế đặt "Song song & đồng thời" thành nguyên lý bắt buộc. `services/jobs.py`
làm bốn việc, không thêm phụ thuộc nào (gói miễn phí không có chỗ chạy Redis/Celery):

| Vấn đề thật | Cách giải | Đo được |
|---|---|---|
| Quét toàn cảnh gọi từng mô-đun nối tiếp | chạy đồng thời | **13,1 s → 2,5 s** |
| Lưới 180 ô / 11×11 chia lô rồi chờ từng lô | các lô chạy cùng lúc | 250 điểm trong ~1 s |
| Nhiều người hỏi cùng toạ độ ⇒ nhiều lượt gọi giống hệt | gộp thành một (`single_flight`) | 6 lời gọi → 1 |
| Không có trần lượt gọi ra ngoài ⇒ nguồn free chặn IP | semaphore toàn tiến trình | `TERRATWIN_UPSTREAM_CONCURRENCY` |
| Việc dài (dựng lưới bộ gen 1–2 phút) giữ kết nối HTTP tới lúc proxy cắt | hàng đợi + `GET /api/jobs/{id}` | trả mã việc ngay |

**Nói rõ giới hạn:** đây là song song TRONG MỘT TIẾN TRÌNH. Hàng đợi nằm trong bộ
nhớ nên restart là mất, và gộp việc trùng chỉ gộp trong cùng tiến trình. Phân tán
thật cần hàng đợi bền bên ngoài — việc của lúc có tải thật, không phải bây giờ.

**Mô-đun "nặng"** (`heavy = True`) bị loại khỏi lượt quét toàn cảnh và khỏi việc
dựng Twin, vì chúng quét cả một vùng chứ không riêng thửa. Phần bị bỏ qua được
khai báo trong `skipped_heavy`, không giấu.

## Lũ đến từ mưa rơi Ở TRÊN CAO

Cho tới gần đây, module Lũ chỉ nhìn lượng mưa rơi trên **chính thửa đó**. Nhưng
Trà Leng 2020 không sập vì mưa tại chỗ — mà vì cả sườn núi phía trên đã ngậm
nước. Một mảnh đất có thể khô ráo suốt buổi sáng rồi ngập trong một giờ vì
chuyện xảy ra cách đó mười cây số về phía núi.

`services/catchment.py` lấy mẫu **8 hướng × 3 vòng (3/7/12 km)**, giữ lại những
điểm cao hơn thửa, cân theo độ dốc về phía thửa, rồi so mưa thượng nguồn với
mưa tại chỗ. Nó chỉ báo động khi thượng nguồn mưa **nhiều hơn hẳn** tại chỗ —
mưa đều cả vùng thì module Lũ đã bắt rồi, báo thêm chỉ làm tăng báo động giả.

**Và nó từ chối trả lời ở đồng bằng.** Chênh cao ở Bến Tre đo được 13 m trong
bán kính 12 km — nằm trong sai số đứng của DEM toàn cầu. Ở đó nước đi đâu là do
đê bao, cống và kênh quyết định, không do độ dốc; phần mềm nói thẳng điều đó
thay vì trả một con số trông có vẻ chính xác.

Đo thật: Trà Leng chênh cao 1194 m, 16/24 điểm cao hơn · Sa Pa 2069 m · Bến Tre
13 m → từ chối.

## Khi nguồn miễn phí cạn hạn mức

Open-Meteo giới hạn **theo ngày**. Cạn hạn mức thì mọi mô-đun đồng loạt trả
"chưa đủ dữ liệu" — nhìn hệt như phần mềm hỏng. Chuyện này đã xảy ra thật trong
lúc phát triển, nên phần mềm tách riêng hai tình huống:

```bash
curl <api>/api/health
# "status":"ok"        → bình thường
# "status":"degraded"  → hết quota nguồn dữ liệu, KHÔNG phải code hỏng
```

Gộp hai cái đó thành một câu "chưa lấy được dữ liệu" là để người vận hành đi
sửa nhầm chỗ cả ngày, và để người dùng tưởng phần mềm hỏng khi nó chỉ đang chờ.

## Lộ trình — 25/26 luồng đã viết xong

`GET /api/roadmap` trả trạng thái sinh **từ mã nguồn**, nên không thể lệch với
phần mềm. Trang trạng thái cũng mở cho người dùng xem: **Khu làm việc → 26 luồng**.

| | Số luồng | |
|---|---|---|
| ✅ **Đã viết xong** | **25** | Signature 9/10 · Cốt lõi 12/12 · Nâng cấp 4/4 |
| ⏳ Chờ khóa Copernicus | **1** | C07 Carbon MRV — mã xong, có test, thiếu khóa |
| ⛔ Bị chặn | **1** | S10 Generative Vision |

Bảng phân biệt rạch ròi hai thứ hay bị trộn: `done` là **mã đã viết, có test,
không bịa số**; `awaiting_config` là **mã xong nhưng deployment này thiếu khóa
nên người dùng chưa dùng được**. Gộp hai cái đó vào một chữ "xong" là lúc một
bảng trạng thái bắt đầu nói dối.

### 17 mũi nhọn phủ đủ 12/12 ngành

Bản thiết kế liệt kê **14 mũi nhọn** nhưng lại hứa **12 ngành** — hai con số đó
không khớp nhau. Ba ngành không có mũi nhọn nào: Đô thị & Quy hoạch, Khai khoáng
& Hạ tầng, Chuỗi cung ứng. Nhóm D lấp đúng ba chỗ đó:

| Mũi nhọn | Ngành | Đo cái gì | Nguồn |
|---|---|---|---|
| 🏙️ **Ngập úng & mảng xanh đô thị** | URB-09 | Bê tông hoá làm nước chảy tràn tăng bao nhiêu lần so với khi chưa đô thị hoá — bằng đường cong dòng chảy **SCS Curve Number (USDA TR-55)**, không phải hệ số tự nghĩ | OSM + mưa + DEM |
| ⛏️ **An toàn mỏ & công trường** | INF-11 | Mái dốc trên đất đã bị đào bới, ghép mỏ/khu công nghiệp quanh đó với độ dốc thật và mưa dự báo | OSM + DEM + Open-Meteo (+ Sentinel) |
| 🔗 **Rủi ro vùng nguyên liệu** | SUP-12 | Bao nhiêu **phần trăm diện tích vùng thu mua** đang ở mức cảnh báo — chạy mô hình hiểm họa trên lưới 5×5 phủ bán kính 25 km. Kèm **hồ sơ truy xuất** điều kiện cả vụ từ ERA5, có mã băm | Open-Meteo + OSM |

Nguồn mới: **OpenStreetMap qua Overpass** — miễn phí, không cần key. Vệ tinh thấy
"bề mặt cứng"; OSM nói bề mặt đó *là gì* — nhà ở, nhà máy, mỏ đá hay quốc lộ.
Mọi kết quả kèm **mức đầy đủ dữ liệu**, vì OSM ở nông thôn VN còn thưa và
"0 công trình" thường nghĩa là chưa ai vẽ, không phải đất trống.

### Mọi luồng đều có mặt trên giao diện

Một luồng người dùng không bấm được thì với họ nó không tồn tại. 11 luồng từng
chỉ có API nay đều có đường vào:

| Ở đâu | Luồng |
|---|---|
| Cột phải → **Xem sâu hơn** | C04 Tua 10 năm · S04 Vùng giống · U03 Trồng gì · U02 Kinh nghiệm · C07 Carbon |
| Cột phải → **Cho phần mềm biết thực tế** | U04 hành động & kết quả · S05 quan sát thực địa |
| Cột trái → **Khu làm việc** | C01 Twin đã lưu · C11 Dữ liệu của tôi · U01 Kênh cảnh báo · C12 Khoá API · S05·S09·U04 Vòng học · 26 luồng |

### Xương sống học hỏi — thứ khiến phần mềm khá lên theo thời gian

```
quan sát thực địa (S05) → chấm điểm mô hình (S09) → hiệu chỉnh ngưỡng
      ↑                                                      ↓
xác nhận kết quả (U04) ←──── khuyến nghị ←──── cảnh báo chính xác hơn
```

- **S05 Federated Learning** — nông dân gửi "hôm 12/10 ruộng tôi ngập thật".
  Quan sát **thô không rời tài khoản người gửi**; chỉ chia sẻ *một con số* hiệu
  chỉnh cho mỗi vùng 0,5°, và chỉ khi đã đủ 3 quan sát. Dịch chuyển chặn trong
  ±15 điểm để một nhóm nhỏ quan sát sai không phá được mô hình.
- **S09 Model Engine** — chấm mô hình bằng **POD · FAR · CSI · bias** trên quan
  sát thật, chỉ ra vùng nào đang lệch và lệch hướng nào.
- **U04 Closed-Loop** — cơ cấu chấp hành là **con người**: khuyến nghị → xác
  nhận đã làm → đối chiếu kết quả → nạp lại hiệu chuẩn.
- **U02 Chợ tri thức** — ghép theo Twin Genome: kinh nghiệm từ vùng cùng bộ gen
  đất đáng học hơn lời khuyên chung chung. Không thanh toán nên không vướng pháp lý.
- **C04 Time-Lapse** — diễn biến rủi ro khí hậu qua 10 năm ERA5, kèm xu thế.
- **U03 Design Studio** — sinh phương án canh tác cụ thể; mỗi điểm cộng/trừ kèm
  lý do truy được về con số gốc.

### Ảnh vệ tinh — con mắt cắm vào đất

Lớp `services/sentinel.py` nối Sentinel-2 L2A qua **Copernicus Data Space**:
NDVI · NDWI · NDMI · NDBI, lọc mây bằng băng SCL, thống kê và histogram theo
từng pixel 10 m, cache 12 giờ (ảnh chỉ 5 ngày mới có tấm mới).

Đăng ký miễn phí, không cần thẻ:

1. https://dataspace.copernicus.eu → tạo tài khoản
2. Sentinel Hub → User settings → **OAuth clients** → Create
3. Đặt `TERRATWIN_COPERNICUS_ID` và `TERRATWIN_COPERNICUS_SECRET`

Cắm khóa vào là mở khoá **5 mũi nhọn** đang trả "chưa đủ dữ liệu" và **C07**:

| Mũi nhọn | Ảnh dùng để làm gì |
|---|---|
| Sâu bệnh | NDVI so với chính thửa 4 tháng qua, **phân biệt giảm ĐỀU (hạn) với giảm LOANG LỔ (ổ bệnh)** bằng tỉ lệ độ lệch chuẩn |
| Năng suất | Đường cong sinh trưởng 180 ngày: đang lên hay đang chín, đỉnh ngày nào. **Cố ý không quy ra tấn/ha** khi chưa có hệ số hiệu chuẩn địa phương |
| Thiệt hại sau bão | So NDVI hai kỳ. Nói rõ đo được **mất thảm thực vật**, không tự nhận biết nguyên nhân |
| Xây dựng trái phép | Đòi hỏi **NDBI tăng VÀ NDVI giảm** cùng lúc — một mình NDBI báo nhầm vì mùa khô cũng làm đất trống tăng NDBI |
| Carbon (C07) | Che phủ tán đo thật từ histogram + hệ số **IPCC Tier 1**, có dải sai số ±50% và mã băm SHA-256 chống sửa |

Không có khóa thì các mô-đun này nói thẳng **đang thiếu khóa hay đang bị mây
che** — hai nguyên nhân khác nhau, một cái sửa trong mười phút, một cái phải
chờ trời. Không có nhánh giả lập nào: một chỉ số NDVI bịa trông y hệt NDVI thật.

### 1 luồng còn bị chặn

| Luồng | Chặn bởi |
|---|---|
| **S10** Generative Vision | Ảnh Sentinel đã có. Còn thiếu **GPU** và **model diffusion đã huấn luyện trên ảnh viễn thám** — hai thứ không mua được bằng công sức viết code. Một tấm ảnh "siêu phân giải" do model bịa ra trông y hệt ảnh thật nhưng chi tiết trong đó là tưởng tượng; dùng nó để kết luận về đất đai còn nguy hiểm hơn không có ảnh |

> **Một điều đã học khi làm:** ban đầu 8 luồng bị xếp "bị chặn" vì mỗi luồng bị
> gán vào *một công nghệ cụ thể*. Xét lại theo **mục đích** thì 6 trong số đó có
> bản thật, hữu ích, làm được bằng dữ liệu đã có. Hỏi "luồng này để làm gì cho
> người dùng" trước khi hỏi "nó cần công nghệ gì".

**Triển khai:** [DEPLOY.md](DEPLOY.md) — Render một cú bấm, Docker, hoặc Fly+Vercel.

**SDK:** [`sdk/python/terratwin.py`](sdk/python/terratwin.py) — một file, không phụ thuộc gói ngoài.

## License
MIT — xem [LICENSE](LICENSE).
