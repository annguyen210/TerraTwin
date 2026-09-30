#!/usr/bin/env bash
# ============================================================================
# Đối chiếu HAI CSDL Postgres sau khi chuyển/khôi phục: số dòng TỪNG BẢNG và
# mọi sequence (id tự tăng). Thoát 1 nếu lệch dù chỉ một bảng/sequence.
#
#   bash ops/db-reconcile.sh "$NGUON_URL" "$DICH_URL"
#
# In bảng Markdown ra stdout (và vào $GITHUB_STEP_SUMMARY nếu có) để dán thẳng
# vào ops/RESTORE.md. Không in URL — URL chứa mật khẩu.
#
# SEQUENCE: pg_dump ghi setval() theo giá trị ở nguồn. Nếu bước đó hỏng/thiếu,
# bảng vẫn đủ dòng nhưng lần INSERT đầu tiên ở đích sẽ đụng khoá chính
# ("duplicate key value violates unique constraint") — lỗi chỉ lộ ra khi app đã
# chạy trên CSDL mới. Nên kiểm hai điều: last_value hai bên BẰNG nhau, và ở
# đích last_value ≥ max(cột) để giá trị kế tiếp không trùng dòng đã có.
# ============================================================================
set -euo pipefail

SRC="${1:?Cần URL nguồn}"; DST="${2:?Cần URL đích}"
SRC="${SRC/postgresql+psycopg:/postgresql:}"
DST="${DST/postgresql+psycopg:/postgresql:}"

# </dev/null: psql chạy trong các vòng `while read` dưới đây — không được đụng
# vào stdin của vòng lặp.
# stderr qua bộ lọc: log Actions công khai, lỗi Postgres có thể đính kèm dữ liệu.
# shellcheck source=pg-redact.sh
. "$(cd "$(dirname "$0")" && pwd)/pg-redact.sh"
QERR="$(mktemp)"; trap 'rm -f "$QERR"' EXIT
q() {
  psql "$1" -X -v ON_ERROR_STOP=1 -At -F $'\t' -c "$2" </dev/null 2>"$QERR" || {
    echo "::error::Truy vấn đối chiếu lỗi (đã lọc dữ liệu):" >&2
    pg_err_redacted "$QERR" >&2
    return 1
  }
}

TABLES_SQL="SELECT quote_ident(schemaname) || '.' || quote_ident(tablename)
            FROM pg_tables
            WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
            ORDER BY 1"
# Sequence gắn với một cột (serial = 'a', identity = 'i').
SEQ_SQL="SELECT quote_ident(sn.nspname) || '.' || quote_ident(s.relname),
                quote_ident(tn.nspname) || '.' || quote_ident(t.relname),
                quote_ident(a.attname)
         FROM pg_class s
         JOIN pg_namespace sn ON sn.oid = s.relnamespace
         JOIN pg_depend d ON d.objid = s.oid AND d.classid = 'pg_class'::regclass
                         AND d.refclassid = 'pg_class'::regclass AND d.deptype IN ('a', 'i')
         JOIN pg_class t ON t.oid = d.refobjid
         JOIN pg_namespace tn ON tn.oid = t.relnamespace
         JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = d.refobjsubid
         WHERE s.relkind = 'S'
         ORDER BY 1"

out=""
emit() { out+="$1"$'\n'; }
fail=0

mapfile -t src_tables < <(q "$SRC" "$TABLES_SQL")
mapfile -t dst_tables < <(q "$DST" "$TABLES_SQL")
declare -A in_src=() in_dst=()
for t in "${src_tables[@]}"; do [ -n "$t" ] && in_src["$t"]=1; done
for t in "${dst_tables[@]}"; do [ -n "$t" ] && in_dst["$t"]=1; done

emit "| Bảng | Nguồn | Đích | Khớp |"
emit "|---|---:|---:|:---:|"
tot_s=0; tot_d=0
all_tables=$(printf '%s\n' "${src_tables[@]}" "${dst_tables[@]}" | sort -u)
while IFS= read -r t; do
  [ -z "$t" ] && continue
  s="—"; d="—"
  if [ -n "${in_src[$t]:-}" ]; then s=$(q "$SRC" "SELECT count(*) FROM $t"); fi
  if [ -n "${in_dst[$t]:-}" ]; then d=$(q "$DST" "SELECT count(*) FROM $t"); fi
  if [ "$s" = "$d" ]; then ok="✅"; else ok="❌"; fail=1; fi
  [[ "$s" =~ ^[0-9]+$ ]] && tot_s=$((tot_s + s))
  [[ "$d" =~ ^[0-9]+$ ]] && tot_d=$((tot_d + d))
  emit "| \`$t\` | $s | $d | $ok |"
done <<< "$all_tables"
emit "| **Tổng (${#src_tables[@]} bảng nguồn, ${#dst_tables[@]} bảng đích)** | **$tot_s** | **$tot_d** | $([ $fail = 0 ] && echo ✅ || echo ❌) |"
emit ""

emit "| Sequence | Cột | last_value nguồn | last_value đích | max(cột) ở đích | Khớp |"
emit "|---|---|---:|---:|---:|:---:|"
nseq=0
while IFS=$'\t' read -r seq tbl col; do
  [ -z "$seq" ] && continue
  nseq=$((nseq + 1))
  seq_lit="'${seq//\'/\'\'}'"
  ls_=$(q "$SRC" "SELECT coalesce(last_value::text, 'null') FROM pg_sequences
                  WHERE format('%I.%I', schemaname, sequencename) = $seq_lit")
  ld=$(q "$DST" "SELECT coalesce(last_value::text, 'null') FROM pg_sequences
                 WHERE format('%I.%I', schemaname, sequencename) = $seq_lit")
  mx=$(q "$DST" "SELECT coalesce(max($col)::text, 'null') FROM $tbl" 2>/dev/null || echo "?")
  ok="✅"
  [ "$ls_" = "$ld" ] || ok="❌"
  if [ "$mx" != "null" ]; then
    # Bảng có dòng → sequence ở đích phải đã chạy tới ít nhất max(cột).
    if [ "$ld" = "null" ] || [ -z "$ld" ] || ! [[ "$mx" =~ ^-?[0-9]+$ ]] || [ "$ld" -lt "$mx" ]; then ok="❌"; fi
  fi
  [ "$ok" = "✅" ] || fail=1
  emit "| \`$seq\` | \`$tbl.$col\` | ${ls_:-thiếu} | ${ld:-thiếu} | $mx | $ok |"
done < <(q "$SRC" "$SEQ_SQL")
[ "$nseq" -gt 0 ] || emit "| _(không có sequence nào)_ | | | | | |"
emit ""
if [ "$fail" = 0 ]; then
  emit "**KẾT LUẬN: ✅ KHỚP** — mọi bảng đủ dòng, mọi sequence đúng."
else
  emit "**KẾT LUẬN: ❌ LỆCH** — KHÔNG trỏ app sang CSDL đích."
fi

printf '%s' "$out"
if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  printf '## Đối chiếu nguồn → đích\n\n%s' "$out" >> "$GITHUB_STEP_SUMMARY"
fi
exit "$fail"
