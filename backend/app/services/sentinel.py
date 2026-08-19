"""Ảnh vệ tinh Sentinel-2 qua Copernicus Data Space Ecosystem (CDSE).

VÌ SAO CÓ FILE NÀY: câu định vị của TerraTwin là "bằng chứng thật từ VỆ TINH".
Trước file này, phần mềm chỉ có khí tượng và địa hình — đúng và hữu ích, nhưng
chưa phải con mắt nhìn thấy chính thửa đất. Đây là con mắt đó.

CÁCH LẤY KHÓA (miễn phí, không cần thẻ):
  1. Đăng ký tại https://dataspace.copernicus.eu
  2. Vào Sentinel Hub → User settings → OAuth clients → Create
  3. Đặt hai biến môi trường:
       TERRATWIN_COPERNICUS_ID
       TERRATWIN_COPERNICUS_SECRET

CHƯA CÓ KHÓA THÌ SAO: mọi hàm ở đây trả về None, và các module gọi tới nó vẫn
trả lời trung thực "chưa đủ dữ liệu". KHÔNG có chế độ giả lập — một chỉ số NDVI
bịa trông y hệt NDVI thật, và đó chính là thứ nguy hiểm nhất phần mềm này có thể
tạo ra.

HẠN MỨC: tài khoản CDSE miễn phí có quota processing unit theo tháng. Vì vậy mọi
kết quả đều được cache lâu (mặc định 12 giờ cho chuỗi thời gian, 7 ngày cho ảnh
lịch sử đã cố định) — ảnh Sentinel-2 chỉ 5 ngày mới bay qua một lần nên hỏi lại
sau 10 phút cũng không có gì mới.
"""
from __future__ import annotations

import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

TOKEN_URL = ("https://identity.dataspace.copernicus.eu/auth/realms/CDSE/"
             "protocol/openid-connect/token")
STATS_URL = "https://sh.dataspace.copernicus.eu/api/v1/statistics"

TIMEOUT = 45.0            # Statistics API chạy lâu hơn hẳn API thời tiết
_TTL_SERIES = 12 * 3600   # chuỗi gần đây — ảnh mới nhất tối đa 5 ngày/lần
_TTL_FIXED = 7 * 86400    # cửa sổ lịch sử đã đóng — không bao giờ đổi nữa

# Bộ chỉ số. Mỗi mục: (các băng cần, biểu thức JS, mô tả cho người đọc).
INDICES: dict[str, tuple[tuple[str, ...], str, str]] = {
    # Sức sống thực vật. Chuẩn de-facto cho sức khỏe cây trồng.
    "NDVI": (("B04", "B08"), "(s.B08 - s.B04) / (s.B08 + s.B04)",
             "Sức sống thực vật (−1…1; cây khỏe > 0,6; đất trống < 0,2)"),
    # Nước mặt. Dương mạnh = mặt nước.
    "NDWI": (("B03", "B08"), "(s.B03 - s.B08) / (s.B03 + s.B08)",
             "Nước mặt (> 0,3 gần như chắc chắn là mặt nước)"),
    # Độ ẩm trong tán lá — nhạy với stress hạn SỚM HƠN NDVI.
    "NDMI": (("B08", "B11"), "(s.B08 - s.B11) / (s.B08 + s.B11)",
             "Độ ẩm tán lá (giảm trước khi NDVI kịp giảm)"),
    # Bề mặt xây dựng. Dương = bê tông, mái tôn, đường.
    "NDBI": (("B08", "B11"), "(s.B11 - s.B08) / (s.B11 + s.B08)",
             "Bề mặt xây dựng (> 0 thường là bê tông/mái/đường)"),
}

_token_cache: tuple[str, float] | None = None      # (access_token, hết hạn lúc)


# ---------------------------------------------------------------- cấu hình

def credentials() -> tuple[str | None, str | None]:
    cid = (os.environ.get("TERRATWIN_COPERNICUS_ID") or "").strip()
    sec = (os.environ.get("TERRATWIN_COPERNICUS_SECRET") or "").strip()
    return (cid or None, sec or None)


def configured() -> bool:
    cid, sec = credentials()
    return bool(cid and sec)


def status() -> dict:
    """Trạng thái để hiển thị cho người dùng — không bao giờ lộ secret."""
    cid, _ = credentials()
    return {
        "configured": configured(),
        "client_id_hint": (cid[:6] + "…") if cid else None,
        "provider": "Copernicus Data Space Ecosystem (Sentinel-2 L2A)",
        "indices": {k: v[2] for k, v in INDICES.items()},
        "message": (
            "Đã nối ảnh Sentinel-2." if configured() else
            "Chưa cấu hình ảnh vệ tinh. Đăng ký miễn phí tại "
            "dataspace.copernicus.eu rồi đặt TERRATWIN_COPERNICUS_ID và "
            "TERRATWIN_COPERNICUS_SECRET. Trong lúc chờ, các mô-đun cần ảnh sẽ "
            "nói thẳng là chưa đủ dữ liệu chứ không đoán."),
    }


