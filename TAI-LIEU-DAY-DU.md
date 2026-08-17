# TerraTwin — Tài liệu đầy đủ (as-built, bản thực tế đã code)

> Tài liệu này mô tả **đúng những gì phần mềm đang chạy** tại `D:\terratwin`, phân biệt rõ
> phần **CHẠY DỮ LIỆU THẬT** với phần **HEURISTIC/MẪU** (chờ nâng cấp) để bạn không nói quá khi đi thi.

---

## 1. Phần mềm là gì
**TerraTwin** = web app tạo "bản sao số (digital twin)" cho một vị trí/vùng đất từ dữ liệu vệ tinh & khí tượng,
rồi **phân tích rủi ro + dự báo 7 ngày + khuyến nghị hành động** cho 14 nhu cầu (module) gắn với đất.
Người dùng bấm/vẽ vùng trên bản đồ → nhận đánh giá, điểm an toàn TerraScore, và hỏi trợ lý AI.

## 2. Cách hoạt động (end-to-end)
1. Người dùng mở web (localhost:1825), chọn **module**, bấm 1 điểm hoặc vẽ **vùng polygon** trên bản đồ.
2. Frontend gửi toạ độ (lat/lon [+ diện tích ha]) tới **API backend**.
3. Backend: module tương ứng **lấy dữ liệu** (thật qua Open-Meteo/NASA POWER, hoặc mô hình mẫu) →
   tính chỉ số/dự báo → trả về **Assessment** (mức rủi ro, dự báo 7 ngày, khuyến nghị, chỉ số, nguồn).
4. Song song, backend tính **TerraScore** (điểm an toàn tổng hợp).
5. Frontend hiển thị kết quả; người dùng có thể hỏi **Copilot** (LLM thật nếu có API key, không thì rule-based).

## 3. Kiến trúc thực tế
```
Frontend (Next.js + MapLibre)  ──HTTP──►  Backend (FastAPI)
                                            │
                                   Lõi: Twin engine + Registry
                                            │
                        ┌───────────────────┼─────────────────────┐
                   14 Module          TerraScore            Copilot
                        │
             Nguồn dữ liệu: Open-Meteo / NASA POWER (THẬT)  ·  mô hình mẫu (fallback)
```
- **Mẫu kiến trúc "1 lõi + module":** mỗi module là 1 lớp con `TwinModule`, đăng ký trong `registry.py`.
  Thêm module mới = thêm 1 file + 1 dòng đăng ký.
- **Không dùng database** ở Phase 0 (Twin lưu tạm trong bộ nhớ). PostGIS/TimescaleDB là bước sau.

## 4. 14 Module — làm gì, dùng gì, THẬT hay MẪU

| # | Module | Nhóm | Làm gì | Nguồn dữ liệu | Trạng thái |
|---|--------|------|--------|---------------|-----------|
| 1 | Xâm nhập mặn | A | Dự báo mặn 7 ngày (g/L) + khuyến nghị đóng cống | Mô hình (khoảng cách biển + triều) | ⚠️ MẪU (cần dữ liệu mặn MRC) |
| 2 | Hạn & thiếu nước | A | Chỉ số thiếu ẩm đất 7 ngày | **Open-Meteo: mưa + ET₀** | ✅ THẬT |
| 3 | Sâu bệnh sớm | A | Chỉ số bất thường thực vật (NDVI) | Mô hình (cần Sentinel-2) | ⚠️ MẪU |
| 4 | Năng suất & thu hoạch | A | Ước lượng năng suất + ngày thu hoạch | Mô hình (cần Sentinel) | ⚠️ MẪU |
| 5 | Carbon rừng | A | Trữ lượng tCO₂/ha + giá trị tín chỉ | Mô hình sinh khối (cần Sentinel) | ⚠️ MẪU |
| 6 | Cháy rừng | A | Chỉ số nguy cơ cháy 7 ngày | **Open-Meteo: nhiệt độ + mưa** | ✅ THẬT |
| 7 | Ao nuôi thủy sản | A | Chỉ số rủi ro môi trường ao | Mô hình (cần Sentinel) | ⚠️ MẪU |
| 8 | Lũ/ngập sớm | B | Chỉ số ngập 7 ngày | **Open-Meteo: mưa + cao độ** | ✅ THẬT |
| 9 | Sạt lở | B | Chỉ số sạt lở 7 ngày | **Open-Meteo: mưa** + độ dốc(mẫu) | ✅ THẬT (một phần) |
| 10 | Thiệt hại sau bão | B | % thiệt hại vùng | Change detection (cần Sentinel) | ⚠️ MẪU |
| 11 | Rủi ro mua đất | B | Điểm an toàn đất 0–100 | **Cao độ + mưa THẬT** + khoảng cách biển | ✅ THẬT (một phần) |
| 12 | Xây dựng trái phép | B | Phát hiện thay đổi bề mặt | Change detection (cần Sentinel) | ⚠️ MẪU |
| 13 | Bảo hiểm tham số | C | Kích hoạt chi trả khi vượt ngưỡng hạn | **Open-Meteo (chỉ số hạn)** | ✅ THẬT |
| 14 | Điện mặt trời | C | Bức xạ + sản lượng dự kiến | **NASA POWER: bức xạ** | ✅ THẬT |

