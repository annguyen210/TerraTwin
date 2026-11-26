"""SỐ ĐO VẬN HÀNH CHUẨN PROMETHEUS (26/11/2026) — /metrics, định dạng văn bản Prometheus 0.0.4, không thêm thư viện.

Grafana / Prometheus / Grafana Cloud kéo được trực tiếp (khoá cron hoặc admin). Đo:
  · terratwin_http_requests_total{route,method,status} — theo MẪU route (/api/assess/{module_id}), không theo URL thật
    (không phình nhãn, không lộ toạ độ người dùng).
  · terratwin_http_request_duration_seconds — histogram độ trễ theo route.
  · rào chắn AI (số bịa bị che, PII bị che, câu chèn lệnh bị bỏ), lượt 429 từ nguồn ngoài, nhớ đệm, hàng đợi, RAM tiến trình.
"""
from __future__ import annotations

import threading
import time

BUCKETS = (0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60)
_lock = threading.Lock()
_req: dict[tuple[str, str, str], int] = {}
_hist: dict[str, list] = {}            # route → [đếm theo bucket…, +Inf, tổng giây, số lần]
_START = time.time()


def observe(route: str, method: str, status: int, seconds: float) -> None:
    with _lock:
        k = (route, method, str(status))
        _req[k] = _req.get(k, 0) + 1
        h = _hist.setdefault(route, [0] * (len(BUCKETS) + 1) + [0.0, 0])
        for i, b in enumerate(BUCKETS):
            if seconds <= b:
                h[i] += 1
        h[len(BUCKETS)] += 1             # +Inf
        h[-2] += seconds
        h[-1] += 1


def _esc(v: str) -> str:
    return str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def render() -> str:
    out: list[str] = []

    def metric(name: str, typ: str, help_: str, rows: list[tuple[dict, float]]) -> None:
        out.append(f"# HELP {name} {help_}")
        out.append(f"# TYPE {name} {typ}")
        for labels, v in rows:
            lab = ",".join(f'{k}="{_esc(x)}"' for k, x in labels.items())
            out.append(f"{name}{{{lab}}} {v}" if lab else f"{name} {v}")

    with _lock:
        req = dict(_req)
        hist = {k: list(v) for k, v in _hist.items()}
    metric("terratwin_http_requests_total", "counter", "Số request theo mẫu route, phương thức, mã trạng thái.",
           [({"route": r, "method": m, "status": s}, n) for (r, m, s), n in sorted(req.items())])
    out.append("# HELP terratwin_http_request_duration_seconds Độ trễ request theo mẫu route.")
    out.append("# TYPE terratwin_http_request_duration_seconds histogram")
    for r, h in sorted(hist.items()):
        for i, b in enumerate(BUCKETS):
            out.append(f'terratwin_http_request_duration_seconds_bucket{{route="{_esc(r)}",le="{b}"}} {h[i]}')
        out.append(f'terratwin_http_request_duration_seconds_bucket{{route="{_esc(r)}",le="+Inf"}} {h[len(BUCKETS)]}')
        out.append(f'terratwin_http_request_duration_seconds_sum{{route="{_esc(r)}"}} {round(h[-2], 4)}')
        out.append(f'terratwin_http_request_duration_seconds_count{{route="{_esc(r)}"}} {h[-1]}')
    try:
        from app.services import ai_guard, guard
        g, ig = guard.stats(), ai_guard.stats()
        metric("terratwin_llm_numbers_redacted_total", "counter", "Số con số LLM bịa bị rào chắn đầu ra che.",
               [({}, g.get("numbers_removed", 0))])
        metric("terratwin_input_guard_total", "counter", "Rào chắn đầu vào: PII bị che, câu chèn lệnh bị bỏ.",
               [({"kind": "pii_masked"}, ig.get("pii_masked", 0)), ({"kind": "injection_removed"}, ig.get("injection_removed", 0))])
    except Exception:  # noqa: BLE001
        pass
    try:
        from app.services import realdata
        q = realdata.quota_status()
        rows = [({"host": h}, n) for h, n in (q.get("count_429_24h") or {}).items()]
        if rows:
            metric("terratwin_upstream_429_24h", "gauge", "Lượt nguồn ngoài trả 429 trong 24 giờ.", rows)
    except Exception:  # noqa: BLE001
        pass
    try:
        from app.services import jobs
        st = jobs.stats()
        metric("terratwin_jobs_tracked", "gauge", "Việc ngắn đang theo dõi trong bể luồng.", [({}, st.get("jobs_tracked", 0))])
    except Exception:  # noqa: BLE001
        pass
    try:
        with open("/proc/self/status") as f:
            rss = next((int(l.split()[1]) * 1024 for l in f if l.startswith("VmRSS:")), None)
        if rss:
            metric("terratwin_process_resident_memory_bytes", "gauge", "RAM tiến trình.", [({}, rss)])
    except OSError:
        pass
    metric("terratwin_process_uptime_seconds", "gauge", "Thời gian tiến trình đã chạy.", [({}, round(time.time() - _START))])
    return "\n".join(out) + "\n"
