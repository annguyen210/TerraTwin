"""Thẩm định hàng loạt: đọc CSV, chạy nền, kết quả bền, tải CSV, quyền riêng.

Không chạm mạng: batch.appraise được giả lập ở phần API; phần đọc CSV/tổng hợp
là hàm thuần.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.services import batch, reqlang


@pytest.fixture(autouse=True)
def _vi():
    reqlang.set_lang("vi")


# ---------------------------------------------------------------- đọc CSV

def test_doc_csv_dau_phay():
    rows, errs = batch.parse_csv("ma,lat,lon,area_ha\nA,16.46,107.59,0.3\nB,10.4,105.2,\n")
    assert errs == []
    assert rows == [{"ref": "A", "lat": 16.46, "lon": 107.59, "area_ha": 0.3},
                    {"ref": "B", "lat": 10.4, "lon": 105.2, "area_ha": None}]


def test_doc_csv_excel_tieng_viet_cham_phay_va_phay_thap_phan():
    text = "﻿Mã;Vĩ độ;Kinh độ;Diện tích\nKV-1;16,46;107,59;1,5\n"
    rows, errs = batch.parse_csv(text)
    assert errs == [] and rows == [{"ref": "KV-1", "lat": 16.46, "lon": 107.59, "area_ha": 1.5}]


def test_bao_loi_tung_dong_va_goi_y_dao_lat_lon():
    rows, errs = batch.parse_csv("ma,lat,lon\nA,107.59,16.46\nB,abc,105\nC,35.0,139.0\nD,10.4,105.2\n")
    assert [r["ref"] for r in rows] == ["D"]
    msgs = {e["line"]: e["message"] for e in errs}
    assert "đảo lat/lon" in msgs[2] and "không phải số" in msgs[3] and "ngoài lãnh thổ" in msgs[4]


def test_thieu_cot_toa_do():
    rows, errs = batch.parse_csv("ten,x,y\nA,1,2\n")
    assert rows == [] and "Thiếu cột toạ độ" in errs[0]["message"]


def test_tran_so_thua_mac_dinh_50_va_chinh_duoc(monkeypatch):
    body = "lat,lon\n" + "".join(f"{10 + i / 1000},106\n" for i in range(80))
    rows, errs = batch.parse_csv(body)
    assert len(rows) == 50 and any("chia phần còn lại" in e["message"] for e in errs)
    monkeypatch.setenv("TERRATWIN_BATCH_MAX_ROWS", "70")
    assert len(batch.parse_csv(body)[0]) == 70


def test_csv_xuat_chong_cong_thuc_excel():
    out = batch.to_csv([{"ref": "=HYPERLINK(\"http://x\")", "lat": 16.46, "lon": 107.59,
                         "risk_level": "safe", "drivers": ["@SUM(A1)"]}])
    assert out.startswith("﻿")
    assert "'=HYPERLINK" in out and "'@SUM" in out
    assert ",16.46,107.59," in out, "số không được thêm dấu '"


def test_tong_hop_danh_muc():
    rows = [
        {"ref": "A", "area_ha": 2, "risk_level": "danger", "land_group": "crop", "grade": "D",
         "drivers": ["Lũ"], "history_10y": {"flood": 3}, "score": 30},
        {"ref": "B", "area_ha": 1, "risk_level": "safe", "land_group": "built", "grade": "A",
         "drivers": [], "history_10y": {"flood": 0}, "score": 95},
        {"ref": "C", "risk_level": "unknown", "error": "x"},
    ]
    s = batch.summarize(rows)
    assert s["n"] == 3 and s["n_ok"] == 2 and s["n_failed"] == 1
    assert s["by_risk"]["danger"] == 1 and s["at_risk_pct"] == 50.0
    assert s["at_risk_ha"] == 2 and s["total_ha"] == 3
    assert s["watchlist"] == ["A"] and s["history_10y_plots"] == {"flood": 1}
    assert "1/2 thửa" in s["headline"]


# ---------------------------------------------------------------- API

PW = "MatKhau123"


@pytest.fixture
def env(tmp_path, monkeypatch):
    from app import db as dbmod

    engine = create_engine(f"sqlite:///{tmp_path/'b.db'}", connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    dbmod.Base.metadata.create_all(engine)
    monkeypatch.setattr(dbmod, "engine", engine)
    monkeypatch.setattr(dbmod, "SessionLocal", Session)
    monkeypatch.setenv("TERRATWIN_BATCH_DELAY_S", "0")
    monkeypatch.setattr(batch, "_wait_for_quota", lambda report: True)
    calls = []
    monkeypatch.setattr(batch, "appraise", lambda row: calls.append(row["ref"]) or {
        **row, "land_group": "crop", "land_label": "Đất trồng trọt", "risk_level": "warning",
        "score": 70, "grade": "B", "drivers": ["Hạn"], "history_10y": {"drought": 2},
        "real_data_ratio": 0.9, "error": None})
    from app.main import app

    def _session():
        s = Session()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[dbmod.get_session] = _session
    with TestClient(app) as c:
        c.calls = calls
        yield c, Session
    app.dependency_overrides.clear()


def _login(c, email="ngan-hang@vd.vn"):
    tok = c.post("/api/auth/register", json={"email": email, "password": PW, "name": "NH"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _drain():
    from app import db as dbmod
    from app.services import jobs_db
    with dbmod.SessionLocal() as s:
        while jobs_db.poll_and_run_one(s):
            pass


CSV = "ma,lat,lon,area_ha\nKV-1,16.46,107.59,0.5\nKV-2,10.40,105.20,2\nsai,abc,1\n"


def test_can_dang_nhap(env):
    c, _ = env
    assert c.post("/api/batch", json={"csv": CSV}).status_code == 401


def test_luong_day_du_gui_chay_xem_tai(env):
    c, _ = env
    h = _login(c)
    r = c.post("/api/batch", json={"csv": CSV, "title": "Danh mục Q4"}, headers=h).json()
    assert r["rows"] == 2 and len(r["errors"]) == 1 and r["job_id"]
    jid = r["job_id"]
    assert c.get(f"/api/batch/{jid}", headers=h).json()["state"] == "queued"

    _drain()
    d = c.get(f"/api/batch/{jid}", headers=h).json()
    assert d["state"] == "done" and d["title"] == "Danh mục Q4"
    assert [x["ref"] for x in d["rows"]] == ["KV-1", "KV-2"]
    assert d["summary"]["by_risk"]["warning"] == 2 and d["summary"]["total_ha"] == 2.5

    csv_text = c.get(f"/api/batch/{jid}/csv", headers=h).text
    assert csv_text.startswith("﻿ref,lat,lon") and "KV-2" in csv_text

    runs = c.get("/api/batch", headers=h).json()["runs"]
    assert runs[0]["id"] == jid and runs[0]["n_rows"] == 2


def test_nguoi_khac_khong_xem_duoc(env):
    c, _ = env
    jid = c.post("/api/batch", json={"csv": CSV}, headers=_login(c)).json()["job_id"]
    _drain()
    other = _login(c, "khac@vd.vn")
    assert c.get(f"/api/batch/{jid}", headers=other).status_code == 404
    assert c.get(f"/api/batch/{jid}/csv", headers=other).status_code == 404
    assert c.delete(f"/api/batch/{jid}", headers=other).status_code == 404


def test_mot_lo_mot_luc(env):
    c, _ = env
    h = _login(c)
    c.post("/api/batch", json={"csv": CSV}, headers=h)
    r = c.post("/api/batch", json={"csv": CSV}, headers=h)
    assert r.status_code == 409


def test_khong_dong_hop_le_422(env):
    c, _ = env
    r = c.post("/api/batch", json={"csv": "ma,lat,lon\nA,1,2\n"}, headers=_login(c))
    assert r.status_code == 422 and r.json()["detail"]["errors"]


def test_xoa_lan_chay(env):
    c, _ = env
    h = _login(c)
    jid = c.post("/api/batch", json={"csv": CSV}, headers=h).json()["job_id"]
    _drain()
    assert c.delete(f"/api/batch/{jid}", headers=h).status_code == 204
    assert c.get("/api/batch", headers=h).json()["runs"] == []


def test_xoa_tai_khoan_xoa_lo_nhung_giu_ho_so_cong_khai(env, monkeypatch):
    """Hồ sơ đất số nằm trong sổ móc xích công khai — xoá là gãy chuỗi. Xoá tài
    khoản thì gỡ người phát hành, còn lô thẩm định thì xoá hẳn."""
    from app import routes_dossier
    from app.db import BatchRun, Dossier
    from app.services import dossier
    c, Session = env
    monkeypatch.setattr(routes_dossier.region, "classify", lambda lat, lon: {"serviceable": True})
    monkeypatch.setattr(dossier, "build_facts", lambda lat, lon, area, db: {"location": {"lat": lat}})
    h = _login(c)
    did = c.post("/api/dossier", json={"lat": 16.46, "lon": 107.59}, headers=h).json()["id"]
    c.post("/api/batch", json={"csv": CSV}, headers=h)
    _drain()
    exp = c.get("/api/account/export", headers=h).json()
    assert len(exp["batch_runs"]) == 1 and exp["dossiers"][0]["id"] == did
    assert c.delete("/api/account", headers=h).status_code == 204
    with Session() as s:
        assert s.query(BatchRun).count() == 0
        assert s.get(Dossier, did).user_id is None
    assert c.get(f"/api/dossier/{did}").json()["verification"]["valid"] is True


def test_may_chu_chet_giua_lo_thi_chay_tiep_tu_thua_do(env):
    """Render free ngủ sau 15 phút không có request: tiến trình chết giữa lô.
    Lần khởi động sau, lô quay về hàng đợi và đi TIẾP — không làm lại thửa đã xong."""
    import json as _json

    from app.db import BatchRun, Job
    from app.services import jobs_db
    c, Session = env
    h = _login(c)
    jid = c.post("/api/batch", json={"csv": CSV}, headers=h).json()["job_id"]
    with Session() as s:                                   # giả lập: đã xong KV-1 rồi chết
        r = s.get(BatchRun, jid)
        r.rows_json = _json.dumps([{"ref": "KV-1", "lat": 16.46, "lon": 107.59, "area_ha": 0.5,
                                    "risk_level": "safe", "drivers": [], "history_10y": {}}])
        r.state = "running"
        s.get(Job, jid).state = "running"
        s.commit()
    p = c.get(f"/api/batch/{jid}", headers=h).json()
    assert p["state"] == "running" and p["progress"]["done"] == 1 and p["progress"]["total"] == 2
    with Session() as s:
        assert jobs_db.requeue_running(s, (batch.JOB_KIND,)) == 1
    _drain()
    d = c.get(f"/api/batch/{jid}", headers=h).json()
    assert d["state"] == "done" and [x["ref"] for x in d["rows"]] == ["KV-1", "KV-2"]
    assert c.calls == ["KV-2"], "chỉ thẩm định thửa CÒN LẠI"


def test_gap_han_muc_thi_tam_dung_khong_na_tiep(monkeypatch):
    """Nguồn dữ liệu báo quá hạn mức → chờ (ngủ), kiểm lại, chỉ chạy khi thông."""
    from app.services import realdata
    states = [["api.open-meteo.com"], ["api.open-meteo.com"], []]
    monkeypatch.setattr(realdata, "quota_status",
                        lambda: {"exhausted": states.pop(0) if states else []})
    slept, phases = [], []
    monkeypatch.setattr("time.sleep", lambda s: slept.append(s))
    monkeypatch.setenv("TERRATWIN_BATCH_PAUSE_S", "60")
    assert batch._wait_for_quota(lambda ph, ex=None: phases.append(ph)) is True
    assert slept == [60.0, 60.0] and phases == ["paused_quota", "paused_quota"]


def test_xoa_lo_truoc_khi_chay_thi_khong_chay(env):
    c, _ = env
    h = _login(c)
    jid = c.post("/api/batch", json={"csv": CSV}, headers=h).json()["job_id"]
    assert c.delete(f"/api/batch/{jid}", headers=h).status_code == 204
    _drain()
    assert c.calls == [], "lô đã xoá không được tự tạo lại rồi chạy"
    assert c.get(f"/api/batch/{jid}", headers=h).status_code == 404


def test_xoa_lo_giua_chung_thi_dung_sau_thua_dang_chay(env, monkeypatch):
    from app.db import BatchRun
    c, Session = env
    h = _login(c)
    jid = c.post("/api/batch", json={"csv": CSV}, headers=h).json()["job_id"]
    real = batch.appraise

    def appraise_then_delete(row):
        out = real(row)
        with Session() as s:                               # người dùng bấm Xoá từ phiên khác
            s.delete(s.get(BatchRun, jid))
            s.commit()
        return out
    monkeypatch.setattr(batch, "appraise", appraise_then_delete)
    _drain()
    assert c.calls == ["KV-1"], "phải thấy lô đã bị xoá và dừng, không chạy KV-2"
