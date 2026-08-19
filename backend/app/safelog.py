"""In log an toàn với mọi bảng mã console.

KHÔNG dùng print() thẳng cho chuỗi tiếng Việt. Console Windows mặc định là
cp1252/cp437; print("chủ động") ở đó ném UnicodeEncodeError, và nếu câu lệnh đó
nằm trong lifespan thì APP KHÔNG KHỞI ĐỘNG ĐƯỢC — sập vì một dòng log. Đã dính
đúng lỗi này một lần, nên chặn ở một chỗ duy nhất.

Đặt ở module riêng thay vì trong main.py để tầng services dùng được mà không
phải import ngược lên entrypoint.
"""
from __future__ import annotations

import sys


def log(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        sys.stdout.buffer.write(msg.encode(enc, "replace") + b"\n")
        sys.stdout.flush()
