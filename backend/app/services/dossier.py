"""HỒ SƠ ĐẤT SỐ — tờ thẩm định một thửa đất, phát hành một lần, ai cũng kiểm được.

Không phải cảnh báo, không phải dự báo: đây là GIẤY TỜ. Người mua đất, cán bộ
tín dụng, người bán bảo hiểm cần một tờ nói thửa này là đất gì, nằm cao hay
trũng, mười năm qua gặp hiểm hoạ gì, dữ liệu lấy từ đâu — và cần TIN rằng tờ giấy trước mặt họ đúng là tờ đã phát hành, chưa ai sửa.

BA LỚP KIỂM CHỨNG, mỗi lớp chặn một kiểu gian lận khác:
  1. facts_hash  — SHA-256 nội dung chuẩn hoá: sửa một chữ là lệch.
  2. chữ ký Ed25519 trên entry_hash — sửa rồi băm lại vẫn không ký lại được,
     vì khoá bí mật chỉ máy chủ giữ (services/signing.py).
  3. móc xích — entry_hash nối prev_hash của hồ sơ trước. Xoá hay sửa một hồ
     sơ cũ là gãy mọi mắt xích sau nó; sổ công khai (log) cho ai cũng tải về
     tự kiểm cả chuỗi mà KHÔNG thấy nội dung hay toạ độ của ai.

Nội dung ĐÓNG BĂNG lúc phát hành, bằng ngôn ngữ lúc phát hành: hồ sơ là ảnh
chụp tại một thời điểm, không phải trang sống. Muốn số mới → phát hành hồ sơ mới.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import Dossier
from app.services import signing
from app.services.reqlang import tr

SCHEMA = "terratwin.dossier/1"
GENESIS = "0" * 64
_ID_ALPHABET = "abcdefghijkmnpqrstuvwxyz23456789"   # bỏ l/o/0/1 — đọc qua điện thoại không nhầm


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def entry_message(seq: int, did: str, created_iso: str, facts_hash: str, prev_hash: str) -> str:
    return f"{SCHEMA}|{seq}|{did}|{created_iso}|{facts_hash}|{prev_hash}"


def _new_id() -> str:
    # 12 ký tự × log2(32) = 60 bit: đoán mò không ra, đủ ngắn để đọc qua điện thoại.
    return "".join(secrets.choice(_ID_ALPHABET) for _ in range(12))


def _iso(dt: datetime) -> str:
    return dt.replace(tzinfo=None).isoformat(timespec="seconds") + "Z"


# ------------------------------------------------------------------ nội dung

SOURCES = [
    "ESA WorldCover 2021 v200 (10 m) — Microsoft Planetary Computer",
    "Open-Meteo: cao độ DEM, lưu trữ tái phân tích ERA5 (ECMWF) 10 năm",
    "GloFAS (Copernicus) — lưu lượng sông tái phân tích",
]

# QUY TẮC TIN CẬY (3/10/2026): hồ sơ dùng để quyết định chuyện tiền bạc chỉ chứa số
# ĐO được và số TÍNH LẠI được từ số đo. Dự báo (rủi ro 7 ngày tới, mô hình học sâu)
# KHÔNG vào nội dung được ký — chúng đổi theo giờ và luôn có xác suất sai; người
# xem tra trực tiếp trên trang thửa, kèm tỉ lệ đúng đã đo (sổ điểm tự chấm).
EVIDENCE_CLASSES = {"land_use": "measured", "terrain": "measured", "history_10y": "derived",
                    "water_history_radar": "measured"}
S1_SOURCE = "Sentinel-1 RTC (Copernicus) — Microsoft Planetary Computer: lịch sử nước radar 2017 → nay"


def _water_section(lat: float, lon: float) -> dict | None:
    """Lịch sử nước radar ĐÃ ĐỌC cho thửa (cache) — chỉ khi cổng GĐ2 đạt. Không tự chạy ở đây: đọc
    vài trăm cảnh mất ~1–2 phút, không bắt người phát hành chờ; người dùng bấm "Xem lịch sử nước" trước."""
    from app import routes_water
    from app.services import cache_store, water_history as wh
    if not routes_water.gate()["passed"]:
        return None
    r = cache_store.get(cache_store.make_key("water", round(lat, 4), round(lon, 4), int(wh.RADIUS_M)))
    if not r or not r.get("available"):
        return None
    return {"n_scenes": r["n_scenes"], "first": r["first"], "last": r["last"], "track": r["track"],
            "n_events": r["n_events"],
            "events": [{k: e[k] for k in ("start", "end", "peak_cover", "n_scenes", "min_p50_db")} for e in r["events"]],
            "rule": {"water_db": wh.WATER_DB, "drop_db": wh.DROP_DB, "merge_gap_days": wh.MERGE_GAP_DAYS},
            "method": r["method"], "limits": r["limits"]}


def listing_section(text: str, lat: float, lon: float) -> dict:
    """GĐ3 — kết quả kiểm chứng tin đăng, CHẠY LẠI phía máy chủ. Chỉ giữ loại câu, kết quả, số đo, nguồn —
    bỏ nguyên văn câu (nội dung tin đăng không được lưu, kể cả trong hồ sơ)."""
    from app.services import listing_check
    r = listing_check.check(text, lat, lon)
    return {"checked_at": _iso(datetime.utcnow()),
            "claims": [{k: c[k] for k in ("type", "label", "verdict", "evidence", "source")} for c in r["claims"]],
            "counts": r["counts"],
            "note": tr("Đối chiếu từng loại câu khẳng định trong tin đăng với dữ liệu đo lúc phát hành. Nguyên văn tin "
                       "đăng KHÔNG được lưu; lời văn trung lập, không phải kết luận pháp lý về người bán.",
                       "Each type of claim in the listing compared against measured data at issuance. The listing text "
                       "itself is NOT stored; neutral wording, not a legal finding about the seller.")}


def build_facts(lat: float, lon: float, area_ha: float | None, db: Session) -> dict:
    """Ghép các dịch vụ SẴN CÓ thành nội dung hồ sơ. Không mô hình mới, không số mới.

    Chạy song song; mục nào hỏng ghi rõ "không lấy được" thay vì bỏ trống im lặng.
    """
    from app.services import jobs, landuse, passport, reqlang

    pp, lu = jobs.gather([lambda: passport.build(lat, lon), lambda: landuse.composition(lat, lon)])
    ok_pp = bool(pp and pp.get("available"))
    water = _water_section(lat, lon)
    return {
        "schema": SCHEMA,
        "lang": reqlang.cur_lang(),
        "location": {"lat": round(lat, 6), "lon": round(lon, 6), "area_ha": area_ha},
        "land_use": lu,
        "terrain": pp.get("terrain") if ok_pp else None,
        "history_10y": pp.get("history") if ok_pp else None,
        "history_caveat": (pp or {}).get("caveat") if pp else None,
        "water_history_radar": water,
        "evidence_classes": EVIDENCE_CLASSES,
        "predictions_included": False,
        "predictions_note": tr(
            "Dự báo (rủi ro 7 ngày tới, cảnh báo) KHÔNG đưa vào hồ sơ ký số: chúng đổi theo giờ và luôn có xác "
            "suất sai. Xem trực tiếp trên trang thửa, kèm tỉ lệ đúng đã đo của chính TerraTwin.",
            "Forecasts (7-day risk, alerts) are NOT part of the signed dossier: they change hourly and can "
            "always be wrong. See them live on the plot page, with TerraTwin's own measured hit rate."),
        "sources": SOURCES + ([S1_SOURCE] if water else []),
        "missing": [name for name, v in (("land_use", lu), ("passport", ok_pp)) if not v],
        "disclaimer": tr(
            "Hồ sơ tổng hợp dữ liệu ĐO và số tính lại được từ dữ liệu mở tại thời điểm phát hành. KHÔNG thay "
            "thế giấy chứng nhận quyền sử dụng đất, quy hoạch hay khảo sát thực địa. Mọi mục ghi rõ nguồn; "
            "mục nào không lấy được thì ghi là thiếu, không điền số thay.",
            "This dossier compiles MEASURED data and figures recomputable from open data at issuance time. "
            "It does NOT replace land-use right certificates, zoning or field surveys. Every section states "
            "its source; anything that couldn't be fetched is marked missing, never filled in."),
    }


# ------------------------------------------------------------------ phát hành

def issue(db: Session, facts: dict, lat: float, lon: float,
          user_id: int | None = None) -> Dossier:
    """Ghi thêm MỘT hồ sơ vào sổ, móc xích + ký. Thử lại khi hai hồ sơ cùng
    giành một số thứ tự (ràng buộc unique trên seq/entry_hash chặn trùng)."""
    facts_json = canonical(facts)
    facts_hash = sha256_hex(facts_json)
    for _ in range(5):
        last = db.execute(select(Dossier).order_by(Dossier.seq.desc()).limit(1)).scalars().first()
        seq = (last.seq + 1) if last else 1
        prev = last.entry_hash if last else GENESIS
        did = _new_id()
        now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
        entry_hash = sha256_hex(entry_message(seq, did, _iso(now), facts_hash, prev))
        sig, kid = signing.sign(db, entry_hash.encode("ascii"))
        row = Dossier(id=did, seq=seq, created_at=now, user_id=user_id,
                      lat=lat, lon=lon, facts_json=facts_json, facts_hash=facts_hash,
                      prev_hash=prev, entry_hash=entry_hash, signature=sig, key_id=kid)
        db.add(row)
        try:
            db.commit()
            return row
        except IntegrityError:
            db.rollback()
    raise RuntimeError("Không cấp được số thứ tự cho hồ sơ sau 5 lần thử")


# ------------------------------------------------------------------ kiểm chứng

def verify_row(db: Session, row: Dossier) -> dict:
    """Bốn phép kiểm độc lập. Hợp lệ khi và chỉ khi cả bốn đạt."""
    checks = []

    ok = sha256_hex(row.facts_json) == row.facts_hash
    checks.append({"id": "content", "ok": ok, "label": tr(
        "Nội dung khớp mã băm lúc phát hành" if ok else "Nội dung ĐÃ BỊ SỬA sau khi phát hành",
        "Content matches its issuance hash" if ok else "Content was ALTERED after issuance")})

    expect = sha256_hex(entry_message(row.seq, row.id, _iso(row.created_at),
                                      row.facts_hash, row.prev_hash))
    ok = expect == row.entry_hash
    checks.append({"id": "entry", "ok": ok, "label": tr(
        "Mục sổ đăng ký toàn vẹn" if ok else "Mục sổ đăng ký bị sửa (số thứ tự/thời điểm/mã)",
        "Registry entry intact" if ok else "Registry entry altered (seq/time/id)")})

    ok = signing.verify(db, row.entry_hash.encode("ascii"), row.signature, row.key_id)
    # Khoá tự sinh lưu trong CSDL: chữ ký vẫn đúng toán học, nhưng ai sửa được CSDL
    # cũng ký lại được — nói ra ngay trên dòng kiểm, không giấu ở tài liệu.
    weak = signing.key_source(db, row.key_id) == "auto"
    checks.append({"id": "signature", "ok": ok, "weak_key": weak, "label": tr(
        (f"Chữ ký Ed25519 hợp lệ (khoá {row.key_id})" + (
            " — khoá TỰ SINH lưu trong CSDL, mức tin thấp hơn" if weak else ""))
        if ok else "Chữ ký KHÔNG hợp lệ",
        (f"Valid Ed25519 signature (key {row.key_id})" + (
            " — AUTO-GENERATED key stored in the database, weaker trust" if weak else ""))
        if ok else "Signature INVALID")})

    if row.seq == 1:
        ok = row.prev_hash == GENESIS
    else:
        prev = db.execute(select(Dossier).where(Dossier.seq == row.seq - 1)).scalars().first()
        ok = prev is not None and prev.entry_hash == row.prev_hash
    checks.append({"id": "chain", "ok": ok, "label": tr(
        f"Móc xích đúng với hồ sơ #{row.seq - 1}" if ok and row.seq > 1 else
        ("Hồ sơ đầu tiên của sổ" if ok else "Móc xích GÃY — sổ đăng ký bị can thiệp"),
        f"Chain links correctly to dossier #{row.seq - 1}" if ok and row.seq > 1 else
        ("First dossier in the registry" if ok else "Chain BROKEN — registry tampered"))})

    # Ảnh thực địa (nếu có): ảnh thu nhỏ đang lưu phải còn đúng mã băm đã đóng
    # băng trong nội dung — thay ảnh trong CSDL là lệch.
    ev = json.loads(row.facts_json).get("field_evidence") or []
    if ev:
        from app.db import FieldPhoto
        bad = []
        for e in ev:
            ph = db.get(FieldPhoto, e.get("id"))
            if ph is None or sha256_bytes(ph.thumb) != e.get("thumb_sha256"):
                bad.append(e.get("id"))
        ok = not bad
        checks.append({"id": "evidence", "ok": ok, "label": tr(
            f"{len(ev)} ảnh thực địa còn nguyên như lúc phát hành" if ok else
            f"Ảnh thực địa bị thay/mất: {', '.join(map(str, bad))}",
            f"{len(ev)} field photo(s) unchanged since issuance" if ok else
            f"Field photo(s) replaced/missing: {', '.join(map(str, bad))}")})

    return {"valid": all(c["ok"] for c in checks), "checks": checks}


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def document(row: Dossier, db: Session | None = None) -> dict:
    """Bản hồ sơ đầy đủ để tải về / in — tự mang đủ thứ để kiểm lại, KỂ CẢ KHI KHÔNG
    CÓ MẠNG: `facts_canonical` là đúng chuỗi đã băm (trình duyệt băm lại chuỗi này,
    không tự dựng lại JSON — Python và JavaScript viết số thực khác nhau: 4.0 / 4), và
    khoá công khai đi kèm để kiểm chữ ký offline (so key_id với /api/dossiers/keys
    khi có mạng)."""
    pub = None
    if db is not None:
        from app.db import SigningKey
        k = db.get(SigningKey, row.key_id)
        pub = k.public_b64 if k else None
    return {
        "id": row.id, "seq": row.seq, "issued_at": _iso(row.created_at),
        "facts": json.loads(row.facts_json),
        "facts_canonical": row.facts_json,
        "proof": {"schema": SCHEMA, "facts_hash": row.facts_hash, "prev_hash": row.prev_hash,
                  "entry_hash": row.entry_hash, "algorithm": signing.ALGORITHM,
                  "key_id": row.key_id, "signature": row.signature, "public_key_b64": pub,
                  "entry_message": entry_message(row.seq, row.id, _iso(row.created_at),
                                                 row.facts_hash, row.prev_hash)},
    }


def verify_document(db: Session, doc: dict) -> dict:
    """Kiểm một tệp hồ sơ ai đó đưa cho bạn: có đúng là bản đã phát hành không.

    So với SỔ ĐĂNG KÝ (không tin mã băm tự khai trong tệp): nội dung trong tệp
    phải băm ra đúng facts_hash của hồ sơ cùng mã trong sổ, và hồ sơ trong sổ
    phải qua đủ bốn phép kiểm."""
    did = str(doc.get("id") or "")
    row = db.get(Dossier, did) if did else None
    if row is None:
        return {"valid": False, "found": False, "message": tr(
            "Không có hồ sơ nào mang mã này trong sổ đăng ký TerraTwin.",
            "No dossier with this ID exists in the TerraTwin registry.")}
    given = sha256_hex(canonical(doc.get("facts")))
    same = given == row.facts_hash
    reg = verify_row(db, row)
    valid = same and reg["valid"]
    return {"valid": valid, "found": True, "matches_registry": same, "registry": reg,
            "message": tr(
                "Tệp KHỚP bản đã phát hành — nội dung chưa bị sửa." if valid else
                ("Tệp KHÁC bản đã phát hành — nội dung đã bị sửa." if not same else
                 "Tệp khớp sổ, nhưng chính sổ đăng ký không qua kiểm chứng."),
                "File MATCHES the issued dossier — content unaltered." if valid else
                ("File DIFFERS from the issued dossier — content was altered." if not same else
                 "File matches the registry, but the registry itself failed verification."))}


def public_log(db: Session, limit: int = 100) -> dict:
    """Sổ công khai: chỉ mã băm + chữ ký + thời điểm. KHÔNG mã hồ sơ, KHÔNG toạ
    độ — ai cũng tải về kiểm cả chuỗi mà không thấy thửa đất của ai."""
    total = db.scalar(select(func.count()).select_from(Dossier)) or 0
    rows = db.execute(select(Dossier).order_by(Dossier.seq.desc()).limit(limit)).scalars().all()
    return {"total": int(total), "genesis": GENESIS, "schema": SCHEMA,
            "entries": [{"seq": r.seq, "issued_at": _iso(r.created_at),
                         "facts_hash": r.facts_hash, "prev_hash": r.prev_hash,
                         "entry_hash": r.entry_hash, "key_id": r.key_id,
                         "signature": r.signature} for r in rows]}
