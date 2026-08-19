"""Chạy song song, gộp việc trùng, và hàng đợi cho việc dài.

Bản thiết kế đặt "Song song & đồng thời" thành một trong bốn nguyên lý bắt buộc:
*pipeline bất đồng bộ dùng chung state, hàng đợi + worker, gom batch*. Trước file
này phần mềm chạy tuần tự hết — đúng nhưng chậm, và có bốn vấn đề thật:

  1. `scan()` gọi 14 mô-đun NỐI TIẾP, mỗi cái chạm mạng. Đây là endpoint được
     dùng nhiều nhất và cũng là cái chậm nhất.
  2. Việc dài (dựng lưới bộ gen 1–2 phút) giữ nguyên một kết nối HTTP. Render và
     nhiều proxy cắt kết nối trước khi xong → người dùng thấy lỗi dù máy chủ vẫn
     đang chạy đúng.
  3. Mười người hỏi cùng một toạ độ cùng lúc = mười lượt gọi Open-Meteo giống hệt
     nhau (cache stampede). Cache chỉ cứu được từ lượt thứ hai TRỞ ĐI.
  4. Không có trần cho số lượt gọi ra ngoài. Nguồn miễn phí bị nã dồn thì chặn
     IP, và lúc đó CẢ phần mềm chết chứ không riêng người gây ra.

Bốn thứ ở đây giải bốn vấn đề đó, không thêm phụ thuộc nào (không Redis, không
Celery) vì gói miễn phí không có chỗ chạy chúng.

GIỚI HẠN PHẢI NÓI RÕ: đây là song song TRONG MỘT TIẾN TRÌNH. Hàng đợi nằm trong
bộ nhớ nên restart là mất; gộp việc trùng chỉ gộp trong cùng tiến trình. Muốn
phân tán thật (nhiều máy, hàng đợi bền) thì cần Redis/RabbitMQ + worker riêng —
đó là việc của giai đoạn có tải thật, không phải bây giờ.
"""
from __future__ import annotations

import os
import threading
import time
import traceback
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable, TypeVar

T = TypeVar("T")

# Số việc nền chạy đồng thời. Nhỏ có chủ đích: phần lớn thời gian là CHỜ MẠNG,
# nên nhiều luồng không giúp gì mà chỉ làm nguồn dữ liệu bị nã dồn.
_POOL_SIZE = int(os.environ.get("TERRATWIN_WORKERS", "4"))

# Trần số lượt gọi RA NGOÀI cùng lúc, tính trên toàn tiến trình. Đây là thứ
# đứng giữa phần mềm và việc bị Open-Meteo chặn IP.
_UPSTREAM_LIMIT = int(os.environ.get("TERRATWIN_UPSTREAM_CONCURRENCY", "6"))

JOB_TTL = 1800.0          # giữ kết quả 30 phút rồi dọn
MAX_JOBS = 200            # trần bộ nhớ; quá thì dọn cái cũ nhất

_pool = ThreadPoolExecutor(max_workers=_POOL_SIZE,
                           thread_name_prefix="terratwin-job")
_upstream = threading.BoundedSemaphore(_UPSTREAM_LIMIT)

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()

_flight: dict[str, Future] = {}
_flight_lock = threading.Lock()


# ------------------------------------------------------------------ trần mạng

class upstream:
    """Cổng vào cho mọi lượt gọi ra Internet.

    Dùng như context manager:  ``with jobs.upstream(): ...``

    Có thời gian chờ để một nguồn treo không khoá vĩnh viễn cả phần mềm — thà
    trả None (người gọi đã xử lý được None) còn hơn treo cả tiến trình.
    """

    __slots__ = ("_got",)

    def __init__(self):
        self._got = False

    def __enter__(self):
        self._got = _upstream.acquire(timeout=30.0)
        return self._got

    def __exit__(self, *exc):
        if self._got:
            _upstream.release()
        return False


# ------------------------------------------------------- gộp việc trùng nhau

def single_flight(key: str, fn: Callable[[], T]) -> T:
    """Nhiều lời gọi cùng `key` cùng lúc → CHỈ chạy `fn` một lần.

    Người đến sau chờ kết quả của người đầu tiên thay vì chạy lại y hệt. Đây là
    khác biệt giữa "cache cứu từ lượt thứ hai" và "cache cứu ngay từ lượt đầu
    khi có nhiều người cùng hỏi".

    Ngoại lệ được ném lại cho MỌI người chờ — không ai được nhận âm thầm None
    trong khi thực tế là lỗi.
    """
    with _flight_lock:
        fut = _flight.get(key)
        leader = fut is None
        if leader:
            fut = Future()
            _flight[key] = fut

    if not leader:
        return fut.result()

    try:
        result = fn()
    except BaseException as e:
        with _flight_lock:
            _flight.pop(key, None)
        fut.set_exception(e)
        raise
    with _flight_lock:
        _flight.pop(key, None)
    fut.set_result(result)
    return result


# --------------------------------------------------------------- chạy song song

