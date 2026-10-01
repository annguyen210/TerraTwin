"""ĐẤT ĐÃ ĐỔI KHÁC SAU 2021? — mô hình học sâu của TerraTwin (U-Net, app/dl) đọc
ảnh Sentinel-2 MỚI NHẤT tại thửa, so với bản đồ ESA WorldCover 2021.

VÌ SAO. WorldCover dừng ở 2021; người mua đất / ngân hàng năm 2026 cần biết
ruộng đã bị san lấp xây lên chưa, rừng còn hay đã mất. Không ai vẽ lại bản đồ
lớp phủ mỗi tháng cho từng thửa — mô hình thì đọc được ảnh mới mỗi 5 ngày.

BẪY ĐÃ CHẶN — ĐỘ LỆCH 1000 CỦA SENTINEL-2. Từ 25/01/2022 (processing baseline
04.00), ESA CỘNG 1000 vào mọi giá trị phản xạ L2A (BOA_ADD_OFFSET = −1000).
Mô hình học trên ảnh 2021 (chưa cộng). Đưa thẳng ảnh 2026 vào thì mọi thứ
"sáng" hơn 0,1 — nước thành đất, cây thành đất trống — và mạng sai MỘT CÁCH
IM LẶNG. Phải trừ 1000 cho ảnh baseline ≥ 04.00 trước khi chia 10000.

NÓI THẲNG GIỚI HẠN: chênh lệch có thể là sai số của mô hình (xem mIoU tập giữ
lại) hoặc của chính WorldCover (~77% đúng tổng thể theo ESA), không chỉ là
thay đổi thật. Kết luận luôn kèm hai con số đó và ảnh để người đọc tự nhìn.
"""
from __future__ import annotations

import io
import urllib.parse
import urllib.request
from datetime import date, timedelta

from app.services import landcover, landuse, mpc
from app.services.reqlang import tr

PATCH_PX = 256                     # 2,56 km ở 10 m — mạng cần ngữ cảnh xung quanh
CENTER_PX = 12                     # kết luận về ô 120 m giữa — cùng cỡ landuse
BANDS = ("B02", "B03", "B04", "B08")
CLEAR_MIN = 90.0                   # % điểm ảnh quang mây TẠI THỬA mới dùng ảnh
CHANGE_PTS = 25.0                  # nhóm đổi ≥25 điểm % mới gọi là "thay đổi"
BAND_URL = "https://planetarycomputer.microsoft.com/api/data/v1/item/bbox"


def _box(lat: float, lon: float, px: int) -> list[float]:
    return mpc.bbox_around(lat, lon, px * 10.0 / 2.0)


def harmonize(arr, baseline: str | None):
    """uint16 DN → phản xạ 0–1, TRỪ 1000 cho baseline ≥ 04.00 (xem đầu tệp)."""
    import numpy as np
    x = arr.astype(np.float32)
    try:
        b = float(baseline) if baseline else 0.0
    except ValueError:
        b = 0.0
    if b >= 4.0:
        x = x - 1000.0
    return np.clip(x / 10000.0, 0.0, 1.0)


