#!/usr/bin/env python3
"""KIỂM ĐỘC LẬP MỘT HỒ SƠ TERRATWIN — không cần tin máy chủ, không import mã của TerraTwin.

Một tệp duy nhất, chỉ cần Python 3.10+ và `pip install cryptography` (thêm `opentimestamps` nếu
muốn tự kiểm luôn neo Bitcoin). Ngân hàng, công chứng viên, nhà báo tải tệp này về là kiểm được:

  1. NỘI DUNG  — SHA-256 của chuỗi nội dung đã ký = facts_hash; nội dung hiển thị = nội dung đã ký.
  2. MỤC SỔ    — SHA-256("terratwin.dossier/1|seq|id|issued_at|facts_hash|prev_hash") = entry_hash.
  3. CHỮ KÝ    — Ed25519 trên entry_hash, bằng khoá công khai lấy từ /api/dossiers/keys.
  4. SỔ MINH BẠCH — bằng chứng bao hàm (RFC 9162 §2.1.3.2) từ lá của hồ sơ lên gốc Merkle của đầu
                 cây đã ký (chữ ký đầu cây cũng được kiểm).
  5. NEO BITCOIN (nếu đã neo) — đọc mục lục neo THẲNG từ nhánh transparency-log trên GitHub (không qua
                 máy chủ TerraTwin), kiểm hồ sơ nằm trong gốc cây đã neo, rồi kiểm bằng chứng
                 OpenTimestamps tới gốc Merkle của khối Bitcoin (so với một trình duyệt khối công khai).

    python ops/verify_dossier.py <mã hồ sơ | https://…/h/<mã>>      # kiểm trực tuyến
    python ops/verify_dossier.py --file terratwin-ho-so-<mã>.json      # kiểm tệp đã tải (1–3 chạy offline)

Thoát mã 0 khi mọi phép kiểm bắt buộc đạt, 1 khi có phép kiểm hỏng (in rõ phép nào).
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import sys
import urllib.request

API = os.environ.get("TERRATWIN_API", "https://terratwin-api.onrender.com")
ANCHORS = "https://raw.githubusercontent.com/annguyen210/TerraTwin/transparency-log"
EXPLORERS = ("https://blockstream.info/api", "https://mempool.space/api")


# ------------------------------------------------------------------ tiện ích

def get(url: str, raw: bool = False, timeout: int = 60):
    req = urllib.request.Request(url, headers={"User-Agent": "terratwin-verify/1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        b = r.read()
    return b if raw else json.loads(b.decode("utf-8"))


def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def ed25519_ok(pub_b64: str, sig_b64: str, msg: bytes) -> bool:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(pub_b64)).verify(base64.b64decode(sig_b64), msg)
        return True
    except (InvalidSignature, ValueError):
        return False


def _node(l: bytes, r: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + l + r).digest()


def leaf_of(entry_hash_hex: str) -> bytes:
    return hashlib.sha256(b"\x00" + bytes.fromhex(entry_hash_hex)).digest()


def verify_inclusion(leaf: bytes, index: int, size: int, proof: list[bytes], root: bytes) -> bool:
    """RFC 9162 §2.1.3.2 — viết lại độc lập, không dùng mã máy chủ."""
    if not 0 <= index < size:
        return False
    fn, sn, r = index, size - 1, leaf
    for p in proof:
        if sn == 0:
            return False
        if fn & 1 or fn == sn:
            r = _node(p, r)
            if not fn & 1:
                while True:
                    fn >>= 1
                    sn >>= 1
                    if fn & 1 or fn == 0:
                        break
        else:
            r = _node(r, p)
        fn >>= 1
        sn >>= 1
    return sn == 0 and r == root


def sth_message(h: dict) -> str:
    return f"{h.get('schema', 'terratwin.sth/1')}|{h['tree_size']}|{h['root_hash']}|{h['timestamp']}"


def verify_ots(ots_bytes: bytes, data: bytes) -> dict:
    """Kiểm một bằng chứng OpenTimestamps cho `data`. Cần `pip install opentimestamps`.

    Trả {status: confirmed|pending|invalid|no_library, bitcoin_height, bitcoin_time, explorer}.
    confirmed = có chứng thực khối Bitcoin VÀ gốc Merkle giao dịch tính từ bằng chứng khớp đầu khối
    do trình duyệt khối công khai trả (thứ tự byte đảo, như Bitcoin hiển thị)."""
    try:
        from opentimestamps.core.notary import BitcoinBlockHeaderAttestation, PendingAttestation
        from opentimestamps.core.serialize import StreamDeserializationContext
        from opentimestamps.core.timestamp import DetachedTimestampFile
    except ImportError:
        return {"status": "no_library"}
    try:
        d = DetachedTimestampFile.deserialize(StreamDeserializationContext(io.BytesIO(ots_bytes)))
    except Exception as e:  # noqa: BLE001 — tệp hỏng là kết quả kiểm, không phải lỗi chương trình
        return {"status": "invalid", "why": f"tệp .ots hỏng: {e}"}
    if d.file_digest != hashlib.sha256(data).digest():
        return {"status": "invalid", "why": "bằng chứng .ots không phải của tệp này (lệch SHA-256)"}
    btc = sorted(((a.height, msg) for msg, a in d.timestamp.all_attestations()
                  if isinstance(a, BitcoinBlockHeaderAttestation)), key=lambda x: x[0])
    if not btc:
        pend = [a.uri for _, a in d.timestamp.all_attestations() if isinstance(a, PendingAttestation)]
        return {"status": "pending", "calendars": pend}
    height, msg = btc[0]
    for ex in EXPLORERS:
        try:
            bh = get(f"{ex}/block-height/{height}", raw=True, timeout=20).decode().strip()
            b = get(f"{ex}/block/{bh}", timeout=20)
        except Exception:  # noqa: BLE001 — thử trình duyệt khối kế tiếp
            continue
        from datetime import datetime, timezone
        when = datetime.fromtimestamp(int(b["timestamp"]), timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        if msg[::-1].hex() != b["merkle_root"]:
            return {"status": "invalid", "why": f"gốc Merkle khối {height} không khớp bằng chứng", "explorer": ex}
        return {"status": "confirmed", "bitcoin_height": height, "bitcoin_time": when, "explorer": ex}
    return {"status": "confirmed_unchecked", "bitcoin_height": height,
            "why": "không gọi được trình duyệt khối nào để đối chiếu đầu khối"}


# ------------------------------------------------------------------ kiểm

class Report:
    def __init__(self) -> None:
        self.fail = 0

    def line(self, ok: bool | None, msg: str) -> None:
        mark = {True: "ĐẠT ", False: "HỎNG", None: "BỎ QUA"}[ok]
        print(f"  [{mark}] {msg}")
        self.fail += ok is False


def check_document(doc: dict, keys: dict[str, str] | None, rep: Report) -> None:
    p = doc["proof"]
    canon = doc.get("facts_canonical")
    if canon is None:
        canon = canonical(doc["facts"])
    rep.line(sha256_hex(canon) == p["facts_hash"], "1. Nội dung khớp mã băm đã ký (facts_hash)")
    if "facts" in doc and doc.get("facts_canonical") is not None:
        rep.line(json.loads(doc["facts_canonical"]) == doc["facts"],
                 "   Nội dung hiển thị trùng nội dung đã ký (không ai sửa phần 'facts')")
    msg = f"{p.get('schema', 'terratwin.dossier/1')}|{doc['seq']}|{doc['id']}|{doc['issued_at']}|{p['facts_hash']}|{p['prev_hash']}"
    rep.line(sha256_hex(msg) == p["entry_hash"], "2. Mục sổ (số thứ tự, mã, thời điểm, móc xích) khớp entry_hash")
    pub = (keys or {}).get(p["key_id"])
    if keys is not None and pub is None:
        rep.line(False, f"3. Khoá {p['key_id']} KHÔNG có trong danh sách khoá công khai của TerraTwin")
        return
    if pub is None:
        pub = p.get("public_key_b64")
        src = "khoá đi kèm tệp (offline — nên đối chiếu key_id với /api/dossiers/keys khi có mạng)"
    else:
        src = "khoá công khai từ /api/dossiers/keys"
        if p.get("public_key_b64") and p["public_key_b64"] != pub:
            rep.line(False, "   Khoá đi kèm tệp KHÁC khoá công khai của TerraTwin")
    rep.line(bool(pub) and ed25519_ok(pub, p["signature"], p["entry_hash"].encode("ascii")),
             f"3. Chữ ký Ed25519 hợp lệ — {src}")


def check_log(api: str, doc: dict, keys: dict[str, str], rep: Report) -> None:
    head = get(f"{api}/api/log/sth")
    hk = keys.get(head["key_id"])
    rep.line(bool(hk) and ed25519_ok(hk, head["signature"], sth_message(head).encode("ascii")),
             f"4. Đầu cây đã ký hợp lệ (cây {head['tree_size']} hồ sơ, {head['timestamp']})")
    inc = get(f"{api}/api/log/inclusion?seq={doc['seq']}&tree_size={head['tree_size']}")
    ok = verify_inclusion(leaf_of(doc["proof"]["entry_hash"]), doc["seq"] - 1, int(head["tree_size"]),
                          [bytes.fromhex(x) for x in inc["proof"]], bytes.fromhex(head["root_hash"]))
    rep.line(ok, f"   Bằng chứng bao hàm: hồ sơ là lá #{doc['seq']} của cây đó ({len(inc['proof'])} mã băm)")


def check_anchor(api: str, doc: dict, rep: Report) -> None:
    try:
        idx = get(f"{ANCHORS}/anchors.json")
    except Exception:  # noqa: BLE001
        rep.line(None, "5. Chưa có mục lục neo trên nhánh transparency-log")
        return
    seq = int(doc["seq"])
    cov = sorted((a for a in idx.get("anchors", []) if int(a["tree_size"]) >= seq), key=lambda a: int(a["tree_size"]))
    if not cov:
        rep.line(None, "5. Hồ sơ phát hành sau lần neo gần nhất — lần neo hằng ngày tới sẽ bao gồm")
        return
    a = next((x for x in cov if x.get("status") == "confirmed"), cov[0])
    sth_txt = get(f"{ANCHORS}/{a['file']}", raw=True)
    parts = sth_txt.decode("ascii").split("|")
    rep.line(parts[1] == str(a["tree_size"]) and parts[2] == a["root_hash"],
             f"5. Tệp đầu cây đã neo ({a['file']}) khớp mục lục neo")
    inc = get(f"{api}/api/log/inclusion?seq={seq}&tree_size={a['tree_size']}")
    rep.line(verify_inclusion(leaf_of(doc["proof"]["entry_hash"]), seq - 1, int(a["tree_size"]),
                              [bytes.fromhex(x) for x in inc["proof"]], bytes.fromhex(parts[2])),
             f"   Hồ sơ nằm trong gốc cây đã neo (cây {a['tree_size']} hồ sơ)")
    r = verify_ots(get(f"{ANCHORS}/{a['ots']}", raw=True), sth_txt)
    if r["status"] == "confirmed":
        rep.line(True, f"   OpenTimestamps → khối Bitcoin #{r['bitcoin_height']} ({r['bitcoin_time']}), "
                       f"đối chiếu đầu khối với {r['explorer']}: hồ sơ tồn tại TRƯỚC thời điểm này")
    elif r["status"] == "pending":
        rep.line(None, "   Đã gửi OpenTimestamps, chờ Bitcoin xác nhận (thường vài giờ)")
    elif r["status"] == "no_library":
        rep.line(None, f"   Muốn tự kiểm neo Bitcoin: pip install opentimestamps, hoặc tải {a['file']} + .ots "
                       f"lên https://opentimestamps.org")
    elif r["status"] == "confirmed_unchecked":
        rep.line(None, f"   Có chứng thực khối #{r['bitcoin_height']} nhưng {r['why']}")
    else:
        rep.line(False, f"   Bằng chứng OpenTimestamps KHÔNG hợp lệ: {r.get('why')}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Kiểm độc lập một hồ sơ TerraTwin")
    ap.add_argument("target", nargs="?", help="mã hồ sơ hoặc đường dẫn /h/<mã>")
    ap.add_argument("--file", help="tệp JSON hồ sơ đã tải về")
    ap.add_argument("--api", default=API)
    ap.add_argument("--offline", action="store_true", help="chỉ kiểm 1–3 bằng khoá đi kèm tệp")
    a = ap.parse_args(argv)
    api = a.api.rstrip("/")
    if a.file:
        doc = json.load(open(a.file, encoding="utf-8"))
    elif a.target:
        did = a.target.rstrip("/").split("/h/")[-1].split("?")[0]
        doc = get(f"{api}/api/dossier/{did}")
    else:
        ap.error("cần mã hồ sơ hoặc --file")
    print(f"Hồ sơ {doc['id']} · số {doc['seq']} · phát hành {doc['issued_at']}")
    rep = Report()
    keys = None if a.offline else {k["key_id"]: k["public_key_b64"] for k in get(f"{api}/api/dossiers/keys")["keys"]}
    check_document(doc, keys, rep)
    if keys is not None:
        check_log(api, doc, keys, rep)
        check_anchor(api, doc, rep)
    print("KẾT LUẬN:", "BẢN GỐC — mọi phép kiểm bắt buộc đạt." if not rep.fail
          else f"KHÔNG QUA — {rep.fail} phép kiểm hỏng. Đừng tin nội dung hồ sơ này.")
    return 0 if not rep.fail else 1


if __name__ == "__main__":
    sys.exit(main())
