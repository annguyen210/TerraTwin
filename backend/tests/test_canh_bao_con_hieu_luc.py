"""Quét toàn bộ 23/11/2026, P1 — danh sách thửa dùng cảnh báo CŨ làm "7 ngày tới".

Trà Leng "có mối NGUY HIỂM — thượng nguồn 225.3 mm" là bản ghi 11/11 trong khi lượt chấm 21/11 chỉ còn cảnh báo; Lai Châu
"Quan sát:" lặp 5 lần; /hom-nay hiện cùng một cảnh báo 2 lần. Mỗi (thửa, mô-đun) chỉ bản ghi MỚI NHẤT còn hiệu lực theo
lượt rà soát gần nhất; bản ghi cũ vẫn còn trong lịch sử, chỉ được đánh dấu hết hiệu lực."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.db import Alert, Plot, SessionLocal, User
from app.main import app
from app.services import alert_current

PW = "RuongLua#2026x"


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _setup(c, email):
    r = c.post("/api/auth/register", json={"email": email, "password": PW, "name": "A"})
    assert r.status_code == 201, r.text
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    with SessionLocal() as s:
        uid = s.query(User).filter(User.email == email).one().id
        p = Plot(user_id=uid, name="Trà Leng", lat=15.33, lon=108.05, grade="A", score=100)
        s.add(p)
        s.commit()
        return h, uid, p.id


def _alert(s, uid, pid, mid, level, head, days_ago):
    a = Alert(user_id=uid, plot_id=pid, module_id=mid, risk_level=level, headline=f"Trà Leng: {head}",
              recommendation="r", created_at=_now() - timedelta(days=days_ago))
    s.add(a)
    s.commit()
    return a.id


def _sweep(s, pid, mods, hours_ago=1):
    p = s.get(Plot, pid)
    alert_current.record_sweep(p, [SimpleNamespace(id=m, risk_level=lv, headline=h) for m, lv, h in mods],
                               when=_now() - timedelta(hours=hours_ago))
    s.commit()


def test_nguy_hiem_11_ngay_truoc_luot_moi_canh_bao_thi_can_de_y():
    with TestClient(app) as c:
        h, uid, pid = _setup(c, "tl1@vd.vn")
        with SessionLocal() as s:
            _alert(s, uid, pid, "upstream_flood", "danger", "thượng nguồn 225.3 mm", 11)
            # lượt mới (sau 72 giờ chống trùng): cảnh báo → bản ghi mới mức warning
            _sweep(s, pid, [("upstream_flood", "warning", "thượng nguồn 120 mm")])
            new_id = _alert(s, uid, pid, "upstream_flood", "warning", "thượng nguồn 120 mm", 0.04)
        cur = c.get("/api/alerts?unread_only=true&current_only=true", headers=h).json()
        assert [a["id"] for a in cur] == [new_id]
        assert cur[0]["current_level"] == "warning" and "225.3" not in cur[0]["current_headline"]
        allrows = c.get("/api/alerts?unread_only=true", headers=h).json()        # lịch sử vẫn còn, chỉ hết hiệu lực
        assert len(allrows) == 2 and [a["current"] for a in allrows] == [True, False]


def test_trong_cua_so_chong_trung_muc_ha_van_doc_muc_hien_tai():
    """Nguy hiểm 2 ngày trước, lượt mới chỉ cảnh báo: chống trùng 72 giờ nên KHÔNG có bản ghi mới — mức phải lấy theo lượt
    rà soát, không theo bản ghi cũ."""
    with TestClient(app) as c:
        h, uid, pid = _setup(c, "tl2@vd.vn")
        with SessionLocal() as s:
            aid = _alert(s, uid, pid, "upstream_flood", "danger", "thượng nguồn 225.3 mm", 2)
            _sweep(s, pid, [("upstream_flood", "warning", "thượng nguồn 120 mm")])
        cur = c.get("/api/alerts?unread_only=true&current_only=true", headers=h).json()
        assert [a["id"] for a in cur] == [aid] and cur[0]["current_level"] == "warning"
        assert cur[0]["risk_level"] == "danger"          # bản ghi lịch sử giữ nguyên


def test_luot_moi_het_canh_bao_thi_ban_ghi_cu_het_hieu_luc():
    with TestClient(app) as c:
        h, uid, pid = _setup(c, "tl3@vd.vn")
        with SessionLocal() as s:
            _alert(s, uid, pid, "urban", "danger", "bê tông hoá", 1)
            _sweep(s, pid, [])
        assert c.get("/api/alerts?unread_only=true&current_only=true", headers=h).json() == []
        assert len(c.get("/api/alerts?unread_only=true", headers=h).json()) == 1      # không xoá lịch sử


def test_quan_sat_lap_5_lan_chi_con_mot():
    with TestClient(app) as c:
        h, uid, pid = _setup(c, "lc@vd.vn")
        with SessionLocal() as s:
            for d in (0.9, 0.7, 0.5, 0.3, 0.1):
                _alert(s, uid, pid, "pest", "warning", "NDVI giảm, ảnh ngày 2026-11-15", d)
        cur = c.get("/api/alerts?unread_only=true&current_only=true", headers=h).json()
        assert len(cur) == 1


def test_chua_co_luot_ra_soat_thi_chi_nhan_48_gio():
    with TestClient(app) as c:
        h, uid, pid = _setup(c, "tl4@vd.vn")
        with SessionLocal() as s:
            _alert(s, uid, pid, "flood", "warning", "cũ", 3)
            fresh = _alert(s, uid, pid, "landslide", "warning", "mới", 1)
        cur = c.get("/api/alerts?unread_only=true&current_only=true", headers=h).json()
        assert [a["id"] for a in cur] == [fresh]


def test_hom_nay_khong_lap_dong():
    with TestClient(app) as c:
        h, uid, pid = _setup(c, "bl@vd.vn")
        with SessionLocal() as s:
            _alert(s, uid, pid, "flood", "warning", "Bảo Lộc mưa lớn", 0.5)
            _alert(s, uid, pid, "flood", "warning", "Bảo Lộc mưa lớn", 0.4)
        items = [i for i in c.get("/api/today?lang=vi", headers=h).json()["items"] if i["kind"] == "alert"]
        assert len(items) == 1
