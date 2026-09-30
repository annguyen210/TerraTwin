"""Lỗi Postgres in ra log Actions CÔNG KHAI không được mang theo dữ liệu người dùng.

psql/pg_dump đính kèm dữ liệu vào lỗi: CONTEXT của COPY in nguyên một dòng (có
thể là email + hash mật khẩu), DETAIL in giá trị khoá, ERROR in giá trị ô, còn
lỗi kết nối có thể in URL kèm mật khẩu. ops/pg-redact.sh phải lọc hết.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REDACT = Path(__file__).resolve().parents[2] / "ops" / "pg-redact.sh"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="cần bash")

STDERR = """\
psql:/tmp/tmp.abc/terratwin.sql:57: ERROR:  duplicate key value violates unique constraint "users_email_key"
DETAIL:  Key (email)=(ai@vd.vn) already exists.
CONTEXT:  COPY users, line 3: "7\tai@vd.vn\t$2b$12$abcdefghijklmnopqrstuv"
psql:/tmp/x.sql:9: ERROR:  invalid input syntax for type integer: "ai@vd.vn"
LINE 1: SELECT 'ai@vd.vn'::int
               ^
NOTICE:  table "t" does not exist, skipping
pg_dump: error: connection to server at "ep-cool-a1.us-west-2.aws.neon.tech" (1.2.3.4), port 5432 failed: FATAL:  password authentication failed for user "neondb_owner"
pg_dump: detail: Query was: SELECT * FROM users WHERE email = 'ai@vd.vn'
psql: error: could not connect: postgresql://neondb_owner:s3cretPW@ep-cool-a1.neon.tech/neondb?sslmode=require
"""

SECRETS = ["ai@vd.vn", "$2b$12$", "s3cretPW", "neondb_owner:", "abcdefghijklmnop"]


def _run(tmp_path: Path, text: str, n: int | None = None) -> str:
    f = tmp_path / "err.txt"
    f.write_text(text, encoding="utf-8")
    arg = f" {n}" if n else ""
    cmd = f'. "{REDACT.as_posix()}"; pg_err_redacted "{f.as_posix()}"{arg}'
    return subprocess.run(["bash", "-c", cmd], capture_output=True, text=True,
                          encoding="utf-8", check=True).stdout


def test_khong_lot_du_lieu_nguoi_dung(tmp_path):
    out = _run(tmp_path, STDERR)
    for s in SECRETS:
        assert s not in out, f"lọt '{s}' ra log công khai:\n{out}"
    assert "CONTEXT" not in out and "DETAIL" not in out and "Query was" not in out


def test_van_giu_loai_loi_de_chan_doan(tmp_path):
    out = _run(tmp_path, STDERR)
    assert "duplicate key value violates unique constraint" in out
    assert "invalid input syntax for type integer" in out
    assert "password authentication failed" in out
    assert "postgresql://…" in out
    assert "NOTICE" not in out, "chỉ in lỗi, không in thông báo thường"


def test_gioi_han_so_dong_va_tep_rong(tmp_path):
    assert len(_run(tmp_path, STDERR, 2).strip().splitlines()) == 2
    assert _run(tmp_path, "") == ""
