"""Những thứ phải đúng TRƯỚC KHI app phục vụ được request đầu tiên.

Bài học đắt: một dòng `print()` tiếng Việt trong `lifespan` làm app không khởi
động nổi trên console cp1252 (mặc định của Windows) — sập với UnicodeEncodeError
trước cả khi mở cổng. Lỗi kiểu này không bao giờ lộ ra trong pytest vì pytest
bắt stdout bằng UTF-8; nó chỉ nổ đúng lúc deploy. Nên phải test có chủ đích.
"""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path

import pytest

from app.safelog import log

APP = Path(__file__).resolve().parent.parent / "app"


class _Cp1252Stdout(io.TextIOWrapper):
    """Giả lập console Windows mặc định: không encode được tiếng Việt."""

    def __init__(self):
        self._raw = io.BytesIO()
        super().__init__(self._raw, encoding="cp1252", errors="strict",
                         write_through=True)


def test_log_khong_sap_khi_console_khong_ho_tro_tieng_viet(monkeypatch):
    fake = _Cp1252Stdout()
    monkeypatch.setattr(sys, "stdout", fake)
    # Không được ném — đây chính là dòng đã làm app không khởi động được.
    log("[TerraTwin] Rà soát chủ động: bộ hẹn giờ nội bộ đã bật — ✓")
    fake.flush()
    out = fake._raw.getvalue()
    assert out, "phải ghi ra được cái gì đó, dù là bản thay ký tự"
    assert b"TerraTwin" in out


def test_log_van_giu_nguyen_tieng_viet_khi_console_utf8(monkeypatch):
    raw = io.BytesIO()
    fake = io.TextIOWrapper(raw, encoding="utf-8", write_through=True)
    monkeypatch.setattr(sys, "stdout", fake)
    log("Rà soát chủ động")
    fake.flush()
    assert "Rà soát chủ động" in raw.getvalue().decode("utf-8")


def test_khong_con_print_tho_o_duong_khoi_dong():
    """main.py và tầng services phải đi qua log(), trừ chính safelog.py.

    Chốt chặn để lần sau ai thêm một dòng print() tiếng Việt vào lifespan thì
    test đỏ ngay, thay vì phát hiện lúc container không chịu khởi động.
    """
    files = [APP / "main.py"] + sorted((APP / "services").glob("*.py"))
    offenders = []
    for f in files:
        if f.name == "safelog.py":
            continue
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if re.match(r"^\s*print\(", line):
                offenders.append(f"{f.name}:{i}")
    assert not offenders, f"print() thô ở: {offenders}"


def test_service_khong_import_nguoc_len_entrypoint():
    """Service ghi log phải dùng app.safelog, không import ngược app.main.

    Import ngược tạo vòng phụ thuộc và biến một dòng log thành lý do khiến
    tầng dữ liệu không nạp được nếu entrypoint đổi.
    """
    rd = (APP / "services" / "realdata.py").read_text(encoding="utf-8")
    assert "from app.main import" not in rd
    assert "from app.safelog import log" in rd


def test_bo_hen_gio_tat_duoc_bang_bien_moi_truong():
    """Chạy nhiều worker thì phải tắt được, không thì mỗi worker quét một lần."""
    src = (APP / "main.py").read_text(encoding="utf-8")
    assert "TERRATWIN_RADAR_INTERVAL_H" in src
    assert "if _RADAR_INTERVAL_H > 0:" in src


def test_radar_logic_chi_ton_tai_mot_ban():
    """Route và bộ hẹn giờ phải gọi CÙNG một hàm.

    Có hai bản logic quét là chuyện sớm muộn chúng lệch nhau, và bản chạy nền
    (không ai nhìn) sẽ là bản sai.
    """
    routes = (APP / "routes_data.py").read_text(encoding="utf-8")
    assert "radar.sweep_user" in routes
    # Logic cũ đã phải biến mất khỏi route
    assert "_DEDUP_HOURS" not in routes
    assert "scan_svc.scan" not in routes


@pytest.mark.parametrize("var", [
    "TERRATWIN_SECRET", "TERRATWIN_TRUST_PROXY", "TERRATWIN_RADAR_INTERVAL_H",
    "TERRATWIN_LLM_PROVIDER", "TERRATWIN_COPERNICUS_ID",
])
def test_render_yaml_khai_bao_du_bien(var):
    """Biến nào code đọc mà render.yaml không khai thì deploy xong mới biết.

    TERRATWIN_LLM_PROVIDER là ví dụ đắt nhất: thiếu nó, người dùng cắm khóa
    Gemini vào sẽ thấy trợ lý im lặng tụt về rule-based mà không có lỗi nào.
    """
    y = (APP.parent.parent / "render.yaml").read_text(encoding="utf-8")
    assert var in y, f"render.yaml thiếu {var}"


# ---------------------------------------------------------------- hạn mức

