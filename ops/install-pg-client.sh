#!/usr/bin/env bash
# ============================================================================
# Cài postgresql-client ĐÚNG BẢN CHÍNH từ kho PGDG (apt.postgresql.org) cho
# GitHub Actions — dùng chung cho backup.yml và migrate-neon.yml.
#
# VÌ SAO: CSDL Render là PostgreSQL 18, còn `apt-get install postgresql-client`
# của Ubuntu 24.04 cho bản 16. pg_dump từ chối dump máy chủ MỚI hơn nó:
#   "aborting because of server version mismatch"
# → backup.yml chưa từng chạy được lần nào (ngoài việc thiếu secret).
# Runner còn có sẵn PostgreSQL 16 trong PATH, nên cài xong phải đưa bản mới lên
# ĐẦU PATH, nếu không `pg_dump` vẫn trỏ bản 16.
#
# CÁCH DÙNG (trong workflow):
#   bash ops/install-pg-client.sh 18
#   bash ops/install-pg-client.sh 18 "$URL_1" "$URL_2"   # kèm kiểm bản máy chủ
#
# Truyền URL thì script hỏi server_version_num của từng máy và DỪNG nếu máy chủ
# mới hơn client — báo lỗi rõ ngay đầu, thay vì để pg_dump chết giữa chừng.
# Cách thêm kho theo hướng dẫn chính thức:
#   https://www.postgresql.org/download/linux/ubuntu/
# ============================================================================
set -euo pipefail

VER="${1:?Cần bản chính của client, vd 18}"
shift

KEY_DIR=/usr/share/postgresql-common/pgdg
KEY="$KEY_DIR/apt.postgresql.org.asc"
. /etc/os-release
sudo install -d "$KEY_DIR"
sudo curl -fsS --retry 3 -o "$KEY" https://www.postgresql.org/media/keys/ACCC4CF8.asc
echo "deb [signed-by=$KEY] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
  | sudo tee /etc/apt/sources.list.d/pgdg.list >/dev/null
sudo apt-get update -qq
sudo apt-get install -y -qq "postgresql-client-$VER"

BIN="/usr/lib/postgresql/$VER/bin"
test -x "$BIN/pg_dump" || { echo "::error::Không thấy $BIN/pg_dump sau khi cài."; exit 1; }
export PATH="$BIN:$PATH"
if [ -n "${GITHUB_PATH:-}" ]; then
  echo "$BIN" >> "$GITHUB_PATH"      # các bước SAU trong job cũng dùng bản này
fi
echo "[pg-client] $(pg_dump --version) · $(psql --version)"

# Kiểm bản máy chủ ≤ bản client. Không in URL (chứa mật khẩu) — chỉ in thứ tự;
# lỗi kết nối cũng qua bộ lọc (pg-redact.sh).
# shellcheck source=pg-redact.sh
. "$(cd "$(dirname "$0")" && pwd)/pg-redact.sh"
ERR="$(mktemp)"; trap 'rm -f "$ERR"' EXIT
i=0
for url in "$@"; do
  i=$((i + 1))
  url="${url/postgresql+psycopg:/postgresql:}"
  srv="$(psql "$url" -X -tAc "SELECT current_setting('server_version_num')::int / 10000" 2>"$ERR")" || {
    echo "::error::Không kết nối được CSDL thứ $i để hỏi bản máy chủ. Lỗi (đã lọc):"
    pg_err_redacted "$ERR"; exit 1; }
  echo "[pg-client] CSDL thứ $i: PostgreSQL $srv"
  if [ "$srv" -gt "$VER" ]; then
    echo "::error::CSDL thứ $i là PostgreSQL $srv, mới hơn client $VER — pg_dump sẽ từ chối. Nâng tham số bản client."
    exit 1
  fi
done
