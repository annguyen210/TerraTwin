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


def test_lan_10_nhan_claude_khong_duoc_tinh_dat():
    """Giao thức lần 10 đăng ký chấm trên nhãn người — nhãn Claude thì CHƯA KẾT LUẬN dù F1 đạt ngưỡng."""
    g = _gate()
    res = {"macro_f1": 0.95, "passed": True}
    g.require_human(res, "10", "claude")
    assert res["passed"] is None and res["verdict"].startswith("CHƯA KẾT LUẬN") and "'claude'" in res["verdict"]


def test_lan_10_giu_ly_do_thieu_tin_dich():
    g = _gate()
    res = {"passed": None, "verdict": "CHƯA KẾT LUẬN — chỉ 5 tin có câu không ngập / cao ráo"}
    g.require_human(res, "10", "claude")
    assert "nhãn người" in res["verdict"] and "chỉ 5 tin" in res["verdict"]


def test_lan_10_nhan_nguoi_va_lan_khac_giu_nguyen():
    g = _gate()
    for run, kind in (("10", "human"), ("9", "claude")):
        res = {"passed": True}
        g.require_human(res, run, kind)
        assert res == {"passed": True}


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
