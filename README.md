# 🛰️ TerraTwin

**Bản sao số (digital twin) của đất đai Việt Nam** — nhìn đất thật từ vệ tinh → mô phỏng → dự đoán kiểm chứng được → khuyến nghị hành động. Một lõi Twin, phủ 14 mũi nhọn.

Ba chữ cốt lõi: **CỦA MÌNH** (từng thửa) · **BIẾT TRƯỚC** (kịp hành động) · **BẰNG CHỨNG THẬT** (vệ tinh/thời tiết, kiểm chứng được — không phỏng đoán).

> Phạm vi phục vụ: **lãnh thổ Việt Nam**. Toạ độ ngoài vùng bị từ chối (HTTP 422).

---

## Trạng thái dữ liệu (minh bạch)

Mỗi kết quả gắn cờ rõ ràng 🛰️ **Dữ liệu thật** hoặc 🧪 **Ước lượng/chờ dữ liệu**, kèm khoảng tin cậy. **Không hứa 100%.**

| Nhóm | Module | Nguồn |
|---|---|---|
| 🛰️ Dữ liệu thật (7) | hạn, cháy rừng, lũ/ngập, sạt lở, rủi ro mua đất, bảo hiểm tham số, điện mặt trời | Open-Meteo (mưa/ET₀/nhiệt/cao độ/**độ dốc DEM**), NASA POWER |
| 🧪 Ước lượng vật lý (1) | xâm nhập mặn | bờ biển VN (34 điểm) + cao độ DEM + **chu kỳ mùa khô/mùa lũ** + triều (**chờ hiệu chỉnh MRC**) |
| ⏳ Chờ ảnh Sentinel (6) | sâu bệnh, năng suất, carbon, ao nuôi, thiệt hại bão, xây dựng trái phép | kiến trúc sẵn sàng — KHÔNG bịa số khi chưa có ảnh |

> **Phạm vi module Mặn:** xâm nhập mặn *nông nghiệp* ở **ĐBSCL** và **ĐB sông Hồng**.
> Ngoài hai vùng đó (Đà Nẵng, Nha Trang, Hạ Long…) module trả `out_of_scope` thay vì
> áp ngưỡng mặn của cây lúa. Mô hình có **mùa vụ**: đỉnh ~15/3 (mùa khô, sông cạn),
> đáy ~15/9 (lũ đẩy mặn ra biển) — tỉ lệ khô/mưa ở Bến Tre ≈ **6,2×**.

**Tính năng thật đã có:** TerraScore (chỉ chấm từ hiểm họa dữ liệu thật) · Quét toàn cảnh 14 module · **Backtest lịch sử ERA5** (đo lead time 4 thiên tai VN có thật) · **What-If / Parallel Futures** (mô phỏng tham số trên nền thời tiết thật) · Danh mục thửa đất + xuất báo cáo · Copilot (rule-based, bật LLM nếu có key) · bản đồ nền ảnh vệ tinh thật.

---

## Kiến trúc: 1 Lõi + 14 Module
```
terratwin/
├── backend/                      # Python + FastAPI
│   └── app/
│       ├── main.py               # API + CORS/rate-limit theo env
│       ├── schemas.py            # kiểu dữ liệu + validate Location
│       ├── services/             # realdata, datasources, terrascore, scan,
│       │                         #   whatif, backtest, copilot, twin
│       └── modules/              # base + util + 14 module + registry
│   └── tests/                    # pytest (32 test, offline & tất định)
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
pytest                      # 32 test, chạy offline & tất định
```

---

## Cấu hình (biến môi trường — xem `.env.example`)
| Biến | Ý nghĩa | Mặc định |
|---|---|---|
| `TERRATWIN_CORS` | origin cho CORS (phân tách dấu phẩy) | `*` |
| `TERRATWIN_RATE_LIMIT` | request/phút mỗi IP (0 = tắt) | `120` |
| `ANTHROPIC_API_KEY` | bật Copilot LLM thật | (trống → rule-based) |
| `NEXT_PUBLIC_API` | URL backend cho frontend | `http://localhost:8000` |

## API (cổng 8000)
`GET /api/health` · `GET /api/modules` · `POST /api/assess/{id}` · `POST /api/terrascore` · `POST /api/scan` · `POST /api/whatif/{id}` · `POST /api/copilot` · `GET /api/backtest[/{event}]` · `/docs`

## Thêm module mới
1. Tạo lớp con `TwinModule` trong `backend/app/modules/`, viết `assess()`.
2. Đăng ký ở `registry.py`. Frontend tự hiện.

## Lộ trình
- **Đã có:** 7 module dữ liệu thật + backtest + what-if + portfolio + báo cáo.
- **Tiếp theo (ra thị trường):** database + đăng nhập (lưu vùng đa thiết bị) · tích hợp ảnh Sentinel (bật 6 module còn lại) · cắm dữ liệu mặn MRC · deploy cloud · cảnh báo Zalo/email.

## License
MIT — xem [LICENSE](LICENSE).
