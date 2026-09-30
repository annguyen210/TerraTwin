#!/usr/bin/env bash
# ============================================================================
# Test THẬT cho ops/migrate-neon.sh + ops/db-reconcile.sh, chạy trong CI trên
# PostgreSQL 18 (cùng bản CSDL Render) với pg_dump/psql cài bằng
# ops/install-pg-client.sh. Không cần Neon: hai CSDL trên cùng máy chủ đóng
# vai nguồn/đích — thứ được kiểm là LOGIC chuyển và đối chiếu.
#
#   PG_ADMIN_URL=postgresql://postgres:postgres@localhost:5432/postgres \
#     bash ops/ci-test-migrate.sh
#
# Nguồn dùng ĐÚNG schema của app (init_db) cộng hai bảng có serial/identity và
# dữ liệu, để kiểm cả số dòng lẫn sequence.
# ============================================================================
set -euo pipefail

: "${PG_ADMIN_URL:?Cần PG_ADMIN_URL}"
HERE="$(cd "$(dirname "$0")" && pwd)"
BASE="${PG_ADMIN_URL%/*}"
SRC="$BASE/mig_src"; DST="$BASE/mig_dst"

psql "$PG_ADMIN_URL" -X -q -v ON_ERROR_STOP=1 <<'SQL'
DROP DATABASE IF EXISTS mig_src;
DROP DATABASE IF EXISTS mig_dst;
CREATE DATABASE mig_src;
CREATE DATABASE mig_dst;
SQL

# Schema thật của app.
( cd "$HERE/../backend" && TERRATWIN_DATABASE_URL="$SRC" python -c "from app import db; db.init_db()" )   > /tmp/m0.log 2>&1 || { cat /tmp/m0.log; bad "init_db trên nguồn lỗi" /tmp/m0.log; exit 1; }

psql "$SRC" -X -q -v ON_ERROR_STOP=1 <<'SQL'
CREATE TABLE ci_serial (id serial PRIMARY KEY, v text);
INSERT INTO ci_serial (v) SELECT 'dòng ' || g FROM generate_series(1, 25) g;
DELETE FROM ci_serial WHERE id > 20;           -- sequence (25) đi trước max(id) (20)
CREATE TABLE ci_ident (id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, v text);
INSERT INTO ci_ident (v) VALUES ('a'), ('b'), ('c');
SQL

pass=0; failn=0
ok()  { echo "✅ $1"; pass=$((pass + 1)); }
# ::error:: để lý do hỏng hiện ở annotation — đọc được qua API công khai, còn
# log job của repo công khai chỉ quản trị viên tải được.
bad() {
  echo "❌ $1"; failn=$((failn + 1))
  local tail_=""
  if [ -n "${2:-}" ] && [ -f "$2" ]; then tail_="$(tail -n 25 "$2")"; fi
  # Mã hoá xuống dòng theo luật workflow command: % → %25, CR → %0D, LF → %0A.
  local msg
  msg="$(printf '%s\n%s' "$1" "$tail_" | python3 -c 'import sys; print(sys.stdin.read().replace("%","%25").replace("\r","%0D").replace("\n","%0A"), end="")')"
  echo "::error title=$(basename "$0")::$msg"
}

echo "── Ca 1: chuyển sang đích trống → phải KHỚP"
if SRC_URL="$SRC" DST_URL="$DST" bash "$HERE/migrate-neon.sh" > /tmp/m1.log 2>&1 \
   && grep -q "KHỚP" /tmp/m1.log; then ok "chuyển + đối chiếu khớp"; else cat /tmp/m1.log; bad "ca 1" /tmp/m1.log; fi
n=$(psql "$DST" -X -At -c "SELECT count(*) FROM ci_serial")
[ "$n" = "20" ] && ok "đích có đủ 20 dòng ci_serial" || bad "ci_serial ở đích = $n"
# Sequence ở đích phải đi tiếp từ 25, không cấp lại id đã dùng.
nid=$(psql "$DST" -X -q -At -c "INSERT INTO ci_serial (v) VALUES ('mới') RETURNING id")
[ "$nid" = "26" ] && ok "sequence đi tiếp đúng (id mới = 26)" || bad "id mới = $nid, mong 26"
psql "$DST" -X -q -c "DELETE FROM ci_serial WHERE id = 26; SELECT setval('ci_serial_id_seq', 25)" >/dev/null

echo "── Ca 2: đích đã có bảng, không reset → phải TỪ CHỐI"
if SRC_URL="$SRC" DST_URL="$DST" bash "$HERE/migrate-neon.sh" > /tmp/m2.log 2>&1; then
  cat /tmp/m2.log; bad "ca 2 lẽ ra phải từ chối" /tmp/m2.log
else
  grep -q "Không trộn dữ liệu" /tmp/m2.log && ok "từ chối trộn vào đích có dữ liệu" || { cat /tmp/m2.log; bad "ca 2 sai lý do" /tmp/m2.log; }
fi

echo "── Ca 3: RESET_TARGET=1 → nạp lại được, vẫn KHỚP"
if RESET_TARGET=1 SRC_URL="$SRC" DST_URL="$DST" bash "$HERE/migrate-neon.sh" > /tmp/m3.log 2>&1 \
   && grep -q "KHỚP" /tmp/m3.log; then ok "reset + nạp lại khớp"; else cat /tmp/m3.log; bad "ca 3" /tmp/m3.log; fi

echo "── Ca 4: đích thiếu một dòng → đối chiếu phải BÁO LỆCH"
psql "$DST" -X -q -c "DELETE FROM ci_ident WHERE v = 'b'" >/dev/null
if bash "$HERE/db-reconcile.sh" "$SRC" "$DST" > /tmp/m4.log 2>&1; then
  cat /tmp/m4.log; bad "ca 4 lẽ ra phải lệch" /tmp/m4.log
else
  grep -q "ci_ident\` | 3 | 2 | ❌" /tmp/m4.log && ok "bắt được bảng thiếu dòng" || { cat /tmp/m4.log; bad "ca 4 sai chỗ" /tmp/m4.log; }
fi

echo "── Ca 5: sequence ở đích bị lùi → đối chiếu phải BÁO LỆCH"
RESET_TARGET=1 SRC_URL="$SRC" DST_URL="$DST" bash "$HERE/migrate-neon.sh" > /dev/null 2>&1
psql "$DST" -X -q -c "SELECT setval('ci_serial_id_seq', 5)" >/dev/null
if bash "$HERE/db-reconcile.sh" "$SRC" "$DST" > /tmp/m5.log 2>&1; then
  cat /tmp/m5.log; bad "ca 5 lẽ ra phải lệch" /tmp/m5.log
else
  grep -q "ci_serial_id_seq.*❌" /tmp/m5.log && ok "bắt được sequence lùi" || { cat /tmp/m5.log; bad "ca 5 sai chỗ" /tmp/m5.log; }
fi

echo "── Ca 6: URL pooler → phải TỪ CHỐI trước khi đụng gì"
if SRC_URL="$SRC" DST_URL="postgresql://u:p@ep-x-pooler.us-west-2.aws.neon.tech/db" \
   bash "$HERE/migrate-neon.sh" > /tmp/m6.log 2>&1; then bad "ca 6 lẽ ra phải từ chối" /tmp/m6.log
else grep -q "pooler" /tmp/m6.log && ok "từ chối URL pooler" || { cat /tmp/m6.log; bad "ca 6 sai lý do" /tmp/m6.log; }; fi

echo "── Kết quả: $pass đạt, $failn hỏng"
[ "$failn" = 0 ]
