#!/usr/bin/env python3
"""NEO ĐẦU CÂY VÀO BITCOIN BẰNG OPENTIMESTAMPS — chạy bởi .github/workflows/transparency.yml.

Sau khi nhân chứng (translog_witness.py) ghi đầu cây mới vào heads.jsonl:
  1. Ghi đúng chuỗi đầu cây đã ký ra sth/<kích thước>.txt (không xuống dòng) — thứ được băm và neo.
  2. Gửi SHA-256 của tệp đó (kèm nonce ngẫu nhiên, như ots-client) lên các máy chủ lịch
     OpenTimestamps công cộng → sth/<kích thước>.txt.ots (đang chờ).
  3. Mọi tệp .ots còn chờ: hỏi lại máy chủ lịch; khi giao dịch Bitcoin được đào, bằng chứng nhận
     chứng thực khối → kiểm ngay gốc Merkle với trình duyệt khối công khai.
  4. Ghi mục lục anchors.json (máy chủ TerraTwin đọc để hiện trạng thái neo trên trang kiểm chứng).

Chỉ cần `pip install opentimestamps` (thư viện lõi; không cần nút Bitcoin, không cần ví).

    python3 ops/ots_anchor.py <thư mục worktree nhánh transparency-log>
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from verify_dossier import verify_ots  # noqa: E402 — cùng thư mục ops/

CALENDARS = ["https://a.pool.opentimestamps.org", "https://b.pool.opentimestamps.org",
             "https://a.pool.eternitywall.com", "https://ots.btc.catallaxy.com"]
MIN_CALENDARS = 2


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def stamp(data: bytes) -> bytes | None:
    """Tạo bằng chứng OpenTimestamps (đang chờ) cho `data`. Trả bytes tệp .ots, None nếu < 2 lịch nhận."""
    from opentimestamps.calendar import RemoteCalendar
    from opentimestamps.core.op import OpAppend, OpSHA256
    from opentimestamps.core.serialize import StreamSerializationContext
    from opentimestamps.core.timestamp import DetachedTimestampFile, Timestamp

    dtf = DetachedTimestampFile(OpSHA256(), Timestamp(hashlib.sha256(data).digest()))
    tip = dtf.timestamp.ops.add(OpAppend(os.urandom(16))).ops.add(OpSHA256())
    ok = 0
    for url in CALENDARS:
        try:
            tip.merge(RemoteCalendar(url, user_agent="terratwin-anchor/1").submit(tip.msg, timeout=20))
            ok += 1
        except Exception as e:  # noqa: BLE001 — một lịch hỏng không chặn các lịch khác
            print(f"::warning::Lịch {url} không nhận: {e}")
    if ok < MIN_CALENDARS:
        return None
    buf = io.BytesIO()
    dtf.serialize(StreamSerializationContext(buf))
    return buf.getvalue()


def upgrade(ots: bytes) -> tuple[bytes, bool]:
    """Hỏi lại các máy chủ lịch cho mọi chứng thực đang chờ. Trả (bytes mới, có đổi không)."""
    from opentimestamps.calendar import CommitmentNotFoundError, RemoteCalendar
    from opentimestamps.core.notary import BitcoinBlockHeaderAttestation, PendingAttestation
    from opentimestamps.core.serialize import StreamDeserializationContext, StreamSerializationContext
    from opentimestamps.core.timestamp import DetachedTimestampFile

    dtf = DetachedTimestampFile.deserialize(StreamDeserializationContext(io.BytesIO(ots)))
    if any(isinstance(a, BitcoinBlockHeaderAttestation) for _, a in dtf.timestamp.all_attestations()):
        return ots, False

    def leaves(st):
        if st.attestations:
            yield st
        for sub in st.ops.values():
            yield from leaves(sub)

    changed = False
    for st in list(leaves(dtf.timestamp)):
        for att in list(st.attestations):
            if not isinstance(att, PendingAttestation) or att.uri not in CALENDARS:
                continue                   # chỉ hỏi máy chủ lịch trong danh sách tin cậy
            try:
                st.merge(RemoteCalendar(att.uri, user_agent="terratwin-anchor/1").get_timestamp(st.msg, timeout=20))
                changed = True
            except CommitmentNotFoundError:
                pass                       # chưa vào khối — lần sau hỏi lại
            except Exception as e:  # noqa: BLE001
                print(f"::warning::Lịch {att.uri}: {e}")
    if not changed:
        return ots, False
    buf = io.BytesIO()
    dtf.serialize(StreamSerializationContext(buf))
    return buf.getvalue(), True


def main(tlog: str) -> None:
    heads_path = os.path.join(tlog, "heads.jsonl")
    sth_dir = os.path.join(tlog, "sth")
    os.makedirs(sth_dir, exist_ok=True)
    idx_path = os.path.join(tlog, "anchors.json")
    old, before = {}, None
    if os.path.exists(idx_path):
        before = json.load(open(idx_path, encoding="utf-8")).get("anchors", [])
        old = {int(a["tree_size"]): a for a in before}

    if os.path.exists(heads_path):
        lines = [ln for ln in open(heads_path, encoding="utf-8").read().splitlines() if ln.strip()]
        if lines:
            h = json.loads(lines[-1])
            n = int(h["tree_size"])
            txt = os.path.join(sth_dir, f"{n}.txt")
            if n > 0 and not os.path.exists(txt + ".ots"):
                msg = f"{h['schema']}|{n}|{h['root_hash']}|{h['timestamp']}".encode("ascii")
                ots = stamp(msg)
                if ots is None:
                    print("::warning::Chưa neo được (ít hơn 2 máy chủ lịch nhận) — lần chạy sau thử lại.")
                else:
                    open(txt, "wb").write(msg)
                    open(txt + ".ots", "wb").write(ots)
                    old[n] = {"tree_size": n, "submitted_at": now()}
                    print(f"Đã gửi neo cây {n} ({h['root_hash'][:16]}…)")

    anchors = []
    for name in sorted(os.listdir(sth_dir)):
        if not name.endswith(".txt.ots"):
            continue
        n = int(name.split(".")[0])
        txt = os.path.join(sth_dir, f"{n}.txt")
        data = open(txt, "rb").read()
        ots_path = txt + ".ots"
        a = dict(old.get(n, {"tree_size": n}))
        if a.get("status") != "confirmed":
            new, changed = upgrade(open(ots_path, "rb").read())
            if changed:
                open(ots_path, "wb").write(new)
            r = verify_ots(open(ots_path, "rb").read(), data)
            if r["status"] == "invalid":
                print(f"::error::Bằng chứng neo cây {n} KHÔNG hợp lệ: {r.get('why')}")
                sys.exit(1)
            a["status"] = "confirmed" if r["status"] == "confirmed" else "pending"
            for k in ("bitcoin_height", "bitcoin_time", "explorer"):
                if r.get(k) is not None:
                    a[k] = r[k]
            if a["status"] == "confirmed":
                a["confirmed_checked_at"] = now()
                print(f"Cây {n}: đã vào khối Bitcoin #{a['bitcoin_height']} ({a['bitcoin_time']})")
        schema, size, root, ts = data.decode("ascii").split("|")
        a.update(tree_size=n, root_hash=root, sth_timestamp=ts, file=f"sth/{n}.txt", ots=f"sth/{n}.txt.ots",
                 digest_sha256=hashlib.sha256(data).hexdigest())
        anchors.append(a)

    if anchors == before:
        print(f"anchors.json không đổi ({len(anchors)} lần neo).")   # không commit rác mỗi lượt chạy
        return
    json.dump({"schema": "terratwin.anchors/1", "updated": now(),
               "how_to_verify": "ots verify sth/<n>.txt.ots (hoặc tải cả hai tệp lên https://opentimestamps.org); "
                                "python ops/verify_dossier.py <mã hồ sơ> kiểm luôn hồ sơ nằm trong gốc cây đã neo.",
               "anchors": anchors}, open(idx_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"anchors.json: {len(anchors)} lần neo, {sum(a.get('status') == 'confirmed' for a in anchors)} đã vào Bitcoin.")


if __name__ == "__main__":
    main(sys.argv[1])
