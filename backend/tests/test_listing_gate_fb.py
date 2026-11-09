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


def test_nhan_nguoi_khong_doc_lap_ghi_ro_trong_ket_qua(tmp_path, monkeypatch):
    """9/11/2026: người gán đã xem nhãn Claude → vẫn chấm (là người), nhưng kết quả phải ghi KHÔNG ĐỘC LẬP."""
    import hashlib
    g = _gate()
    texts = {1: "Đất cao ráo, không ngập, sổ hồng thổ cư 100%", 2: "Lô đất vuông vức, đường ô tô"}
    lab = {"protocol": "terratwin.listing_gate/10", "labeler": "Chủ dự án", "labeler_kind": "human", "independent": False,
           "labels": [{"id": i, "region": "x", "sha256": hashlib.sha256(t.encode("utf-8")).hexdigest(),
                       "claims": ["high_ground", "no_flood", "residential"] if i == 1 else []} for i, t in texts.items()]}
    (tmp_path / g.RUNS["10"][0]).write_text(json.dumps(lab, ensure_ascii=False), encoding="utf-8")
    tin = tmp_path / "tin.json"
    tin.write_text(json.dumps([{"id": i, "source": "x", "text": t} for i, t in texts.items()], ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(g, "EVAL", str(tmp_path))
    monkeypatch.setattr("sys.argv", ["listing_gate_fb.py", str(tin), "--run", "10"])
    g.main()
    res = json.loads((tmp_path / g.RUNS["10"][1]).read_text(encoding="utf-8"))
    assert res["labeler_kind"] == "human" and res["labeler_independent"] is False
    assert "KHÔNG ĐỘC LẬP" in res["data_note"] and "NOT independent" in res["data_note_en"]
    assert res["passed"] is None          # 1 tin có câu đích < 8 → CHƯA KẾT LUẬN


def _strata_mod():
    spec = importlib.util.spec_from_file_location("listing_gate_strata", os.path.join(HERE, "..", "..", "ops", "listing_gate_strata.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_lan_10_f1_tung_tang_tinh_lai_duoc_tu_tep_cong_khai():
    """Review Qodo PR #8: số phụ 'F1 riêng tầng A/B' phải tính lại được từ per_listing + nhật ký chọn mẫu (khớp mã băm khoá
    7/11), KHÔNG chạy lại bộ tách câu — và khớp tệp đã công bố."""
    m = _strata_mod()
    got = m.strata("10")
    saved = json.load(open(os.path.join(m.EVAL, "listing_gate_v10_strata.json"), encoding="utf-8"))
    assert got == saved
    a, b = got["strata"]["A"], got["strata"]["B"]
    assert a["n"] + b["n"] == 29 and a["target_listings"] + b["target_listings"] == 6
    res = json.load(open(os.path.join(m.EVAL, "listing_gate_v10_result.json"), encoding="utf-8"))
    for t in ("tp", "fp", "fn"):           # cộng hai tầng = tổng của lần chấm một lần
        for row in res["per_type"]:
            assert sum(r[t] for s in (a, b) for r in s["per_type"] if r["type"] == row["type"]) == row[t]


def test_nhat_ky_chon_mau_lech_ma_bam_thi_dung(tmp_path):
    import shutil
    m = _strata_mod()
    for f in ("listing_gate_v10_result.json", "listing_gate_v10_hashes.json", "listing_gate_v10_selection.json"):
        shutil.copy(os.path.join(m.EVAL, f), tmp_path / f)
    p = tmp_path / "listing_gate_v10_selection.json"
    p.write_bytes(p.read_bytes() + b" ")
    with pytest.raises(SystemExit):
        m.strata("10", str(tmp_path))


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
