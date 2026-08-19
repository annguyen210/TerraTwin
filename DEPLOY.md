# Triển khai TerraTwin

Ba cách, xếp từ nhanh nhất. Mọi cách đều cần **một biến bắt buộc**:
`TERRATWIN_SECRET` — khóa ký token đăng nhập. Không đặt thì mỗi lần khởi động
lại sẽ sinh khóa mới và toàn bộ người dùng bị đăng xuất.

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

---

## Cách A — Render (một cú bấm, có sẵn database)

1. Đẩy repo lên GitHub.
2. Render → **New → Blueprint** → chọn repo. Render đọc `render.yaml` và dựng
   backend + frontend + PostgreSQL.
3. Dựng xong, điền hai biến nối hai service với nhau:
   - `terratwin-api` → `TERRATWIN_CORS` = URL của `terratwin-web`
   - `terratwin-web` → `NEXT_PUBLIC_API` = URL của `terratwin-api`

`TERRATWIN_SECRET` do Render tự sinh và giữ cố định — đừng sửa.

> ⚠️ `TERRATWIN_TRUST_PROXY=1` đã bật sẵn trong `render.yaml`. **Bắt buộc** khi
> đứng sau proxy: nếu không, rate limiter thấy mọi người dùng chung một IP (IP
> của proxy) và chặn nhầm cả nhà ngay khi có vài người truy cập.

---

## Cách B — Docker ở đâu cũng được (VPS, máy chủ trường, máy cá nhân)

```bash
cp .env.example .env      # sửa TERRATWIN_SECRET và TERRATWIN_CORS
docker compose up --build -d
```

Frontend `:1825` · API `:8000/docs`. Mặc định dùng SQLite (một file), đủ cho
demo và vài chục người dùng. Muốn PostgreSQL thì đặt `TERRATWIN_DATABASE_URL`
và thêm `psycopg[binary]` vào `backend/requirements.txt`.

> ⚠️ `docker compose` **chưa được kiểm thử** trên máy phát triển vì máy đó không
> cài Docker. Dockerfile đọc thì hợp lý, nhưng hãy chạy thử trước khi dùng cho
> buổi demo quan trọng.

---

## Cách C — Fly.io + Vercel (tách backend/frontend)

Backend lên Fly, frontend lên Vercel:

```bash
cd backend && fly launch --no-deploy
fly secrets set TERRATWIN_SECRET=... TERRATWIN_TRUST_PROXY=1 TERRATWIN_CORS=https://<app>.vercel.app
fly deploy
```

Vercel: import repo, Root Directory = `frontend`, đặt `NEXT_PUBLIC_API` bằng
URL Fly.

---

## Danh sách kiểm tra trước khi mở cho người dùng thật

| | Việc | Vì sao |
|---|---|---|
| ☐ | `TERRATWIN_SECRET` đặt cố định | Không đặt = đăng xuất toàn bộ mỗi lần restart |
| ☐ | `TERRATWIN_TRUST_PROXY=1` nếu sau proxy | Không đặt = rate limiter chặn nhầm mọi người |
| ☐ | `TERRATWIN_CORS` đúng domain frontend | Để `*` là ai cũng gọi API của bạn được |
| ☐ | PostgreSQL thay SQLite | SQLite không chịu được ghi đồng thời |
| ☐ | Chạy `pytest` | Bắt lỗi trước khi người dùng gặp |
| ☐ | Gọi `POST /api/genome/warm` một lần | Dựng sẵn lưới, người dùng đầu không phải chờ 2–3 phút |
| ☐ | Sao lưu database định kỳ | Thửa đất và Twin của người dùng nằm trong đó |
| ☐ | `TERRATWIN_RADAR_INTERVAL_H` | Xem mục dưới — đặt sai thì cảnh báo chủ động **không tự chạy** |
| ☐ | `TERRATWIN_LLM_PROVIDER` nếu dùng Gemini/Anthropic | Thiếu = khóa gửi sai giao thức, trợ lý **im lặng** tụt về rule-based |
| ☐ | Khóa Copernicus (tuỳ chọn) | Mở khoá 5 mũi nhọn quang học + C07 Carbon |

---

## Cảnh báo chủ động — thứ dễ tưởng có mà không có

C05 Proactive Radar là điểm bán hàng số một, nhưng nó chỉ *chủ động* nếu có gì
đó gọi nó khi người dùng đang ngủ. **Gói miễn phí của Render và Fly không có
cron.** Vì vậy bộ hẹn giờ nằm ngay trong tiến trình:

```
TERRATWIN_RADAR_INTERVAL_H=6     # mặc định: tự quét mọi tài khoản mỗi 6 giờ
TERRATWIN_RADAR_INTERVAL_H=0     # tắt — dùng khi chạy NHIỀU WORKER
```

⚠️ Chạy nhiều worker (`--workers 4`) thì **mỗi worker quét một lần**. Chống
trùng 12 giờ hấp thụ được cảnh báo lặp, nhưng vẫn đốt lượt gọi Open-Meteo gấp 4.
Nhiều worker thì đặt `0` và dùng cron ngoài:

```bash
# cron-job.org, GitHub Actions, hay crontab — 6 giờ một lần
curl -X POST https://<api>/api/radar/run -H "Authorization: Bearer <token>"
```

Gói free Render còn **ngủ sau 15 phút không có request**, nên lần gọi đầu mất
~50 giây và bộ hẹn giờ bị ngắt trong lúc ngủ. Muốn cảnh báo chạy đều thì cần
gói trả phí hoặc một dịch vụ ping bên ngoài.

---

## Ảnh vệ tinh Sentinel-2 (tuỳ chọn, miễn phí)

Không có thì phần mềm vẫn chạy đủ 9/14 mũi nhọn bằng khí tượng và địa hình; 5
mũi nhọn quang học sẽ nói thẳng là chưa có ảnh. Có thì mở khoá cả 14.

1. Đăng ký tại https://dataspace.copernicus.eu (miễn phí, không cần thẻ)
2. Sentinel Hub → User settings → **OAuth clients** → Create
3. Đặt hai biến:

```bash
TERRATWIN_COPERNICUS_ID=<client id>
TERRATWIN_COPERNICUS_SECRET=<client secret>
```

Kiểm tra: `curl https://<api>/api/satellite` → `"configured": true`.

Hạn mức tài khoản miễn phí tính theo processing unit mỗi tháng. Phần mềm cache
12 giờ cho chuỗi gần đây và 7 ngày cho cửa sổ lịch sử đã đóng, vì Sentinel-2
chỉ 5 ngày mới bay qua một lần — hỏi lại sau 10 phút cũng không có gì mới.

## Sau khi deploy, kiểm nhanh

```bash
curl https://<api>/api/health           # {"status":"ok","modules":14}
curl https://<api>/api/roadmap          # trạng thái thật 26 luồng
curl https://<api>/api/satellite        # ảnh vệ tinh đã nối chưa
curl -X POST https://<api>/api/scan \
  -H 'content-type: application/json' \
  -d '{"lat":10.19,"lon":106.70}'
```
