"""VÒNG LẶP TIN CẬY — sổ điểm tự chấm, một chạm, bản đồ độ tin cậy.

Nhóm test này canh ba thứ dễ hỏng theo kiểu KHÔNG ai nhìn thấy:

① SỔ ĐIỂM TỰ KHEN. Nếu chỉ đếm những cảnh báo đã phát thì mọi lần bỏ sót đều
   vô hình và tỉ lệ thu được luôn đẹp. Có test riêng bắt buộc hàng hồi cứu
   (`retro=1`) phải được tính vào sổ điểm — và đồng thời KHÔNG được hiện trong
   danh sách cảnh báo của người dùng, vì chúng chưa từng được gửi cho ai.

② TOKEN MỘT CHẠM BIẾN THÀNH CHÌA KHOÁ VẠN NĂNG. Liên kết trả lời không cần
   đăng nhập, nên nếu quên kiểm loại token thì một token đăng nhập thường cũng
   lọt qua. Có test cho đúng chuyện đó.

③ KÊNH GỬI IM LẶNG GIẢ VỜ THÀNH CÔNG. Một hệ thống cảnh báo báo "đã gửi" trong
   khi không gửi gì nguy hiểm hơn hẳn một hệ thống không có cảnh báo.

Không test nào ở đây chạm mạng.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.services import hazard, notify, onetap, scorecard, verify

GOOD_PW = "MatKhau123"
BEN_TRE = (10.19, 106.70)
HA_NOI = (21.03, 105.85)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _rows(start: date, n: int, precip=25.0):
    return [{"day": i, "date": (start + timedelta(days=i)).isoformat(),
             "precip": precip, "et0": 4.0, "tmax": 33.0} for i in range(n)]


@pytest.fixture
def env(tmp_path, monkeypatch):
    """CSDL riêng + mọi nguồn mạng đã bị chặn. Trả (client, Session)."""
    from app import db as dbmod
    from app.services import calibration as cal
    from app.services import genome, realdata

    engine = create_engine(f"sqlite:///{tmp_path/'t.db'}",
                           connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    dbmod.Base.metadata.create_all(engine)
    monkeypatch.setattr(dbmod, "engine", engine)
    monkeypatch.setattr(dbmod, "SessionLocal", Session)

    monkeypatch.setattr(realdata, "elevation_m", lambda la, lo: 4.0)
    monkeypatch.setattr(realdata, "slope_deg", lambda la, lo, step_m=500.0: 1.0)
    monkeypatch.setattr(cal, "climatology", lambda *a, **k:
                        sorted((i / 400) ** 2 * 200.0 for i in range(400)))
    monkeypatch.setattr(genome, "genome_of", lambda la, lo: None)
    # Không kênh nào được cấu hình -> không lời gọi mạng nào rời khỏi máy.
    for var in ("TERRATWIN_ZALO_TOKEN", "TERRATWIN_ZALO_TEMPLATE_ID",
                "TERRATWIN_TELEGRAM_TOKEN", "TERRATWIN_SMTP_HOST"):
        monkeypatch.delenv(var, raising=False)

    from app.main import app

    def _session():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[dbmod.get_session] = _session
    with TestClient(app) as c:
        yield c, Session
    app.dependency_overrides.clear()


def _tok(c, email="a@x.com"):
    r = c.post("/api/auth/register",
               json={"email": email, "password": GOOD_PW, "name": "Nong dan"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


_seq = [0]


def _seed(Session, *, outcomes=(), retro_misses=0, coord=BEN_TRE,
          module="flood", age_days=20):
    """Tạo một người + một thửa + các cảnh báo đã chấm sẵn. Trả (user_id, plot_id).

    Email phải TĂNG DẦN, không lấy theo id(Session): một test gọi _seed hai lần
    sẽ nhận cùng một Session và đâm vào ràng buộc unique — lỗi giả không liên
    quan gì tới thứ đang được kiểm tra.
    """
    from app.db import Alert, Plot, User
    from app import auth

    _seq[0] += 1
    s = Session()
    u = User(email=f"seed{_seq[0]}@x.com",
             password_hash=auth.hash_password(GOOD_PW), name="Seed")
    s.add(u)
    s.commit()
    p = Plot(user_id=u.id, name="Ruong", lat=coord[0], lon=coord[1])
    s.add(p)
    s.commit()

    born = _now() - timedelta(days=age_days)
    for i, oc in enumerate(outcomes):
        s.add(Alert(user_id=u.id, plot_id=p.id, module_id=module,
                    risk_level="danger", headline=f"canh bao {i}",
                    created_at=born, outcome=oc, verified_at=_now(),
                    verify_source="data", observed_peak=80.0 if oc == "hit" else 5.0))
    for i in range(retro_misses):
        s.add(Alert(user_id=u.id, plot_id=p.id, module_id=module,
                    risk_level="danger", headline=f"[HOI CUU] bo sot {i}",
                    created_at=born, outcome="miss", verified_at=_now(),
                    verify_source="data", observed_peak=85.0, retro=1,
                    acknowledged=1))
    s.commit()
    uid, pid = u.id, p.id
    s.close()
    return uid, pid


# ---------------------------------------------------------------------------
# ① SỔ ĐIỂM KHÔNG ĐƯỢC TỰ KHEN
# ---------------------------------------------------------------------------

def test_lan_bo_sot_duoc_tinh_vao_so_diem(env):
    """Không đếm bỏ sót thì POD luôn 100% — con số đẹp và vô nghĩa."""
    c, Session = env
    _seed(Session, outcomes=("hit",) * 8, retro_misses=4)

    s = Session()
    r = scorecard.summary(s, days=365)
    s.close()

    assert r["counts"]["hit"] == 8
    assert r["counts"]["miss"] == 4, "hàng hồi cứu phải vào sổ điểm"
    # 8/(8+4) = 66,7% — KHÔNG phải 100%.
    assert r["pod_pct"] == pytest.approx(66.7, abs=0.1)


def test_hang_hoi_cuu_khong_hien_trong_danh_sach_canh_bao(env):
    """Chúng chưa từng được gửi cho ai. Hiện ra là nói dối người dùng."""
    c, Session = env
    uid, _ = _seed(Session, outcomes=("hit",), retro_misses=3)

    from app import auth
    h = {"Authorization": f"Bearer {auth.create_token(uid)}"}
    rows = c.get("/api/alerts", headers=h).json()

    assert len(rows) == 1
    assert all("HOI CUU" not in r["headline"] for r in rows)


def test_duoi_nguong_mau_thi_khong_cong_bo_ti_le(env):
    """“Chính xác 100%” trên ba mẫu là đúng số học và dối trá về bản chất."""
    c, Session = env
    _seed(Session, outcomes=("hit", "hit", "hit"))

    s = Session()
    r = scorecard.summary(s, days=365)
    s.close()

    assert r["scored"] == 3 < scorecard.MIN_SAMPLE
    assert r["enough"] is False
    assert "%" not in r["headline"].split("chưa đủ")[0]
    assert "chưa đủ" in r["headline"]


def test_so_diem_cong_khai_khong_can_dang_nhap(env):
    """Sổ điểm chỉ chủ nhà xem được thì không phải sổ điểm."""
    c, _ = env
    r = c.get("/api/scorecard")
    assert r.status_code == 200
    assert "far_pct" in r.json() and "method" in r.json()


def test_ti_le_khong_co_mau_tra_None_chu_khong_tra_0(env):
    """Không có dữ liệu và làm đúng 0% là hai chuyện khác hẳn nhau."""
    c, Session = env
    s = Session()
    r = scorecard.summary(s, days=90)
    s.close()
    assert r["pod_pct"] is None and r["far_pct"] is None
    assert r["scored"] == 0


def test_tach_theo_mo_dun(env):
    """Gộp chung sẽ giấu mất chuyện giỏi lũ mà kém hạn."""
    c, Session = env
    _seed(Session, outcomes=("hit",) * 12, module="flood")
    _seed(Session, outcomes=("false_alarm",) * 12, module="drought",
          coord=HA_NOI)

    s = Session()
    rows = {r["module_id"]: r for r in scorecard.by_module(s, days=365)}
    s.close()

    assert rows["flood"]["far_pct"] == 0.0
    assert rows["drought"]["far_pct"] == 100.0


# ---------------------------------------------------------------------------
# ② MỘT CHẠM — token không được thành chìa khoá vạn năng
# ---------------------------------------------------------------------------

def test_token_mot_cham_di_ve_dung_canh_bao(env):
    assert onetap.read_token(onetap.make_token(4242)) == 4242


def test_lien_ket_mot_cham_dung_dia_chi_cong_khai(env, monkeypatch):
    """Bẫy im lặng nhất trong cả tính năng.

    `base_url()` rơi về http://localhost:3000 khi thiếu TERRATWIN_PUBLIC_URL.
    Trên máy phát triển thì đúng; trên máy chủ thật thì MỌI liên kết gửi tới
    điện thoại người dùng là link chết — mà tin vẫn gửi thành công, không một
    dòng lỗi nào trong log. Kho quan sát sẽ mãi không lớn lên và không ai hiểu
    tại sao.

    Test này không sửa được lỗi cấu hình, nhưng nó chốt hợp đồng: đặt biến vào
    thì liên kết PHẢI đi theo, và dấu "/" thừa phải được cắt.
    """
    monkeypatch.setenv("TERRATWIN_PUBLIC_URL", "https://terratwin.vn/")
    link = onetap.link_for(77)
    assert link.startswith("https://terratwin.vn/tap/"), link
    assert "localhost" not in link
    assert "//tap/" not in link, "dấu gạch chéo thừa phải bị cắt"
    assert onetap.read_token(link.rsplit("/", 1)[-1]) == 77


def test_thieu_bien_thi_lui_ve_localhost_chu_khong_no(env, monkeypatch):
    """Thiếu cấu hình thì phải chạy được ở máy phát triển, không được ném lỗi."""
    monkeypatch.delenv("TERRATWIN_PUBLIC_URL", raising=False)
    assert onetap.base_url() == "http://localhost:3000"


def test_token_dang_nhap_KHONG_mo_duoc_cua_mot_cham(env):
    """Thiếu kiểm `k == "tap"` thì token đăng nhập thường cũng lọt qua đây."""
    from app import auth
    assert onetap.read_token(auth.create_token(1)) is None


def test_token_bi_sua_thi_bi_tu_choi(env):
    t = onetap.make_token(7)
    assert onetap.read_token(t[:-3] + "AAA") is None


def test_tra_loi_mot_cham_khong_can_dang_nhap_va_sinh_quan_sat(env):
    c, Session = env
    uid, pid = _seed(Session, outcomes=(), age_days=20)

    from app.db import Alert, Observation
    s = Session()
    a = Alert(user_id=uid, plot_id=pid, module_id="flood", risk_level="danger",
              headline="Sap ngap", created_at=_now() - timedelta(days=20))
    s.add(a)
    s.commit()
    aid = a.id
    s.close()

    tok = onetap.make_token(aid)
    # KHÔNG gửi header Authorization — đó chính là điểm mấu chốt.
    q = c.get(f"/api/tap/{tok}")
    assert q.status_code == 200
    assert "có xảy ra không" in q.json()["question"].lower()
    assert len(q.json()["options"]) == 3

    r = c.post(f"/api/tap/{tok}", json={"answer": "yes"})
    assert r.status_code == 200 and r.json()["outcome"] == "hit"

    s = Session()
    a = s.get(Alert, aid)
    obs = s.execute(select(Observation).where(
        Observation.alert_id == aid)).scalars().all()
    s.close()

    assert a.outcome == "hit" and a.verify_source == "user"
    assert len(obs) == 1
    assert obs[0].source == "onetap" and obs[0].outcome == "occurred"


def test_tra_loi_lan_hai_khong_lat_nguoc_so_diem(env):
    """Một liên kết bị chuyển tiếp không được phép sửa sổ điểm đã chốt."""
    c, Session = env
    uid, pid = _seed(Session)
    from app.db import Alert, Observation
    s = Session()
    a = Alert(user_id=uid, plot_id=pid, module_id="flood", risk_level="danger",
              headline="x", created_at=_now() - timedelta(days=20))
    s.add(a)
    s.commit()
    aid = a.id
    s.close()

    tok = onetap.make_token(aid)
    c.post(f"/api/tap/{tok}", json={"answer": "yes"})
    second = c.post(f"/api/tap/{tok}", json={"answer": "no"}).json()

    assert second["already"] is True
    s = Session()
    assert s.get(Alert, aid).outcome == "hit"
    assert len(s.execute(select(Observation)).scalars().all()) == 1
    s.close()


def test_khong_ro_thi_khong_cham_diem(env):
    """Một câu “không rõ” trung thực có giá trị hơn một phán quyết bịa."""
    c, Session = env
    uid, pid = _seed(Session)
    from app.db import Alert
    s = Session()
    a = Alert(user_id=uid, plot_id=pid, module_id="flood", risk_level="warning",
              headline="x", created_at=_now() - timedelta(days=20))
    s.add(a)
    s.commit()
    aid = a.id
    s.close()

    r = c.post(f"/api/tap/{onetap.make_token(aid)}", json={"answer": "unsure"})
    assert r.status_code == 200 and r.json()["outcome"] is None
    s = Session()
    assert s.get(Alert, aid).outcome is None
    s.close()


def test_nguoi_dung_thang_du_lieu(env):
    """Họ đứng trên thửa; ERA5 là ô lưới ~9 km nội suy."""
    c, Session = env
    uid, pid = _seed(Session)
    from app.db import Alert
    s = Session()
    a = Alert(user_id=uid, plot_id=pid, module_id="flood", risk_level="danger",
              headline="x", created_at=_now() - timedelta(days=20),
              outcome="false_alarm", verify_source="data", observed_peak=12.0)
    s.add(a)
    s.commit()
    aid = a.id
    s.close()

    c.post(f"/api/tap/{onetap.make_token(aid)}", json={"answer": "yes"})
    s = Session()
    a = s.get(Alert, aid)
    s.close()
    assert a.outcome == "hit" and a.verify_source == "user"


def test_token_hong_tra_404_chu_khong_no_500(env):
    c, _ = env
    assert c.get("/api/tap/khong-phai-token").status_code == 404
    assert c.post("/api/tap/rac", json={"answer": "yes"}).status_code == 404


def test_cau_tra_loi_la_tu_bay_bi_tu_choi(env):
    c, Session = env
    uid, pid = _seed(Session)
    from app.db import Alert
    s = Session()
    a = Alert(user_id=uid, plot_id=pid, module_id="flood", risk_level="danger",
              headline="x", created_at=_now() - timedelta(days=20))
    s.add(a)
    s.commit()
    aid = a.id
    s.close()
    r = c.post(f"/api/tap/{onetap.make_token(aid)}", json={"answer": "maybe"})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# ③ CHẤM ĐIỂM TỪ SỐ LIỆU THỰC ĐO
# ---------------------------------------------------------------------------

def test_chua_toi_han_thi_khong_cham(env, monkeypatch):
    """Chấm sớm sẽ nhận dữ liệu rỗng rồi tự kết luận là “báo bừa”."""
    c, Session = env
    uid, pid = _seed(Session)
    from app.db import Alert
    s = Session()
    a = Alert(user_id=uid, plot_id=pid, module_id="flood", risk_level="danger",
              headline="x", created_at=_now() - timedelta(days=2))
    s.add(a)
    s.commit()

    goi = []
    monkeypatch.setattr(verify.realdata, "historical_weather",
                        lambda *a, **k: goi.append(1) or None)
    out = verify.sweep(s)
    s.close()

    assert out["verified"] == 0
    assert goi == [], "chưa tới hạn thì không được gọi mạng"


@pytest.mark.parametrize("peak,mong_doi", [(88.0, "hit"), (5.0, "false_alarm")])
def test_cham_theo_dinh_thuc_do(env, monkeypatch, peak, mong_doi):
    c, Session = env
    uid, pid = _seed(Session)
    from app.db import Alert
    s = Session()
    born = _now() - timedelta(days=30)
    a = Alert(user_id=uid, plot_id=pid, module_id="flood", risk_level="danger",
              headline="x", created_at=born)
    s.add(a)
    s.commit()
    aid = a.id

    monkeypatch.setattr(verify.realdata, "historical_weather",
                        lambda la, lo, st, en: _rows(date.fromisoformat(st), 100))
    # index_series trả CHUỖI 3-TUPLE (_, _, giá trị) — khớp hazard.peak_of và
    # code thật; mock bằng scalar sẽ che giấu bug production (đã xảy ra một lần).
    monkeypatch.setattr(verify.hazard, "index_series",
                        lambda m, la, lo, rows: [(0, 0, peak)] * len(rows))

    verify.sweep(s)
    a = s.get(Alert, aid)
    s.close()

    assert a.outcome == mong_doi
    assert a.observed_peak == pytest.approx(peak)
    assert a.verify_source == "data"
    assert "Open-Meteo Archive" in a.verify_note, "phải ghi rõ nguồn bằng chứng"


def test_canh_bao_mo_coi_khong_treo_mai_trong_hang_doi(env, monkeypatch):
    c, Session = env
    uid, _ = _seed(Session)
    from app.db import Alert
    s = Session()
    a = Alert(user_id=uid, plot_id=None, module_id="flood", risk_level="danger",
              headline="x", created_at=_now() - timedelta(days=30))
    s.add(a)
    s.commit()
    aid = a.id
    verify.sweep(s)
    a = s.get(Alert, aid)
    s.close()
    assert a.outcome == "expired"


def test_chi_lay_dinh_TRONG_cua_so_canh_bao(env, monkeypatch):
    """Tính cả phần chạy đà là chấm nhầm sang chuyện xảy ra TRƯỚC khi báo."""
    c, Session = env
    uid, pid = _seed(Session)
    from app.db import Alert
    s = Session()
    born = (_now() - timedelta(days=30)).replace(microsecond=0)
    a = Alert(user_id=uid, plot_id=pid, module_id="flood", risk_level="danger",
              headline="x", created_at=born, window_days=7)
    s.add(a)
    s.commit()
    aid = a.id

    def fake_hist(la, lo, st, en):
        return _rows(date.fromisoformat(st),
                     (date.fromisoformat(en) - date.fromisoformat(st)).days + 1)

    # Đỉnh 99 nằm ở ngày ĐẦU chuỗi — tức trong phần chạy đà 60 ngày trước khi
    # cảnh báo được phát. Trong cửa sổ thật mọi ngày chỉ có 10.
    monkeypatch.setattr(verify.realdata, "historical_weather", fake_hist)
    monkeypatch.setattr(verify.hazard, "index_series",
                        lambda m, la, lo, rows: [(0, 0, 99.0)] + [(0, 0, 10.0)] * (len(rows) - 1))

    verify.sweep(s)
    a = s.get(Alert, aid)
    s.close()

    assert a.observed_peak == pytest.approx(10.0)
    assert a.outcome == "false_alarm"


def test_bo_sot_lien_tiep_gop_thanh_MOT_dot(env, monkeypatch):
    """Một trận mưa bảy ngày phải là một lần bỏ sót, không phải bảy."""
    c, Session = env
    uid, pid = _seed(Session)
    from app.db import Alert

    s = Session()
    start = date.today() - timedelta(days=40)
    rows = _rows(start, 20)
    # Bảy ngày liền vượt ngưỡng nguy hiểm, rồi lặng.
    series = [(0, 0, 10.0)] * 3 + [(0, 0, 85.0)] * 7 + [(0, 0, 10.0)] * 10
    monkeypatch.setattr(verify.realdata, "historical_weather",
                        lambda la, lo, st, en: rows)
    monkeypatch.setattr(verify.hazard, "index_series",
                        lambda m, la, lo, r: series)
    monkeypatch.setattr(verify.hazard, "IDS", ("flood",))

    out = verify.sweep_misses(s, days=90)
    n = len(s.execute(select(Alert).where(Alert.retro == 1)).scalars().all())
    s.close()

    assert out["misses_recorded"] == 1
    assert n == 1


def test_da_bao_roi_thi_khong_tinh_la_bo_sot(env, monkeypatch):
    c, Session = env
    uid, pid = _seed(Session)
    from app.db import Alert

    s = Session()
    start = date.today() - timedelta(days=40)
    rows = _rows(start, 20)
    series = [(0, 0, 10.0)] * 3 + [(0, 0, 85.0)] * 4 + [(0, 0, 10.0)] * 13
    dot = datetime.combine(start + timedelta(days=3), datetime.min.time())
    # Đã có cảnh báo phát ra một ngày trước khi đợt bắt đầu.
    s.add(Alert(user_id=uid, plot_id=pid, module_id="flood",
                risk_level="danger", headline="da bao",
                created_at=dot - timedelta(days=1)))
    s.commit()

    monkeypatch.setattr(verify.realdata, "historical_weather",
                        lambda la, lo, st, en: rows)
    monkeypatch.setattr(verify.hazard, "index_series",
                        lambda m, la, lo, r: series)
    monkeypatch.setattr(verify.hazard, "IDS", ("flood",))

    out = verify.sweep_misses(s, days=90)
    s.close()
    assert out["misses_recorded"] == 0


def test_quet_bo_sot_hai_lan_khong_ghi_trung(env, monkeypatch):
    c, Session = env
    uid, pid = _seed(Session)
    from app.db import Alert

    s = Session()
    rows = _rows(date.today() - timedelta(days=40), 20)
    series = [(0, 0, 10.0)] * 3 + [(0, 0, 85.0)] * 4 + [(0, 0, 10.0)] * 13
    monkeypatch.setattr(verify.realdata, "historical_weather",
                        lambda la, lo, st, en: rows)
    monkeypatch.setattr(verify.hazard, "index_series",
                        lambda m, la, lo, r: series)
    monkeypatch.setattr(verify.hazard, "IDS", ("flood",))

    verify.sweep_misses(s, days=90)
    verify.sweep_misses(s, days=90)
    n = len(s.execute(select(Alert).where(Alert.retro == 1)).scalars().all())
    s.close()
    assert n == 1


# ---------------------------------------------------------------------------
# ④ KÊNH GỬI — không bao giờ im lặng giả vờ thành công
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("vao,ra", [
    ("0912345678", "84912345678"),
    ("+84 912 345 678", "84912345678"),
    ("84912345678", "84912345678"),
    ("0912 345 678", "84912345678"),
])
def test_chuan_hoa_so_dien_thoai(vao, ra):
    assert notify.normalize_phone(vao) == ra


@pytest.mark.parametrize("xau", ["091234567", "0112345678", "", "abc",
                                 "091234567890"])
def test_so_dien_thoai_sai_bi_tu_choi(xau):
    assert notify.normalize_phone(xau) is None


def test_kenh_chua_cau_hinh_bao_loi_ro_chu_khong_im_lang(env):
    """Báo “đã gửi” trong khi không gửi gì là kiểu hỏng nguy hiểm nhất."""
    err_z = notify.send_zalo("0912345678", "thu")
    err_t = notify.send_telegram("123456", "thu")
    assert err_z and "TERRATWIN_ZALO_TOKEN" in err_z
    assert err_t and "TERRATWIN_TELEGRAM_TOKEN" in err_t


def test_dispatch_kenh_zalo_chua_cau_hinh_dem_la_that_bai(env):
    class Ch:
        id, kind, target, min_level, enabled = 1, "zalo", "84912345678", "warning", 1
        last_sent_at = last_error = None

    ch = Ch()
    r = notify.dispatch([ch], [{"module_id": "flood", "risk_level": "danger",
                                "headline": "x", "recommendation": "y"}])
    assert r["sent"] == 0 and r["failed"] == 1
    assert ch.last_error and ch.last_sent_at is None


def test_tao_kenh_zalo_luu_dang_chuan_84(env):
    c, _ = env
    h = _tok(c, "zalo@x.com")
    r = c.post("/api/channels", headers=h,
               json={"kind": "zalo", "target": "0912 345 678"})
    assert r.status_code == 201, r.text
    assert r.json()["target"] == "84912345678"


def test_tao_kenh_zalo_so_sai_bi_chan_ngay(env):
    c, _ = env
    h = _tok(c, "zalo2@x.com")
    r = c.post("/api/channels", headers=h,
               json={"kind": "zalo", "target": "0112345678"})
    assert r.status_code == 422


def test_tao_kenh_telegram_doi_chat_id_la_so(env):
    c, _ = env
    h = _tok(c, "tg@x.com")
    assert c.post("/api/channels", headers=h,
                  json={"kind": "telegram", "target": "@toi"}).status_code == 422
    assert c.post("/api/channels", headers=h,
                  json={"kind": "telegram", "target": "-1001234"}
                  ).status_code == 201


def test_trang_thai_kenh_noi_that_ve_cai_chua_cau_hinh(env):
    c, _ = env
    r = c.get("/api/channels/status").json()
    assert r["ready"]["zalo"] is False and r["ready"]["telegram"] is False
    assert r["ready"]["webhook"] is True
    assert "giấy phép kinh doanh" in r["note"]["zalo"]


def test_cau_hoi_gui_rieng_khong_bi_loc_theo_muc_rui_ro(env):
    """Cảnh báo mức nhẹ mới là loại đáng hỏi nhất — đó là chỗ hay báo bừa."""
    class Ch:
        id, kind, target, min_level, enabled = 1, "telegram", "1", "danger", 1
        last_sent_at = last_error = None

    r = notify.ask([Ch()], [{"alert_id": 9, "question": "co ngap khong?",
                             "link": "http://x/tap/abc"}])
    # Chưa cấu hình nên gửi hỏng — nhưng nó ĐÃ THỬ, tức không bị min_level loại.
    assert r["failed"] == 1 and r["alert_id"] == 9


# ---------------------------------------------------------------------------
# ⑤ BẢN ĐỒ ĐỘ TIN CẬY
# ---------------------------------------------------------------------------

def test_vung_it_mau_khong_cong_bo_ti_le(env):
    c, Session = env
    _seed(Session, outcomes=("hit", "hit"))
    s = Session()
    r = scorecard.reliability(s, days=365)
    s.close()
    o = r["cells"][0]
    assert o["scored"] == 2 and o["enough"] is False
    assert "chưa đủ" in o["label"]


def test_gop_dung_theo_o_luoi_va_khong_lo_toa_do(env):
    c, Session = env
    _seed(Session, outcomes=("hit",) * 6, coord=BEN_TRE)
    s = Session()
    r = scorecard.reliability(s, days=365)
    s.close()
    o = r["cells"][0]
    assert o["enough"] is True and o["pod_pct"] == 100.0
    # Toạ độ trả về là GÓC Ô, không phải vị trí thửa (10.19, 106.70).
    assert (o["lat"], o["lon"]) == (10.0, 106.5)


def test_endpoint_do_tin_cay_cong_khai(env):
    c, _ = env
    r = c.get("/api/reliability")
    assert r.status_code == 200 and "cells" in r.json()


def test_kho_quan_sat_dem_rieng_duong_mot_cham(env):
    """Nếu con số này không lớn lên thì đường một chạm chưa chạy."""
    c, Session = env
    s = Session()
    g = scorecard.ground_truth(s)
    s.close()
    assert g["by_onetap"] == 0 and "observations" in g


def test_dong_thoi_gian_thua_noi_ca_lan_bo_sot(env):
    """Giấu lần bỏ sót đi thì dòng thời gian chỉ còn là bảng thành tích."""
    c, Session = env
    uid, pid = _seed(Session, outcomes=("hit", "false_alarm"), retro_misses=2)

    from app import auth
    h = {"Authorization": f"Bearer {auth.create_token(uid)}"}
    r = c.get(f"/api/plots/{pid}/timeline", headers=h)
    assert r.status_code == 200, r.text
    d = r.json()

    assert d["tally"]["hit"] == 1 and d["tally"]["false_alarm"] == 1
    assert d["tally"]["miss"] == 2
    khong_bao = [e for e in d["events"] if not e["was_warned"]]
    assert len(khong_bao) == 2, "lần bỏ sót phải hiện, kèm cờ was_warned=False"
    assert d["plot"]["name"] == "Ruong"


def test_dong_thoi_gian_thua_nguoi_khac_bi_chan(env):
    c, Session = env
    _, pid = _seed(Session, outcomes=("hit",))
    h = _tok(c, "kegian@x.com")
    assert c.get(f"/api/plots/{pid}/timeline", headers=h).status_code == 404


def test_so_diem_theo_thoi_gian_co_du_moc(env):
    c, _ = env
    r = c.get("/api/scorecard/timeline?days=90&buckets=6").json()
    assert len(r["buckets"]) == 6
    assert r["buckets"][0]["from"] < r["buckets"][-1]["from"], "phải theo thứ tự thời gian"
