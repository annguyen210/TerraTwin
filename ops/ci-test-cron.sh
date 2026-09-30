#!/usr/bin/env bash
# ============================================================================
# Test THẬT cho ops/wake-api.sh + ops/radar-sweep.sh trong CI (Ubuntu, curl
# thật) — thứ radar.yml/brief.yml gọi mỗi ngày trên api gói free.
#
#   bash ops/ci-test-cron.sh      # cần python3 + backend đã cài requirements
#
# Ba máy chủ:
#   · giả "bị đình chỉ": luôn 503 + x-render-routing: suspend → wake phải
#     nhận ra NGAY lần đầu, không chờ hết lượt thử.
#   · giả "đang dậy": 503 hai lần đầu rồi 200 → wake phải chờ và thành công.
#   · backend THẬT (uvicorn, SQLite tạm, worker hàng đợi bật) → radar-sweep
#     phải gửi việc, hỏi tiến độ, nhận "done"; khoá sai phải bị từ chối.
# ============================================================================
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$(mktemp -d)"
PIDS=()
cleanup() { for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null || true; done; rm -rf "$WORK"; }
trap cleanup EXIT

pass=0; failn=0
ok()  { echo "✅ $1"; pass=$((pass + 1)); }
bad() { echo "❌ $1"; failn=$((failn + 1)); }

fake_server() {  # fake_server <cổng> <chế độ: suspend|waking>
  python3 - "$1" "$2" <<'PY' &
import http.server, sys
port, mode = int(sys.argv[1]), sys.argv[2]
hits = {"n": 0}
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        hits["n"] += 1
        if mode == "suspend" or hits["n"] <= 2:
            self.send_response(503)
            if mode == "suspend":
                self.send_header("x-render-routing", "suspend")
            self.end_headers(); self.wfile.write(b"Service Unavailable"); return
        self.send_response(200); self.end_headers(); self.wfile.write(b'{"status":"ok"}')
http.server.HTTPServer(("127.0.0.1", port), H).serve_forever()
PY
  PIDS+=($!)
}

wait_port() {  # wait_port <url> — chờ tối đa 60 giây
  for _ in $(seq 1 60); do curl -s -o /dev/null "$1" && return 0; sleep 1; done
  return 1
}

echo "── Ca 1: api bị ĐÌNH CHỈ → báo đúng lỗi ngay lần đầu"
fake_server 8781 suspend
wait_port http://127.0.0.1:8781/ || true
t0=$SECONDS
WAKE_DELAY=5 bash "$HERE/wake-api.sh" http://127.0.0.1:8781 > "$WORK/w1.log" 2>&1; rc=$?
if [ $rc -ne 0 ] && grep -q "ĐÌNH CHỈ" "$WORK/w1.log" && [ $((SECONDS - t0)) -lt 5 ]; then
  ok "nhận ra bị đình chỉ, không chờ hết 6 lượt"
else cat "$WORK/w1.log"; bad "ca 1 (rc=$rc, $((SECONDS - t0))s)"; fi

echo "── Ca 2: api đang dậy (503, 503, rồi 200) → chờ và thành công"
fake_server 8782 waking
wait_port http://127.0.0.1:8782/ || true
# wait_port đã tiêu một lượt 503 của máy giả; còn một lượt 503 rồi 200.
if WAKE_DELAY=1 bash "$HERE/wake-api.sh" http://127.0.0.1:8782 > "$WORK/w2.log" 2>&1 \
   && grep -q "HTTP 503" "$WORK/w2.log" && grep -q "đã thức" "$WORK/w2.log"; then
  ok "thử lại khi 503, dừng ở 200"
else cat "$WORK/w2.log"; bad "ca 2"; fi

echo "── Dựng backend thật"
(
  cd "$HERE/../backend" && \
  TERRATWIN_DATABASE_URL="sqlite:///$WORK/cron.db" TERRATWIN_ENV=dev \
  TERRATWIN_SECRET=ci-cron-secret TERRATWIN_CRON_KEY=ci-cron-key \
  TERRATWIN_JOBS_POLL_INTERVAL_S=1 TERRATWIN_RADAR_INTERVAL_H=0 \
  TERRATWIN_RADAR_RETRY_INTERVAL_MIN=0 TERRATWIN_STARTUP_WARMUP=0 \
  exec python -m uvicorn app.main:app --host 127.0.0.1 --port 8783
) > "$WORK/api.log" 2>&1 &
PIDS+=($!)
if ! wait_port http://127.0.0.1:8783/api/health; then cat "$WORK/api.log"; bad "backend không lên"; fi

echo "── Ca 3: radar-sweep trọn luồng → gửi việc, hỏi tiến độ, xong"
if CRON_KEY=ci-cron-key POLL_EVERY=2 WAKE_DELAY=1 \
   bash "$HERE/radar-sweep.sh" http://127.0.0.1:8783 > "$WORK/r1.log" 2>&1 \
   && grep -q "lượt quét nền" "$WORK/r1.log" && grep -q "\[radar\] xong" "$WORK/r1.log"; then
  ok "chạy nền + hỏi tiến độ tới done"
else cat "$WORK/r1.log"; tail -20 "$WORK/api.log"; bad "ca 3"; fi

echo "── Ca 4: khoá cron sai → từ chối, không thử lại"
if CRON_KEY=sai POLL_EVERY=2 WAKE_DELAY=1 \
   bash "$HERE/radar-sweep.sh" http://127.0.0.1:8783 > "$WORK/r2.log" 2>&1; then
  bad "ca 4 lẽ ra phải hỏng"
else
  grep -q "Khoá cron bị từ chối" "$WORK/r2.log" && [ "$(grep -c 'POST sweep-all' "$WORK/r2.log")" = 1 ] \
    && ok "khoá sai bị từ chối ngay" || { cat "$WORK/r2.log"; bad "ca 4 sai lý do"; }
fi

echo "── Kết quả: $pass đạt, $failn hỏng"
[ "$failn" = 0 ]
