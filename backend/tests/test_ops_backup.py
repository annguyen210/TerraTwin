"""N2 — kiểm tra ops/backup.sh mã hoá đúng trước khi rời máy.

Không cần Postgres thật: thay pg_dump bằng một script giả in ra nội dung biết
trước, rồi kiểm tra bash ops/backup.sh mã hoá đúng, xoay vòng đúng, và bản mã
hoá giải mã lại được đúng nội dung gốc.

Repo CÔNG KHAI (xem ops/backup.sh) — nếu ba test này không xanh thì đừng bật
.github/workflows/backup.yml, vì có nguy cơ đẩy dữ liệu người dùng ra công khai.
"""
from __future__ import annotations

import gzip
import os
import shutil
import stat
import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKUP_SH = REPO_ROOT / "ops" / "backup.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("gpg") is None,
    reason="cần bash + gpg (có sẵn trên CI ubuntu-latest)")

PASSPHRASE = "mat-khau-thu-nghiem-khong-dung-that"
FAKE_SQL = "-- fake sql dump\nSELECT 1;\n"


def _fake_pg_dump(bin_dir: Path) -> None:
    """pg_dump giả: bỏ qua mọi tham số, in nội dung biết trước ra stdout —
    đúng hành vi pg_dump thật khi không có -f, chỉ khác nguồn dữ liệu."""
    script = bin_dir / "pg_dump"
    script.write_text(f"#!/usr/bin/env bash\ncat <<'EOF'\n{FAKE_SQL}EOF\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)


def _run_backup(tmp_path: Path, passphrase: str | None) -> subprocess.CompletedProcess:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    _fake_pg_dump(bin_dir)

    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
    env["TERRATWIN_DATABASE_URL"] = "postgresql://fake/db"
    # .as_posix() CHỨ KHÔNG str(): trên Windows, str(Path) dùng dấu "\" —
    # truyền thẳng vào bash thì "\U", "\A"... bị hiểu như escape, khiến `ls`
    # stat nhầm và mất luôn thứ tự -t (đã đo được: rơi về thứ tự bảng chữ
    # cái). CI thật (ubuntu-latest) không có dấu "\" trong path nên không gặp
    # lỗi này — đây là gotcha CHỈ của việc test trên Windows, không phải lỗi
    # của backup.sh.
    env["TERRATWIN_BACKUP_DIR"] = (tmp_path / "backups").as_posix()
    if passphrase is not None:
        env["TERRATWIN_BACKUP_PASSPHRASE"] = passphrase
    else:
        env.pop("TERRATWIN_BACKUP_PASSPHRASE", None)

    # encoding="utf-8" tường minh: script in tiếng Việt UTF-8, còn console
    # Windows mặc định cp1252 — không ép thì subprocess vỡ giữa chừng khi đọc
    # stdout/stderr (UnicodeDecodeError), một gotcha đã gặp nhiều lần trong dự án.
    return subprocess.run(["bash", str(BACKUP_SH)], env=env, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=30)


def test_co_mat_khau_thi_ban_dump_duoc_ma_hoa(tmp_path):
    """Việc quan trọng nhất: repo công khai, có mật khẩu thì bản dump PHẢI
    mã hoá, và bản gốc (chưa mã hoá) KHÔNG được để lại trên đĩa."""
    r = _run_backup(tmp_path, passphrase=PASSPHRASE)
    assert r.returncode == 0, r.stderr

    daily = list((tmp_path / "backups" / "daily").glob("*"))
    assert len(daily) == 1
    out = daily[0]
    assert out.suffix == ".gpg", f"phải mã hoá, file hiện tại: {out.name}"

    # Bản mã hoá không được lộ nội dung gốc dưới dạng chuỗi thô.
    raw = out.read_bytes()
    assert b"SELECT 1" not in raw

    # Giải mã lại phải RA ĐÚNG nội dung gốc (đường vòng gpg -> gunzip).
    dec = subprocess.run(
        ["gpg", "--batch", "--yes", "--pinentry-mode", "loopback",
         "--passphrase", PASSPHRASE, "--decrypt", str(out)],
        capture_output=True, timeout=15)
    assert dec.returncode == 0, dec.stderr
    assert gzip.decompress(dec.stdout).decode() == FAKE_SQL


def test_khong_mat_khau_thi_canh_bao_va_khong_ma_hoa(tmp_path):
    """Không đặt mật khẩu vẫn phải chạy được (chạy tay/local) — nhưng phải
    CẢNH BÁO rõ, không được im lặng để bản thô trông giống bản đã an toàn."""
    r = _run_backup(tmp_path, passphrase=None)
    assert r.returncode == 0, r.stderr
    assert "CẢNH BÁO" in r.stdout or "CANH BAO" in r.stdout

    daily = list((tmp_path / "backups" / "daily").glob("*"))
    assert len(daily) == 1
    assert daily[0].suffix != ".gpg"


def test_xoay_vong_giu_dung_7_ban_ngay(tmp_path):
    """Xoay vòng chỉ giữ 7 bản ngày mới nhất. Tạo sẵn 9 bản cũ (giả, mtime
    cách nhau 1 giờ) rồi chạy thêm 1 lần — phải còn đúng 7, và 2 bản cũ nhất
    trong số 9 bản giả phải bị xoá."""
    daily_dir = tmp_path / "backups" / "daily"
    daily_dir.mkdir(parents=True)
    for i in range(9):
        f = daily_dir / f"terratwin-fake{i:02d}.sql.gz.gpg"
        f.write_bytes(b"fake old backup")
        t = time.time() - (9 - i) * 3600   # i=0 cũ nhất, i=8 mới nhất trong đám giả
        os.utime(f, (t, t))

    r = _run_backup(tmp_path, passphrase=PASSPHRASE)
    assert r.returncode == 0, r.stderr

    remaining = {f.name for f in daily_dir.glob("*")}
    assert len(remaining) == 7, f"phải giữ đúng 7 bản, hiện có {len(remaining)}: {remaining}"
    assert "terratwin-fake00.sql.gz.gpg" not in remaining
    assert "terratwin-fake01.sql.gz.gpg" not in remaining
