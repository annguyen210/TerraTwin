#!/usr/bin/env bash
# ============================================================================
# Chuyển toàn bộ CSDL TerraTwin từ Render sang Neon — MỘT LẦN, 29/9/2026.
# Đồng thời là bài DIỄN TẬP KHÔI PHỤC N2: dump thật → nạp vào CSDL trống →
# đối chiếu từng bảng. Kết quả ghi vào ops/RESTORE.md mục 6.
#
#   SRC_URL=<URL ngoài Render>  DST_URL=<URL Neon DIRECT>  bash ops/migrate-neon.sh
#   RESET_TARGET=1 ...   # CHỈ khi chạy lại: xoá sạch schema public ở Neon trước
#
# AN TOÀN:
#   · Chỉ ĐỌC nguồn. Đích phải TRỐNG (hoặc RESET_TARGET=1) — không bao giờ trộn
#     dữ liệu vào một CSDL đang có bảng.
#   · Nạp trong MỘT transaction (--single-transaction + ON_ERROR_STOP): lỗi ở
#     bất kỳ dòng nào thì Neon quay về trống, không bao giờ nửa vời. backup.yml
#     dựa vào điều này — nó coi "Neon có bảng" là "đã chuyển xong".
#   · Bản dump nằm trong thư mục tạm quyền 700, xoá khi thoát (kể cả khi lỗi).
#     KHÔNG in URL, KHÔNG in nội dung dump, KHÔNG upload làm artifact — repo
#     công khai, dump chứa email + hash mật khẩu + toạ độ thửa.
# ============================================================================
set -euo pipefail

: "${SRC_URL:?Cần SRC_URL (URL ngoài của CSDL Render)}"
: "${DST_URL:?Cần DST_URL (URL Neon loại DIRECT)}"
SRC="${SRC_URL/postgresql+psycopg:/postgresql:}"
DST="${DST_URL/postgresql+psycopg:/postgresql:}"
HERE="$(cd "$(dirname "$0")" && pwd)"

case "$DST" in
  *-pooler.*) echo "::error::DST_URL là URL pooler (PgBouncer). Dùng URL DIRECT của Neon (host không có '-pooler')."; exit 1 ;;
esac

WORK="$(mktemp -d)"; chmod 700 "$WORK"
trap 'rm -rf "$WORK"' EXIT
DUMP="$WORK/terratwin.sql"

q() { psql "$1" -X -v ON_ERROR_STOP=1 -At -c "$2" </dev/null; }

echo "── 1. Nguồn"
q "$SRC" "SELECT 'PostgreSQL ' || current_setting('server_version') || ' · ' ||
                 pg_size_pretty(pg_database_size(current_database()))"
echo "   5 bảng lớn nhất:"
q "$SRC" "SELECT '   ' || relname || ': ' || pg_size_pretty(pg_total_relation_size(relid))
          FROM pg_stat_user_tables ORDER BY pg_total_relation_size(relid) DESC LIMIT 5"
SRC_BYTES="$(q "$SRC" "SELECT pg_database_size(current_database())")"
# Neon gói miễn phí giới hạn dung lượng mỗi project (0,5 GB lúc viết). Vượt thì
# Neon từ chối ghi giữa chừng → transaction quay lui, không hỏng gì, nhưng báo
# sớm để biết phải dọn bảng cache (kv_cache) trước.
if [ "$SRC_BYTES" -gt $((450 * 1024 * 1024)) ]; then
  echo "::warning::CSDL nguồn > 450 MB — sát/vượt hạn dung lượng Neon gói miễn phí. Nạp có thể bị từ chối."
fi

echo "── 2. Đích"
q "$DST" "SELECT 'PostgreSQL ' || current_setting('server_version')"
DST_TABLES="$(q "$DST" "SELECT count(*) FROM pg_tables
                        WHERE schemaname NOT IN ('pg_catalog', 'information_schema')")"
if [ "$DST_TABLES" -gt 0 ]; then
  if [ "${RESET_TARGET:-0}" = "1" ]; then
    echo "   RESET_TARGET=1: xoá $DST_TABLES bảng ở schema public của đích."
    q "$DST" "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" >/dev/null
  else
    echo "::error::Đích đã có $DST_TABLES bảng. Không trộn dữ liệu. Chạy lại với reset_target nếu chắc chắn muốn ghi đè."
    exit 1
  fi
else
  echo "   Trống — sẵn sàng nạp."
fi

echo "── 3. pg_dump nguồn (plain, --no-owner --no-privileges)"
pg_dump "$SRC" --format=plain --no-owner --no-privileges --file="$DUMP"
echo "   $(du -h "$DUMP" | cut -f1)"

echo "── 4. Nạp vào đích (một transaction, dừng ở lỗi đầu tiên)"
psql "$DST" -X -q -v ON_ERROR_STOP=1 --single-transaction -f "$DUMP" >/dev/null
rm -f "$DUMP"
echo "   Xong."

echo "── 5. Đối chiếu"
bash "$HERE/db-reconcile.sh" "$SRC" "$DST"
