#!/usr/bin/env bash
# ============================================================================
# Đánh thức terratwin-api (gói free, ngủ sau 15 phút không có request) TRƯỚC
# khi cron gọi việc thật — dùng chung cho radar.yml và brief.yml.
#
#   bash ops/wake-api.sh [URL gốc api]      # mặc định bản production
#   WAKE_TRIES=6 WAKE_DELAY=20 ...          # mặc định: 6 lần, cách 20 giây
#
# Lượt gọi đầu vào một máy đang ngủ có thể treo tới lúc máy dậy hoặc trả 503
# trong 30–60 giây. Gọi GET /api/health (không đổi gì) cho tới khi nhận 200, rồi
# mới gửi POST — không bao giờ thử lại một POST chỉ vì máy còn đang dậy.
#
# Bị ĐÌNH CHỈ (hết 750 giờ free) khác với NGỦ: Render trả 503 kèm header
# x-render-routing: suspend, và gọi bao nhiêu lần cũng không lên cho tới đầu
# tháng sau. Nhận ra ngay để báo đúng lỗi thay vì chờ hết lượt thử.
# ============================================================================
set -uo pipefail

BASE="${1:-https://terratwin-api.onrender.com}"
TRIES="${WAKE_TRIES:-6}"
DELAY="${WAKE_DELAY:-20}"
HDR="$(mktemp)"
trap 'rm -f "$HDR"' EXIT

for i in $(seq 1 "$TRIES"); do
  code="$(curl -sS -o /dev/null -D "$HDR" -w '%{http_code}' --max-time 60 \
          "$BASE/api/health" 2>/dev/null)" || code="000"
  if [ "$code" = "200" ]; then
    echo "[wake] api đã thức (lần $i/$TRIES)."
    exit 0
  fi
  if grep -qi '^x-render-routing: *suspend' "$HDR" 2>/dev/null; then
    echo "::error::terratwin-api bị Render ĐÌNH CHỈ (hết 750 giờ miễn phí của tháng) — không đánh thức được tới ngày 1 tháng sau."
    exit 1
  fi
  echo "[wake] lần $i/$TRIES: HTTP $code — máy đang dậy."
  [ "$i" -lt "$TRIES" ] && sleep "$DELAY"
done
echo "::error::terratwin-api không trả 200 sau $TRIES lần thử (cách ${DELAY}s)."
exit 1
