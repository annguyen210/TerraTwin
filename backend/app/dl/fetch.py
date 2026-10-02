"""Dựng bộ dữ liệu HỌC SÂU: ảnh Sentinel-2 + nhãn lớp phủ ESA WorldCover.

CHẠY TRÊN MÁY CÓ GPU CỦA BẠN, không phải trên máy chủ sản phẩm.

VÌ SAO BÀI TOÁN NÀY, KHÔNG PHẢI BÀI TOÁN KHÁC. Điều duy nhất học sâu làm được
mà chỉ số phổ không làm được là NHÌN ĐƯỢC NGỮ CẢNH KHÔNG GIAN. Chỉ số NDBI xét
từng điểm ảnh một, nên nó lẫn lộn mái tôn với đất khô — hai thứ có phổ gần
giống nhau. Một mạng tích chập nhìn cả vùng lân cận: nó thấy HÌNH DẠNG chữ nhật,
thấy đường thẳng, thấy kết cấu đều đặn của mái nhà. Đó là khác biệt về năng lực
thật, không phải nhãn dán "AI".

Ba mũi nhọn được nâng thẳng nhờ việc này:
  · xây dựng trái phép  — lớp 50 (bề mặt xây dựng), thay cho NDBI hay báo nhầm
  · carbon rừng         — lớp 10 (tán cây), thay cho ngưỡng NDVI thô
  · thiệt hại sau bão   — so lớp phủ hai kỳ, thay cho hiệu NDVI

NHÃN LÀ THẬT VÀ MIỄN PHÍ. ESA WorldCover 10 m, 11 lớp, do Cơ quan Vũ trụ châu Âu
phát hành. Đã kiểm chứng phủ Việt Nam và tải được không cần đăng ký (chỉ cần xin
token ký, cũng công khai). Không có dòng dữ liệu nào tự bịa.

CẢNH BÁO TRUNG THỰC: tệp này được viết trên máy KHÔNG có numpy/rasterio/torch và
KHÔNG chạy thử được. Trước khi tải cả bộ dữ liệu vài giờ, hãy chạy:
    python -m app.dl.fetch --smoke
Nó lấy đúng một ô, in ra kích thước mảng và bảng lớp, mất khoảng một phút. Sai
gì thì lộ ra ngay ở đó.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import random
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
SAS = "https://planetarycomputer.microsoft.com/api/sas/v1/token/{coll}"
UA = "TerraTwin/0.7 (Vietnam land digital twin; research)"

S2 = "sentinel-2-l2a"
LC = "esa-worldcover"
BANDS = ("B02", "B03", "B04", "B08")      # lam, lục, đỏ, cận hồng ngoại — đều 10 m

PATCH = 256                # điểm ảnh, ở 10 m ⇒ ô 2,56 km
MAX_CLOUD = 20.0

# ESA WorldCover: mã gốc thưa (10,20,…,100) → chỉ số liên tục 0..10 cho mạng.
WC_CODES = [10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100]
WC_NAMES = ["Tán cây", "Cây bụi", "Đồng cỏ", "Đất trồng trọt", "Bề mặt xây dựng",
            "Đất trống", "Băng tuyết", "Mặt nước", "Đất ngập nước",
            "Rừng ngập mặn", "Rêu địa y"]
N_CLASSES = len(WC_CODES)

# Điểm lấy mẫu: phủ hết KIỂU khí hậu và KIỂU sử dụng đất, không phủ theo dân số.
# Cùng danh sách dùng cho mô hình khí hậu, thêm vài nơi đặc thù về lớp phủ.
SITES = [
    (22.82, 104.98, "Hà Giang · núi đá"),
    (22.40, 103.47, "Lai Châu · núi cao"),
    (21.03, 105.85, "Hà Nội · đô thị"),
    (20.86, 106.68, "Hải Phòng · cảng"),
    (20.25, 106.15, "Nam Định · lúa"),
    (19.81, 105.78, "Thanh Hoá"),
    (18.68, 105.68, "Vinh"),
    (16.46, 107.59, "Huế"),
    (16.05, 108.21, "Đà Nẵng · đô thị"),
    (15.33, 108.05, "Trà Leng · rừng núi"),
    (13.78, 109.22, "Quy Nhơn"),
    (13.98, 108.00, "Pleiku · cao nguyên"),
    (12.67, 108.05, "Buôn Ma Thuột · cà phê"),
    (11.56, 108.99, "Phan Rang · khô hạn"),
    (10.82, 106.63, "TP.HCM · đô thị dày"),
    (10.41, 106.95, "Cần Giờ · rừng ngập mặn"),
    (10.24, 106.37, "Bến Tre · dừa"),
    (10.03, 105.78, "Cần Thơ · lúa"),
    (9.18, 105.15, "Cà Mau · ngập mặn"),
    (8.62, 104.90, "Đất Mũi"),
]


def _http(url: str, payload: dict | None = None, timeout: float = 120.0,
          retries: int = 3) -> bytes | None:
    for k in range(retries):
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode() if payload else None,
                headers={"User-Agent": UA, "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:
            if k == retries - 1:
                print(f"    lỗi mạng: {type(e).__name__} {str(e)[:70]}")
                return None
            time.sleep(2 * (k + 1))
    return None


_tokens: dict[str, tuple[str, float]] = {}


def sas(coll: str) -> str | None:
    """Token ký để tải asset. Công khai, không cần tài khoản. Giữ 30 phút."""
    hit = _tokens.get(coll)
    if hit and time.time() - hit[1] < 1800:
        return hit[0]
    b = _http(SAS.format(coll=coll))
    if not b:
        return None
    try:
        tok = json.loads(b.decode())["token"]
    except Exception:
        return None
    _tokens[coll] = (tok, time.time())
    return tok


def search(coll: str, box, start=None, end=None, cloud=None, limit=10):
    q = {"collections": [coll], "bbox": box, "limit": limit}
    if start and end:
        q["datetime"] = f"{start}/{end}"
    if cloud is not None:
        q["query"] = {"eo:cloud_cover": {"lt": cloud}}
        q["sortby"] = [{"field": "eo:cloud_cover", "direction": "asc"}]
    b = _http(STAC, q)
    if not b:
        return []
    try:
        return json.loads(b.decode())["features"]
    except Exception:
        return []


def _box(lat: float, lon: float, px: int = PATCH) -> list[float]:
    """Khung bao quanh một điểm, cạnh đúng px điểm ảnh 10 m."""
    import math
    half_m = px * 10.0 / 2.0
    dlat = half_m / 111_320.0
    dlon = half_m / (111_320.0 * max(0.2, abs(math.cos(math.radians(lat)))))
    return [lon - dlon, lat - dlat, lon + dlon, lat + dlat]


def read_window(href: str, box: list[float], token: str, size: int = PATCH):
    """Đọc một ô ảnh về mảng numpy, cắt và lấy mẫu lại đúng size×size.

    Dùng rasterio đọc qua HTTP theo dải byte (COG), nên KHÔNG tải cả tệp 100 MB
    mà chỉ lấy đúng phần chồng lên ô cần.
    """
    import numpy as np
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.warp import transform_bounds
    from rasterio.windows import from_bounds

    url = href + ("&" if "?" in href else "?") + token
    # GDAL mặc định KHÔNG có thời gian chờ HTTP: chạy thật 1/10/2026 một lần đọc
    # treo 25 phút không lỗi, không tiến. Đặt trần + thử lại ở tầng GDAL; hỏng
    # hẳn thì ném lỗi để vòng ngoài thử lại / bỏ ô.
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
                      CPL_VSIL_CURL_USE_HEAD="NO",
                      GDAL_HTTP_TIMEOUT="60", GDAL_HTTP_CONNECTTIMEOUT="20",
                      GDAL_HTTP_MAX_RETRY="3", GDAL_HTTP_RETRY_DELAY="2"):
        with rasterio.open(url) as ds:
            l, b, r, t = transform_bounds("EPSG:4326", ds.crs, *box, densify_pts=21)
            win = from_bounds(l, b, r, t, ds.transform)
            arr = ds.read(1, window=win, out_shape=(size, size),
                          resampling=Resampling.nearest, boundless=True,
                          fill_value=0)
    return np.asarray(arr)


# HAI MÙA (lần huấn luyện thứ hai, 2/10/2026): lần đầu dùng ảnh MỘT ngày và lớp
# "đất trồng trọt" chỉ đạt IoU 0,026 — ruộng lúc ngập / mới gặt trông như mặt
# nước / đất trống; WorldCover dựng nhãn trồng trọt từ chuỗi ảnh nhiều mùa. Nay
# mỗi ô lấy HAI ảnh của 2021: nửa đầu năm và nửa cuối năm (mỗi nửa ảnh ít mây
# nhất) → 8 kênh. Ruộng đổi màu giữa hai mùa, rừng và mái nhà thì không.
SEASON_WINDOWS = {1: [("01-01", "12-31")], 2: [("01-01", "06-30"), ("07-01", "12-31")]}


def build_patch(lat: float, lon: float, year: int = 2021, seasons: int = 1):
    """Một mẫu huấn luyện: (ảnh (4·seasons)×H×W, nhãn H×W) hoặc None nếu không đủ dữ liệu.

    Nhãn WorldCover là bản 2021, nên ẢNH cũng phải lấy trong 2021 — ghép ảnh
    2026 với nhãn 2021 là dạy mạng học sai, và sai một cách không ai nhìn ra
    khi xem điểm số.
    """
    import numpy as np

    box = _box(lat, lon)

    lc_items = search(LC, box, limit=1)
    if not lc_items:
        return None
    tok_lc = sas(LC)
    if not tok_lc:
        return None
    lab_raw = read_window(lc_items[0]["assets"]["map"]["href"], box, tok_lc)

    # Mã thưa → chỉ số liên tục. Mã lạ (0 = không có dữ liệu) bị đánh dấu 255 và
    # bị hàm mất mát bỏ qua, thay vì gán bừa vào một lớp nào đó.
    lab = np.full(lab_raw.shape, 255, dtype=np.uint8)
    for i, code in enumerate(WC_CODES):
        lab[lab_raw == code] = i
    if (lab == 255).mean() > 0.5:
        return None

    tok_s2 = sas(S2)
    if not tok_s2:
        return None
    chans = []
    for start, end in SEASON_WINDOWS[seasons]:
        s2 = search(S2, box, f"{year}-{start}", f"{year}-{end}", cloud=MAX_CLOUD, limit=1)
        if not s2:
            return None                      # thiếu một mùa → bỏ cả ô, không ghép lệch
        for b in BANDS:
            chans.append(read_window(s2[0]["assets"][b]["href"], box, tok_s2))
    img = np.stack(chans).astype(np.float32)

    # Phản xạ Sentinel-2 L2A ở thang 0–10000. Chia 10000 đưa về 0–1; cắt trần ở
    # 1.0 vì mây và mặt nước sáng có thể vượt thang.
    img = np.clip(img / 10000.0, 0.0, 1.0)
    if not np.isfinite(img).all():
        return None
    return img, lab


def jitter(lat: float, lon: float, km: float = 12.0):
    """Xê dịch ngẫu nhiên quanh một điểm, để không lấy trùng một ô mãi."""
    d = km / 111.0
    return lat + random.uniform(-d, d), lon + random.uniform(-d, d)


def _fetch_one(pt, year: int, seasons: int = 1):
    """Một ô, chạy trong TIẾN TRÌNH con (xem ghi chú ProcessPoolExecutor ở main)."""
    lat, lon = pt
    for k in range(2):
        try:
            return build_patch(lat, lon, year, seasons), lat, lon
        except Exception as e:               # lỗi mạng/ô hỏng — thử lại một lần
            if k == 1:
                print(f"    bỏ ô ({lat:.3f}, {lon:.3f}): {type(e).__name__}", flush=True)
            time.sleep(2)
    return None, lat, lon


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/dl")
    ap.add_argument("--per-site", type=int, default=40)
    ap.add_argument("--year", type=int, default=2021)
    ap.add_argument("--seasons", type=int, choices=(1, 2), default=1,
                    help="1 = một ảnh/ô (4 kênh); 2 = nửa đầu + nửa cuối năm (8 kênh)")
    ap.add_argument("--seed", type=int, default=20260825)
    ap.add_argument("--smoke", action="store_true",
                    help="lấy đúng một ô rồi in kết quả — chạy cái này TRƯỚC")
    a = ap.parse_args()

    try:
        import numpy as np  # noqa: F401
        import rasterio     # noqa: F401
    except ImportError:
        print("Thiếu thư viện. Cài trước:")
        print("    pip install numpy rasterio")
        return 1

    import numpy as np
    random.seed(a.seed)

    if a.smoke:
        lat, lon, ten = SITES[16]
        print(f"Thử một ô tại {ten} ({lat}, {lon})…")
        t = time.time()
        r = build_patch(lat, lon, a.year)
        if r is None:
            print("THẤT BẠI — không lấy được ô này. Thử điểm khác hoặc năm khác.")
            return 1
        img, lab = r
        print(f"  xong trong {time.time() - t:.1f}s")
        print(f"  ảnh   {img.shape} {img.dtype}  min={img.min():.3f} max={img.max():.3f}")
        print(f"  nhãn  {lab.shape} {lab.dtype}")
        vals, cnt = np.unique(lab, return_counts=True)
        for v, c in sorted(zip(vals, cnt), key=lambda p: -p[1])[:5]:
            ten_lop = "KHÔNG CÓ DỮ LIỆU" if v == 255 else WC_NAMES[v]
            print(f"    {ten_lop:22} {100 * c / lab.size:5.1f}%")
        print("\nHợp lý thì chạy tiếp: python -m app.dl.fetch --per-site 40")
        return 0

    os.makedirs(a.out, exist_ok=True)
    parts = os.path.join(a.out, "parts")
    os.makedirs(parts, exist_ok=True)
    imgs, labs, meta = [], [], []
    t0 = time.time()

    # CHẠY THẬT LẦN ĐẦU (1/10/2026) lộ hai điều: (1) một ô tải về bị cắt cụt
    # ("TIFFFillTile: got 57498 bytes, expected 382016") làm sập CẢ lượt sau 10
    # phút — lỗi mạng thoáng qua, thử lại là được; (2) ~100 giây/ô khi tải tuần
    # tự. Nay: thử lại từng ô, bỏ qua ô hỏng hẳn; tải song song (việc chờ mạng,
    # không tốn CPU); lưu từng điểm vào parts/ để chạy lại thì đi tiếp từ chỗ dở.
    # TIẾN TRÌNH, KHÔNG PHẢI LUỒNG: bản chạy nhiều LUỒNG treo cứng (CPU ~0,
    # không kết nối mạng nào) ở Quy Nhơn hai lần liền, trong khi chạy tuần tự
    # cùng điểm đó xong trong vài giây. Cấu hình GDAL của rasterio.Env là toàn
    # cục trong một tiến trình — nhiều luồng cùng mở/đóng Env thì khoá chết. Mỗi
    # tiến trình có GDAL riêng, vẫn song song mà không chia trạng thái.
    from concurrent.futures import ProcessPoolExecutor
    from functools import partial

    _one = partial(_fetch_one, year=a.year, seasons=a.seasons)

    for lat0, lon0, ten in SITES:
        slug = "".join(ch if ch.isalnum() else "_" for ch in ten)[:40]
        part = os.path.join(parts, f"{slug}.npz")
        if os.path.exists(part):
            d = np.load(part, allow_pickle=False)
            pm = json.load(open(part + ".json", encoding="utf-8"))
            imgs += list(d["X"].astype(np.float16)); labs += list(d["Y"]); meta += pm
            print(f"  {ten:26} {len(pm):3}/{a.per_site} ô  (đã có từ lần trước)")
            continue
        # Toạ độ thử sinh ở luồng chính (random có seed) → chạy lại ra đúng bộ đó.
        cands = [jitter(lat0, lon0) for _ in range(a.per_site * 3)]   # mây hay chắn
        got_x, got_y, got_m = [], [], []
        with ProcessPoolExecutor(max_workers=4) as ex:
            for i in range(0, len(cands), a.per_site):
                if len(got_x) >= a.per_site:
                    break
                for r, lat, lon in ex.map(_one, cands[i:i + a.per_site]):
                    if r is None or len(got_x) >= a.per_site:
                        continue
                    got_x.append(r[0].astype(np.float16)); got_y.append(r[1])
                    got_m.append({"site": ten, "lat": round(lat, 4), "lon": round(lon, 4)})
        if got_x:
            np.savez_compressed(part, X=np.stack(got_x), Y=np.stack(got_y))
            json.dump(got_m, open(part + ".json", "w", encoding="utf-8"), ensure_ascii=False)
        imgs += got_x; labs += got_y; meta += got_m
        print(f"  {ten:26} {len(got_x):3}/{a.per_site} ô  ({time.time() - t0:.0f}s)", flush=True)

    if not imgs:
        print("Không lấy được ô nào. Kiểm tra mạng rồi chạy lại --smoke.")
        return 1

    X = np.stack(imgs)
    Y = np.stack(labs)
    np.savez_compressed(os.path.join(a.out, "patches.npz"), X=X, Y=Y)
    with open(os.path.join(a.out, "meta.json"), "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "classes": WC_NAMES, "codes": WC_CODES,
                   "bands": list(BANDS), "year": a.year, "seasons": a.seasons,
                   "season_windows": SEASON_WINDOWS[a.seasons]}, f, ensure_ascii=False)

    print(f"\nĐã lưu {len(imgs)} ô vào {a.out}/patches.npz")
    print(f"  ảnh {X.shape} {X.dtype} · nhãn {Y.shape} · {X.nbytes / 1e6:.0f} MB trong bộ nhớ")
    vals, cnt = np.unique(Y[Y != 255], return_counts=True)
    print("  phân bố lớp:")
    for v, c in sorted(zip(vals, cnt), key=lambda p: -p[1]):
        print(f"    {WC_NAMES[v]:22} {100 * c / cnt.sum():5.1f}%")
    print("\nTiếp theo: python -m app.dl.train")
    return 0


if __name__ == "__main__":
    sys.exit(main())
