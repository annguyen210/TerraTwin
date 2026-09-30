#!/usr/bin/env bash
# ============================================================================
# Cron radar: đánh thức api → gửi lượt quét nền → hỏi tiến độ MỖI PHÚT tới khi
# xong. Gọi từ radar.yml.
#
#   CRON_KEY=... bash ops/radar-sweep.sh [URL gốc api]
#   POLL_EVERY=60 POLL_MAX_MIN=50       # mặc định
#
# VÌ SAO HỎI MỖI PHÚT: Render tắt máy free sau 15 phút KHÔNG có request vào.
# Lượt quét chạy nền trong máy chủ (hàng đợi bền), không phải một request —
# nếu cron gửi xong rồi bỏ đi, máy bị tắt giữa lượt quét. Mỗi lượt hỏi tiến độ
# là một request vào, giữ máy thức tới khi quét xong.
#
# GỬI LẠI AN TOÀN: gọi POST khi lượt trước chưa xong thì máy chủ trả lại ĐÚNG
# việc đang chạy (radar.active_sweep_all_job), không đẩy lượt thứ hai.
# ============================================================================
set -uo pipefail

: "${CRON_KEY:?Thiếu CRON_KEY (secret TERRATWIN_CRON_KEY)}"
BASE="${1:-https://terratwin-api.onrender.com}"
EVERY="${POLL_EVERY:-60}"
MAX_MIN="${POLL_MAX_MIN:-50}"
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$(mktemp)"
trap 'rm -f "$OUT"' EXIT

jget() {  # jget <tệp json> <khoá> — in "" nếu hỏng; dict/list in dạng JSON
  python3 - "$1" "$2" <<'PY' 2>/dev/null || true
import json, sys
try:
    v = json.load(open(sys.argv[1], encoding="utf-8")).get(sys.argv[2])
    print("" if v is None else (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v))
except Exception:
    print("")
PY
}

bash "$HERE/wake-api.sh" "$BASE" || exit 1

code="000"
for i in 1 2 3; do
  code="$(curl -sS -o "$OUT" -w '%{http_code}' --max-time 120 \
          -X POST "$BASE/api/radar/sweep-all" -H "X-Cron-Key: $CRON_KEY")" || code="000"
  echo "[radar] POST sweep-all lần $i: HTTP $code"
  case "$code" in
    200) break ;;
    401|403) echo "::error::Khoá cron bị từ chối (HTTP $code) — TERRATWIN_CRON_KEY ở GitHub và trên Render phải trùng nhau."; exit 1 ;;
  esac
  [ "$i" -lt 3 ] && sleep 20
done
[ "$code" = "200" ] || { echo "::error::radar/sweep-all trả $code sau 3 lần."; cat "$OUT"; exit 1; }

JOB="$(jget "$OUT" job_id)"
if [ -z "$JOB" ]; then
  # Bản api cũ (quét tại chỗ) hoặc máy chủ tắt worker nền → kết quả có luôn.
  echo "[radar] quét tại chỗ, kết quả:"; cat "$OUT"; echo
  exit 0
fi
echo "[radar] lượt quét nền $JOB — hỏi tiến độ mỗi ${EVERY}s, tối đa ${MAX_MIN} phút."

deadline=$((SECONDS + MAX_MIN * 60))
while [ "$SECONDS" -lt "$deadline" ]; do
  sleep "$EVERY"
  code="$(curl -sS -o "$OUT" -w '%{http_code}' --max-time 60 \
          "$BASE/api/radar/sweep-all/$JOB" -H "X-Cron-Key: $CRON_KEY")" || code="000"
  if [ "$code" != "200" ]; then
    echo "[radar] hỏi tiến độ: HTTP $code — thử lại sau ${EVERY}s."
    [ "$code" = "404" ] && { echo "::error::Máy chủ không còn lượt quét $JOB (đã dọn hoặc khởi động lại)."; exit 1; }
    continue
  fi
  state="$(jget "$OUT" state)"
  echo "[radar] $state · $(jget "$OUT" progress) · ${SECONDS}s"
  case "$state" in
    done)  echo "[radar] xong: $(jget "$OUT" result)"; exit 0 ;;
    error) echo "::error::Lượt quét nền lỗi: $(jget "$OUT" error)"; exit 1 ;;
  esac
done
echo "::error::Lượt quét $JOB chưa xong sau ${MAX_MIN} phút."
exit 1
