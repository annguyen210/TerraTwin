"""26/11/2026 — bản đồ công nghệ phải TRUNG THỰC: đủ mục, mỗi mục có lý do, tệp mã được dẫn phải tồn tại thật."""
from __future__ import annotations

import glob
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
D = json.loads((ROOT / "backend" / "data" / "tech_map.json").read_text(encoding="utf-8"))
PATH = re.compile(r"((?:backend/|frontend/|ops/|app/|services/|components/|lib/|public/|data/|tests/|\.github/)[\w./*-]+\.(?:py|tsx?|js|json|yml|onnx|md))")


def test_du_muc_va_co_ly_do():
    assert len(D["items"]) == 413
    assert all(x["status"] in ("used", "platform", "no") and len(x["note"]) > 15 for x in D["items"])
    assert sum(D["counts"].values()) == 413


def test_tep_duoc_dan_ton_tai():
    missing = []
    for x in D["items"]:
        for ref in PATH.findall(x["note"]):
            cands = [ROOT / ref, ROOT / "backend" / ref, ROOT / "backend" / "app" / ref, ROOT / "frontend" / ref]
            if "*" in ref:
                ok = any(glob.glob(str(c)) for c in cands)
            else:
                ok = any(c.exists() for c in cands)
            if not ok:
                missing.append((x["item"], ref))
    assert not missing, missing
