"""CHẤM kiểm thực địa bộ phát hiện đợt nước — đúng giao thức backend/data/eval/water_field_protocol.json, MỘT lần.

    cd backend && python ../ops/water_field_gate.py            # xem tiến độ; đủ cỡ mẫu thì chấm và ghi kết quả
    cd backend && python ../ops/water_field_gate.py --status   # chỉ xem tiến độ, không bao giờ ghi

Đọc CSDL theo DATABASE_URL (như các script ops khác). Chưa đủ cỡ mẫu tối thiểu → không chấm, không ghi gì.
Đã có data/eval/water_field_result.json → từ chối chấm lại (muốn chấm nữa phải đăng ký giao thức mới).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))

from app.db import SessionLocal, init_db  # noqa: E402
from app.services import field_truth  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Chấm kiểm thực địa bộ phát hiện đợt nước (một lần)")
    ap.add_argument("--status", action="store_true", help="chỉ xem tiến độ")
    a = ap.parse_args(argv)
    init_db()
    with SessionLocal() as db:
        st = field_truth.status(db)
        print("Tiến độ:", ", ".join(f"{k} {st['have'][k]}/{st['need'][k]}" for k in st["have"]))
        if st["result"]:
            print("ĐÃ CHẤM ngày", st["result"].get("scored_at"), "→", st["result"].get("outcome"), "— không chấm lại.")
            return 0
        if a.status or not st["ready"]:
            print("Chưa chấm." + ("" if st["ready"] else " Chưa đủ cỡ mẫu tối thiểu."))
            return 0
        res = {**field_truth.score(db), "scored_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    with open(field_truth.RESULT, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(f"CHẤM: P = {res['precision']} (Wilson 95% {res['wilson95']}) trên {res['sample']['labelled_events']} đợt → {res['outcome']}")
    print("Đã ghi", os.path.relpath(field_truth.RESULT), "— commit tệp này để công bố.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
