#!/usr/bin/env bash
# ============================================================================
# TerraTwin — sao lưu PostgreSQL.
#
# VÌ SAO: kho quan sát thực địa là tài sản DUY NHẤT đối thủ không mua được, và
# gói Postgres miễn phí của Render CÓ THỜI HẠN. Một cơ sở dữ liệu chưa ai sao
# lưu lần nào là một quả bom hẹn giờ.
#
# CÁCH DÙNG (cron ngoài — cron-job.org / GitHub Actions theo lịch, mỗi ngày):
#   TERRATWIN_DATABASE_URL=postgresql://...  TERRATWIN_BACKUP_DIR=/data/backups \
#     bash ops/backup.sh
#
# Giữ 7 bản NGÀY + 4 bản TUẦN. Sau khi tạo bản local, ĐẨY sang nơi khác (object
# storage, hoặc một kho Git riêng tư nếu dữ liệu còn nhỏ) — bản sao nằm cùng máy
# với bản gốc thì không cứu được khi mất cả máy. Chỗ đẩy tuỳ hạ tầng: điền ở
# cuối file.
#
# QUAN TRỌNG: một bản sao lưu CHƯA TỪNG khôi phục thử thì CHƯA phải bản sao lưu.
# Xem ops/restore-drill.sh — phải chạy thành công một lần trước khi tin nó.
# ============================================================================
set -euo pipefail

: "${TERRATWIN_DATABASE_URL:?Cần TERRATWIN_DATABASE_URL (postgresql://...)}"
DIR="${TERRATWIN_BACKUP_DIR:-./backups}"
mkdir -p "$DIR/daily" "$DIR/weekly"

# pg_dump nhận trực tiếp URL. Bỏ tiền tố SQLAlchemy nếu có (+psycopg).
URL="${TERRATWIN_DATABASE_URL/postgresql+psycopg:/postgresql:}"
STAMP="$(date +%Y%m%d-%H%M)"
OUT="$DIR/daily/terratwin-$STAMP.sql.gz"

echo "[backup] pg_dump → $OUT"
pg_dump "$URL" --no-owner --no-privileges | gzip -9 > "$OUT"
test -s "$OUT" || { echo "[backup] LỖI: bản dump rỗng"; exit 1; }

# Bản tuần: mỗi thứ Hai giữ một bản riêng.
if [ "$(date +%u)" = "1" ]; then
  cp "$OUT" "$DIR/weekly/terratwin-$STAMP.sql.gz"
fi

# Xoay vòng: giữ 7 bản ngày mới nhất, 4 bản tuần mới nhất.
ls -1t "$DIR/daily"/*.sql.gz 2>/dev/null | tail -n +8  | xargs -r rm -f
ls -1t "$DIR/weekly"/*.sql.gz 2>/dev/null | tail -n +5 | xargs -r rm -f

echo "[backup] xong: $(du -h "$OUT" | cut -f1) — $(ls -1 "$DIR/daily" | wc -l) bản ngày"

# --- ĐẨY RA NGOÀI (điền theo hạ tầng của bạn) -------------------------------
# Ví dụ object storage:  rclone copy "$OUT" remote:terratwin-backups/
# Ví dụ kho Git riêng:   (cd "$DIR" && git add -A && git commit -m "backup $STAMP" && git push)
# Chưa điền = bản sao lưu vẫn nằm CÙNG máy với bản gốc: chống xoá nhầm, KHÔNG
# chống mất máy. Điền trước khi có 100 quan sát thật.
