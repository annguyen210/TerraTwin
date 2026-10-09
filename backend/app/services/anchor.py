"""GĐ4 · NĂNG LỰC 3 — NEO GỐC CÂY VÀO BITCOIN BẰNG OPENTIMESTAMPS.

Sổ minh bạch (translog.py) + nhân chứng GitHub đã chặn SỬA/XOÁ hồ sơ cũ. Còn một kẽ hở: chủ
hệ thống vẫn có thể dựng một hồ sơ hôm nay rồi ghi "phát hành từ tháng trước" — miễn là chưa
có đầu cây nào sau thời điểm đó được người ngoài lưu. OpenTimestamps đóng kẽ hở này: mỗi ngày
tác vụ .github/workflows/transparency.yml gửi mã băm của đầu cây đã ký lên các máy chủ lịch
OpenTimestamps (miễn phí); chúng gom lại và ghi vào một giao dịch Bitcoin. Từ lúc khối đó được
đào, KHÔNG AI — kể cả TerraTwin — chứng minh được rằng gốc cây đó ra đời muộn hơn.

Kết quả neo nằm trên nhánh `transparency-log` của kho công khai:
    sth/<kích thước cây>.txt       — đúng chuỗi đầu cây đã ký (thứ được băm và neo)
    sth/<kích thước cây>.txt.ots   — bằng chứng OpenTimestamps (kiểm bằng `ots verify` hoặc
                                     opentimestamps.org, không cần tin TerraTwin)
    anchors.json                   — mục lục cho máy đọc: trạng thái từng lần neo

Ở đây chỉ ĐỌC mục lục đó và chứng minh hồ sơ #seq nằm trong cây đã neo: bằng chứng bao hàm
(inclusion proof) từ lá của hồ sơ lên đúng gốc cây đã neo.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.request

from sqlalchemy.orm import Session

from app.services import translog

REPO_RAW = "https://raw.githubusercontent.com/annguyen210/TerraTwin/transparency-log"
BRANCH_URL = "https://github.com/annguyen210/TerraTwin/tree/transparency-log"
TTL_S = 3600

_lock = threading.Lock()
_memo: dict = {"at": 0.0, "anchors": None}


def _url() -> str | None:
    u = os.environ.get("TERRATWIN_ANCHORS_URL", f"{REPO_RAW}/anchors.json").strip()
    return None if u.lower() in ("", "0", "off", "none") else u


def load(force: bool = False) -> list[dict] | None:
    """Mục lục neo (cache 1 giờ trong bộ nhớ). Lỗi mạng → trả bản cũ nếu có, không thì None."""
    url = _url()
    if url is None:
        return None
    with _lock:
        if not force and _memo["anchors"] is not None and time.time() - _memo["at"] < TTL_S:
            return _memo["anchors"]
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "terratwin-anchor/1"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode("utf-8"))
        anchors = sorted((a for a in data.get("anchors", []) if isinstance(a, dict) and a.get("tree_size")),
                         key=lambda a: int(a["tree_size"]))
    except Exception:
        with _lock:
            _memo["at"] = time.time() - TTL_S + 300      # thử lại sau 5 phút, đừng gọi mỗi lượt xem
            return _memo["anchors"]
    with _lock:
        _memo.update(at=time.time(), anchors=anchors)
    return anchors


def clear_cache() -> None:
    with _lock:
        _memo.update(at=0.0, anchors=None)


def for_seq(db: Session, seq: int) -> dict | None:
    """Trạng thái neo của hồ sơ số `seq`.

    status:
      confirmed      — nằm trong một gốc cây đã ghi vào khối Bitcoin (có số khối, thời điểm)
      pending        — đã gửi lên OpenTimestamps, chờ Bitcoin xác nhận (thường vài giờ)
      not_yet        — phát hành sau lần neo gần nhất; lần neo hằng ngày tới sẽ bao gồm
      root_mismatch  — gốc cây đã neo KHÔNG khớp sổ hiện tại → sổ đã bị viết lại. Báo đỏ.
      unavailable    — chưa đọc được mục lục neo (mạng) — không kết luận gì
    """
    anchors = load()
    if anchors is None:
        return None if _url() is None else {"status": "unavailable", "branch": BRANCH_URL}
    size = translog.size(db)
    covering = [a for a in anchors if seq <= int(a["tree_size"]) <= size]
    if not covering:
        return {"status": "not_yet", "branch": BRANCH_URL,
                "latest_anchor_size": int(anchors[-1]["tree_size"]) if anchors else None}
    pick = next((a for a in covering if a.get("status") == "confirmed"), covering[0])
    inc = translog.inclusion(db, seq, int(pick["tree_size"]))
    ok = inc["root_hash"] == pick.get("root_hash")
    return {
        "status": pick.get("status", "pending") if ok else "root_mismatch",
        "tree_size": int(pick["tree_size"]), "root_hash": pick.get("root_hash"),
        "sth_timestamp": pick.get("sth_timestamp"), "submitted_at": pick.get("submitted_at"),
        "bitcoin_height": pick.get("bitcoin_height"), "bitcoin_time": pick.get("bitcoin_time"),
        "leaf_index": inc["leaf_index"], "leaf_hash": inc["leaf_hash"], "proof": inc["proof"],
        "sth_url": f"{REPO_RAW}/{pick['file']}" if pick.get("file") else None,
        "ots_url": f"{REPO_RAW}/{pick['ots']}" if pick.get("ots") else None,
        "branch": BRANCH_URL,
    }