# ---------------------------------------------------------------- HTTP

def _token() -> str | None:
    """Lấy access token, giữ lại tới trước khi hết hạn 60 giây."""
    global _token_cache
    now = time.time()
    if _token_cache and _token_cache[1] > now + 60:
        return _token_cache[0]

    cid, sec = credentials()
    if not (cid and sec):
        return None

    body = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": cid,
        "client_secret": sec,
    }).encode()
    req = urllib.request.Request(
        TOKEN_URL, data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "User-Agent": "TerraTwin/0.6"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            d = json.loads(r.read().decode("utf-8"))
    except Exception:
        return None

    tok = d.get("access_token")
    if not tok:
        return None
    _token_cache = (tok, now + float(d.get("expires_in", 600)))
    return tok


def _post(url: str, payload: dict) -> dict | None:
    tok = _token()
    if tok is None:
        return None
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {tok}",
                 "Content-Type": "application/json",
                 "Accept": "application/json",
                 "User-Agent": "TerraTwin/0.6"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 401:
            # Token có thể đã bị thu hồi — bỏ cache để lần sau xin lại.
            global _token_cache
            _token_cache = None
        return None
    except Exception:
        return None


# ---------------------------------------------------------------- hình học

def bbox_around(lat: float, lon: float, buffer_m: float = 300.0) -> list[float]:
    """Ô vuông quanh một điểm, cạnh 2×buffer_m. Mặc định 600 m ≈ 36 ha."""
    dlat = buffer_m / 111_320.0
    dlon = buffer_m / (111_320.0 * max(0.2, math.cos(math.radians(lat))))
    return [round(lon - dlon, 6), round(lat - dlat, 6),
            round(lon + dlon, 6), round(lat + dlat, 6)]


def _evalscript(index: str) -> str:
    bands, expr, _ = INDICES[index]
    need = sorted(set(bands) | {"SCL", "dataMask"})
    band_list = ", ".join(f'"{b}"' for b in need)
    # SCL (Scene Classification Layer) loại mây, bóng mây, tuyết, pixel hỏng.
    # Không lọc mây thì một tấm ảnh mây trắng cho NDVI ≈ 0 và bị đọc nhầm
    # thành "cây chết" — sai lầm kinh điển của phân tích viễn thám nghiệp dư.
    return (
        "//VERSION=3\n"
        "function setup() {\n"
        f"  return {{ input: [{{ bands: [{band_list}] }}],\n"
        "    output: [ { id: \"index\", bands: 1, sampleType: \"FLOAT32\" },\n"
        "              { id: \"dataMask\", bands: 1 } ] };\n"
        "}\n"
        "function evaluatePixel(s) {\n"
        f"  let v = {expr};\n"
        "  let bad = [0, 1, 3, 8, 9, 10, 11];\n"
        "  let ok = (s.dataMask === 1) && (bad.indexOf(s.SCL) < 0) ? 1 : 0;\n"
        "  return { index: [v], dataMask: [ok] };\n"
        "}\n"
    )


# ---------------------------------------------------------------- chuỗi chỉ số

def index_series(lat: float, lon: float, index: str = "NDVI",
                 days: int = 90, interval_days: int = 10,
                 buffer_m: float = 300.0,
                 end: date | None = None) -> list[dict] | None:
    """Chuỗi thống kê của một chỉ số quang học trên thửa đất.

    Trả None nếu chưa cấu hình khóa hoặc gọi hỏng — người gọi PHẢI phân biệt
    được "không có dữ liệu" với "có dữ liệu và nó bằng 0".

    Mỗi phần tử: date, mean, std, min, max, valid_px, total_px, coverage_pct.
    Khoảng nào toàn mây (coverage thấp) vẫn được trả về kèm coverage_pct để
    người gọi tự quyết bỏ hay dùng — giấu đi thì người đọc tưởng vệ tinh không
    bay qua, trong khi thực tế là bay qua nhưng nhìn không thấy đất.
    """
    if index not in INDICES:
        raise ValueError(f"Chỉ số không hỗ trợ: {index}")
    if not configured():
        return None

    end = end or date.today()
    start = end - timedelta(days=int(days))
    fixed = (date.today() - end).days > 14      # cửa sổ đã đóng hẳn

    from app.services import cache_store
    key = cache_store.make_key("sentinel", index, round(lat, 4), round(lon, 4),
                               days, interval_days, buffer_m, end.isoformat())
    hit = cache_store.get(key)
    if hit is not None:
        return hit

    payload = {
        "input": {
            "bounds": {
                "bbox": bbox_around(lat, lon, buffer_m),
                "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"},
            },
            "data": [{
                "type": "sentinel-2-l2a",
                "dataFilter": {"mosaickingOrder": "leastCC"},
            }],
        },
        "aggregation": {
            "timeRange": {"from": f"{start.isoformat()}T00:00:00Z",
                          "to": f"{end.isoformat()}T23:59:59Z"},
            "aggregationInterval": {"of": f"P{int(interval_days)}D"},
            "evalscript": _evalscript(index),
            "resx": 10, "resy": 10,          # đúng độ phân giải gốc Sentinel-2
        },
        "calculations": {"index": {"statistics": {"default": {}}}},
    }

    d = _post(STATS_URL, payload)
    if d is None or "data" not in d:
        return None

    out: list[dict] = []
    for item in d.get("data", []):
        iv = item.get("interval") or {}
        band = (((item.get("outputs") or {}).get("index") or {})
                .get("bands") or {}).get("B0") or {}
        st = band.get("stats") or {}
        n = int(st.get("sampleCount") or 0)
        nodata = int(st.get("noDataCount") or 0)
        valid = max(0, n - nodata)
        mean = st.get("mean")
        if mean is None or valid == 0:
            # Khoảng toàn mây. Giữ lại bản ghi để chuỗi không "biến mất" một
            # cách bí ẩn, nhưng mean = None để không ai lỡ dùng nhầm.
            out.append({"date": (iv.get("from") or "")[:10], "mean": None,
                        "std": None, "min": None, "max": None,
                        "valid_px": valid, "total_px": n, "coverage_pct": 0.0})
            continue
        out.append({
            "date": (iv.get("from") or "")[:10],
            "mean": round(float(mean), 4),
            "std": round(float(st.get("stDev") or 0.0), 4),
            "min": round(float(st.get("min") or 0.0), 4),
            "max": round(float(st.get("max") or 0.0), 4),
            "valid_px": valid, "total_px": n,
            "coverage_pct": round(100.0 * valid / n, 1) if n else 0.0,
        })

    out.sort(key=lambda r: r["date"])
    cache_store.put(key, out, _TTL_FIXED if fixed else _TTL_SERIES)
    return out


