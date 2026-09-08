#!/usr/bin/env bash
# ============================================================================
# TerraTwin — DIỄN TẬP khôi phục. Một bản sao lưu chưa từng khôi phục thử thì
# CHƯA phải bản sao lưu.
#
# Khôi phục bản mới nhất vào một CSDL SCRATCH (không đụng production), rồi so số
# hàng bảng observations với bản gốc. Đây là cửa ải của Đợt 1 — chỉ tick N2 xong
# khi script này chạy thành công MỘT lần trên Postgres thật.
#
# CÁCH DÙNG:
#   TERRATWIN_DATABASE_URL=postgresql://...      # DB gốc (để đếm đối chiếu)
#   TERRATWIN_SCRATCH_URL=postgresql://.../scratch  # DB trống để khôi phục vào
#   TERRATWIN_BACKUP_DIR=/data/backups  bash ops/restore-drill.sh
# ============================================================================
set -euo pipefail

: "${TERRATWIN_DATABASE_URL:?Cần URL DB gốc}"
: "${TERRATWIN_SCRATCH_URL:?Cần TERRATWIN_SCRATCH_URL (một DB trống để khôi phục vào)}"
DIR="${TERRATWIN_BACKUP_DIR:-./backups}"
SRC="${TERRATWIN_DATABASE_URL/postgresql+psycopg:/postgresql:}"
DST="${TERRATWIN_SCRATCH_URL/postgresql+psycopg:/postgresql:}"

LATEST="$(ls -1t "$DIR"/daily/*.sql.gz 2>/dev/null | head -1)"
test -n "$LATEST" || { echo "Không tìm thấy bản sao lưu trong $DIR/daily"; exit 1; }
echo "[drill] khôi phục $LATEST → scratch"

gunzip -c "$LATEST" | psql "$DST" >/dev/null

count() { psql "$1" -tAc "SELECT count(*) FROM observations" 2>/dev/null || echo 0; }
A="$(count "$SRC")"; B="$(count "$DST")"
echo "[drill] observations — gốc=$A  khôi phục=$B"
if [ "$A" = "$B" ]; then
  echo "[drill] ✅ KHỚP — bản sao lưu khôi phục được. Được phép tick N2 xong."
else
  echo "[drill] ❌ LỆCH — chưa được tin bản sao lưu này."; exit 1
fi
