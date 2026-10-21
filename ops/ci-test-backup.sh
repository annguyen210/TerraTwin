#!/usr/bin/env bash
# ============================================================================
# Test THẬT cho ops/backup.sh + ops/restore-drill.sh trên PostgreSQL 18 trong CI
# (cùng job với ci-test-migrate.sh). Không cần Neon hay secret: một CSDL nguồn có
# đúng schema của app + dữ liệu, sao lưu MÃ HOÁ, rồi diễn tập khôi phục vào CSDL trống.
#
#   PG_ADMIN_URL=postgresql://postgres:postgres@localhost:5432/postgres \
#     bash ops/ci-test-backup.sh
#
# Ba ca: (1) có ghi thêm trong lúc sao lưu + có số đếm trước → KHỚP; (2) không có số
# đếm trước mà gốc đã đổi → phải LỆCH; (3) sai chuỗi mật khẩu → phải hỏng, không
# được báo khớp. Ca 2–3 là lý do viết lại diễn tập 21/10/2026: bản cũ chỉ so bảng
# observations và đếm lỗi thì ra 0, nên khôi phục hỏng vẫn "0 = 0, KHỚP".
# ============================================================================
set -euo pipefail

: "${PG_ADMIN_URL:?Cần PG_ADMIN_URL}"
HERE="$(cd "$(dirname "$0")" && pwd)"
BASE="${PG_ADMIN_URL%/*}"
SRC="$BASE/bk_src"; D1="$BASE/bk_dst1"; D2="$BASE/bk_dst2"; D3="$BASE/bk_dst3"
BK="$(mktemp -d)"; PASS="ci-test-passphrase-$RANDOM"

psql "$PG_ADMIN_URL" -X -q -v ON_ERROR_STOP=1 <<'SQL'
DROP DATABASE IF EXISTS bk_src; DROP DATABASE IF EXISTS bk_dst1;
DROP DATABASE IF EXISTS bk_dst2; DROP DATABASE IF EXISTS bk_dst3;
CREATE DATABASE bk_src; CREATE DATABASE bk_dst1; CREATE DATABASE bk_dst2; CREATE DATABASE bk_dst3;
SQL
( cd "$HERE/../backend" && TERRATWIN_DATABASE_URL="$SRC" python -c "from app import db; db.init_db()" ) > /tmp/b0.log 2>&1 \
  || { cat /tmp/b0.log; echo "::error::init_db trên nguồn lỗi"; exit 1; }
psql "$SRC" -X -q -v ON_ERROR_STOP=1 <<'SQL'
CREATE TABLE ci_live (id serial PRIMARY KEY, v text);
INSERT INTO ci_live (v) SELECT 'dòng ' || g FROM generate_series(1, 30) g;
SQL

pass=0; failn=0
ok()  { echo "✅ $1"; pass=$((pass + 1)); }
bad() { echo "❌ $1"; failn=$((failn + 1)); echo "::error title=$(basename "$0")::$1"; }

bash "$HERE/restore-drill.sh" count "$SRC" > "$BK/before.tsv"
grep -q "^ci_live	30$" "$BK/before.tsv" && ok "đếm trước: ci_live 30 hàng" || bad "đếm trước sai: $(grep ci_live "$BK/before.tsv")"

TERRATWIN_DATABASE_URL="$SRC" TERRATWIN_BACKUP_DIR="$BK" TERRATWIN_BACKUP_PASSPHRASE="$PASS" \
  bash "$HERE/backup.sh" > /tmp/b1.log 2>&1 || { cat /tmp/b1.log; bad "backup.sh lỗi"; }
ls "$BK"/daily/*.sql.gz.gpg >/dev/null 2>&1 && ok "bản sao lưu đã mã hoá" || bad "không có tệp .gpg"
ls "$BK"/daily/*.sql.gz >/dev/null 2>&1 && bad "còn bản THÔ chưa mã hoá" || ok "không còn bản thô"

psql "$SRC" -X -q -v ON_ERROR_STOP=1 -c "INSERT INTO ci_live (v) VALUES ('sau 1'), ('sau 2')"   # ghi trong lúc sao lưu

echo "── Ca 1: có số đếm trước, gốc ghi thêm 2 hàng sau khi dump → KHỚP"
if TERRATWIN_DATABASE_URL="$SRC" TERRATWIN_SCRATCH_URL="$D1" TERRATWIN_BACKUP_DIR="$BK" \
   TERRATWIN_BACKUP_PASSPHRASE="$PASS" TERRATWIN_DRILL_BEFORE="$BK/before.tsv" \
   bash "$HERE/restore-drill.sh" > /tmp/b2.log 2>&1 && grep -q "KHỚP" /tmp/b2.log; then ok "diễn tập khớp"; else cat /tmp/b2.log; bad "ca 1"; fi
n=$(psql "$D1" -X -At -c "SELECT count(*) FROM ci_live")
[ "$n" = "30" ] && ok "bản khôi phục có đúng 30 hàng ci_live" || bad "ci_live khôi phục = $n"
tables_src=$(psql "$SRC" -X -At -c "SELECT count(*) FROM pg_tables WHERE schemaname='public'")
tables_dst=$(psql "$D1" -X -At -c "SELECT count(*) FROM pg_tables WHERE schemaname='public'")
[ "$tables_src" = "$tables_dst" ] && ok "đủ $tables_dst bảng" || bad "bảng: gốc $tables_src, khôi phục $tables_dst"

echo "── Ca 2: KHÔNG có số đếm trước, gốc đã khác bản dump → phải LỆCH"
if TERRATWIN_DATABASE_URL="$SRC" TERRATWIN_SCRATCH_URL="$D2" TERRATWIN_BACKUP_DIR="$BK" \
   TERRATWIN_BACKUP_PASSPHRASE="$PASS" bash "$HERE/restore-drill.sh" > /tmp/b3.log 2>&1; then
  cat /tmp/b3.log; bad "ca 2 báo khớp dù gốc đã đổi"
else grep -q "ci_live" /tmp/b3.log && ok "ca 2 lệch đúng chỗ (ci_live)" || { cat /tmp/b3.log; bad "ca 2 lệch nhưng không chỉ ra bảng"; }; fi

echo "── Ca 3: sai chuỗi mật khẩu → phải hỏng"
if TERRATWIN_DATABASE_URL="$SRC" TERRATWIN_SCRATCH_URL="$D3" TERRATWIN_BACKUP_DIR="$BK" \
   TERRATWIN_BACKUP_PASSPHRASE="sai-$PASS" TERRATWIN_DRILL_BEFORE="$BK/before.tsv" \
   bash "$HERE/restore-drill.sh" > /tmp/b4.log 2>&1; then cat /tmp/b4.log; bad "ca 3 báo khớp với mật khẩu sai"
else ok "ca 3 hỏng đúng (sai mật khẩu)"; fi

rm -rf "$BK"
echo "Kết quả: $pass đạt, $failn hỏng"
[ "$failn" = "0" ]