**Tóm tắt: 7 module chạy dữ liệu THẬT, 7 module còn heuristic/mẫu (chờ ảnh Sentinel + key).**

## 5. TerraScore
Điểm an toàn 0–100 (cao = an toàn) + hạng A–D, tổng hợp rủi ro từ 5 module hiểm họa
(mặn, hạn, lũ, sạt lở, cháy). Mỗi mức `danger` −22, `warning` −11. → `services/terrascore.py`.

## 6. Copilot
- Định tuyến câu hỏi → module liên quan, tổng hợp kết quả + TerraScore làm "dữ liệu nền".
- Nếu có `ANTHROPIC_API_KEY` → gọi **Anthropic Messages API** trả lời tiếng Việt bám dữ liệu (RAG-lite).
- Nếu không → **fallback rule-based** (vẫn chạy). → `services/copilot.py`.

## 7. Vẽ vùng (polygon) + diện tích
- Bấm nhiều điểm trên bản đồ → tạo polygon → tính **tâm (centroid)** + **diện tích (ha)** (công thức shoelace).
- Diện tích được gửi vào phân tích: module Carbon/Năng suất/Bảo hiểm dùng để ra **tổng** (tổng tCO₂, sản lượng, tiền chi trả).

## 8. Nguồn dữ liệu
| Nguồn | Loại | Trạng thái | Dùng cho |
|-------|------|-----------|----------|
| **Open-Meteo** (nền ECMWF) | Mưa, ET₀, nhiệt độ, cao độ | ✅ Thật, miễn phí, không key | Hạn, cháy, lũ, sạt lở, mua đất, bảo hiểm |
| **NASA POWER** | Bức xạ mặt trời | ✅ Thật, miễn phí, không key | Điện mặt trời |
| **Sentinel-1/2 (Copernicus)** | Ảnh quang học/radar | ❌ Cần API key (hook đã chừa) | Mặn, sâu bệnh, carbon, thiệt hại bão, xây dựng, ao nuôi |
| **Ủy hội Mekong (MRC)** | Độ mặn | ❌ Chưa có API mở | Xâm nhập mặn |

## 9. Công nghệ ĐANG áp dụng thật (as-built)
- **Backend:** Python 3.12, FastAPI, Pydantic v2, Uvicorn, urllib (gọi API dữ liệu + LLM).
- **Frontend:** Next.js 14, React 18, TypeScript, MapLibre GL (bản đồ WebGL).
- **Kỹ thuật:** thiết kế REST API; xử lý không gian (toạ độ, centroid, diện tích shoelace);
  dự báo chuỗi thời gian 7 ngày; mô hình thủy văn/khí hậu đơn giản (deficit ẩm, chỉ số ngập/cháy);
  caching; CORS; async fetch; React state; kiến trúc plugin.
- **LLM:** Anthropic Messages API (tùy chọn).

> Lưu ý trung thực: các mảng **Computer Vision / Deep Learning / huấn luyện model / database / vector DB**
> nằm trong **lộ trình**, CHƯA có trong bản as-built. Đừng khẳng định đã có khi đi thi.

## 10. API endpoints (backend, cổng 8000)
- `GET /api/health` — trạng thái + số module.
- `GET /api/modules` — danh sách 14 module + metadata.
- `POST /api/assess/{module_id}` — body `{lat, lon, area_ha?}` → Assessment.
- `POST /api/terrascore` — body `{lat, lon}` → điểm + hạng.
- `POST /api/copilot` — body `{question, location:{lat,lon}}` → câu trả lời.
- Trang thử API tương tác: **http://localhost:8000/docs**

