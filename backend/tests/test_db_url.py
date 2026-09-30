"""Kết nối Neon (29/9/2026): URL phải tới libpq nguyên vẹn, pooler phải tắt prepare.

Không chạm mạng — chỉ kiểm hai hàm thuần trong app.db.
"""
from __future__ import annotations

from app.db import connect_args_for, normalize_url

NEON = ("postgresql://neondb_owner:pw@ep-cool-name-a1b2c3.us-west-2.aws.neon.tech/neondb"
        "?sslmode=require&channel_binding=require")


def test_chuan_hoa_driver_giu_nguyen_sslmode():
    u = normalize_url(NEON)
    assert u.startswith("postgresql+psycopg://")
    assert u.endswith("?sslmode=require&channel_binding=require"), (
        "mất sslmode thì Neon từ chối kết nối")


def test_postgres_scheme_cu_va_url_da_co_driver():
    assert normalize_url("postgres://u:p@h/db?sslmode=require") == \
        "postgresql+psycopg://u:p@h/db?sslmode=require"
    already = "postgresql+psycopg://u:p@h/db"
    assert normalize_url(already) == already
    assert normalize_url("sqlite:///./x.db") == "sqlite:///./x.db"


def test_url_direct_giu_prepared_statement():
    assert connect_args_for(normalize_url(NEON)) == {}


def test_url_pooler_tat_prepared_statement():
    """PgBouncer chế độ transaction: câu đã prepare nằm ở một kết nối máy chủ,
    lần sau có thể sang kết nối khác → 'prepared statement does not exist'."""
    pooler = NEON.replace("a1b2c3.", "a1b2c3-pooler.")
    assert connect_args_for(normalize_url(pooler)) == {"prepare_threshold": None}


def test_sqlite_giu_check_same_thread():
    assert connect_args_for("sqlite:///./x.db") == {"check_same_thread": False}