def index_distribution(lat: float, lon: float, index: str = "NDVI",
                       days: int = 60, buffer_m: float = 600.0,
                       bins: int = 20, end: date | None = None) -> dict | None:
    """PHÂN BỐ giá trị chỉ số trên toàn ô, không chỉ trung bình.

    Trung bình không đủ để đo độ che phủ: một ô nửa rừng già nửa đất trống và
    một ô toàn cây bụi thưa có thể cho cùng NDVI trung bình 0,45. Muốn biết
    "bao nhiêu phần trăm diện tích thực sự là rừng" thì phải nhìn histogram.
    """
    if index not in INDICES:
        raise ValueError(f"Chỉ số không hỗ trợ: {index}")
    if not configured():
        return None

    end = end or date.today()
    start = end - timedelta(days=int(days))

    from app.services import cache_store
    key = cache_store.make_key("sentinel-hist", index, round(lat, 4),
                               round(lon, 4), days, buffer_m, bins,
                               end.isoformat())
    hit = cache_store.get(key)
    if hit is not None:
        return hit

    payload = {
        "input": {
            "bounds": {
                "bbox": bbox_around(lat, lon, buffer_m),
                "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"},
            },
            "data": [{"type": "sentinel-2-l2a",
                      "dataFilter": {"mosaickingOrder": "leastCC"}}],
        },
        "aggregation": {
            "timeRange": {"from": f"{start.isoformat()}T00:00:00Z",
                          "to": f"{end.isoformat()}T23:59:59Z"},
            # Một khoảng duy nhất phủ cả cửa sổ: ta cần MỘT bức tranh không
            # gian rõ nhất, không cần diễn biến theo thời gian.
            "aggregationInterval": {"of": f"P{int(days) + 1}D"},
            "evalscript": _evalscript(index),
            "resx": 10, "resy": 10,
        },
        "calculations": {"index": {
            "statistics": {"default": {}},
            "histograms": {"default": {"nBins": int(bins), "lowEdge": -1.0,
                                       "highEdge": 1.0}},
        }},
    }

    d = _post(STATS_URL, payload)
    if d is None or not d.get("data"):
        return None

    item = d["data"][0]
    out_idx = ((item.get("outputs") or {}).get("index") or {})
    band = (out_idx.get("bands") or {}).get("B0") or {}
    st = band.get("stats") or {}
    total = int(st.get("sampleCount") or 0)
    nodata = int(st.get("noDataCount") or 0)
    valid = max(0, total - nodata)
    if valid == 0:
        return None

    raw_bins = ((band.get("histogram") or {}).get("bins")) or []
    hist = []
    for b in raw_bins:
        lo = b.get("lowEdge")
        hi = b.get("highEdge")
        cnt = int(b.get("count") or 0)
        if lo is None or hi is None:
            continue
        hist.append({"low": round(float(lo), 3), "high": round(float(hi), 3),
                     "count": cnt,
                     "pct": round(100.0 * cnt / valid, 2) if valid else 0.0})

    res = {
        "index": index,
        "observed_window": [start.isoformat(), end.isoformat()],
        "mean": round(float(st.get("mean") or 0.0), 4),
        "std": round(float(st.get("stDev") or 0.0), 4),
        "valid_px": valid, "total_px": total,
        "coverage_pct": round(100.0 * valid / total, 1) if total else 0.0,
        "pixel_m": 10.0,
        "area_ha": round(valid * 100.0 / 10_000.0, 2),   # 10×10 m = 100 m²/px
        "bins": hist,
    }
    cache_store.put(key, res, _TTL_SERIES)
    return res


