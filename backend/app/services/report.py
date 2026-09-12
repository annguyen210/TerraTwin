"""A9/G1 — KÝ BÁO CÁO bằng mã băm để bên nhận tự kiểm bản in không bị sửa.

Tờ trình rủi ro thửa đất là thứ đưa cho ngân hàng (thẩm định vay), bảo hiểm, hay
người mua đất. Một bản in không có gì chứng minh nó chưa bị chỉnh sửa thì vô giá
trị với những bên đó. Băm SHA-256 nội dung chuẩn hoá + đóng dấu thời gian máy
chủ: bên nhận băm lại đúng các trường in ra và so — khớp là bản gốc.

Dùng lại đúng cơ chế của mrv.py: JSON gọn (sort_keys, không khoảng trắng) →
sha256. Chữ ký này chứng minh TÍNH TOÀN VẸN (chưa bị sửa sau khi ký), không phải
tính đúng của số liệu — số liệu đã có sổ điểm và nhãn 🛰️/🧪 lo.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

_META = ("hash", "short", "verify_note")


def _canonical(facts: dict) -> str:
    return json.dumps(facts, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


def sign(facts: dict) -> dict:
    """Đóng dấu thời gian + băm. Trả lại chính facts kèm hash/short/verify_note."""
    body = {k: v for k, v in facts.items() if k not in _META}
    body["signed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    digest = hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()
    return {**body, "hash": digest, "short": digest[:16],
            "verify_note": ("Băm lại (SHA-256) chuỗi JSON gọn — khóa sắp xếp, "
                            "không khoảng trắng — của mọi trường trừ hash/short/"
                            "verify_note. Khớp = bản in chưa bị sửa.")}


def verify(report: dict) -> dict:
    """Kiểm một báo cáo đã ký còn nguyên vẹn hay đã bị sửa sau khi lập."""
    given = str(report.get("hash", ""))
    body = {k: v for k, v in report.items() if k not in _META}
    actual = hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()
    return {"valid": bool(given) and actual == given,
            "expected": actual, "given": given,
            "message": ("Bản in KHỚP mã băm — chưa bị sửa." if actual == given
                        else "KHÔNG khớp — nội dung đã bị thay đổi sau khi ký.")}