def _get_npy(url: str):
    import numpy as np

    from app.services import jobs
    with jobs.upstream() as allowed:
        if not allowed:
            return None
        try:
            req = urllib.request.Request(url, headers={"User-Agent": mpc.USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as r:
                return np.load(io.BytesIO(r.read()), allow_pickle=False)
        except Exception:
            return None


def recent_patch(lat: float, lon: float, days: int = 365) -> tuple | None:
    """Ảnh mới nhất mà TẠI THỬA quang mây ≥ CLEAR_MIN% → (mảng 4×256×256, meta)."""
    big = _box(lat, lon, PATCH_PX)
    small = _box(lat, lon, CENTER_PX)
    end = date.today()
    items = mpc.search(big, end - timedelta(days=days), end, max_cloud=40.0, limit=20)
    if not items:
        return None
    for it in items[:8]:
        clear = mpc.clear_fraction(it["id"], small)
        if clear is None or clear < CLEAR_MIN:
            continue
        q = urllib.parse.urlencode([("collection", mpc.COLLECTION), ("item", it["id"])]
                                   + [("assets", b) for b in BANDS])
        arr = _get_npy(f"{BAND_URL}/{big[0]},{big[1]},{big[2]},{big[3]}/"
                       f"{PATCH_PX}x{PATCH_PX}.npy?{q}")
        if arr is None or arr.shape[0] < len(BANDS):
            continue
        props = it.get("properties", {})
        baseline = props.get("s2:processing_baseline")
        return harmonize(arr[:len(BANDS)], baseline), {
            "item": it["id"], "date": (props.get("datetime") or "")[:10],
            "clear_pct_at_plot": round(clear, 1), "processing_baseline": baseline,
            "offset_removed": (float(baseline) >= 4.0) if baseline else False,
        }
    return None


def detect(lat: float, lon: float) -> dict:
    """So nhóm lớp phủ HIỆN NAY (mô hình trên ảnh mới) với WorldCover 2021."""
    st = landcover.status()
    if not st.get("available"):
        return {"available": False, "reason": tr(
            "Mô hình học sâu lớp phủ chưa bật (chưa huấn luyện, hoặc điểm trên tập "
            "giữ lại dưới ngưỡng).", "The land-cover deep-learning model is not "
            "enabled (not trained yet, or its held-out score is below the bar)."),
            "model": st}
    before = landuse.composition(lat, lon)
    got = recent_patch(lat, lon)
    if got is None:
        return {"available": False, "reason": tr(
            "Không có ảnh Sentinel-2 nào trong 12 tháng qua mà tại thửa quang mây ≥ 90%.",
            "No Sentinel-2 image in the past 12 months is ≥90% cloud-free at the plot.")}
    patch, meta = got
    now = landcover.classify_window(patch, CENTER_PX)
    if now is None or before is None:
        return {"available": False, "reason": tr("Không chạy được mô hình hoặc không "
                                                 "lấy được WorldCover.", "Model or "
                                                 "WorldCover unavailable.")}
    groups = ("built", "crop", "tree", "water", "open")
    delta = {g: round(now["groups_pct"].get(g, 0.0) - before["group_pct"].get(g, 0.0), 1)
             for g in groups}
    flags = []
    if delta["built"] >= CHANGE_PTS:
        flags.append(tr(f"Bề mặt xây dựng TĂNG {delta['built']:.0f} điểm % so với 2021 — "
                        "có dấu hiệu xây dựng mới.",
                        f"Built-up surface UP {delta['built']:.0f} pts vs 2021 — signs of new construction."))
    if delta["tree"] <= -CHANGE_PTS:
        flags.append(tr(f"Tán cây GIẢM {-delta['tree']:.0f} điểm % so với 2021 — có dấu hiệu "
                        "mất rừng / chặt cây.",
                        f"Tree cover DOWN {-delta['tree']:.0f} pts vs 2021 — signs of clearing."))
    if delta["crop"] <= -CHANGE_PTS and delta["built"] > 0:
        flags.append(tr("Đất trồng trọt GIẢM, phần mất chuyển sang xây dựng — có thể đã "
                        "chuyển mục đích sử dụng.",
                        "Cropland DOWN with the loss going to built-up — possible land-use conversion."))
    return {
        "available": True,
        "changed": bool(flags),
        "flags": flags,
        "headline": flags[0] if flags else tr(
            "Không thấy thay đổi lớp phủ lớn so với 2021.",
            "No major land-cover change vs 2021."),
        "before": {"source": before["source"], "groups_pct": before["group_pct"]},
        "now": {"source": tr(f"Mô hình TerraTwin trên ảnh Sentinel-2 {meta['date']}",
                             f"TerraTwin model on Sentinel-2 image {meta['date']}"),
                "groups_pct": now["groups_pct"], "image": meta},
        "delta_pts": delta,
        "model": {"miou_holdout": st.get("miou_holdout"),
                  "iou_per_class": st.get("iou_per_class"),
                  "holdout_provinces": st.get("holdout_provinces")},
        "caveat": tr(
            "Chênh lệch có thể là thay đổi thật, sai số mô hình (xem mIoU tập giữ lại) "
            "hoặc sai số của WorldCover (~77% đúng tổng thể). Dùng như dấu hiệu cần "
            "kiểm tra thực địa, không phải kết luận.",
            "A difference may be real change, model error (see held-out mIoU) or "
            "WorldCover error (~77% overall accuracy). Treat it as a reason to check "
            "on the ground, not a verdict."),
    }