def gather(tasks: list[Callable[[], T]], limit: int | None = None,
           timeout: float = 180.0) -> list[T | None]:
    """Chạy nhiều việc ĐỒNG THỜI, giữ nguyên thứ tự kết quả.

    Việc nào hỏng trả None thay vì kéo đổ cả mẻ — dùng cho những chỗ mà một
    mô-đun lỗi không được làm hỏng mười ba mô-đun còn lại.

    KHÔNG gọi hàm này từ bên trong một việc đã chạy trong `_pool`: pool có số
    luồng hữu hạn nên lồng nhau sẽ tự khoá chính mình. Vì vậy `gather` dùng pool
    RIÊNG, tạo theo từng lần gọi.
    """
    if not tasks:
        return []
    n = min(len(tasks), limit or _UPSTREAM_LIMIT)
    out: list[T | None] = [None] * len(tasks)
    with ThreadPoolExecutor(max_workers=max(1, n),
                            thread_name_prefix="terratwin-par") as ex:
        futs = {ex.submit(t): i for i, t in enumerate(tasks)}
        for f, i in futs.items():
            try:
                out[i] = f.result(timeout=timeout)
            except Exception:
                out[i] = None
    return out


# ------------------------------------------------------------ hàng đợi việc dài

def _prune() -> None:
    """Dọn việc đã xong quá hạn. Gọi khi đang giữ _jobs_lock."""
    now = time.time()
    dead = [k for k, v in _jobs.items()
            if v["state"] in ("done", "error") and now - v["finished_at"] > JOB_TTL]
    for k in dead:
        _jobs.pop(k, None)
    if len(_jobs) > MAX_JOBS:
        for k, _ in sorted(_jobs.items(), key=lambda kv: kv[1]["created_at"]):
            if len(_jobs) <= MAX_JOBS:
                break
            if _jobs[k]["state"] in ("done", "error"):
                _jobs.pop(k, None)


def submit(kind: str, fn: Callable[[], object], label: str = "") -> str:
    """Đẩy một việc dài xuống nền, trả mã để hỏi lại kết quả sau."""
    job_id = uuid.uuid4().hex[:16]
    now = time.time()
    with _jobs_lock:
        _prune()
        _jobs[job_id] = {"id": job_id, "kind": kind, "label": label,
                         "state": "queued", "created_at": now,
                         "started_at": None, "finished_at": None,
                         "result": None, "error": None}

    def _run():
        with _jobs_lock:
            j = _jobs.get(job_id)
            if j is None:
                return
            j["state"] = "running"
            j["started_at"] = time.time()
        try:
            r = fn()
            with _jobs_lock:
                j = _jobs.get(job_id)
                if j is not None:
                    j.update(state="done", result=r, finished_at=time.time())
        except Exception as e:
            # Chi tiết lỗi vào log máy chủ; người dùng chỉ thấy loại lỗi, không
            # thấy đường dẫn nội bộ hay chuỗi kết nối database.
            traceback.print_exc()
            with _jobs_lock:
                j = _jobs.get(job_id)
                if j is not None:
                    j.update(state="error", error=type(e).__name__,
                             finished_at=time.time())

    _pool.submit(_run)
    return job_id


def status(job_id: str) -> dict | None:
    """Trạng thái một việc. None nếu mã không tồn tại hoặc đã bị dọn."""
    with _jobs_lock:
        j = _jobs.get(job_id)
        if j is None:
            return None
        now = time.time()
        out = {
            "id": j["id"], "kind": j["kind"], "label": j["label"],
            "state": j["state"],
            "queued_s": round((j["started_at"] or now) - j["created_at"], 1),
            "elapsed_s": round((j["finished_at"] or now)
                               - (j["started_at"] or now), 1),
        }
        if j["state"] == "done":
            out["result"] = j["result"]
        elif j["state"] == "error":
            out["error"] = j["error"]
            out["message"] = ("Việc chạy nền gặp lỗi. Thử lại; nếu vẫn hỏng thì "
                              "nhiều khả năng nguồn dữ liệu ngoài đang không "
                              "phản hồi.")
        return out


def stats() -> dict:
    with _jobs_lock:
        by = {}
        for j in _jobs.values():
            by[j["state"]] = by.get(j["state"], 0) + 1
    with _flight_lock:
        in_flight = len(_flight)
    return {
        "workers": _POOL_SIZE,
        "upstream_concurrency_limit": _UPSTREAM_LIMIT,
        "jobs_tracked": sum(by.values()),
        "by_state": by,
        "coalesced_in_flight": in_flight,
        "job_ttl_s": JOB_TTL,
        "note": ("Hàng đợi nằm TRONG tiến trình: restart là mất việc đang chờ, "
                 "và gộp việc trùng chỉ gộp trong cùng tiến trình. Đủ cho quy mô "
                 "hiện tại; muốn phân tán thật thì cần hàng đợi bền bên ngoài."),
    }


def shutdown(wait: bool = False) -> None:
    _pool.shutdown(wait=wait, cancel_futures=not wait)
