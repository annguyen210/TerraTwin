""""Rà soát ngay" chạy NỀN qua hàng đợi bền (bảng jobs).

Đo thật: 3 thửa mất 196–519 giây chạy đồng bộ — 10 thửa chắc chắn vượt thời
gian chờ của proxy. Nay POST /api/radar/run trả job_id ngay, worker nền chạy,
giao diện hỏi tiến độ ở GET /api/radar/run/{id}.

Không chạm mạng: scan giả lập; hàng đợi được "vắt" tay bằng
jobs_db.poll_and_run_one thay cho vòng lặp worker nền (tắt trong test).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PW = "MatKhau123"


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app import db as dbmod

    engine = create_engine(f"sqlite:///{tmp_path/'a.db'}",
                           connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    dbmod.Base.metadata.create_all(engine)
    monkeypatch.setattr(dbmod, "engine", engine)
    monkeypatch.setattr(dbmod, "SessionLocal", Session)
    # Giả như production: có worker nền thăm dò hàng đợi.
    monkeypatch.setenv("TERRATWIN_JOBS_POLL_INTERVAL_S", "2")

    from app.main import app

    def _session():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[dbmod.get_session] = _session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def fake_scan(monkeypatch):
    """scan() đếm số lần gọi và luôn có đúng một cảnh báo lũ thật."""
    from app.schemas import ScanModule, ScanResult, TerraScoreResult
    from app.services import scan as scan_svc

    calls = {"n": 0}
    flood = ScanModule(id="flood", name="Lũ", icon="", group="B", risk_level="danger",
                       headline="Lũ", recommendation="", is_real=True)

    def fake(loc, include_heavy=False):
        calls["n"] += 1
        ts = TerraScoreResult(location=loc, score=50, grade="C", summary="t")
        return ScanResult(location=loc, terrascore=ts, modules=[flood], alerts=[flood],
                          real_data_ratio=1.0, generated_at="2026-09-28T00:00:00")

    monkeypatch.setattr(scan_svc, "scan", fake)
    return calls


def _user(c, email="a@example.com", plots=((10.24, 106.37), (16.46, 107.59))):
    tok = c.post("/api/auth/register",
                 json={"email": email, "password": PW, "name": "A"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    for i, (la, lo) in enumerate(plots):
        c.post("/api/plots", headers=h, json={"name": f"T{i}", "location": {"lat": la, "lon": lo}})
    return h


def _drain():
    from app import db as dbmod
    from app.services import jobs_db
    with dbmod.SessionLocal() as s:
        while jobs_db.poll_and_run_one(s):
            pass


def test_tra_job_id_ngay_khong_quet_trong_request(client, fake_scan):
    h = _user(client)
    r = client.post("/api/radar/run", headers=h).json()
    assert r["state"] == "queued" and r["job_id"] and r["plots"] == 2
    assert fake_scan["n"] == 0, "request không được tự quét — việc đó của worker nền"


def test_bam_hai_lan_tra_lai_dung_viec_dang_chay(client, fake_scan):
    h = _user(client)
    a = client.post("/api/radar/run", headers=h).json()["job_id"]
    b = client.post("/api/radar/run", headers=h).json()["job_id"]
    assert a == b


def test_worker_chay_xong_co_ket_qua_va_tien_do(client, fake_scan):
    h = _user(client)
    jid = client.post("/api/radar/run", headers=h).json()["job_id"]
    _drain()
    st = client.get(f"/api/radar/run/{jid}", headers=h).json()
    assert st["state"] == "done"
    assert st["result"]["plots_scanned"] == 2
    assert st["result"]["new_alerts"] == 2
    assert st["progress"] == {"done": 2, "total": 2, "current": ""}
    assert fake_scan["n"] == 2


def test_nguoi_khac_khong_xem_duoc_ket_qua(client, fake_scan):
    h = _user(client)
    jid = client.post("/api/radar/run", headers=h).json()["job_id"]
    other = _user(client, email="b@example.com", plots=())
    assert client.get(f"/api/radar/run/{jid}", headers=other).status_code == 404


def test_endpoint_jobs_cong_khai_khong_lo_ket_qua_ra_soat(client, fake_scan):
    h = _user(client)
    jid = client.post("/api/radar/run", headers=h).json()["job_id"]
    _drain()
    st = client.get(f"/api/jobs/{jid}").json()
    assert st["state"] == "done"
    assert "result" not in st and "progress" not in st


def test_chua_co_thua_thi_tra_loi_ngay(client, fake_scan):
    h = _user(client, plots=())
    r = client.post("/api/radar/run", headers=h).json()
    assert r["plots_scanned"] == 0 and "job_id" not in r


def test_khong_co_worker_thi_chay_tai_cho(client, fake_scan, monkeypatch):
    """Worker tắt (=0) mà vẫn đẩy vào hàng đợi thì việc nằm 'queued' mãi."""
    monkeypatch.setenv("TERRATWIN_JOBS_POLL_INTERVAL_S", "0")
    h = _user(client)
    r = client.post("/api/radar/run", headers=h).json()
    assert r["plots_scanned"] == 2 and "job_id" not in r
