#!/usr/bin/env bash
# ============================================================================
# In lỗi của psql / pg_dump ra log CÔNG KHAI mà không lộ dữ liệu người dùng.
# Dùng bằng `source`: migrate-neon.sh, db-reconcile.sh, backup.sh,
# install-pg-client.sh.
#
# VÌ SAO. Log GitHub Actions của repo công khai ai cũng đọc được. Postgres đính
# kèm DỮ LIỆU vào thông báo lỗi:
#   CONTEXT:  COPY users, line 3: "7<TAB>ai@vd.vn<TAB>$2b$12$…"   ← nguyên một dòng
#   DETAIL:  Key (email)=(ai@vd.vn) already exists.            ← giá trị khoá
#   ERROR:  invalid input syntax for type integer: "ai@vd.vn"   ← giá trị ô
# Chuyển stderr vào tệp, rồi chỉ in các dòng ERROR/FATAL đã:
#   · bỏ hẳn DETAIL / CONTEXT / HINT / QUERY / STATEMENT / LINE và dòng thụt lề;
#   · thay mọi chuỗi trong ngoặc kép, mọi cặp (khoá)=(giá trị), mọi URL
#     Postgres (chứa mật khẩu) bằng "…".
# Mất tên bảng/ràng buộc trong ngoặc kép là cái giá chấp nhận được: thà khó
# chẩn đoán hơn một chút còn hơn lộ email + hash mật khẩu lên mạng.
# ============================================================================

pg_err_redacted() {   # pg_err_redacted <tệp stderr> [số dòng tối đa, mặc định 20]
  local f="$1" n="${2:-20}"
  [ -s "$f" ] || return 0
  grep -Ev '^[[:space:]]|(^|: )(DETAIL|CONTEXT|HINT|QUERY|STATEMENT|LINE [0-9]+|detail|hint):' "$f" \
    | grep -E 'ERROR|FATAL|PANIC|error|fatal|could not|failed' \
    | sed -E 's#postgres(ql)?(\+psycopg)?://[^[:space:]]*#postgresql://…#g' \
    | sed -E 's/"[^"]*"/"…"/g; s/\([^)]*\)=\([^)]*\)/(…)=(…)/g' \
    | head -n "$n"
}
