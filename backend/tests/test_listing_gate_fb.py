"""ops/listing_gate_fb.py — ai gán nhãn chấm cổng (đính chính 8/11/2026: nhãn "người" lần 6–9 là của Claude)."""
import importlib.util
import json
import os

import pytest

HERE = os.path.dirname(__file__)


def _gate():
    spec = importlib.util.spec_from_file_location("listing_gate_fb", os.path.join(HERE, "..", "..", "ops", "listing_gate_fb.py"))
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)
    return g


def test_lan_10_nhan_claude_thi_khong_cham():
    """Giao thức lần 10 đăng ký chấm trên nhãn người — nhãn Claude thì dừng trước khi ghi tệp kết quả một lần."""
    g = _gate()
    with pytest.raises(SystemExit) as e:
        g.require_human("10", "claude")
    assert "nhãn người" in str(e.value) and "'claude'" in str(e.value)


def test_lan_10_nhan_nguoi_va_lan_khac_van_cham():
    g = _gate()
    g.require_human("10", "human")
    g.require_human("9", "claude")


def test_lan_10_nhan_claude_khong_ghi_tep_ket_qua(tmp_path, monkeypatch):
    """Chạy cả main(): tệp nhãn lần 10 khai 'claude' → dừng, KHÔNG có tệp kết quả nào được ghi."""
    g = _gate()
    lab = {"labeler": "Claude", "labeler_kind": "claude", "labels": []}
    (tmp_path / g.RUNS["10"][0]).write_text(json.dumps(lab), encoding="utf-8")
    tin = tmp_path / "tin.json"
    tin.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(g, "EVAL", str(tmp_path))
    monkeypatch.setattr("sys.argv", ["listing_gate_fb.py", str(tin), "--run", "10"])
    with pytest.raises(SystemExit):
        g.main()
    assert not (tmp_path / g.RUNS["10"][1]).exists()


def test_tep_nhan_lan_4_den_9_deu_xac_dinh_duoc_nguoi_gan():
    """Tệp nhãn lần 4–5 không có labeler_kind → mặc định 'claude' (REPRODUCE.md §13); lần 6–9 tự khai 'claude'."""
    g = _gate()
    for run in ("4", "5", "6", "7", "8", "9"):
        lab = json.load(open(os.path.join(g.EVAL, g.RUNS[run][0]), encoding="utf-8"))
        assert g.labeler_kind(run, lab) == "claude"


def test_tep_nhan_khong_khai_nguoi_gan_thi_dung():
    g = _gate()
    with pytest.raises(SystemExit):
        g.labeler_kind("10", {"labels": []})
