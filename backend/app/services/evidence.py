"""ẢNH THỰC ĐỊA ĐÃ KIỂM — bằng chứng từ mặt đất gắn vào Hồ sơ đất số.

VÌ SAO. Vệ tinh nói thửa là đất gì; người mua/ngân hàng còn muốn thấy tận mắt.
Nhưng ảnh "thực địa" là thứ dễ gian nhất: ảnh chụp chỗ khác, ảnh cũ nhiều năm,
ảnh đã dùng cho một hồ sơ khác. Mỗi ảnh ở đây qua NĂM phép kiểm:

  1. gps       — EXIF có toạ độ chụp không
  2. location  — toạ độ chụp cách thửa bao xa (sai số GPS điện thoại ~5–30 m)
  3. time      — chụp lúc nào; quá cũ thì hiện trạng có thể đã khác
  4. edited    — EXIF có dấu phần mềm chỉnh ảnh (Photoshop, Snapseed…)
  5. duplicate — cùng ảnh (SHA-256) hoặc ảnh gần giống (băm cảm quan dHash,
                 chịu được nén lại / thu nhỏ) đã nộp cho một thửa KHÁC

NÓI THẲNG GIỚI HẠN: EXIF sửa được bằng công cụ miễn phí. Các phép kiểm này bắt
sai sót và gian lận vụng (ảnh chỗ khác, ảnh dùng lại) — KHÔNG chứng thực được
một ảnh đã bị làm giả EXIF cẩn thận. Kết luận luôn ghi "bằng chứng hỗ trợ".
Phép kiểm trùng chỉ so với kho ảnh của chính TerraTwin, không phải cả Internet.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import FieldPhoto
from app.services.reqlang import tr

MAX_BYTES = 8 * 1024 * 1024         # một ảnh điện thoại thường 2–6 MB
MAX_PIXELS = 50_000_000             # chặn "bom giải nén"
THUMB_PX = 640
FRESH_DAYS = 90                     # ảnh cũ hơn → hiện trạng có thể đã khác
DUP_HAMMING = 6                     # ≤6/64 bit khác nhau = cùng một cảnh
SAME_PLOT_M = 1000.0                # ảnh gần giống nhưng cùng thửa thì không phải "dùng lại"
_EDITORS = ("photoshop", "lightroom", "gimp", "snapseed", "picsart", "canva",
            "facetune", "meitu", "pixlr", "affinity")
_ID_ALPHABET = "abcdefghijkmnpqrstuvwxyz23456789"


class PhotoError(ValueError):
    """Ảnh không đọc được / quá lớn / sai định dạng — thông báo đã dịch."""


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def allowed_radius_m(area_ha: float | None) -> float:
    """Bán kính chấp nhận: nửa đường chéo thửa (coi như hình vuông) + 100 m cho
    sai số GPS và việc đứng ở bờ thửa để chụp. Không rõ diện tích → 150 m."""
    if not area_ha or area_ha <= 0:
        return 150.0
    return math.sqrt(area_ha * 10_000) * math.sqrt(2) / 2 + 100.0


def _deg(dms, ref: str | None) -> float | None:
    try:
        d, m, s = (float(x) for x in dms)
    except (TypeError, ValueError):
        return None
    v = d + m / 60 + s / 3600
    return -v if (ref or "").upper() in ("S", "W") else v


def _exif(img) -> dict:
    ex = img.getexif()
    gps = ex.get_ifd(0x8825) if ex else {}
    sub = ex.get_ifd(0x8769) if ex else {}
    lat = _deg(gps.get(2), gps.get(1)) if gps else None
    lon = _deg(gps.get(4), gps.get(3)) if gps else None
    raw_t = sub.get(0x9003) or ex.get(0x0132)            # DateTimeOriginal, rồi DateTime
    taken = None
    if raw_t:
        try:
            taken = datetime.strptime(str(raw_t).strip()[:19], "%Y:%m:%d %H:%M:%S")
        except ValueError:
            taken = None
    return {"lat": lat, "lon": lon, "taken": taken,
            "software": str(ex.get(0x0131) or "").strip()}


def dhash(img) -> str:
    """Băm cảm quan 64 bit: ảnh xám 9×8, so từng điểm với điểm bên phải. Nén lại,
    thu nhỏ, chỉnh sáng nhẹ vẫn ra gần như cùng mã."""
    from PIL import Image

    g = img.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    px = list(g.getdata())
    bits = 0
    for row in range(8):
        for col in range(8):
            bits = (bits << 1) | (px[row * 9 + col] > px[row * 9 + col + 1])
    return f"{bits:016x}"


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def low_detail(ph: str) -> bool:
    """Ảnh gần như một màu (che ống kính, ảnh đen, trời trắng) cho dHash gần như
    toàn 0 hoặc toàn 1 — mọi ảnh như thế "giống nhau" theo mã băm. Không dùng
    băm cảm quan cho chúng, chỉ so trùng từng byte, để không kết tội oan."""
    n = bin(int(ph, 16)).count("1")
    return n <= 3 or n >= 61


def _open(data: bytes):
    from PIL import Image, UnidentifiedImageError

    if len(data) > MAX_BYTES:
        raise PhotoError(tr(f"Ảnh quá lớn (> {MAX_BYTES // 1024 // 1024} MB).",
                            f"Photo too large (> {MAX_BYTES // 1024 // 1024} MB)."))
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as e:
        raise PhotoError(tr("Không đọc được ảnh. Dùng JPEG hoặc PNG (ảnh HEIC của "
                            "iPhone: chọn 'Tương thích nhất' trong Cài đặt → Camera).",
                            "Couldn't read the photo. Use JPEG or PNG (iPhone HEIC: "
                            "choose 'Most Compatible' in Settings → Camera).")) from e
    return img


def _thumb(img) -> bytes:
    from PIL import ImageOps

    t = ImageOps.exif_transpose(img).convert("RGB")
    t.thumbnail((THUMB_PX, THUMB_PX))
    buf = io.BytesIO()
    t.save(buf, "JPEG", quality=72, optimize=True)        # không truyền exif → xoá sạch
    return buf.getvalue()


def _check(cid: str, ok: bool | None, label: str) -> dict:
    return {"id": cid, "ok": ok, "label": label}


def analyze(db: Session, data: bytes, plot_lat: float, plot_lon: float,
            area_ha: float | None = None, now: datetime | None = None) -> dict:
    """Kiểm một ảnh. Không ghi gì — xem `store` để lưu."""
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    img = _open(data)
    sha = hashlib.sha256(data).hexdigest()
    ph = dhash(img)
    ex = _exif(img)
    checks = []

    has_gps = ex["lat"] is not None and ex["lon"] is not None
    checks.append(_check("gps", has_gps, tr(
        "Ảnh có toạ độ GPS" if has_gps else "Ảnh KHÔNG có toạ độ GPS (bật định vị cho camera, "
        "và gửi ảnh gốc — Zalo/Messenger xoá mất toạ độ)",
        "Photo has GPS coordinates" if has_gps else "Photo has NO GPS coordinates (enable "
        "location for the camera and send the original — chat apps strip it)")))

    dist = None
    if has_gps:
        dist = haversine_m(ex["lat"], ex["lon"], plot_lat, plot_lon)
        lim = allowed_radius_m(area_ha)
        near = dist <= lim
        checks.append(_check("location", near, tr(
            f"Chụp cách thửa {dist:.0f} m" + ("" if near else f" — XA hơn mức cho phép {lim:.0f} m"),
            f"Taken {dist:.0f} m from the plot" + ("" if near else f" — FARTHER than the {lim:.0f} m allowed"))))
    else:
        checks.append(_check("location", None, tr("Không kiểm được vị trí chụp",
                                                  "Capture location can't be checked")))

    taken = ex["taken"]
    if taken is None:
        checks.append(_check("time", None, tr("Ảnh không ghi thời điểm chụp",
                                              "Photo has no capture time")))
    elif taken > now + timedelta(days=1):
        checks.append(_check("time", False, tr(
            f"Thời điểm chụp {taken:%d/%m/%Y} ở TƯƠNG LAI — đồng hồ máy sai hoặc EXIF bị sửa",
            f"Capture time {taken:%d/%m/%Y} is in the FUTURE — wrong device clock or edited EXIF")))
    else:
        age = (now - taken).days
        fresh = age <= FRESH_DAYS
        checks.append(_check("time", fresh if fresh else None, tr(
            f"Chụp ngày {taken:%d/%m/%Y} ({age} ngày trước)" + ("" if fresh else
                f" — cũ hơn {FRESH_DAYS} ngày, hiện trạng có thể đã khác"),
            f"Taken {taken:%d/%m/%Y} ({age} days ago)" + ("" if fresh else
                f" — older than {FRESH_DAYS} days, the site may have changed"))))

    sw = ex["software"]
    edited = any(e in sw.lower() for e in _EDITORS)
    checks.append(_check("edited", not edited, tr(
        f"Có dấu phần mềm chỉnh ảnh: {sw}" if edited else "Không thấy dấu phần mềm chỉnh ảnh",
        f"Photo-editing software tag: {sw}" if edited else "No photo-editing software tag")))

    dup = _find_duplicate(db, sha, ph, plot_lat, plot_lon)
    checks.append(_check("duplicate", dup is None, tr(
        "Chưa từng nộp cho thửa khác" if dup is None else
        f"ĐÃ DÙNG cho một thửa khác cách đây {dup['km']:.1f} km ({dup['how']})",
        "Never submitted for another plot" if dup is None else
        f"ALREADY USED for another plot {dup['km']:.1f} km away ({dup['how_en']})")))

    by = {c["id"]: c["ok"] for c in checks}
    if by["location"] is False or by["duplicate"] is False or by["time"] is False:
        verdict = "mismatch"
    elif all(v is True for v in by.values()):
        verdict = "match"
    else:
        verdict = "review"

    return {"sha256": sha, "phash": ph, "gps": (ex["lat"], ex["lon"]) if has_gps else None,
            "taken_at": taken, "distance_m": round(dist, 1) if dist is not None else None,
            "verdict": verdict, "checks": checks, "thumb": _thumb(img)}


def _find_duplicate(db: Session, sha: str, ph: str, lat: float, lon: float) -> dict | None:
    """Ảnh này (hoặc gần giống) đã nộp cho thửa KHÁC chưa. So toàn kho —
    với kho vài nghìn ảnh, quét tuyến tính mã 64 bit là tức thì."""
    rows = db.execute(select(FieldPhoto.sha256, FieldPhoto.phash, FieldPhoto.plot_lat,
                             FieldPhoto.plot_lon)).all()
    for r_sha, r_ph, r_lat, r_lon in rows:
        d = haversine_m(lat, lon, r_lat, r_lon)
        if d <= SAME_PLOT_M:
            continue
        if r_sha == sha:
            return {"km": d / 1000, "how": "trùng từng byte", "how_en": "byte-identical"}
        if not low_detail(ph) and not low_detail(r_ph) and hamming(r_ph, ph) <= DUP_HAMMING:
            return {"km": d / 1000, "how": "ảnh gần giống", "how_en": "near-identical image"}
    return None


def store(db: Session, result: dict, plot_lat: float, plot_lon: float,
          user_id: int | None = None) -> FieldPhoto:
    thumb = result["thumb"]
    row = FieldPhoto(
        id="".join(secrets.choice(_ID_ALPHABET) for _ in range(12)),
        user_id=user_id, plot_lat=plot_lat, plot_lon=plot_lon,
        sha256=result["sha256"], phash=result["phash"],
        gps_lat=result["gps"][0] if result["gps"] else None,
        gps_lon=result["gps"][1] if result["gps"] else None,
        taken_at=result["taken_at"], distance_m=result["distance_m"],
        verdict=result["verdict"], checks_json=json.dumps(result["checks"], ensure_ascii=False),
        thumb=thumb, thumb_sha256=hashlib.sha256(thumb).hexdigest())
    db.add(row)
    db.commit()
    return row


VERDICT_LABEL = {
    "match": ("Khớp thửa", "Matches the plot"),
    "review": ("Cần xem thêm", "Needs review"),
    "mismatch": ("Không khớp", "Does not match"),
}


def public(row: FieldPhoto) -> dict:
    """Thông tin trả ra ngoài / đóng băng vào hồ sơ — KHÔNG kèm toạ độ GPS gốc."""
    vi, en = VERDICT_LABEL[row.verdict]
    return {"id": row.id, "verdict": row.verdict, "verdict_label": tr(vi, en),
            "checks": json.loads(row.checks_json or "[]"),
            "distance_m": row.distance_m,
            "taken_at": row.taken_at.isoformat(timespec="seconds") if row.taken_at else None,
            "sha256": row.sha256, "phash": row.phash, "thumb_sha256": row.thumb_sha256,
            "thumb_url": f"/api/evidence/{row.id}/thumb",
            "caveat": tr("Bằng chứng hỗ trợ: EXIF sửa được; phép kiểm trùng chỉ so với kho "
                         "ảnh của TerraTwin.",
                         "Supporting evidence: EXIF can be edited; the duplicate check only "
                         "covers TerraTwin's own photo store.")}
