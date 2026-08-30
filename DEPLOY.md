# Đưa TerraTwin lên Internet (Render) — checklist từng bước

Mục tiêu: từ chạy trên máy bạn → chạy trên Internet để **người khác dùng được**.
Đây là mắt xích mở khoá mọi thứ còn lại (người dùng thật → quan sát thực địa → moat).
Toàn bộ ~1 giờ, **0 đồng** (gói free Render). File `render.yaml` đã dựng sẵn mọi thứ.

> Ba bẫy đã biết — đọc trước:
> 1. **Windows:** dừng server theo cổng bằng `Stop-Process`, KHÔNG dùng `pkill`.
> 2. **Đừng** `npm run build` khi `next dev` đang chạy (ghi đè `.next` → 500).
> 3. Ảnh vệ tinh chạy qua **Microsoft Planetary Computer — KHÔNG cần khoá Copernicus**.

---

## Bước 0 — Đưa mã lên GitHub (~10 phút)

```bash
cd D:\terratwin
git add -A && git commit -m "chuan bi deploy"    # nếu còn thay đổi
# Tạo repo rỗng trên github.com (New repository), rồi:
git remote add origin https://github.com/<tên-bạn>/terratwin.git
git branch -M main
git push -u origin main
```
✅ **Xong khi:** mở repo trên GitHub thấy đủ thư mục `backend/`, `frontend/`, và file `render.yaml` ở gốc.

---

## Bước 1 — Dựng bằng Blueprint (~15 phút, Render tự làm)

1. Vào https://render.com → đăng ký (login bằng GitHub cho nhanh).
2. **New → Blueprint** → chọn repo `terratwin`.
3. Render đọc `render.yaml` và hiện 3 thứ sẽ tạo: `terratwin-db` (Postgres), `terratwin-api` (backend), `terratwin-web` (frontend). Bấm **Apply**.
4. Chờ build (~5–10 phút). Backend cài xong sẽ tự chạy `uvicorn`; frontend chạy `npm run build` rồi `npm start`.

✅ **Xong khi:** cả `terratwin-api` và `terratwin-web` đều xanh (Live).

---

## Bước 2 — Nối frontend ↔ backend (~5 phút, BẮT BUỘC)

Render cấp cho bạn 2 URL, ví dụ:
- API: `https://terratwin-api.onrender.com`
- Web: `https://terratwin-web.onrender.com`

Đặt 2 biến môi trường (dashboard Render → service → **Environment**):

| Service | Biến | Giá trị |
|---|---|---|
| `terratwin-web` | `NEXT_PUBLIC_API` | URL của **api** (vd `https://terratwin-api.onrender.com`) |
| `terratwin-api` | `TERRATWIN_CORS` | URL của **web** (vd `https://terratwin-web.onrender.com`) |

Đặt xong bấm **Manual Deploy → Deploy latest** cho `terratwin-web` (vì `NEXT_PUBLIC_*` nhúng lúc build).

✅ **Xong khi:** mở URL web, bấm 1 nơi → ra kết quả (không lỗi CORS trong Console trình duyệt).

> `TERRATWIN_SECRET` Render tự sinh và giữ cố định — **đừng đặt tay**, đổi là mọi người bị đăng xuất.

---

## Bước 3 — Kiểm tra volume (dữ liệu KHÔNG được mất khi deploy lại)

Đây là bài kiểm QUAN TRỌNG NHẤT — kho quan sát thực địa là thứ đối thủ không tải được.

1. Trên web đã deploy: **đăng ký** một tài khoản → **lưu một thửa đất**.
2. Vào Render → `terratwin-api` → **Manual Deploy → Deploy latest** (deploy lại lần nữa).
3. Sau khi Live lại: đăng nhập lại → **thửa đó còn không?**

✅ **Còn** → volume/DB đúng, an tâm mở cho người dùng.
❌ **Mất** → DỪNG LẠI, kiểm `TERRATWIN_DATABASE_URL` đã nối Postgres chưa (trong `render.yaml` là `fromDatabase`). Đừng mời người dùng khi còn mất dữ liệu.

---

## Bước 4 — Hâm nóng trên chính server (~35 phút, chạy 1 lần)

Xoá 15 giây chờ của người-dùng-đầu-tiên ở mỗi toạ độ.

- Render → `terratwin-api` → tab **Shell**:
```bash
cd backend
python -m app.warm --demo        # 8 nơi demo (~35 giây) — chạy trước buổi thi
python -m app.warm --provinces   # phủ cả nước (~35 phút)
```

✅ **Xong khi:** mở một tỉnh bất kỳ trên điện thoại → trả lời trong vài giây, không phải 15.

> Gói free Render KHÔNG có cron; `render.yaml` đã bật radar quét nền trong tiến trình
> (`TERRATWIN_RADAR_INTERVAL_H=6`). Nếu server "ngủ" do free tier, dùng cron ngoài
> (vd cron-job.org) gọi `GET https://terratwin-api.onrender.com/api/radar/run` mỗi 6h.

---

## Bước 5 — Bật cảnh báo tự động (tùy chọn, nhưng là "engine giữ chân")

Để TerraTwin **tự canh đất và báo trước** — thứ khiến người ta dùng mỗi ngày:
- Người dùng vào **Khu làm việc → Kênh cảnh báo** → thêm webhook (nối Zalo OA/Telegram)
  hoặc email SMTP. Radar nền quét thửa đã lưu và gửi khi có rủi ro.

---

## (Tùy chọn) Bật trợ lý LLM
`terratwin-api` → Environment, đặt theo nhà cung cấp:
- OpenAI-compatible (DeepSeek/Groq/OpenRouter…): `TERRATWIN_LLM_API_KEY` + `TERRATWIN_LLM_BASE_URL` + `TERRATWIN_LLM_MODEL`.
- Gemini/Anthropic: BẮT BUỘC thêm `TERRATWIN_LLM_PROVIDER=gemini|anthropic`.
Không đặt gì → Copilot tự chạy bằng luật tiếng Việt (vẫn hoạt động).

## (Tùy chọn) Bật 5 mũi nhọn quang học bằng model học sâu
Sau khi huấn luyện trên máy có GPU (xem `backend/app/dl/`), chép `data/landcover.onnx`
+ `data/landcover.json` vào `terratwin-api` → `/api/landcover` sẽ báo `available: true`.

---

### Tóm tắt "xong khi nào"
- [ ] Repo trên GitHub có `render.yaml`
- [ ] `terratwin-api` + `terratwin-web` đều Live
- [ ] `NEXT_PUBLIC_API` + `TERRATWIN_CORS` đã đặt đúng chéo nhau
- [ ] Đăng ký + lưu thửa → deploy lại → **thửa vẫn còn**
- [ ] Đã chạy `python -m app.warm --provinces`
- [ ] (tùy chọn) Kênh cảnh báo đã nối
