"""Gán nhãn kiểm định EUDR v3: mù với kết quả máy, độc lập giữa người gán, chỉ người được cấp
mới gán, độ đồng thuận/nhóm sự thật đúng, và quy tắc v3 không bao giờ nặng hơn v2."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

PW = "MatKhau123"


def _cells(n=6):
    out = []
    for i in range(n):
        lat, lon = 12.5 + i * 0.01, 108.0 + i * 0.01
        out.append({"lon0": lon, "lat0": lat, "lon1": lon + 0.001, "lat1": lat + 0.001,
                    "stratum": ["S_loss", "S_old_trees", "S_new_trees", "S_open"][i % 4], "region": "Tây Nguyên",
                    "imagery": {"wayback": {"before": {"date": "2019-02-15", "res_m": 0.46, "source": "Maxar"},
                                            "after": {"date": "2026-02-23", "res_m": 0.34, "source": "Vantor"}},
                                "s2": {"2020": {"item": "S2A_X", "date": "2020-02-01", "cloud_pct": 1.0,
                                                "bbox": [lon - 0.005, lat - 0.005, lon + 0.006, lat + 0.006]},
                                       "2026": None},
                                "complete": False}})
    return out


@pytest.fixture
def c(tmp_path, monkeypatch):
    from app import db as dbmod
    from app.services import label_v3, quota
    sample = tmp_path / "sample_v3.json"
    sample.write_text(json.dumps({"cells": _cells()}), encoding="utf-8")
    monkeypatch.setattr(label_v3, "SAMPLE_V3", str(sample))
    engine = create_engine(f"sqlite:///{tmp_path/'label.db'}", connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    dbmod.Base.metadata.create_all(engine)
    monkeypatch.setattr(dbmod, "engine", engine)
    monkeypatch.setattr(dbmod, "SessionLocal", Session)
    quota.reset()
    from app.main import app

    def _session():
        s = Session()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[dbmod.get_session] = _session
    with TestClient(app) as cl:
        cl.Session, cl.sample = Session, sample
        yield cl
    app.dependency_overrides.clear()


def _login(c, email, admin=False):
    c.post("/api/auth/register", json={"email": email, "password": PW, "name": "N"})
    if admin:
        from app.db import User
        s = c.Session()
        s.execute(select(User).where(User.email == email)).scalar_one().role = "admin"
        s.commit()
        s.close()
    tok = c.post("/api/auth/login", json={"email": email, "password": PW}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


LBL = {"cover2020": "tree_crop", "loss": "no", "confidence": 3}


def test_nguoi_chua_duoc_cap_khong_gan_duoc_admin_cap_thi_gan_duoc(c):
    assert c.get("/api/label/v3/next").status_code == 401
    h = _login(c, "nguoi2@vd.vn")
    assert c.get("/api/label/v3/me", headers=h).json()["can_label"] is False
    assert c.get("/api/label/v3/next", headers=h).status_code == 403
    assert c.post("/api/label/v3/cell/0", json=LBL, headers=h).status_code == 403
    a = _login(c, "admin@vd.vn", admin=True)
    assert c.post("/api/admin/label/v3/labelers", json={"email": "Nguoi2@VD.vn"}, headers=h).status_code == 403
    assert c.post("/api/admin/label/v3/labelers", json={"email": "Nguoi2@VD.vn"}, headers=a).status_code == 200
    assert c.get("/api/label/v3/me", headers=h).json()["can_label"] is True
    assert c.get("/api/label/v3/next", headers=h).status_code == 200
    c.delete("/api/admin/label/v3/labelers/nguoi2@vd.vn", headers=a)
    assert c.get("/api/label/v3/next", headers=h).status_code == 403


def test_nguoi_gan_nhan_bi_mu_voi_tang_va_ket_qua_may(c):
    h = _login(c, "admin@vd.vn", admin=True)
    r = c.get("/api/label/v3/next", headers=h).json()
    blob = json.dumps(r, ensure_ascii=False)
    for leak in ("stratum", "S_loss", "S_old", "S_new", "S_open", "p_forest", "level", "votes", "majority", "truth"):
        assert leak not in blob, leak
    v = r["view"]
    assert v["wayback"]["before"]["acquired"] == "2019-02-15" and len(v["wayback"]["before"]["tiles"]) == 3
    assert "/tile/29260/17/" in v["wayback"]["before"]["tiles"][1][1]
    assert v["s2"]["2020"]["url"].startswith("https://planetarycomputer.microsoft.com/") and v["s2"]["2026"] is None
    box = v["mosaic_box"]
    # ô 0,001° ≈ 111 m; lưới 3 ô ảnh z17 ≈ 0,0082° → khung ≈ 12% bề ngang, nằm trong ô ảnh giữa
    assert 30 < box["left"] < 70 and 30 < box["top"] < 70 and 8 < box["width"] < 16


def test_gan_nhan_tung_o_theo_thu_tu_rieng_va_khong_thay_nhan_nguoi_khac(c):
    a = _login(c, "admin@vd.vn", admin=True)
    b = _login(c, "admin2@vd.vn", admin=True)
    seen = []
    for _ in range(6):
        r = c.get("/api/label/v3/next", headers=a).json()
        k = r["view"]["cell"]
        assert k not in seen
        seen.append(k)
        assert c.post(f"/api/label/v3/cell/{k}", json=LBL, headers=a).status_code == 200
    assert c.get("/api/label/v3/next", headers=a).json()["done"] is True
    assert sorted(seen) == list(range(6))
    # người thứ hai: không thấy nhãn của người thứ nhất
    rb = c.get(f"/api/label/v3/cell/{seen[0]}", headers=b).json()
    assert rb["mine"] is None
    ra = c.get(f"/api/label/v3/cell/{seen[0]}", headers=a).json()
    assert ra["mine"]["cover2020"] == "tree_crop"
    # sửa nhãn của mình được, không tạo bản ghi thứ hai
    c.post(f"/api/label/v3/cell/{seen[0]}", json={**LBL, "cover2020": "natural_forest", "loss": "yes"}, headers=a)
    from app.db import LabelV3
    s = c.Session()
    assert s.execute(select(LabelV3)).scalars().all().__len__() == 6
    s.close()


@pytest.mark.parametrize("bad", [{"cover2020": "rung"}, {"loss": "co"}, {"confidence": 0}, {"confidence": 4},
                                 {"note": "x" * 301}])
def test_nhan_sai_dinh_dang_bi_tu_choi(c, bad):
    h = _login(c, "admin@vd.vn", admin=True)
    assert c.post("/api/label/v3/cell/0", json={**LBL, **bad}, headers=h).status_code == 422
    assert c.post("/api/label/v3/cell/99", json=LBL, headers=h).status_code == 404


def test_khoa_nhan_thi_khong_sua_duoc(c):
    h = _login(c, "admin@vd.vn", admin=True)
    c.sample.write_text(json.dumps({"cells": _cells(), "locked_at": "2026-10-20"}), encoding="utf-8")
    import os
    import time
    os.utime(c.sample, (time.time() + 5, time.time() + 5))
    assert c.post("/api/label/v3/cell/0", json=LBL, headers=h).status_code == 409


def test_tong_hop_va_xuat_chi_admin_va_an_email(c):
    a = _login(c, "admin@vd.vn", admin=True)
    b = _login(c, "admin2@vd.vn", admin=True)
    for k in range(4):
        c.post(f"/api/label/v3/cell/{k}", json=LBL, headers=a)
        c.post(f"/api/label/v3/cell/{k}", json=LBL if k < 3 else {**LBL, "cover2020": "natural_forest"}, headers=b)
    u = _login(c, "thuong@vd.vn")
    assert c.get("/api/admin/label/v3/summary", headers=u).status_code == 403
    s = c.get("/api/admin/label/v3/summary", headers=a).json()
    assert s["cells_2plus"] == 4 and s["truth_counts"]["T_clean"] == 3 and s["excluded"]["disagree_forest"] == 1
    assert s["agree_forest"] == 0.75
    e = c.get("/api/admin/label/v3/export", headers=a).json()
    assert len(e["labels"]) == 8 and "@" not in json.dumps(e) and {r["labeler"] for r in e["labels"]} == {1, 2}


def test_xoa_tai_khoan_giu_nhan_nhung_go_khoi_nguoi(c):
    from app.db import LabelV3
    h = _login(c, "admin@vd.vn", admin=True)
    c.post("/api/label/v3/cell/0", json=LBL, headers=h)
    assert c.delete("/api/account", headers=h).status_code == 204
    s = c.Session()
    rows = s.execute(select(LabelV3)).scalars().all()
    s.close()
    assert len(rows) == 1 and rows[0].user_id < 0


# ------------------------------------------------------------------ thuần

def test_nhom_su_that_va_kappa():
    from app.services import label_v3 as L
    lab = [
        # ô 0: cả hai rừng + mất → T_lost
        {"cell": 0, "user_id": 1, "cover2020": "natural_forest", "loss": "yes"},
        {"cell": 0, "user_id": 2, "cover2020": "planted_forest", "loss": "yes"},
        # ô 1: rừng, không mất → T_forest
        {"cell": 1, "user_id": 1, "cover2020": "natural_forest", "loss": "no"},
        {"cell": 1, "user_id": 2, "cover2020": "natural_forest", "loss": "no"},
        # ô 2: cao su vs không cây — cùng "không phải rừng" → T_clean, mất cây không quan trọng
        {"cell": 2, "user_id": 1, "cover2020": "tree_crop", "loss": "yes"},
        {"cell": 2, "user_id": 2, "cover2020": "no_trees", "loss": "no"},
        # ô 3: bất đồng rừng → loại
        {"cell": 3, "user_id": 1, "cover2020": "natural_forest", "loss": "no"},
        {"cell": 3, "user_id": 2, "cover2020": "tree_crop", "loss": "no"},
        # ô 4: một người "không xác định" → loại
        {"cell": 4, "user_id": 1, "cover2020": "unclear", "loss": "no"},
        {"cell": 4, "user_id": 2, "cover2020": "tree_crop", "loss": "no"},
        # ô 5: rừng nhưng bất đồng mất cây → loại
        {"cell": 5, "user_id": 1, "cover2020": "natural_forest", "loss": "yes"},
        {"cell": 5, "user_id": 2, "cover2020": "natural_forest", "loss": "unclear"},
        # ô 6: một nhãn → loại
        {"cell": 6, "user_id": 1, "cover2020": "tree_crop", "loss": "no"},
    ]
    t = L.truth(lab)
    assert t["sets"] == {0: "T_lost", 1: "T_forest", 2: "T_clean"}
    assert t["excluded"] == {"one_label": 1, "unclear": 1, "disagree_forest": 1, "disagree_loss": 1}
    assert L.kappa([(True, True), (False, False)]) == 1.0
    assert L.kappa([(True, False), (False, True)]) == -1.0
    assert L.kappa([(True, True), (True, True)]) is None          # không có biến thiên
    m = L.metrics({0: "high", 1: "low", 2: "low"}, t["sets"])
    assert m == {"M1_detect_lost": 1.0, "M2_flag_forest": 0.0, "M3_pass_clean": 1.0}
    assert L.decide(m, t["counts"]) == "insufficient"              # < 25 ô mỗi nhóm
    big = {"T_lost": 30, "T_forest": 30, "T_clean": 30}
    assert L.decide({"M1_detect_lost": 0.9, "M2_flag_forest": 0.85, "M3_pass_clean": 0.75}, big) == "pass"
    assert L.decide({"M1_detect_lost": 0.9, "M2_flag_forest": 0.85, "M3_pass_clean": 0.69}, big) == "fail"


def test_thu_tu_rieng_tat_dinh_va_khac_nhau_giua_nguoi():
    from app.services import label_v3 as L
    assert L.order_for(1, 50) == L.order_for(1, 50) and sorted(L.order_for(1, 50)) == list(range(50))
    assert L.order_for(1, 50) != L.order_for(2, 50)


def test_quy_tac_v3_vuon_tan_day_ha_xuong_dat_chi_khi_mo_hinh_chac_la_vuon():
    from app.services import eudr_forest as ef
    dense = {"wc2020": 100.0, "alos2020": 100.0, "io": 100.0}
    flat = {y: 95.0 for y in ef.IO_YEARS}
    assert ef.verdict(dense, flat, None, None, [], rule=2)[0] == "review"
    lv, reasons, sig = ef.verdict(dense, flat, None, None, [], rule=3, p_forest=0.1)
    assert lv == "low" and "rừng-hay-vườn" in reasons[0] and sig["p_forest"] == 0.1
    assert ef.verdict(dense, flat, None, None, [], rule=3, p_forest=0.5)[0] == "review"
    assert ef.verdict(dense, flat, None, None, [], rule=3, p_forest=None)[0] == "review"   # thiếu mô hình → thận trọng
    lost = {y: (95.0 if y <= 2020 else 30.0) for y in ef.IO_YEARS}
    assert ef.verdict(dense, lost, None, None, [], rule=3, p_forest=0.01)[0] == "high"     # mất cây: mô hình không cứu


def test_quy_tac_v3_khong_bao_gio_nang_hon_v2():
    from app.services import eudr_forest as ef
    rank = {"low": 0, "review": 1, "high": 2, "unknown": 0}
    flat = {y: 90.0 for y in ef.IO_YEARS}
    lost = {y: (60.0 if y <= 2020 else 20.0) for y in ef.IO_YEARS}
    for a in (0, 15, 40, 60, 100):
        for b in (0, 15, 40, 60, 100):
            for cc in (0, 15, 40, 60, 100):
                for traj in (flat, lost):
                    for p in (None, 0.05, 0.2, 0.21, 0.9):
                        m = {"wc2020": float(a), "alos2020": float(b), "io": float(cc)}
                        v3 = ef.verdict(m, traj, None, None, [], rule=3, p_forest=p)[0]
                        v2 = ef.verdict(m, traj, None, None, [], rule=2)[0]
                        assert rank[v3] <= rank[v2]
                        if p is None or p > 0.2:
                            assert v3 == v2


def test_production_khong_bat_v3_khi_chua_cham():
    from app.services import eudr_forest as ef, label_v3 as L
    assert ef.ACTIVE_RULE == 1 and L.PROTOCOL_DOC_V3["rules"]["primary"] == ef.RULES[3]