## 11. Cấu trúc thư mục
```
D:\terratwin\
├─ backend\
│  ├─ app\
│  │  ├─ main.py            # API + CORS
│  │  ├─ schemas.py         # kiểu dữ liệu (Location, Assessment, ...)
│  │  ├─ services\
│  │  │  ├─ realdata.py     # gọi Open-Meteo / NASA POWER (dữ liệu thật)
│  │  │  ├─ datasources.py  # chỉ số thật + fallback mẫu
│  │  │  ├─ twin.py         # Twin engine (bộ nhớ)
│  │  │  ├─ terrascore.py   # điểm an toàn
│  │  │  └─ copilot.py      # trợ lý (LLM/fallback)
│  │  └─ modules\
│  │     ├─ base.py         # khuôn TwinModule
│  │     ├─ util.py         # tiện ích dự báo
│  │     ├─ salinity.py     # module mặn
│  │     ├─ group_a.py      # hạn, sâu bệnh, năng suất, carbon, cháy, ao nuôi
│  │     ├─ group_b.py      # lũ, sạt lở, thiệt hại bão, mua đất, xây dựng
│  │     ├─ group_c.py      # bảo hiểm tham số, điện mặt trời
│  │     └─ registry.py     # đăng ký 14 module
│  └─ requirements.txt
├─ frontend\
│  ├─ app\ (page.tsx, layout.tsx, globals.css)
│  ├─ components\ (MapView.tsx, ResultsPanel.tsx, Copilot.tsx)
│  └─ lib\api.ts
├─ README.md
└─ TAI-LIEU-DAY-DU.md   ← file này
```

## 12. Cách chạy & test
```powershell
# Backend (cửa sổ 1)
cd D:\terratwin\backend
.\.venv\Scripts\uvicorn.exe app.main:app --port 8000

# Frontend (cửa sổ 2)
cd D:\terratwin\frontend
npm run dev -- -p 1825
```
→ Mở **http://localhost:1825** · Bật LLM: đặt `ANTHROPIC_API_KEY` trước khi chạy backend.

## 13. Trạng thái THẬT vs LỘ TRÌNH (rất quan trọng khi đi thi)
**Đã có, chạy thật:** 14 module có kết quả · 7 module dùng dữ liệu thật · TerraScore · Copilot (fallback + LLM-ready) · vẽ vùng + diện tích · bản đồ · API đầy đủ.

**CHƯA có (lộ trình — đừng nói đã có):**
- Ảnh Sentinel thật (CV) cho mặn/sâu bệnh/carbon/thiệt hại/xây dựng.
- Huấn luyện model (CNN) + dataset gán nhãn.
- Database thật (PostGIS/TimescaleDB/Vector DB).
- Các tính năng "wow" trong bản vẽ: Parallel Futures, Twin Genome, Federated Learning, Marketplace,
  Generative Vision, Autonomous Agent, Backtest, Causal Explain, Multi-Twin Portfolio, Twin API/SDK.

## 14. Việc cần làm — ra thị trường & đi thi (checklist)
**Để chính xác & thuyết phục:**
1. Cắm **1 nguồn dữ liệu thật còn thiếu** (ưu tiên mặn: lấy số MRC/trạm tỉnh) → module mặn thành thật.
2. **Backtest** 1–2 module trên mùa 2024–2025 → có con số độ chính xác để trưng ra.
3. Thêm **cảnh báo qua Zalo/email** (tăng tính "hành động thật").

**Để ra thị trường:**
4. Thêm **đăng nhập + lưu vùng của người dùng** (cần database — PostGIS).
5. **Deploy** lên cloud (VD: backend trên Render/Fly, frontend trên Vercel).
6. **Phỏng vấn 5–7 người dùng thật** (nông dân/HTX/cán bộ) xác nhận nhu cầu + ai trả tiền.

**Để đi thi:**
7. Chuẩn bị **demo kịch bản**: chọn 1 điểm ĐBSCL trũng + đang mưa → module Lũ ra "nguy cơ cao" (dữ liệu thật).
8. Nhấn đúng **điểm mạnh thật**: dữ liệu thật + kiến trúc mở rộng + bản địa hóa VN; **không khoe** thứ chưa có.
9. Trình bày **lộ trình rõ** (Phase 1: ảnh Sentinel + backtest; Phase 2: model training + database + tính năng wow).
