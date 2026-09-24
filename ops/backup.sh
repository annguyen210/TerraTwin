#!/usr/bin/env bash
# ============================================================================
# TerraTwin — sao lưu PostgreSQL, MÃ HOÁ trước khi rời máy.
#
# VÌ SAO: kho quan sát thực địa là tài sản DUY NHẤT đối thủ không mua được, và
# gói Postgres miễn phí của Render CÓ THỜI HẠN. Một cơ sở dữ liệu chưa ai sao
# lưu lần nào là một quả bom hẹn giờ.
#
# VÌ SAO PHẢI MÃ HOÁ: bản dump Postgres thô chứa email, hash mật khẩu, và toạ
# độ thửa — lộ những thứ đó ra ngoài còn tệ hơn không sao lưu. Đặt
# TERRATWIN_BACKUP_PASSPHRASE thì script mã hoá bằng gpg (AES256, đối xứng)
# trước khi ghi ra đĩa; KHÔNG đặt thì cảnh báo đỏ và vẫn để bản THÔ (chỉ dùng
# khi chạy tay, backup cục bộ, không đẩy đi đâu).
#
# CÁCH DÙNG (cron ngoài — cron-job.org / GitHub Actions theo lịch, mỗi ngày):
#   TERRATWIN_DATABASE_URL=postgresql://...  TERRATWIN_BACKUP_DIR=/data/backups \
#     TERRATWIN_BACKUP_PASSPHRASE=...        bash ops/backup.sh
#
# Giữ 7 bản NGÀY + 4 bản TUẦN. Sau khi tạo bản local, ĐẨY sang nơi khác — bản
# sao nằm cùng máy với bản gốc thì không cứu được khi mất cả máy.
#
# backup.yml đẩy vào một REPO RIÊNG TƯ KHÁC (TERRATWIN_BACKUP_REPO) — TUYỆT
# ĐỐI không đẩy vào repo TerraTwin này (repo này CÔNG KHAI). Mã hoá GPG chỉ
# trễ việc đọc được, không cứu được việc PHÁT TÁN: ai `git clone` một nhánh
# công khai cũng tải được các bản .sql.gz.gpg đó vĩnh viễn, kể cả sau khi xoá
# nhánh — đây là lý do bắt buộc phải là repo riêng tư, không phải chỉ mã hoá
# là đủ.
#
# QUAN TRỌNG: một bản sao lưu CHƯA TỪNG khôi phục thử thì CHƯA phải bản sao lưu.
# Xem ops/restore-drill.sh — phải chạy thành công một lần trước khi tin nó.
# Cách GIẢI MÃ một bản để khôi phục: xem ops/RESTORE.md.
# ============================================================================
set -euo pipefail

: "${TERRATWIN_DATABASE_URL:?Cần TERRATWIN_DATABASE_URL (postgresql://...)}"
DIR="${TERRATWIN_BACKUP_DIR:-./backups}"
mkdir -p "$DIR/daily" "$DIR/weekly"

# pg_dump nhận trực tiếp URL. Bỏ tiền tố SQLAlchemy nếu có (+psycopg).
URL="${TERRATWIN_DATABASE_URL/postgresql+psycopg:/postgresql:}"
STAMP="$(date +%Y%m%d-%H%M%S)"
RAW="$DIR/daily/terratwin-$STAMP.sql.gz"

echo "[backup] pg_dump → $RAW"
pg_dump "$URL" --no-owner --no-privileges | gzip -9 > "$RAW"
test -s "$RAW" || { echo "[backup] LỖI: bản dump rỗng"; exit 1; }

# Mã hoá NGAY, rồi xoá bản thô — không được để bản thô nằm lại dù chỉ một giây
# lâu hơn cần thiết trên máy có thể đẩy lên nơi công khai.
if [ -n "${TERRATWIN_BACKUP_PASSPHRASE:-}" ]; then
  OUT="$RAW.gpg"
  gpg --batch --yes --pinentry-mode loopback \
      --passphrase-fd 3 3<<< "$TERRATWIN_BACKUP_PASSPHRASE" \
      --symmetric --cipher-algo AES256 -o "$OUT" "$RAW"
  rm -f "$RAW"
else
  OUT="$RAW"
  echo "[backup] CẢNH BÁO: chưa đặt TERRATWIN_BACKUP_PASSPHRASE — bản dump KHÔNG được"
  echo "[backup] mã hoá. TUYỆT ĐỐI không đẩy bản này lên nơi công khai (repo CÔNG KHAI)."
fi

# Bản tuần: mỗi thứ Hai giữ một bản riêng.
if [ "$(date +%u)" = "1" ]; then
  cp "$OUT" "$DIR/weekly/$(basename "$OUT")"
fi

# Xoay vòng: giữ 7 bản ngày mới nhất, 4 bản tuần mới nhất (dù thô hay đã mã hoá).
#
# `|| true` sau ls BẮT BUỘC: dưới set -e + pipefail, "ls glob-không-khớp" tự nó
# thoát mã khác 0 (dù 2>/dev/null đã nuốt THÔNG BÁO lỗi, KHÔNG nuốt MÃ THOÁT) —
# và pipefail thì lấy mã thoát khác 0 đầu tiên trong cả ống, nên script CHẾT
# ngay ở LẦN CHẠY ĐẦU TIÊN khi thư mục weekly còn trống. Lỗi này có từ bản gốc,
# lộ ra khi viết test_ops_backup.py (không có Postgres thật để lỡ có sẵn file cũ).
{ ls -1t "$DIR/daily"/*.sql.gz* 2>/dev/null || true; }  | tail -n +8 | xargs -r rm -f
{ ls -1t "$DIR/weekly"/*.sql.gz* 2>/dev/null || true; } | tail -n +5 | xargs -r rm -f

echo "[backup] xong: $(du -h "$OUT" | cut -f1) — $(ls -1 "$DIR/daily" | wc -l) bản ngày"

# --- ĐẨY RA NGOÀI ------------------------------------------------------------
# .github/workflows/backup.yml đã tự đẩy vào nhánh `backups` của repo này sau
# khi script này chạy xong (xem workflow đó) — không cần điền gì thêm ở đây
# cho luồng tự động. Chạy TAY thì tự đẩy theo hạ tầng của bạn, ví dụ:
#   rclone copy "$OUT" remote:terratwin-backups/
