#!/usr/bin/env bash
# ============================================================================
# TerraTwin — DIỄN TẬP khôi phục. Một bản sao lưu chưa từng khôi phục thử thì
# CHƯA phải bản sao lưu.
#
# Khôi phục bản mới nhất vào một CSDL SCRATCH (không đụng production), rồi so số
# hàng của MỌI bảng với bản gốc. Từ 21/10/2026 chạy TỰ ĐỘNG mỗi ngày trong
# backup.yml, vào một Postgres tạm trên máy chạy CI (dữ liệu không rời máy đó).
#
# Bản cũ chỉ so bảng observations, và đếm lỗi thì trả 0 — production đang 0 quan
# sát, nên khôi phục hỏng hoàn toàn vẫn ra "0 = 0, KHỚP". Bản này: psql dừng ở lỗi
# đầu tiên, so đủ mọi bảng, thiếu bảng là trượt, đếm lỗi là trượt.
#
# CÁCH DÙNG:
#   bash ops/restore-drill.sh count <url>        # in "bảng<TAB>số hàng" (đếm trước khi sao lưu)
#
#   TERRATWIN_DATABASE_URL=postgresql://...      # DB gốc (để đếm đối chiếu)
#   TERRATWIN_SCRATCH_URL=postgresql://.../scratch  # DB trống để khôi phục vào
#   TERRATWIN_BACKUP_DIR=/data/backups
#   TERRATWIN_BACKUP_PASSPHRASE=...              # CHỈ cần nếu bản mới nhất đã mã hoá (.gpg)
#   TERRATWIN_DRILL_BEFORE=before.tsv            # tuỳ chọn: số đếm TRƯỚC khi sao lưu
#   bash ops/restore-drill.sh
#
# Có TERRATWIN_DRILL_BEFORE thì mỗi bảng phải nằm GIỮA số đếm trước và sau khi sao
# lưu (CSDL vẫn đang ghi trong lúc sao lưu — bảng cache, nhật ký); bảng không đổi
# trong khoảng đó thì phải khớp đúng. Không có thì phải khớp đúng số đếm hiện tại.
# Chỉ in tên bảng và số hàng — không bao giờ in nội dung.
# ============================================================================
set -euo pipefail

counts() {
  local url="${1/postgresql+psycopg:/postgresql:}" t n
  local tables
  tables="$(psql "$url" -X -v ON_ERROR_STOP=1 -tAc \
    "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1")"
  for t in $tables; do
    n="$(psql "$url" -X -v ON_ERROR_STOP=1 -tAc "SELECT count(*) FROM public.\"$t\"")"
    printf '%s\t%s\n' "$t" "$n"
  done
}

if [ "${1:-}" = "count" ]; then
  counts "${2:?Cần URL}"
  exit 0
fi

: "${TERRATWIN_DATABASE_URL:?Cần URL DB gốc}"
: "${TERRATWIN_SCRATCH_URL:?Cần TERRATWIN_SCRATCH_URL (một DB trống để khôi phục vào)}"
DIR="${TERRATWIN_BACKUP_DIR:-./backups}"
DST="${TERRATWIN_SCRATCH_URL/postgresql+psycopg:/postgresql:}"
TMP="$(mktemp -d)"

# `|| true` sau ls BẮT BUỘC dưới set -e + pipefail — xem ghi chú trong backup.sh.
LATEST="$({ ls -1t "$DIR"/daily/*.sql.gz* 2>/dev/null || true; } | head -1)"
test -n "$LATEST" || { echo "Không tìm thấy bản sao lưu trong $DIR/daily"; exit 1; }
echo "[drill] khôi phục $(basename "$LATEST") → scratch"

restore() { psql "$DST" -X -q -v ON_ERROR_STOP=1 >/dev/null; }
if [[ "$LATEST" == *.gpg ]]; then
  : "${TERRATWIN_BACKUP_PASSPHRASE:?Bản mới nhất đã mã hoá — cần TERRATWIN_BACKUP_PASSPHRASE để giải mã}"
  gpg --batch --yes --quiet --pinentry-mode loopback \
      --passphrase-fd 3 3<<< "$TERRATWIN_BACKUP_PASSPHRASE" \
      --decrypt "$LATEST" | gunzip -c | restore
else
  gunzip -c "$LATEST" | restore
fi

counts "$TERRATWIN_DATABASE_URL" > "$TMP/after.tsv"
counts "$DST" > "$TMP/restored.tsv"
BEFORE="${TERRATWIN_DRILL_BEFORE:-$TMP/after.tsv}"
test -s "$TMP/after.tsv" || { echo "[drill] ❌ CSDL gốc không có bảng nào — không có gì để đối chiếu."; exit 1; }

# So khớp (ops/restore-drill-compare.awk): mỗi bảng ở gốc phải có trong bản khôi phục, số hàng nằm giữa trước/sau.
if awk -F'\t' -v B="$BEFORE" -v R="$TMP/restored.tsv" -f "$(dirname "$0")/restore-drill-compare.awk" "$TMP/after.tsv"; then
  echo "[drill] ✅ KHỚP — bản sao lưu khôi phục được, đủ mọi bảng."
else
  echo "[drill] ❌ LỆCH — chưa được tin bản sao lưu này."; exit 1
fi
rm -rf "$TMP"
