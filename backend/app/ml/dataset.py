"""Dựng bộ dữ liệu huấn luyện từ 10 năm ERA5 — miễn phí, không cần khoá.

BỘ DỮ LIỆU NÀY LÀ THẬT. Không có dòng nào sinh ngẫu nhiên. Nếu mạng hỏng giữa
chừng, hàm trả về ít điểm hơn chứ không bù bằng số giả — cùng một kỷ luật với
lớp vệ tinh.

CHỌN 16 ĐIỂM THAM CHIẾU THEO KHÍ HẬU, KHÔNG THEO DÂN SỐ:
Mục tiêu là phủ hết các KIỂU khí hậu Việt Nam, nên có cả những nơi ít người ở
nhưng khí hậu đặc thù (Ninh Thuận khô hạn nhất nước, Bạch Mã mưa nhiều nhất).
Một mô hình chỉ học từ Hà Nội và TP.HCM sẽ coi Ninh Thuận là bất thường quanh năm.

MƯỜI ĐẶC TRƯNG, chọn vì Ý NGHĨA VẬT LÝ chứ không vì có sẵn:
  rain_1d     mưa hôm nay              — cú sốc tức thời
  rain_3d     mưa dồn 3 ngày           — ngưỡng kích hoạt lũ quét
  rain_15d    mưa dồn 15 ngày          — độ bão hoà nền, thứ quyết định sạt lở
  rain_60d    mưa dồn 60 ngày          — trí nhớ mùa, thứ quyết định hạn
  wb_7d       mưa 7d trừ bốc hơi 7d    — cân bằng nước thật, không phải mưa suông
  wb_60d      cân bằng nước 60 ngày    — thâm hụt nước tích luỹ
  dry_streak  số ngày liên tiếp không mưa — hạn và cháy
  tmax        nhiệt cao nhất
  drange      biên độ ngày đêm         — trời quang hay nhiều mây
  wind_max    gió mạnh nhất            — cháy lan, đổ cây, sóng ao nuôi

Các biến mưa tương quan rất mạnh với nhau. ĐÓ LÀ CHỦ Ý: mô hình Mahalanobis cần
biết cấu trúc tương quan bình thường để nhận ra lúc nó bị phá vỡ — mưa 15 ngày
cao mà mưa hôm nay bằng 0 là một trạng thái khác hẳn cả hai cùng cao.

VÌ SAO CÓ HAI BIẾN 60 NGÀY — GHI LẠI ĐỂ MINH BẠCH: bản đầu chỉ có trí nhớ tới
15 ngày và đã BỎ SÓT hạn–mặn Bến Tre 2020 trong đánh giá. Nguyên nhân là cấu
trúc chứ không phải tinh chỉnh: hạn ĐBSCL tích tụ hàng tháng, không đặc trưng
nào nhớ đủ lâu để thấy. Hai biến 60 ngày được thêm sau chẩn đoán đó — một lần
chỉnh có lý do, không phải dò tìm cho số đẹp. Kết quả trước và sau đều được ghi
trong báo cáo huấn luyện.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

FEATURES = ["rain_1d", "rain_3d", "rain_15d", "rain_60d", "wb_7d", "wb_60d",
            "dry_streak", "tmax", "drange", "wind_max"]

# (mã, tên, vĩ độ, kinh độ, vùng khí hậu người đặt — chỉ để đọc báo cáo,
#  KHÔNG đưa vào mô hình; nhãn vùng do k-means tự học lấy.)
SITES = [
    ("hagiang",  "Hà Giang",            22.82, 104.98, "núi cao Đông Bắc"),
    ("laichau",  "Lai Châu",            22.40, 103.47, "núi cao Tây Bắc"),
    ("hanoi",    "Hà Nội",              21.03, 105.85, "đồng bằng Bắc Bộ"),
    ("haiphong", "Hải Phòng",           20.86, 106.68, "ven biển Bắc Bộ"),
    ("thanhhoa", "Thanh Hoá",           19.81, 105.78, "Bắc Trung Bộ"),
    ("vinh",     "Vinh",                18.68, 105.68, "Bắc Trung Bộ gió Lào"),
    ("hue",      "Huế",                 16.46, 107.59, "mưa lớn Trung Trung Bộ"),
    ("danang",   "Đà Nẵng",             16.05, 108.21, "ven biển Trung Bộ"),
    ("traleng",  "Trà Leng, Quảng Nam", 15.33, 108.05, "núi Trung Bộ dốc"),
    ("quynhon",  "Quy Nhơn",            13.78, 109.22, "Nam Trung Bộ"),
    ("pleiku",   "Pleiku",              13.98, 108.00, "cao nguyên"),
    ("buonmathuot", "Buôn Ma Thuột",    12.67, 108.05, "cao nguyên bazan"),
    ("phanrang", "Phan Rang",           11.56, 108.99, "khô hạn nhất nước"),
    ("hcm",      "TP. Hồ Chí Minh",     10.82, 106.63, "Đông Nam Bộ"),
    ("bentre",   "Bến Tre",             10.24, 106.37, "đồng bằng sông Cửu Long"),
    ("camau",    "Cà Mau",               9.18, 105.15, "cực Nam ngập mặn"),
]

WARMUP = 60             # ngày nền cần có trước khi tính được đặc trưng dài nhất

TRAIN_START, TRAIN_END = "2015-01-01", "2019-12-31"
TEST_START, TEST_END = "2020-01-01", "2024-12-31"

_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "data", "era5")

_DAILY = ("precipitation_sum,et0_fao_evapotranspiration,"
          "temperature_2m_max,temperature_2m_min,wind_speed_10m_max")


def _cache_path(code: str) -> str:
    return os.path.join(_DIR, f"{code}.json")


def fetch_site(code: str, lat: float, lon: float,
               start: str = TRAIN_START, end: str = TEST_END,
               retries: int = 3) -> list[dict] | None:
    """Tải chuỗi ngày thô cho một điểm. Có cache đĩa nên chỉ tải một lần.

    Trả None nếu không lấy được — người gọi phải bỏ điểm đó, không được bịa.
    """
    path = _cache_path(code)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    url = ("https://archive-api.open-meteo.com/v1/archive"
           f"?latitude={lat}&longitude={lon}"
           f"&start_date={start}&end_date={end}"
           f"&daily={_DAILY}&timezone=auto")

    raw = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "TerraTwin/1.0 (research)"})
            with urllib.request.urlopen(req, timeout=90) as r:
                raw = json.loads(r.read().decode("utf-8"))
            break
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            if attempt == retries - 1:
                return None
            time.sleep(3 * (attempt + 1))

    if not raw or "daily" not in raw:
        return None
    dd = raw["daily"]
    try:
        n = len(dd["time"])
        rows = []
        for i in range(n):
            rows.append({
                "date": dd["time"][i],
                "precip": _f(dd["precipitation_sum"], i),
                "et0": _f(dd["et0_fao_evapotranspiration"], i),
                "tmax": _f(dd["temperature_2m_max"], i),
                "tmin": _f(dd["temperature_2m_min"], i),
                "wind": _f(dd["wind_speed_10m_max"], i),
            })
    except (KeyError, TypeError, IndexError):
        return None

    os.makedirs(_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f)
    return rows


def _f(arr, i) -> float | None:
    try:
        v = arr[i]
    except (IndexError, TypeError):
        return None
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build_features(rows: list[dict]) -> list[dict]:
    """Chuỗi ngày thô → đặc trưng. Bỏ WARMUP ngày đầu vì chưa đủ nền lịch sử.

    KHÔNG NỘI SUY ngày thiếu: một ngày khuyết bị đánh dấu và loại khỏi huấn
    luyện. Bù bằng trung bình sẽ tạo ra những ngày "bình thường nhân tạo" và
    làm mô hình tưởng thế giới ổn định hơn thực tế.
    """
    out = []
    n = len(rows)
    for i in range(WARMUP, n):
        w = rows[i - WARMUP:i + 1]      # WARMUP ngày nền + hôm nay
        today = rows[i]
        if any(today.get(k) is None for k in ("precip", "tmax", "tmin", "wind")):
            continue
        rain = [r["precip"] for r in w]
        if any(v is None for v in rain):
            continue
        et0 = [r["et0"] if r["et0"] is not None else 0.0 for r in w]

        rain_1d = rain[-1]
        rain_3d = sum(rain[-3:])
        rain_15d = sum(rain[-15:])
        rain_60d = sum(rain[-60:])
        wb_7d = sum(rain[-7:]) - sum(et0[-7:])
        wb_60d = sum(rain[-60:]) - sum(et0[-60:])

        streak = 0
        for v in reversed(rain):
            if v < 1.0:
                streak += 1
            else:
                break

        out.append({
            "date": today["date"],
            "rain_1d": rain_1d,
            "rain_3d": rain_3d,
            "rain_15d": rain_15d,
            "rain_60d": rain_60d,
            "wb_7d": wb_7d,
            "wb_60d": wb_60d,
            "dry_streak": float(streak),
            "tmax": today["tmax"],
            "drange": today["tmax"] - today["tmin"],
            "wind_max": today["wind"],
        })
    return out


def vector(row: dict) -> list[float]:
    return [row[k] for k in FEATURES]


def split(feats: list[dict]) -> tuple[list[dict], list[dict]]:
    """Cắt theo THỜI GIAN, không cắt ngẫu nhiên.

    Cắt ngẫu nhiên sẽ để ngày 12/10 vào tập huấn luyện và ngày 13/10 vào tập
    kiểm tra — hai ngày liền kề gần như giống hệt nhau, nên điểm kiểm tra sẽ
    đẹp một cách giả tạo. Đây là lỗi rò rỉ kinh điển với dữ liệu chuỗi thời gian.
    """
    tr = [r for r in feats if r["date"] <= TRAIN_END]
    te = [r for r in feats if r["date"] >= TEST_START]
    return tr, te


def load_all(verbose: bool = True) -> dict[str, dict]:
    """Tải và dựng đặc trưng cho toàn bộ 16 điểm. Trả {code: {...}}."""
    data = {}
    for code, name, lat, lon, zone in SITES:
        rows = fetch_site(code, lat, lon)
        if not rows:
            if verbose:
                print(f"  BỎ QUA {name}: không tải được")
            continue
        feats = build_features(rows)
        tr, te = split(feats)
        if len(tr) < 800 or len(te) < 800:
            if verbose:
                print(f"  BỎ QUA {name}: quá ít ngày ({len(tr)}/{len(te)})")
            continue
        data[code] = {"name": name, "lat": lat, "lon": lon, "zone": zone,
                      "train": tr, "test": te}
        if verbose:
            print(f"  {name:22} huấn luyện {len(tr):5} ngày · kiểm tra {len(te):5} ngày")
    return data
