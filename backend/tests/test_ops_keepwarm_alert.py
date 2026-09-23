"""N11 — báo Telegram khi keepwarm phát hiện health đổi trạng thái.

Không chạm mạng: fetch_health/notify_telegram luôn được monkeypatch. Trọng
tâm kiểm là logic ĐỔI TRẠNG THÁI (chỉ báo khi khác lần trước) và việc thiếu
secret phải bỏ qua ÊM chứ không làm hỏng gì.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "ops" / "keepwarm_alert.py"

spec = importlib.util.spec_from_file_location("keepwarm_alert", MODULE_PATH)
keepwarm_alert = importlib.util.module_from_spec(spec)
sys.modules["keepwarm_alert"] = keepwarm_alert
spec.loader.exec_module(keepwarm_alert)


def test_classify_trang_thai():
    assert keepwarm_alert.classify({"status": "ok"}) == "ok"
    assert keepwarm_alert.classify({"status": "degraded"}) == "degraded"
    assert keepwarm_alert.classify({"status": "gi-do-la"}) == "broken"
    assert keepwarm_alert.classify(None) == "broken"
    assert keepwarm_alert.classify({}) == "broken"


def test_lan_dau_khong_bao_chi_ghi_nhan(tmp_path, monkeypatch):
    state_file = tmp_path / "state.txt"
    sent = []
    monkeypatch.setattr(keepwarm_alert, "fetch_health", lambda url, timeout=30.0: {"status": "ok"})
    monkeypatch.setattr(keepwarm_alert, "notify_telegram",
                        lambda token, chat_id, text, timeout=15.0: sent.append(text) or True)

    cur = keepwarm_alert.run("http://fake/health", str(state_file), "tok", "chat")
    assert cur == "ok"
    assert sent == [], "lần đầu chưa có trạng thái trước đó — không được báo"
    assert state_file.read_text(encoding="utf-8") == "ok"


def test_doi_trang_thai_thi_bao(tmp_path, monkeypatch):
    state_file = tmp_path / "state.txt"
    state_file.write_text("ok", encoding="utf-8")
    sent = []
    monkeypatch.setattr(keepwarm_alert, "fetch_health", lambda url, timeout=30.0: None)  # → broken
    monkeypatch.setattr(keepwarm_alert, "notify_telegram",
                        lambda token, chat_id, text, timeout=15.0: sent.append((chat_id, text)) or True)

    cur = keepwarm_alert.run("http://fake/health", str(state_file), "tok", "chat")
    assert cur == "broken"
    assert len(sent) == 1
    assert sent[0][0] == "chat"
    assert "ok → broken" in sent[0][1]
    assert state_file.read_text(encoding="utf-8") == "broken"


def test_khong_doi_trang_thai_thi_khong_bao(tmp_path, monkeypatch):
    state_file = tmp_path / "state.txt"
    state_file.write_text("degraded", encoding="utf-8")
    sent = []
    monkeypatch.setattr(keepwarm_alert, "fetch_health", lambda url, timeout=30.0: {"status": "degraded"})
    monkeypatch.setattr(keepwarm_alert, "notify_telegram",
                        lambda token, chat_id, text, timeout=15.0: sent.append(text) or True)

    cur = keepwarm_alert.run("http://fake/health", str(state_file), "tok", "chat")
    assert cur == "degraded"
    assert sent == []


def test_thieu_secret_thi_bo_qua_em_khong_goi_mang(tmp_path, monkeypatch):
    """BẮT BUỘC: thiếu token/chat_id thì notify_telegram không được GỌI —
    nếu gọi với token=None sẽ tạo URL 'https://api.telegram.org/botNone/...'
    và request thật ra ngoài, sai hoàn toàn tinh thần 'bỏ qua êm'."""
    state_file = tmp_path / "state.txt"
    state_file.write_text("ok", encoding="utf-8")
    called = []
    monkeypatch.setattr(keepwarm_alert, "fetch_health", lambda url, timeout=30.0: None)  # → broken
    monkeypatch.setattr(keepwarm_alert, "notify_telegram",
                        lambda *a, **k: called.append(1) or True)

    cur = keepwarm_alert.run("http://fake/health", str(state_file), None, None)
    assert cur == "broken", "vẫn phải ghi nhận trạng thái mới dù không báo được"
    assert called == [], "thiếu secret thì KHÔNG được gọi notify_telegram"


def test_gui_telegram_that_bai_khong_lam_hong_run(tmp_path, monkeypatch):
    """Telegram lỗi (API sập, token sai...) không được ném exception ra ngoài —
    N11 không được làm hỏng cron keepwarm vốn có việc quan trọng hơn."""
    state_file = tmp_path / "state.txt"
    state_file.write_text("ok", encoding="utf-8")
    monkeypatch.setattr(keepwarm_alert, "fetch_health", lambda url, timeout=30.0: None)
    monkeypatch.setattr(keepwarm_alert, "notify_telegram",
                        lambda *a, **k: False)  # giả lập gửi thất bại

    cur = keepwarm_alert.run("http://fake/health", str(state_file), "tok", "chat")
    assert cur == "broken"
    assert state_file.read_text(encoding="utf-8") == "broken"


def test_notify_telegram_that_that_bat_moi_loi(monkeypatch):
    """notify_telegram thật (không mock) phải nuốt lỗi mạng, không ném ra."""
    import urllib.request

    def boom(*a, **k):
        raise OSError("mang hong roi")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert keepwarm_alert.notify_telegram("tok", "chat", "test") is False


def test_fetch_health_that_bat_moi_loi(monkeypatch):
    import urllib.request

    def boom(*a, **k):
        raise OSError("mang hong roi")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert keepwarm_alert.fetch_health("http://fake") is None
