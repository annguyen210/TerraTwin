"""SỔ MINH BẠCH — cây Merkle (RFC 6962) trên MỌI hồ sơ đã phát hành.

Sổ móc xích (dossier.py) đã chặn sửa một hồ sơ lẻ. Nhưng chính máy chủ — hay ai
chiếm được nó — vẫn có thể dựng lại TOÀN BỘ chuỗi từ một điểm và ký lại, vì khoá
nằm trên máy chủ. Certificate Transparency giải đúng bài này: công bố ĐẦU CÂY ĐÃ KÝ
(kích thước + gốc Merkle) cho bên ngoài giữ; lần sau đòi BẰNG CHỨNG NHẤT QUÁN rằng
cây mới chứa nguyên vẹn cây cũ. Viết lại lịch sử → không đưa ra được bằng chứng.

Bên ngoài ở đây là kho GitHub công khai: tác vụ .github/workflows/transparency.yml
mỗi ngày lấy đầu cây, kiểm chữ ký + bằng chứng nhất quán với đầu cây hôm trước, rồi
commit vào nhánh `transparency-log`. Muốn xoá dấu vết phải viết lại cả lịch sử Git
mà ai cũng đã sao chép — không cần blockchain, không cần token.

Lá thứ i (đếm từ 0) = leaf_hash(bytes của entry_hash hồ sơ số i+1).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import Dossier, LogHead
from app.services import merkle, signing

SCHEMA = "terratwin.sth/1"


def sth_message(size: int, root_hex: str, ts: str) -> str:
    return f"{SCHEMA}|{size}|{root_hex}|{ts}"


def size(db: Session) -> int:
    return int(db.scalar(select(func.count()).select_from(Dossier)) or 0)


def leaves(db: Session, n: int | None = None) -> list[bytes]:
    q = select(Dossier.entry_hash).order_by(Dossier.seq)
    if n is not None:
        q = q.limit(n)
    return [merkle.leaf_hash(bytes.fromhex(h)) for h in db.execute(q).scalars().all()]


def _public(h: LogHead) -> dict:
    return {"schema": SCHEMA, "tree_size": h.tree_size, "root_hash": h.root_hash, "timestamp": h.timestamp,
            "algorithm": signing.ALGORITHM, "key_id": h.key_id, "signature": h.signature}


def head(db: Session) -> dict:
    """Đầu cây hiện tại. Cùng kích thước thì trả ĐÚNG đầu cây đã ký trước đó (ổn định,
    bên giữ đầu cây so sánh được), cây lớn lên thì ký đầu cây mới."""
    n = size(db)
    h = db.get(LogHead, n)
    if h is not None:
        return _public(h)
    root_hex = merkle.root(leaves(db, n)).hex()
    ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    sig, kid = signing.sign(db, sth_message(n, root_hex, ts).encode("ascii"))
    h = LogHead(tree_size=n, root_hash=root_hex, timestamp=ts, signature=sig, key_id=kid)
    db.add(h)
    try:
        db.commit()
    except Exception:                       # hai yêu cầu cùng ký một kích thước
        db.rollback()
        h = db.get(LogHead, n)
    return _public(h)


def verify_head(db: Session, h: dict) -> bool:
    return signing.verify(db, sth_message(int(h["tree_size"]), h["root_hash"], h["timestamp"]).encode("ascii"),
                          h["signature"], h["key_id"])


def inclusion(db: Session, seq: int, tree_size: int | None = None) -> dict:
    n = tree_size or size(db)
    if not 1 <= seq <= n <= size(db):
        raise ValueError("số thứ tự hoặc kích thước cây không hợp lệ")
    lv = leaves(db, n)
    return {"seq": seq, "leaf_index": seq - 1, "tree_size": n, "leaf_hash": lv[seq - 1].hex(),
            "root_hash": merkle.root(lv).hex(), "proof": merkle.hexes(merkle.inclusion_proof(seq - 1, lv))}


def consistency(db: Session, first: int, second: int | None = None) -> dict:
    n = second or size(db)
    if not 0 < first <= n <= size(db):
        raise ValueError("kích thước cây không hợp lệ")
    lv = leaves(db, n)
    return {"first": first, "second": n, "first_root": merkle.root(lv[:first]).hex(),
            "second_root": merkle.root(lv).hex(),
            "proof": merkle.hexes(merkle.consistency_proof(first, lv))}
