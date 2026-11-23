"""Kiểm Chrome 23/11/2026 (main 24f19f1): (1) /hom-nay hiện 2 dòng trùng hệt cùng thửa, cùng câu, cùng phút; (2) công cụ
carbon hiện nhãn mất dấu "khung xet ha" — khoá metrics chưa có nhãn ở giao diện."""
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.db import Alert, Plot, SessionLocal, User
from app.services import plot_journal

ROOT = Path(__file__).resolve().parents[2]


def test_nhat_ky_gop_dong_trung_cung_thua_cung_cau_cung_phut():
    now = datetime.now(timezone.utc).replace(tzinfo=None).replace(second=10, microsecond=0)
    with SessionLocal() as s:
        u = User(email="nk-trung@vd.vn", password_hash="x", name="A")
        s.add(u)
        s.commit()
        p = Plot(user_id=u.id, name="Bảo Lộc", lat=11.55, lon=107.8)
        s.add(p)
        s.commit()
        head = "Bảo Lộc: Bê tông hoá 69.5% — cùng trận mưa 16.8 mm"
        for sec in (10, 40):                                   # cùng phút, hai bản ghi
            s.add(Alert(user_id=u.id, plot_id=p.id, module_id="urban", risk_level="warning", headline=head,
                        created_at=now.replace(second=sec)))
        s.add(Alert(user_id=u.id, plot_id=p.id, module_id="urban", risk_level="warning", headline=head,
                    created_at=now + timedelta(minutes=5)))      # phút khác → vẫn là một dòng riêng
        s.commit()
        ev = [e for e in plot_journal._db_events(s, u.id, p, now - timedelta(hours=1)) if e["kind"] == "alert"]
    assert len(ev) == 2


def test_moi_khoa_so_do_deu_co_nhan_o_giao_dien():
    keys = set()
    for f in list((ROOT / "backend/app/modules").glob("*.py")) + list((ROOT / "backend/app/services").glob("*.py")):
        src = f.read_text(encoding="utf-8")
        for m in re.finditer(r"metrics\s*=\s*\{(.*?)\}", src, re.S):
            keys |= set(re.findall(r"[\"']([a-z][a-z0-9_]*)[\"']\s*:", m.group(1)))
        keys |= set(re.findall(r"metrics\[\s*[\"']([a-z][a-z0-9_]*)[\"']\s*\]\s*=", src))
    panel = (ROOT / "frontend/components/ResultsPanel.tsx").read_text(encoding="utf-8")
    have = set(re.findall(r"^\s*([a-z][a-z0-9_]*)\s*:\s*\[\"", panel, re.M))
    assert "khung_xet_ha" in keys and not sorted(keys - have), sorted(keys - have)
