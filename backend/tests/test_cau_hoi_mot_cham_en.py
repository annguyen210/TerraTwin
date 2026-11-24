"""Kiểm A–Z 24/11/2026: bản tiếng Anh vẫn hiện "Ngày 15/11 chúng tôi báo lũ/ngập sớm thửa… Có / Không / Không rõ"."""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace as NS

from app.services import onetap, reqlang


def _alert():
    return NS(id=1, module_id="flood", created_at=datetime(2026, 11, 15, 8), headline="Thửa A: Có nguy cơ ngập",
              plot_id=None, outcome=None, verify_source=None)


def test_cau_hoi_theo_ngon_ngu():
    try:
        reqlang.set_lang("en")
        q = onetap.question(_alert(), None)
        assert q["question"].startswith("On 15/11 we warned of ") and q["question"].endswith("Did it actually happen?")
        assert [o["label"] for o in q["options"]] == ["Yes", "No", "Not sure"]
        assert "Your answer" in q["why"]
        reqlang.set_lang("vi")
        q = onetap.question(_alert(), None)
        assert q["question"].startswith("Ngày 15/11 chúng tôi báo ") and [o["label"] for o in q["options"]] == ["Có", "Không", "Không rõ"]
    finally:
        reqlang.set_lang("vi")
