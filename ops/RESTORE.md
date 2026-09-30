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
- **Quyền đọc repo sao lưu riêng tư** (`TERRATWIN_BACKUP_REPO`, xem mục 3) —
  repo này KHÔNG PHẢI TerraTwin công khai; bạn cần tài khoản GitHub có quyền
  vào đó (chủ tài khoản đã tạo nó khi đặt secret `TERRATWIN_BACKUP_REPO`).

## 1. Diễn tập (làm trước, không đụng dữ liệu thật)

```bash
git clone https://github.com/annguyen210/TerraTwin.git
cd TerraTwin

# Tải bản sao lưu từ repo RIÊNG TƯ (KHÁC repo TerraTwin công khai này) —
# thay <chủ-sở-hữu>/<tên-repo> bằng đúng giá trị đã đặt trong secret
# TERRATWIN_BACKUP_REPO. Repo này private nên `git clone` cần bạn đã đăng
# nhập/có quyền (SSH key hoặc `gh auth login`).
git clone https://github.com/<chủ-sở-hữu>/<tên-repo-sao-lưu>.git ../terratwin-backups
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
  Bản cũ hơn tự động bị xoá — không cần dọn tay.
- **Nằm ở repo RIÊNG TƯ KHÁC**, không phải nhánh của repo TerraTwin công khai
  này — xem secret `TERRATWIN_BACKUP_REPO` để biết chính xác tên repo đó.
  ĐÂY LÀ THAY ĐỔI so với bản thiết kế đầu tiên (từng lưu trong nhánh `backups`
  của chính repo công khai — đã sửa vì mã hoá chỉ trễ việc đọc được, không
  cứu được việc một repo công khai bị `git clone` và giữ bản mãi mãi).
- Mọi bản đều **đã mã hoá** trước khi lưu — hai lớp bảo vệ cộng lại (repo
  riêng tư + mã hoá), không chỉ dựa vào một lớp.

## 4. Thiết lập repo sao lưu riêng tư LẦN ĐẦU (chỉ chủ dự án làm, một lần)

1. Tạo một repo GitHub MỚI, đặt **Private**, không cần file nào bên trong
   (không cần README, không cần .gitignore).
2. Vào GitHub → ảnh đại diện góc phải → **Settings** → **Developer settings**
   → **Personal access tokens** → **Fine-grained tokens** → **Generate new
   token**.
   - **Repository access**: chọn **Only select repositories**, chọn ĐÚNG repo
     vừa tạo ở bước 1. TUYỆT ĐỐI không chọn repo TerraTwin công khai.
   - **Permissions** → **Repository permissions** → **Contents**: chọn
     **Read and write**.
   - Tạo token, copy lại ngay (chỉ hiện một lần).
3. Vào repo **TerraTwin** (repo công khai, repo đang chạy code) → **Settings**
   → **Secrets and variables** → **Actions**, thêm hai secret:
   - `TERRATWIN_BACKUP_REPO` = `<chủ-sở-hữu>/<tên-repo-vừa-tạo>` (vd
     `annguyen210/terratwin-backups`)
   - `TERRATWIN_BACKUP_REPO_PAT` = token vừa copy ở bước 2

## 5. Nếu workflow báo đỏ trên GitHub Actions

Nguyên nhân thường gặp nhất là thiếu hoặc sai một trong bốn secret sau
(Settings → Secrets and variables → Actions, trên repo **TerraTwin**):

| Secret | Lấy ở đâu |
|---|---|
| `TERRATWIN_NEON_URL` | Neon → project → **Connect** → chọn kết nối **Direct** (host KHÔNG có `-pooler`), giữ nguyên đuôi `?sslmode=require…`. Từ khi chuyển xong (mục 6) đây là CSDL được sao lưu |
| `TERRATWIN_DB_EXTERNAL_URL` | Render → database `terratwin-db` → tab Connect → **External Database URL** (không phải Internal — GitHub Actions không nằm trong mạng nội bộ Render). Chỉ cần tới khi chuyển sang Neon xong; CSDL này bị Render xoá ngày 9/10/2026 |
| `TERRATWIN_BACKUP_PASSPHRASE` | Chuỗi bạn tự sinh một lần và cất giữ — nếu chưa có, sinh mới bằng `openssl rand -base64 32` rồi lưu an toàn (đổi chuỗi này thì các bản sao lưu CŨ giải mã bằng chuỗi cũ vẫn đọc được, chỉ bản MỚI dùng chuỗi mới) |
| `TERRATWIN_BACKUP_REPO` | Xem mục 4 — tạo repo riêng tư trước, rồi mới đặt secret này |
| `TERRATWIN_BACKUP_REPO_PAT` | Xem mục 4 — fine-grained PAT chỉ cấp quyền cho ĐÚNG repo `TERRATWIN_BACKUP_REPO` |

Đọc chi tiết lỗi trong tab Actions → chọn lần chạy đỏ → xem log.

## 6. Chuyển CSDL từ Render sang Neon (29/9/2026) — cũng là diễn tập N2

**Vì sao.** Postgres miễn phí của Render hết hạn 30 ngày sau khi tạo, thêm 14
ngày ân hạn rồi bị **xoá cả dữ liệu** — `terratwin-db` bị xoá ngày
**9/10/2026**. Neon gói miễn phí không có hạn xoá. Lần chuyển này là một lần
khôi phục thật từ bản dump vào một CSDL trống, có đối chiếu từng bảng, nên nó
cũng là bài diễn tập khôi phục N2.

**Làm theo thứ tự:**

1. Tạo project Neon (vùng US West Oregon), chọn **Postgres 17 trở lên** (18
   nếu có — cùng bản Render). Bản cũ hơn có thể không hiểu vài câu `SET` trong
   bản dump của pg_dump 18.
2. Đặt 2 secret ở repo TerraTwin → Settings → Secrets → Actions:
   `TERRATWIN_NEON_URL` (URL **Direct**) và `TERRATWIN_DB_EXTERNAL_URL` (URL
   ngoài của Render) — xem bảng ở mục 5.
3. Actions → **Migrate DB to Neon (one-time)** → Run workflow. Nên chạy
   **trước 1/10/2026**, khi api còn bị đình chỉ: CSDL nguồn đứng yên, không có
   dòng mới chen vào giữa lúc dump và lúc trỏ app sang Neon.
4. Chỉ khi kết luận là **✅ KHỚP**: Render → `terratwin-api` → Environment →
   đặt `TERRATWIN_DATABASE_URL` = URL Neon (Direct). Làm trước 1/10 để khi api
   sống lại, nó ghi vào Neon ngay từ lượt đầu.
5. Sau khi api chạy: mở `/api/health` — trường `database` phải là
   `{"kind": "postgresql", "provider": "neon"}`. Thấy `"sqlite"` là biến chưa
   đặt: app đang ghi vào đĩa tạm và mất dữ liệu mỗi lần khởi động lại.

Workflow chỉ ĐỌC Render; nạp vào Neon trong **một transaction** nên lỗi ở bất
kỳ dòng nào thì Neon quay về trống (chạy lại được). Neon đã có bảng thì workflow
từ chối nạp, trừ khi bật ô `reset_target` (xoá sạch schema `public` ở Neon
trước). Bản dump không bao giờ được in ra hay upload — repo công khai.

**Cách đọc kết quả.** Summary của lần chạy có hai bảng: số dòng từng bảng ở
hai bên, và mọi sequence (id tự tăng). Sequence phải khớp `last_value` và ở
Neon phải ≥ `max(id)` — nếu không, lần thêm dòng đầu tiên trên Neon sẽ lỗi
trùng khoá chính dù bảng đủ dòng.

**Kết quả lần chạy thật:** _chưa chạy._ Bảng đối chiếu của lần chạy thành công
được chép vào đây, kèm ngày và mã lần chạy.
