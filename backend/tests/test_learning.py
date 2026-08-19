"""S05 Federated · S09 Model Engine · C04 Time-Lapse · U02 · U03 · U04.

Phần quan trọng nhất: chứng minh "federated" không phải nhãn dán. Quan sát THÔ
của một người không được lộ cho người khác qua bất kỳ endpoint nào, và bảng
tổng hợp phải giữ kín khi vùng chưa đủ số quan sát tối thiểu.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.services import federated

BEN_TRE = {"lat": 10.19, "lon": 106.70}
FAR_AWAY = {"lat": 21.03, "lon": 105.85}
GOOD_PW = "MatKhau123"
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()


def _rows(precip=25.0, n=7, start="2026-08-11"):
    d0 = date.fromisoformat(start)
    return [{"day": i, "date": (d0 + timedelta(days=i)).isoformat(),
             "precip": precip, "et0": 4.0, "tmax": 33.0} for i in range(n)]


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app import db as dbmod
    from app.services import calibration as cal
    from app.services import genome, realdata

    engine = create_engine(f"sqlite:///{tmp_path/'l.db'}",
                           connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    dbmod.Base.metadata.create_all(engine)
    monkeypatch.setattr(dbmod, "engine", engine)
    monkeypatch.setattr(dbmod, "SessionLocal", Session)

    monkeypatch.setattr(realdata, "elevation_m", lambda la, lo: 4.0)
    monkeypatch.setattr(realdata, "slope_deg", lambda la, lo, step_m=500.0: 1.0)
    monkeypatch.setattr(realdata, "weather_7d", lambda la, lo: _rows())
    monkeypatch.setattr(realdata, "river_discharge_7d", lambda la, lo: None)
    monkeypatch.setattr(realdata, "marine_7d", lambda la, lo: None)
    monkeypatch.setattr(realdata, "solar_annual", lambda la, lo: 4.9)
    # Mưa đủ lớn để chỉ số vượt ngưỡng 40 với khí hậu giả lập bên dưới —
    # nếu model không bao giờ "báo" thì không có hit/false_alarm nào để chấm.
    monkeypatch.setattr(realdata, "historical_weather",
                        lambda la, lo, s, e: _rows(precip=90.0, start=s, n=8))
    monkeypatch.setattr(cal, "climatology", lambda *a, **k:
                        sorted((i / 400) ** 2 * 200.0 for i in range(400)))
    monkeypatch.setattr(genome, "genome_of", lambda la, lo: None)

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


def _tok(c, email="a@x.com"):
    r = c.post("/api/auth/register",
               json={"email": email, "password": GOOD_PW, "name": "Nong dan"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _obs(c, h, outcome="occurred", loc=None, module="flood", note="ruong ngap"):
    return c.post("/api/observations", headers=h, json={
        "location": loc or BEN_TRE, "module_id": module,
        "observed_on": YESTERDAY, "outcome": outcome, "note": note})


# ---------- S05: gửi quan sát ----------

def test_submit_observation_records_model_index(client):
    """Chỉ số model phải được CHỐT lúc gửi, để chấm điểm về sau không bị trôi."""
    h = _tok(client)
    r = _obs(client, h)
    assert r.status_code == 201
    assert r.json()["model_index"] is not None


def test_rejects_future_observation(client):
    h = _tok(client)
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    r = client.post("/api/observations", headers=h, json={
        "location": BEN_TRE, "module_id": "flood",
        "observed_on": tomorrow, "outcome": "occurred"})
    assert r.status_code == 422


def test_rejects_unsupported_module(client):
    h = _tok(client)
    r = client.post("/api/observations", headers=h, json={
        "location": BEN_TRE, "module_id": "carbon",
        "observed_on": YESTERDAY, "outcome": "occurred"})
    assert r.status_code == 422


def test_observations_require_auth(client):
    assert client.get("/api/observations").status_code == 401


# ---------- S05: QUYỀN RIÊNG TƯ — phần quan trọng nhất ----------

def test_raw_observations_never_visible_to_others(client):
    """Nếu test này fail thì chữ 'federated' chỉ là nhãn dán."""
    a = _tok(client, "a@x.com")
    b = _tok(client, "b@x.com")
    _obs(client, a, note="BI MAT RUONG NHA TOI")
    assert client.get("/api/observations", headers=b).json() == []


def test_aggregate_leaks_no_identifying_field(client):
    a = _tok(client, "a@x.com")
    for _ in range(4):
        _obs(client, a, note="BI MAT RUONG NHA TOI")
    raw = client.get("/api/federated").text
    for leak in ("BI MAT", "user_id", "a@x.com", "note", "observed_on"):
        assert leak not in raw, f"lộ '{leak}' trong bảng tổng hợp"


def test_aggregate_withholds_cells_below_minimum(client):
    """Vùng ít quan sát bị giữ kín — nếu công bố thì truy ngược được cá nhân."""
    from app.services import federated
    h = _tok(client)
    _obs(client, h)                      # chỉ 1 quan sát
    d = client.get("/api/federated").json()
    assert d["cells_published"] == 0 and d["cells_pending"] == 1
    assert d["min_observations"] == federated.MIN_OBS


def test_aggregate_publishes_once_enough(client):
    h = _tok(client)
    for _ in range(federated.MIN_OBS):
        _obs(client, h)
    d = client.get("/api/federated").json()
    assert d["cells_published"] == 1
    a = d["adjustments"][0]
    assert "," in a["cell"] and a["module_id"] == "flood"


def test_cell_coarser_than_exact_coordinates(client):
    from app.services import federated
    c1 = federated.cell_of(10.19, 106.70)
    c2 = federated.cell_of(10.22, 106.73)      # cách ~4 km
    assert c1 == c2, "lưới phải thô hơn toạ độ để không truy ngược được thửa"


# ---------- S05: hướng hiệu chỉnh ----------

def test_false_alarms_raise_threshold(client):
    """Model báo mà thực tế không xảy ra → phải NÂNG ngưỡng."""
    h = _tok(client)
    for _ in range(4):
        _obs(client, h, outcome="none")       # mưa lớn nên model CÓ báo
    adj = client.get("/api/federated").json()["adjustments"]
    assert adj and adj[0]["threshold_shift"] > 0


def test_shift_is_clamped_against_poisoning(client):
    """Một nhóm nhỏ quan sát sai không được phá mô hình."""
    from app.services import federated
    h = _tok(client)
    for _ in range(50):
        _obs(client, h, outcome="none")
    adj = client.get("/api/federated").json()["adjustments"]
    assert adj[0]["threshold_shift"] <= federated.MAX_SHIFT


def test_shift_lookup_for_location(client):
    h = _tok(client)
    for _ in range(3):
        _obs(client, h, outcome="none")
    r = client.get("/api/federated/shift",
                   params={"lat": 10.19, "lon": 106.70, "module_id": "flood"})
    assert r.json()["applied"] is True
    far = client.get("/api/federated/shift",
                     params={"lat": 21.03, "lon": 105.85, "module_id": "flood"})
    assert far.json()["applied"] is False


# ---------- S09: chấm điểm mô hình ----------

def test_evaluate_needs_minimum_observations(client):
    d = client.get("/api/model/evaluate").json()
    assert d["dataset"]["observations"] == 0
    assert "cần ít nhất" in d["headline"]


def test_evaluate_computes_contingency_metrics(client):
    h = _tok(client)
    for _ in range(3):
        _obs(client, h, outcome="occurred")   # model báo + xảy ra = hit
    for _ in range(2):
        _obs(client, h, outcome="none", loc={"lat": 10.31, "lon": 106.81})
    d = client.get("/api/model/evaluate").json()
    o = d["overall"]
    assert o["hit"] == 3 and o["false_alarm"] == 2
    assert o["pod"] == 1.0                    # bắt hết sự việc thật
    assert o["far"] == pytest.approx(0.4)     # 2/(3+2)
    assert o["csi"] == pytest.approx(0.6)     # 3/(3+2+0)


def test_evaluate_flags_over_warning(client):
    h = _tok(client)
    for i in range(5):
        _obs(client, h, outcome="none", loc={"lat": 10.19 + i * 0.01, "lon": 106.70})
    d = client.get("/api/model/evaluate").json()
    assert d["overall"]["bias"] is None or d["overall"]["bias"] > 1
    assert "POD một mình vô nghĩa" in d["why_csi_first"]


def test_evaluate_admits_training_not_done(client):
    d = client.get("/api/model/evaluate").json()
    assert "HUẤN LUYỆN" in d["honesty_note"]


# ---------- C04 Time-Lapse ----------

def test_timelapse_rejects_non_hazard_module(client):
    assert client.post("/api/timelapse/carbon", json=BEN_TRE).status_code == 404


def test_timelapse_states_it_is_not_image_change_detection(client):
    d = client.post("/api/timelapse/flood?years=4", json=BEN_TRE).json()
    if d.get("available"):
        assert "Sentinel" in d["caveat"]
        assert d["trend"] in ("stable", "worsening", "improving")


# ---------- U03 Design Studio ----------

def test_design_recommends_and_explains(client):
    d = client.post("/api/design", json=BEN_TRE).json()
    assert d["recommended"]["score"] >= 0
    assert len(d["options"]) == 7
    # Mỗi lựa chọn phải có lý do hoặc cảnh báo — không được chấm điểm suông.
    assert all(o["reasons"] or o["warnings"] for o in d["options"])
    assert d["options"] == sorted(d["options"], key=lambda o: -o["score"])


def test_design_says_it_is_not_a_generative_model(client):
    d = client.post("/api/design", json=BEN_TRE).json()
    assert "không phải model sinh ảnh" in d["generative_note"]
    assert "Sở NN&PTNT" in d["caveat"]


def test_design_lists_infrastructure_priorities(client):
    d = client.post("/api/design", json=BEN_TRE).json()
    assert d["infrastructure"]
    assert all(i["priority"] in ("cao", "trung bình", "thấp") and i["why"]
               for i in d["infrastructure"])


# ---------- U04 Closed-Loop ----------

def test_action_loop_closes(client):
    h = _tok(client)
    aid = client.post("/api/actions", headers=h, json={
        "module_id": "flood", "recommendation": "Kê cao tài sản",
        "acted_on": YESTERDAY, "status": "done"}).json()["id"]
    r = client.post(f"/api/actions/{aid}/outcome", headers=h,
                    json={"outcome": "avoided", "outcome_note": "khong thiet hai"})
    assert r.json()["outcome"] == "avoided"

    _obs(client, h)
    loop = client.get("/api/loop", headers=h).json()
    assert loop["closed"] is True
    assert loop["outcomes_verified"] == 1 and loop["help_rate"] == 1.0
    assert len(loop["stages"]) == 4


def test_loop_not_closed_without_verification(client):
    h = _tok(client)
    client.post("/api/actions", headers=h, json={
        "module_id": "flood", "recommendation": "x", "acted_on": YESTERDAY})
    assert client.get("/api/loop", headers=h).json()["closed"] is False


def test_loop_admits_human_is_the_actuator(client):
    h = _tok(client)
    assert "IoT" in client.get("/api/loop", headers=h).json()["note"]


def test_actions_isolated_between_users(client):
    a = _tok(client, "a@x.com")
    b = _tok(client, "b@x.com")
    aid = client.post("/api/actions", headers=a, json={
        "module_id": "flood", "recommendation": "x", "acted_on": YESTERDAY}).json()["id"]
    assert client.get("/api/actions", headers=b).json() == []
    assert client.post(f"/api/actions/{aid}/outcome", headers=b,
                       json={"outcome": "avoided"}).status_code == 404


# ---------- U02 Marketplace tri thức ----------

def test_knowledge_share_and_find(client):
    h = _tok(client)
    r = client.post("/api/knowledge", headers=h, json={
        "location": BEN_TRE, "topic": "man",
        "title": "Cach tru nuoc ngot truoc mua kho",
        "body": "Dao ao 200m2, dong cong tu thang 12, kiem tra do man moi tuan."})
    assert r.status_code == 201
    found = client.get("/api/knowledge",
                       params={"lat": 10.19, "lon": 106.70, "topic": "man"}).json()
    assert len(found["notes"]) == 1
    assert found["notes"][0]["similarity_pct"] > 0


def test_knowledge_says_no_payment(client):
    h = _tok(client)
    client.post("/api/knowledge", headers=h, json={
        "location": BEN_TRE, "topic": "man", "title": "abc",
        "body": "noi dung du dai de qua validate"})
    d = client.get("/api/knowledge", params={"lat": 10.19, "lon": 106.70}).json()
    assert "thanh toán" in d["note"]


def test_knowledge_empty_is_honest(client):
    d = client.get("/api/knowledge",
                   params={"lat": 10.19, "lon": 106.70, "topic": "khongco"}).json()
    assert d["notes"] == [] and "Chưa có ai" in d["message"]


def test_helpful_counter(client):
    h = _tok(client)
    nid = client.post("/api/knowledge", headers=h, json={
        "location": BEN_TRE, "topic": "lu", "title": "abc",
        "body": "noi dung du dai de qua validate"}).json()["id"]
    assert client.post(f"/api/knowledge/{nid}/helpful", headers=h
                       ).json()["helpful_count"] == 1


# ---------- Roadmap sau khi thêm 6 luồng ----------

def test_roadmap_dem_dung_va_khop_tong(client):
    """Không ghim con số tuyệt đối — ghim tính NHẤT QUÁN của bảng.

    Một test kiểu `done == 24` phải sửa mỗi lần làm xong thêm một luồng, và
    người sửa dễ chỉnh con số cho test xanh lại mà không kiểm gì cả. Ghim
    bất biến thì test vẫn bắt được lỗi thật mà không cản tiến độ.
    """
    d = client.get("/api/roadmap").json()
    assert d["total"] == 26
    assert d["done"] + d["partial"] + d["blocked"] == 26
    assert d["live"] + d["awaiting_config"] == d["done"]
    assert d["live"] <= d["done"] <= d["total"]
    for tier in d["by_tier"].values():
        assert tier["live"] <= tier["done"] <= tier["total"]


def test_luong_bi_chan_phai_noi_ro_dang_thieu_gi(client):
    """`blocked` phải nêu đích danh thứ đang chặn, không được viết chung chung."""
    for f in client.get("/api/roadmap").json()["flows"]:
        if f["status"] == "blocked":
            note = f["note"]
            assert any(k in note for k in ("GPU", "Sentinel", "model")), f["id"]
            assert "đang phát triển" not in note, f["id"]


def test_luong_cho_khoa_phai_tu_danh_dau(client, monkeypatch):
    """Luồng cần vệ tinh phải tự khai là chưa chạy được khi thiếu khóa.

    Đây là chỗ dễ nói dối nhất: mã đã viết xong nên rất cám dỗ để đếm là
    "xong", trong khi người dùng bấm vào chỉ thấy 'chưa đủ dữ liệu'.
    """
    monkeypatch.delenv("TERRATWIN_COPERNICUS_ID", raising=False)
    monkeypatch.delenv("TERRATWIN_COPERNICUS_SECRET", raising=False)
    d = client.get("/api/roadmap").json()
    assert d["satellite_configured"] is False
    sat = [f for f in d["flows"] if f["requires"] == "satellite"]
    assert sat, "phải có ít nhất một luồng phụ thuộc vệ tinh"
    for f in sat:
        assert f["awaiting_config"] is True
        assert f["awaiting_note"]
    assert d["live"] < d["done"]


def test_co_khoa_thi_khong_con_luong_nao_cho(client, monkeypatch):
    monkeypatch.setenv("TERRATWIN_COPERNICUS_ID", "id")
    monkeypatch.setenv("TERRATWIN_COPERNICUS_SECRET", "secret")
    d = client.get("/api/roadmap").json()
    assert d["satellite_configured"] is True
    assert d["awaiting_config"] == 0
    assert d["live"] == d["done"]

