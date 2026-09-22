# Khôi phục dữ liệu từ bản sao lưu — TerraTwin

Tài liệu này cho **chủ dự án**, không cần biết lập trình. Làm theo từng bước.
Nếu một bước báo lỗi, dừng lại và đọc đúng dòng lỗi trước khi làm bước sau.

> Nguyên tắc: **diễn tập trước khi cần thật.** Một bản sao lưu chưa từng khôi
> phục thử là một bản sao lưu chưa được tin. Làm phần "1. Diễn tập" ít nhất một
> lần trước khi có sự cố thật — đừng để lần đầu khôi phục là lúc đang hoảng.

## 0. Cần chuẩn bị trước

- Máy có cài [git](https://git-scm.com), [PostgreSQL client](https://www.postgresql.org/download/) (để có lệnh `psql`), và [GnuPG](https://gnupg.org) (để có lệnh `gpg` — Mac/Linux thường có sẵn).
- **Chuỗi mật khẩu sao lưu** (`TERRATWIN_BACKUP_PASSPHRASE`) — chuỗi này KHÔNG nằm trong repo, phải lấy từ nơi bạn đã cất giữ khi tạo (trình quản lý mật khẩu, GitHub Secrets…). **Mất chuỗi này = mất khả năng đọc mọi bản sao lưu cũ, không ai cứu được kể cả người viết phần mềm.**
- Một URL Postgres để khôi phục vào — KHÔNG bao giờ khôi phục thẳng vào production khi mới diễn tập.

## 1. Diễn tập (làm trước, không đụng dữ liệu thật)

```bash
git clone https://github.com/annguyen210/TerraTwin.git
cd TerraTwin

# Tải nhánh chứa các bản sao lưu đã mã hoá.
git fetch origin backups:backups
git worktree add ../terratwin-backups backups
```

Tạo một Postgres TRỐNG để khôi phục thử vào — cách nhanh nhất là mở một
service Postgres free mới trên Render (vài phút, không tốn tiền), lấy External
Database URL của nó.

```bash
cd backend
TERRATWIN_DATABASE_URL="<URL Postgres THẬT trên Render>" \
TERRATWIN_SCRATCH_URL="<URL Postgres TRỐNG vừa tạo>" \
TERRATWIN_BACKUP_DIR="../../terratwin-backups" \
TERRATWIN_BACKUP_PASSPHRASE="<chuỗi mật khẩu sao lưu>" \
bash ../ops/restore-drill.sh
```

Thấy dòng `✅ KHỚP — bản sao lưu khôi phục được` nghĩa là bản sao lưu dùng
được thật. Thấy `❌ LỆCH` thì báo ngay cho người vận hành kỹ thuật — đừng tự
sửa, đây là dấu hiệu bản sao lưu hoặc script có vấn đề.

Xong rồi thì **xoá** service Postgres scratch vừa tạo (Render → service đó →
Settings → Delete) — nó chỉ để thử, không cần giữ.

## 2. Khôi phục thật (khi có sự cố)

Chỉ làm bước này khi database production thật sự hỏng/mất — nó GHI ĐÈ dữ liệu
hiện có trên đích.

```bash
git -C ../terratwin-backups pull                # lấy bản sao lưu mới nhất

# Tìm bản mới nhất:
ls -1t ../terratwin-backups/daily/*.sql.gz* | head -1
```

Nếu tên file kết thúc bằng `.gpg` (đã mã hoá — trường hợp bình thường):

```bash
gpg --batch --yes --pinentry-mode loopback \
    --passphrase-fd 3 3<<< "<chuỗi mật khẩu sao lưu>" \
    --decrypt ../terratwin-backups/daily/<tên_file>.sql.gz.gpg \
  | gunzip -c \
  | psql "<URL Postgres ĐÍCH cần khôi phục vào>"
```

Nếu tên file chỉ kết thúc bằng `.sql.gz` (không có `.gpg` — chỉ xảy ra khi
sao lưu tay mà quên đặt mật khẩu, không phải luồng tự động bình thường):

```bash
gunzip -c ../terratwin-backups/daily/<tên_file>.sql.gz \
  | psql "<URL Postgres ĐÍCH cần khôi phục vào>"
```

Xong thì mở web TerraTwin, đăng nhập thử một tài khoản biết trước, kiểm tra
thửa/cảnh báo còn nguyên.

## 3. Vòng đời một bản sao lưu

- **Tự động mỗi ngày** lúc 02:00 sáng giờ Việt Nam — xem
  `.github/workflows/backup.yml`. Kiểm tra chạy được hay không tại tab
  **Actions** trên GitHub (tìm workflow "Database backup").
- **Giữ 7 bản gần nhất** (mỗi ngày) + **4 bản Chủ Nhật gần nhất** (mỗi tuần).
  Bản cũ hơn tự động bị xoá khỏi nhánh `backups` — không cần dọn tay.
- Mọi bản đều **đã mã hoá** trước khi lưu — kể cả khi kẻ xấu đọc được toàn bộ
  repo công khai này, họ vẫn không đọc được nội dung nếu không có chuỗi mật
  khẩu sao lưu.

## 4. Nếu workflow báo đỏ trên GitHub Actions

Nguyên nhân thường gặp nhất là thiếu hoặc sai một trong hai secret sau
(Settings → Secrets and variables → Actions, trên repo):

| Secret | Lấy ở đâu |
|---|---|
| `TERRATWIN_DB_EXTERNAL_URL` | Render → database `terratwin-db` → tab Connect → **External Database URL** (không phải Internal — GitHub Actions không nằm trong mạng nội bộ Render) |
| `TERRATWIN_BACKUP_PASSPHRASE` | Chuỗi bạn tự sinh một lần và cất giữ — nếu chưa có, sinh mới bằng `openssl rand -base64 32` rồi lưu an toàn (đổi chuỗi này thì các bản sao lưu CŨ giải mã bằng chuỗi cũ vẫn đọc được, chỉ bản MỚI dùng chuỗi mới) |

Đọc chi tiết lỗi trong tab Actions → chọn lần chạy đỏ → xem log.
