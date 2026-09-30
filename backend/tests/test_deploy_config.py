"""Chốt cấu hình triển khai — lớp lỗi chỉ lộ ra SAU khi đã lên máy chủ.

Vì sao cần nhóm test này: mọi lỗi ở đây đều chạy tốt trên máy phát triển và chỉ
hỏng khi triển khai thật. Không có test thì cách duy nhất phát hiện là mất dữ
liệu người dùng — quá muộn.

Ba lỗi có thật đã bắt được khi viết nhóm này:
  ① Dockerfile chỉ COPY app, không COPY data → anomaly_model.json biến mất
    trong container, /api/anomaly-ml âm thầm trả None dù máy nhà vẫn chạy.
  ② docker-compose không có volume → mỗi lần `up --build` là mất sạch tài
    khoản, khoá API và toàn bộ kho quan sát thực địa.
  ③ Volume định gắn vào /app/data sẽ CHE MẤT thư mục chứa mô hình, khiến bản
    mô hình mới trong ảnh không bao giờ xuất hiện ở lần triển khai sau.
"""
from __future__ import annotations

import os
import re

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _doc(name: str) -> str:
    path = os.path.join(_ROOT, name)
    if not os.path.exists(path):
        pytest.skip(f"không có {name}")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _code(text: str) -> str:
    """Bỏ dòng chú thích — để test bắt CẤU HÌNH chứ không bắt lời giải thích."""
    return "\n".join(l for l in text.split("\n") if not l.strip().startswith("#"))


def test_dockerfile_co_copy_thu_muc_data():
    """Thiếu dòng này thì mô hình không lên máy chủ, và hỏng trong im lặng."""
    d = _code(_doc("backend/Dockerfile"))
    assert re.search(r"COPY\s+data\s", d), (
        "backend/Dockerfile phải COPY data — trong đó có anomaly_model.json")


def test_mo_hinh_da_commit_de_di_theo_ma_nguon():
    """Render clone repo rồi chạy thẳng, không có bước tải mô hình riêng."""
    p = os.path.join(_ROOT, "backend", "data", "anomaly_model.json")
    assert os.path.exists(p), "anomaly_model.json phải nằm trong repo"
    assert os.path.getsize(p) < 400 * 1024, "quá lớn để đi kèm mã nguồn"


def test_compose_co_volume_giu_csdl():
    """Kho quan sát thực địa là thứ duy nhất đối thủ không tải được từ nguồn mở.

    Mất nó khi rebuild là mất lợi thế cạnh tranh, không phải mất dữ liệu vặt.
    """
    c = _code(_doc("docker-compose.yml"))
    assert "volumes:" in c, "docker-compose.yml phải khai báo volume"
    assert re.search(r"terratwin-db:\s*$", c, re.M), "phải có volume đặt tên"


def test_csdl_khong_nam_trong_thu_muc_mo_hinh():
    """Nếu volume gắn đè lên /app/data thì bản mô hình mới không bao giờ tới nơi.

    Docker chỉ chép nội dung ảnh vào volume ở LẦN ĐẦU. Từ lần thứ hai, volume
    cũ che mất thư mục ảnh — mô hình vĩnh viễn kẹt ở bản đầu tiên.
    """
    c = _code(_doc("docker-compose.yml"))
    mounts = re.findall(r"-\s+terratwin-db:(\S+)", c)
    assert mounts, "không tìm thấy điểm gắn volume"
    for m in mounts:
        assert not m.rstrip("/").endswith("/data"), (
            f"volume gắn vào {m} sẽ che mất thư mục chứa mô hình")

    url = re.search(r"TERRATWIN_DATABASE_URL=(\S+)", c)
    assert url, "phải chỉ định TERRATWIN_DATABASE_URL trỏ vào volume"
    path = url.group(1)
    assert any(path.startswith(f"sqlite:////{m.lstrip('/')}") or m in path
               for m in mounts), (
        f"CSDL ở {path} không nằm trong volume {mounts} — sẽ mất khi rebuild")


def test_khong_khoa_cung_vao_mot_nha_cung_cap_llm():
    """Ràng buộc của người dùng: họ dùng khoá của nhà cung cấp khác, không phải Claude."""
    c = _code(_doc("docker-compose.yml"))
    assert "ANTHROPIC_API_KEY" not in c, (
        "không được nêu đích danh một nhà cung cấp trong cấu hình mẫu; "
        "dùng TERRATWIN_LLM_* để trung lập")


def test_render_dung_postgres_chu_khong_phai_sqlite():
    """Trên nền tảng có hệ thống tệp tạm thời, SQLite là mất dữ liệu chắc chắn.

    CSDL nằm ở Neon từ 29/9/2026 (Postgres free của Render bị xoá sau 30 ngày +
    14 ngày ân hạn). TERRATWIN_DATABASE_URL phải khai `sync: false` — chủ dự án
    đặt tay URL Neon — và Blueprint KHÔNG được khai CSDL Render nào: có khối
    databases/fromDatabase thì lần đồng bộ Blueprint sau ghi đè URL Neon bằng
    một CSDL free 30 ngày dựng lại từ đầu."""
    r = _code(_doc("render.yaml"))
    m = re.search(r"-\s*key:\s*TERRATWIN_DATABASE_URL\s*\n\s*(\S[^\n]*)", r)
    assert m, "render.yaml phải khai TERRATWIN_DATABASE_URL"
    assert m.group(1).replace(" ", "").startswith("sync:false"), (
        "TERRATWIN_DATABASE_URL phải là sync: false (URL Neon đặt tay)")
    assert "fromDatabase" not in r and "databases:" not in r, (
        "không được khai CSDL Render — đồng bộ Blueprint sẽ ghi đè URL Neon")
    assert "TERRATWIN_TRUST_PROXY" in r, (
        "đứng sau proxy mà không bật thì giới hạn tần suất sẽ chặn nhầm")


def test_keepwarm_khong_co_lich_tu_dong():
    """0 đồng (29/9/2026): api + web cùng free. Giữ ấm tự động một service đã là
    744 giờ/tháng 31 ngày, cộng giờ service kia thức → vượt 750 giờ → Render
    đình chỉ cả hai. Chỉ được bấm tay trước buổi demo."""
    k = _code(_doc(".github/workflows/keepwarm.yml"))
    assert "schedule:" not in k and "cron:" not in k
    assert "workflow_dispatch" in k


def test_sao_luu_va_chuyen_csdl_dung_pg_client_pgdg():
    """CSDL là PostgreSQL 18; postgresql-client mặc định của Ubuntu 24.04 là 16
    → pg_dump dừng "server version mismatch"."""
    for wf in ("backup.yml", "migrate-neon.yml"):
        y = _code(_doc(f".github/workflows/{wf}"))
        assert "ops/install-pg-client.sh" in y, f"{wf} phải cài client từ kho PGDG"
        assert not re.search(r"apt-get install[^\n]*postgresql-client\s*$", y, re.M), (
            f"{wf} không được cài postgresql-client mặc định của Ubuntu")


def test_chuyen_csdl_chi_chay_tay_va_khong_upload_ban_dump():
    """Repo công khai: artifact ai cũng tải được, dump chứa email + hash mật khẩu."""
    y = _code(_doc(".github/workflows/migrate-neon.yml"))
    assert "workflow_dispatch" in y and "schedule:" not in y and "push:" not in y
    assert "upload-artifact" not in y