def test_can_han_muc_khac_voi_mat_mang(monkeypatch):
    """429 phải được ghi nhận riêng, không lẫn vào 'không có dữ liệu'.

    Open-Meteo giới hạn theo NGÀY. Cạn hạn mức thì mọi mô-đun đồng loạt trả
    "chưa đủ dữ liệu" — nhìn hệt như phần mềm hỏng. Người vận hành phải phân
    biệt được "hết quota, mai lại chạy" với "code hỏng", nếu không sẽ đi sửa
    nhầm chỗ suốt một ngày.
    """
    import urllib.error

    from app.services import cache_store, realdata

    cache_store.clear_prefix("quota")
    cache_store.clear_prefix("realdata")

    def _429(req, timeout=None):
        raise urllib.error.HTTPError(
            "https://api.open-meteo.com/v1/x", 429, "Too Many Requests", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", _429)
    assert realdata._get("https://api.open-meteo.com/v1/forecast?x=1") is None

    q = realdata.quota_status()
    assert "api.open-meteo.com" in q["exhausted"]
    assert "quá nhiều" in q["message"]
    # KHÔNG được hứa hẹn một thời gian phục hồi cụ thể — đo lại 2026-09-17 cho
    # thấy có lúc chặn liên tục 18 phút, lâu hơn hẳn ghi chú "mười phút" cũ mà
    # bản thân ghi chú đó từng làm người vận hành tưởng chắc chắn chờ 10 phút
    # là xong. Không được chép lại câu "thử lại ngày mai" của Open-Meteo — thế
    # còn tệ hơn theo hướng ngược lại (bắt chờ vô ích cả ngày).
    assert "ngày mai" not in q["message"]
    cache_store.clear_prefix("quota")


def test_loi_mang_thuong_khong_bi_ghi_la_can_han_muc(monkeypatch):
    from app.services import cache_store, realdata

    cache_store.clear_prefix("quota")
    cache_store.clear_prefix("realdata")

    def _boom(req, timeout=None):
        raise OSError("mat mang")

    monkeypatch.setattr("urllib.request.urlopen", _boom)
    assert realdata._get("https://api.open-meteo.com/v1/forecast?y=1") is None
    assert realdata.quota_status()["exhausted"] == []


def test_cache_song_qua_restart_va_lam_phao_cuu_sinh(monkeypatch):
    """2026-09-21 — _CACHE cũ nằm trong RAM: mất sạch mỗi lần Render tự dựng
    lại tiến trình (đo được: count_429_24h đọc 38 rồi về rỗng mà không có
    deploy nào ở giữa). Hậu quả kép: (a) mỗi restart nã lại Open-Meteo cho mọi
    toạ độ đang hoạt động — chính nguyên nhân sinh ra 38 lần 429 đó; (b) khi bị
    429 giữa lúc cache vừa hết hạn, phần mềm rơi thẳng xuống None (mô hình mẫu)
    dù vẫn còn một bản đo thật cũ hơn 30 phút nhưng chưa quá cũ để dùng được.

    Test này không mô phỏng "restart" trực tiếp (đó là cache_store, đã có test
    riêng ở test_cache.py/test_cache_survives_and_expires) mà khoá chặt HAI
    hành vi mới của realdata._get(): (1) cache vẫn đọc được qua một "tiến
    trình mới" — tức là qua cache_store, không phải dict trong RAM của chính
    module này; (2) gọi mạng hỏng thì dùng bản CŨ làm phao cứu sinh thay vì None.
    """
    import time

    from app.services import cache_store, realdata

    url = "https://api.open-meteo.com/v1/forecast?lat=1.0&lon=1.0"
    key = realdata._cache_key(url)
    cache_store.clear_prefix("realdata")

    # Bản cache "cũ" — quá 30 phút (_TTL) nên không còn tính là MỚI, nhưng
    # trong hạn 6 giờ (_STALE_MAX) nên còn dùng làm phao cứu sinh được.
    stale_at = time.time() - 3600
    cache_store.put(key, {"at": stale_at, "data": {"daily": {"time": ["x"]}}},
                    ttl_seconds=6 * 3600)

    # Không dùng dict `realdata._CACHE` nào cả — đọc thẳng từ cache_store, đúng
    # như một tiến trình MỚI (sau restart) sẽ làm. Mạng THẬT SỰ được thử (không
    # bị chặn ở đây) nhưng trả về hỏng (429/mất mạng) — điều cần khoá chặt là
    # phần mềm KHÔNG rơi xuống None chỉ vì lần thử đó hỏng.
    monkeypatch.setattr(realdata, "_fetch", lambda u, t: None)
    assert realdata._get(url) == {"daily": {"time": ["x"]}}


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app
    return TestClient(app)


def test_health_bao_degraded_khi_can_han_muc(client, monkeypatch):
    from app.services import cache_store, realdata

    cache_store.clear_prefix("quota")
    assert client.get("/api/health").json()["status"] == "ok"

    realdata._record_429("api.open-meteo.com")
    d = client.get("/api/health").json()
    assert d["status"] == "degraded"
    assert "api.open-meteo.com" in d["quota"]["exhausted"]
    cache_store.clear_prefix("quota")