def fraction_above(dist: dict | None, threshold: float) -> float | None:
    """Tỉ lệ diện tích có chỉ số vượt ngưỡng, nội suy tuyến tính trong bin biên.

    Nội suy chứ không đếm nguyên bin: với bins rộng 0,1 mà ngưỡng rơi giữa bin
    thì đếm nguyên bin sai tới cả chục phần trăm diện tích — sai số đó đi thẳng
    vào con số carbon ở cuối.
    """
    if not dist or not dist.get("bins"):
        return None
    total = sum(b["count"] for b in dist["bins"])
    if total <= 0:
        return None
    above = 0.0
    for b in dist["bins"]:
        if b["low"] >= threshold:
            above += b["count"]
        elif b["high"] > threshold:
            span = b["high"] - b["low"]
            if span > 0:
                above += b["count"] * (b["high"] - threshold) / span
    return round(above / total, 4)


def latest_clear(series: list[dict] | None, min_coverage: float = 40.0):
    """Bản ghi mới nhất nhìn thấy đủ đất. None nếu cả chuỗi đều bị mây che."""
    if not series:
        return None
    for r in reversed(series):
        if r["mean"] is not None and r["coverage_pct"] >= min_coverage:
            return r
    return None


def window_mean(lat: float, lon: float, index: str,
                start: date, end: date, buffer_m: float = 300.0):
    """Giá trị trung bình của một chỉ số trong MỘT cửa sổ thời gian.

    Dùng cho so sánh hai kỳ (trước/sau bão, trước/sau xây dựng). Gộp cả cửa sổ
    thành một khoảng để tăng khả năng có ít nhất một ngày quang mây.
    """
    days = max(1, (end - start).days)
    s = index_series(lat, lon, index=index, days=days,
                     interval_days=days + 1, buffer_m=buffer_m, end=end)
    return latest_clear(s, min_coverage=25.0)


def change_between(lat: float, lon: float, index: str,
                   before: tuple[date, date], after: tuple[date, date],
                   buffer_m: float = 300.0) -> dict | None:
    """So sánh hai kỳ — nền của mọi phát hiện thay đổi bề mặt.

    Trả None khi thiếu một trong hai kỳ. KHÔNG suy diễn từ một kỳ: "sau bão
    NDVI thấp" tự nó vô nghĩa nếu không biết trước bão nó bao nhiêu.
    """
    b = window_mean(lat, lon, index, before[0], before[1], buffer_m)
    a = window_mean(lat, lon, index, after[0], after[1], buffer_m)
    if b is None or a is None:
        return None
    delta = round(a["mean"] - b["mean"], 4)
    return {
        "index": index,
        "before": b, "after": a,
        "delta": delta,
        "delta_pct": (round(100.0 * delta / abs(b["mean"]), 1)
                      if b["mean"] else None),
        "before_window": [before[0].isoformat(), before[1].isoformat()],
        "after_window": [after[0].isoformat(), after[1].isoformat()],
    }


def source_note(index: str) -> str:
    return (f"Sentinel-2 L2A ({index}) qua Copernicus Data Space, ô "
            f"600×600 m quanh thửa, đã lọc mây bằng băng SCL.")
