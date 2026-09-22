"""Nguồn dữ liệu THẬT, miễn phí, không cần API key.

- Open-Meteo (nền ECMWF): dự báo mưa, bốc thoát hơi (ET₀), nhiệt độ, cao độ.
- NASA POWER: bức xạ mặt trời (climatology).
- MET Norway Locationforecast 2.0: dự phòng dự báo mưa/nhiệt khi Open-Meteo bị
  chặn vì hạn mức — xem weather_7d_metno().

Có cache BỀN qua restart (kv_cache) + tự fallback khi offline/timeout để app
luôn chạy. Ảnh vệ tinh Sentinel (quang học/radar) cần API key → thêm ở đây khi
triển khai.
"""
from __future__ import annotations

import json
import math
import os
import time
import urllib.error
import urllib.request

# Trạng thái hạn mức của nguồn dữ liệu miễn phí.
#
# VÌ SAO PHẢI TÁCH RIÊNG: cạn hạn mức thì mọi lời gọi trả 429, và nếu gộp chung
# với "mất mạng" thì người vận hành thấy đúng một câu "chưa lấy được dữ liệu"
# cho hai tình huống khác hẳn nhau — một cái tự khỏi, một cái phải đi sửa.
#
# QUAN SÁT THỰC TẾ, không phải đọc tài liệu: Open-Meteo trả nguyên văn "Daily
# API request limit exceeded. Please try again tomorrow." Ghi chú cũ ở đây nói
# "phục hồi sau khoảng mười phút" — ĐÍNH CHÍNH (đo lại 2026-09-17): chặn liên
# tục 18 phút, 12 lần đo cách nhau 90 giây đều bị chặn, không hồi lần nào. Con
# số "mười phút" lạc quan hơn thực tế đo được — KHÔNG hứa hẹn thời gian phục
# hồi cụ thể trong thông báo nữa, chỉ nói sự thật đo được: đây là hạn mức, tự
# nó có thể qua, không phải lỗi cần đi sửa code.
#
# BỀN QUA RESTART (2026-09-21): trước đây _QUOTA/_QUOTA_LOG/_CACHE là dict
# trong RAM. Render free dựng lại tiến trình liên tục (ngủ rồi thức, redeploy,
# OOM) — đo được thật: count_429_24h đọc 38 rồi về 0 mà KHÔNG có deploy nào ở
# giữa, tức tiến trình tự restart và bộ đếm mất sạch. Tệ hơn: mất _CACHE nghĩa
# là MỌI lần restart đều nã lại Open-Meteo cho mọi toạ độ đang hoạt động —
# chính nguyên nhân sinh ra 38 lần 429 mà công cụ đo lại không sống nổi để đo.
# Chuyển cả ba xuống kv_cache (bảng DB, đã dùng cho passport/scorecard/heatmap)
# — cùng cách đã làm cho nhật ký lượt quét radar.
_QUOTA_TTL = 1800.0                # sau nửa giờ không tái diễn thì coi như đã qua
_QUOTA_LOG_WINDOW = 86400.0


def _quota_key(host: str) -> str:
    from app.services import cache_store
    return cache_store.make_key("quota", host)


def _record_429(host: str) -> None:
    from app.services import cache_store

    now = time.time()
    key = _quota_key(host)
    row = cache_store.get(key) or {"last": 0.0, "log": []}
    if now - row.get("last", 0.0) > _QUOTA_TTL:
        from app.safelog import log
        log(f"[TerraTwin] {host}: bi chan vi qua han muc (HTTP 429). "
            f"Moi ket qua se bao 'chua du du lieu'.")
    log_ = [t for t in row.get("log", []) if now - t < _QUOTA_LOG_WINDOW]
    log_.append(now)
    cache_store.put(key, {"last": now, "log": log_},
                    ttl_seconds=int(_QUOTA_LOG_WINDOW) + 3600)


def _host_exhausted(host: str, now: float | None = None) -> bool:
    """Host này có đang trong cửa sổ BIẾT LÀ bị chặn không (đo lần 429 gần
    nhất, xem _QUOTA_TTL)?

    2026-09-22 (đo production sau khi bật MET Norway): count_429_24h vọt lên
    288 — vì weather_7d() vẫn cứ THỬ Open-Meteo trước ở MỖI lượt gọi rồi mới
    rơi xuống MET Norway, kể cả khi ĐÃ BIẾT chắc host đang bị chặn từ lần 429
    trước đó vài giây. Gọi hàm này TRƯỚC khi thử một host — biết chắc đang bị
    chặn thì bỏ qua thẳng, đỡ một lượt gọi vô ích (và đỡ làm phồng bộ đếm 429
    bằng chính những lượt gọi mà ta đã biết trước kết quả)."""
    from app.services import cache_store
    now = time.time() if now is None else now
    row = cache_store.get(_quota_key(host))
    if not row:
        return False
    return now - row.get("last", 0.0) < _QUOTA_TTL


# Danh sách CỐ ĐỊNH — mọi host thật sự được gọi trong file này (+ probabilistic
# .py, dùng chung realdata._get). kv_cache không hỗ trợ "liệt kê mọi khoá khớp
# tiền tố kèm giá trị", nên phải biết trước tên để tự đọc từng cái thay vì dò
# động như bản dict cũ.
_KNOWN_HOSTS = (
    "api.open-meteo.com", "archive-api.open-meteo.com",
    "flood-api.open-meteo.com", "marine-api.open-meteo.com",
    "ensemble-api.open-meteo.com", "power.larc.nasa.gov",
    "api.met.no",
)


def quota_status() -> dict:
    """Nguồn nào đang bị chặn vì quá hạn mức, và cách đây bao lâu."""
    from app.services import cache_store

    now = time.time()
    hit: dict[str, float] = {}
    counts_24h: dict[str, int] = {}
    for host in _KNOWN_HOSTS:
        row = cache_store.get(_quota_key(host))
        if not row:
            continue
        last = row.get("last", 0.0)
        if now - last < _QUOTA_TTL:
            hit[host] = round((now - last) / 60.0, 1)
        n = len([t for t in row.get("log", []) if now - t < _QUOTA_LOG_WINDOW])
        if n:
            counts_24h[host] = n
    return {
        "exhausted": sorted(hit),
        "minutes_since_detected": hit,
        "count_429_24h": counts_24h,
        "message": (
            "Đang bị nguồn dữ liệu chặn vì gọi quá nhiều: " + ", ".join(sorted(hit))
            + ". Đây là hạn mức của nguồn miễn phí, thường tự qua — nhưng đo "
              "thực tế 2026-09-17 cho thấy có lúc kéo dài hơn 18 phút liên tục, "
              "không phải mười phút như từng ghi. Nếu lặp lại nhiều khi có "
              "người dùng thật thì tăng thời gian cache hoặc nâng gói Open-Meteo."
            if hit else "Chưa nguồn nào bị chặn vì quá hạn mức."),
    }

# THỜI GIAN CACHE THEO TỪNG NGUỒN (2026-09-21) — trước đây MỘT hằng số 1800s
# áp cho mọi URL. Sai ở cả hai đầu: cao độ mặt đất KHÔNG BAO GIỜ đổi mà bị gọi
# lại mỗi 30 phút (lãng phí lượt gọi vô ích, góp phần đốt hạn mức); dự báo thời
# tiết mà Open-Meteo cũng chỉ CHẠY MÔ HÌNH mới vài giờ một lần, nên cache 30
# phút không "tươi" hơn cache 3 giờ chút nào, chỉ tốn thêm 6x lượt gọi.
_TTL_FOREVER = 3650 * 86400   # ~10 năm — cao độ, không đổi theo thời gian
_TTL_30D = 30 * 86400         # ERA5 lịch sử — dữ liệu quá khứ, không đổi
_TTL_3H = 3 * 3600            # dự báo (forecast/marine/ensemble/MET Norway)
_TTL_6H = 6 * 3600            # lưu lượng sông (flood-api)
_STALE_MAX = 12 * 3600        # phao cứu sinh khi gọi mạng hỏng — nâng từ 6h


def _ttl_for(url: str) -> tuple[int, int]:
    """(TTL mới, hạn phao cứu sinh) theo loại nguồn suy từ chính URL."""
    if "/v1/elevation" in url:
        return _TTL_FOREVER, _TTL_FOREVER
    if "archive-api." in url:
        return _TTL_30D, _TTL_30D
    if "flood-api." in url:
        return _TTL_6H, _STALE_MAX
    # /v1/forecast (Open-Meteo), marine-api, ensemble-api, api.met.no —
    # đều là dự báo, đổi theo giờ chứ không theo phút.
    return _TTL_3H, _STALE_MAX


# ĐẾM LỜI GỌI — cho /api/health biết một lượt quét 18 mô-đun thật sự tốn bao
# nhiêu lượt ra ngoài và tỉ lệ trúng cache, để chẩn đoán "đang gọi thừa ở đâu"
# thay vì đoán. Chỉ là đồng hồ đo TỪ LÚC TIẾN TRÌNH NÀY khởi động — không cần
# bền qua restart vì đây là chỉ báo sống, không phải dữ liệu cần giữ.
_CALLS_TOTAL = 0
_CALLS_HIT = 0


def call_stats() -> dict:
    return {
        "total": _CALLS_TOTAL,
        "cache_hits": _CALLS_HIT,
        "hit_rate_pct": (round(100.0 * _CALLS_HIT / _CALLS_TOTAL, 1)
                        if _CALLS_TOTAL else None),
    }


def _fetch(url: str, timeout: float, headers: dict | None = None):
    """Gọi mạng thật. Đi qua trần đồng thời để không nã dồn nguồn miễn phí.

    GIỚI HẠN CẦN BIẾT: `timeout` chỉ chi phối lúc kết nối và lúc đọc, KHÔNG chi
    phối lúc phân giải tên miền — getaddrinfo() của Python không nhận timeout.
    Nếu DNS treo thì luồng này giữ luôn giấy phép của trần đồng thời cho tới
    khi hệ điều hành bỏ cuộc. Đã quan sát thấy thật: một lần phân giải treo làm
    bộ test đứng im hơn hai mươi phút.

    Vì sao chấp nhận được trong sản phẩm: trần đồng thời có thời hạn chờ riêng,
    nên các yêu cầu khác trả None nhanh thay vì xếp hàng vô tận — hỏng một chỗ
    chứ không kéo sập cả hệ. Muốn chữa tận gốc thì phải phân giải DNS ở luồng
    riêng hoặc dùng thư viện có bể kết nối; cả hai đều thêm phụ thuộc, nên chỉ
    làm khi có người dùng thật và đo được là nó xảy ra thường xuyên.
    """
    from app.services import jobs

    with jobs.upstream() as allowed:
        if not allowed:
            # Hàng đợi ra ngoài tắc quá lâu. Trả None đúng như khi mất mạng —
            # người gọi đã biết xử lý None; treo thì không ai xử lý được.
            return None
        try:
            req = urllib.request.Request(
                url, headers=headers or {"User-Agent": "TerraTwin/0.2"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                host = url.split("/")[2] if "//" in url else url[:40]
                _record_429(host)
            return None
        except Exception:
            return None


def _cache_key(url: str) -> str:
    from app.services import cache_store
    return cache_store.make_key("realdata", url)


def _get(url: str, timeout: float = 8.0, headers: dict | None = None):
    """Lấy JSON có cache BỀN (kv_cache, sống qua restart) + GỘP những lời gọi
    trùng nhau đang chạy cùng lúc.

    Cache thường chỉ cứu từ lượt thứ hai trở đi. Khi nhiều người cùng hỏi một
    toạ độ trong cùng một giây — chuyện xảy ra ngay trong một lượt quét toàn
    cảnh, trong bản đồ nhiệt, và trong mọi lần demo trước đám đông — thì tất cả
    đều thấy cache rỗng và cùng gọi ra ngoài. `single_flight` để đúng MỘT lượt
    chạy, số còn lại chờ chung kết quả đó.

    PHAO CỨU SINH KHI GỌI MẠNG HỎNG: nếu fetch thất bại (mất mạng HOẶC 429)
    nhưng có bản cache CŨ (quá TTL nhưng chưa quá hạn phao cứu sinh), trả bản
    cũ đó thay vì None. Đây VẪN LÀ dữ liệu thật, chỉ không mới bằng bình
    thường — trung thực hơn hẳn so với rơi xuống mô hình mẫu chỉ vì cache vừa
    hết hạn đúng lúc nguồn đang bị hạn mức chặn.
    """
    global _CALLS_TOTAL, _CALLS_HIT
    from app.services import cache_store, jobs

    key = _cache_key(url)
    ttl, stale_max = _ttl_for(url)
    now = time.time()
    _CALLS_TOTAL += 1
    cached = cache_store.get(key)
    if cached and now - cached["at"] < ttl:
        _CALLS_HIT += 1
        return cached["data"]

    def _work():
        # Kiểm lại trong "phòng chờ": người dẫn đầu có thể vừa ghi cache xong
        # ngay trước khi ta bước vào đây.
        h = cache_store.get(key)
        now2 = time.time()
        if h and now2 - h["at"] < ttl:
            return h["data"]

        # BIẾT TRƯỚC là host này đang bị chặn (429 gần đây, còn trong
        # _QUOTA_TTL) thì bỏ qua thẳng, không thử lại — đo được production
        # 2026-09-22: không bỏ qua thì count_429_24h vọt lên 288 vì mỗi lượt
        # gọi đều tự lặp lại đúng lượt gọi ĐÃ BIẾT TRƯỚC là sẽ bị chặn.
        host = url.split("/")[2] if "//" in url else url[:40]
        data = None if _host_exhausted(host, now2) else _fetch(url, timeout, headers=headers)
        if data is not None:
            cache_store.put(key, {"at": now2, "data": data}, max(ttl, stale_max))
            return data
        # Gọi mạng hỏng (hoặc bỏ qua vì đã biết bị chặn) — dùng bản CŨ nếu còn
        # trong hạn phao cứu sinh.
        if h and now2 - h["at"] < stale_max:
            return h["data"]
        return None

    return jobs.single_flight(f"om:{url}", _work)


def _bust(url: str) -> None:
    """Xóa cache một URL để lần gọi sau fetch lại (tự lành khi response hỏng).

    CỐ Ý xoá hẳn thay vì chỉ đánh dấu hết hạn: response từng lưu là HỎNG (thiếu
    trường, mảng toàn null) — không phải thứ muốn dùng làm phao cứu sinh cho
    lần gọi sau.
    """
    from app.services import cache_store
    cache_store.delete(_cache_key(url))


def _num(x):
    """Trả float nếu là số thật; None nếu thiếu dữ liệu (KHÔNG nhầm null thành 0)."""
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def weather_7d(lat: float, lon: float):
    """Dự báo 7 ngày THẬT. Trả list dict {day,date,precip,et0,tmax,source} hoặc
    None. `source` = "open-meteo" hoặc "metno" — xem weather_7d_metno().

    Phân biệt null (thiếu dữ liệu) vs 0.0 (thật sự không mưa). Nếu Open-Meteo trả
    mảng mưa toàn null (dữ liệu chưa sẵn), coi như KHÔNG hợp lệ → None + xóa cache
    để lần sau fetch lại (tránh 'khô giả' bị kẹt 30 phút).

    NGUỒN DỰ PHÒNG (2026-09-21): Open-Meteo dùng CHUNG hạn mức cho mọi tiến
    trình chạy trên IP dùng chung của Render — đo được thật: 100% lượt gọi
    /v1/forecast từ production bị 429, trong khi gọi cùng toạ độ từ máy ngoài
    Render vẫn bình thường. Cache dài hơn (xem _ttl_for) giảm SỐ LƯỢT gọi,
    nhưng không cứu được lượt gọi ĐẦU TIÊN cho một toạ độ chưa từng quét — lúc
    đó bắt buộc phải có nguồn thứ hai, nếu không is_real=False vĩnh viễn cho
    bất kỳ ai bấm vào chỗ chưa ai bấm trước. MET Norway Locationforecast dùng
    IP khác, hạn mức khác — không cùng bị chặn.
    """
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&daily=precipitation_sum,et0_fao_evapotranspiration,temperature_2m_max"
        "&forecast_days=7&timezone=auto"
    )
    d = _get(url)
    if d and "daily" in d:
        dd = d["daily"]
        try:
            times = dd["time"]
            precip = [_num(v) for v in dd.get("precipitation_sum", [])]
            et0 = [_num(v) for v in dd.get("et0_fao_evapotranspiration", [])]
            tmax = [_num(v) for v in dd.get("temperature_2m_max", [])]
        except (KeyError, TypeError):
            times = None
        else:
            # Bắt buộc có ≥ nửa số ngày với lượng mưa thật; nếu không → dữ
            # liệu chưa sẵn.
            valid_precip = [p for p in precip if p is not None]
            if not times or len(valid_precip) < max(1, len(times) // 2):
                times = None

        if times:
            return [
                {
                    "day": i, "date": times[i],
                    "precip": precip[i] if i < len(precip) and precip[i] is not None else 0.0,
                    "et0": et0[i] if i < len(et0) and et0[i] is not None else 0.0,
                    "tmax": tmax[i] if i < len(tmax) and tmax[i] is not None else 0.0,
                    "source": "open-meteo",
                }
                for i in range(len(times))
            ]
        _bust(url)   # response có nhưng hỏng (thiếu trường/toàn null) — xoá hẳn

    return weather_7d_metno(lat, lon)


# ---------------------------------------------------------------------------
# NGUỒN DỰ PHÒNG — MET Norway Locationforecast 2.0 (miễn phí, không khoá)
# ---------------------------------------------------------------------------

_METNO_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"


def _metno_headers() -> dict:
    # BẮT BUỘC theo điều kiện dùng của MET Norway: User-Agent nhận dạng được
    # ứng dụng + cách liên hệ. Không đặt TERRATWIN_METNO_CONTACT vẫn chạy được
    # (repo công khai đủ để họ liên hệ nếu cần), nhưng nên đặt thật khi deploy.
    contact = os.environ.get("TERRATWIN_METNO_CONTACT",
                             "https://github.com/annguyen210/TerraTwin")
    return {"User-Agent": f"TerraTwin/1.0 ({contact})"}


def _extraterrestrial_radiation_mm(lat_deg: float, doy: int) -> float:
    """Bức xạ ngoài khí quyển Ra, quy đổi ra mm/ngày tương đương (FAO-56 #21-25).

    Tính được thẳng từ vĩ độ + ngày trong năm — KHÔNG cần đo bức xạ thật, nên
    dùng được để ước lượng ET0 khi nguồn chỉ cho nhiệt độ (MET Norway không có
    et0_fao_evapotranspiration sẵn như Open-Meteo).
    """
    phi = math.radians(lat_deg)
    dr = 1 + 0.033 * math.cos(2 * math.pi * doy / 365)
    delta = 0.409 * math.sin(2 * math.pi * doy / 365 - 1.39)
    x = max(-1.0, min(1.0, -math.tan(phi) * math.tan(delta)))
    ws = math.acos(x)
    ra_mj = ((24 * 60 / math.pi) * 0.0820 * dr *
             (ws * math.sin(phi) * math.sin(delta)
              + math.cos(phi) * math.cos(delta) * math.sin(ws)))
    return max(0.0, ra_mj * 0.408)   # MJ/m²/ngày → mm/ngày tương đương


def _hargreaves_et0(tmin: float, tmax: float, tmean: float,
                    lat: float, doy: int) -> float:
    """ET0 kiểu Hargreaves-Samani — chỉ cần tmin/tmax/vĩ độ. ƯỚC LƯỢNG VẬT LÝ
    thật (công thức FAO-56 chuẩn), không phải số bịa, nhưng thô hơn phiên bản
    Penman-Monteith đầy đủ mà Open-Meteo dùng (cần độ ẩm, gió, bức xạ đo thật)."""
    if tmax <= tmin:
        return 0.0
    ra = _extraterrestrial_radiation_mm(lat, doy)
    return max(0.0, 0.0023 * (tmean + 17.8) * math.sqrt(tmax - tmin) * ra)


def weather_7d_metno(lat: float, lon: float):
    """Dự phòng cho weather_7d() khi Open-Meteo bị chặn/mất mạng. Trả cùng
    khuôn {day,date,precip,et0,tmax,source} hoặc None — is_real=True vẫn đúng,
    đây LÀ dữ liệu đo thật, chỉ khác nguồn.

    Gộp timeseries theo giờ/6 giờ của MET Norway thành từng ngày lịch (quy đổi
    thô sang giờ VN = UTC+7, đủ cho tổng mưa/đỉnh nhiệt theo ngày, không cần
    múi giờ chính xác tuyệt đối). Chỉ dùng field `next_6_hours` cho mưa — đó
    là field duy nhất phủ đều suốt cả tuần dự báo trong sản phẩm "compact"
    (next_1_hours co lại chỉ còn vài chục giờ đầu, next_12_hours thô hơn).
    """
    from datetime import datetime as _dt
    from datetime import timedelta as _td

    url = f"{_METNO_URL}?lat={lat:.4f}&lon={lon:.4f}"
    d = _get(url, timeout=10.0, headers=_metno_headers())
    if not d:
        return None
    try:
        series = d["properties"]["timeseries"]
    except (KeyError, TypeError):
        return None

    by_day: dict[str, dict] = {}
    for entry in series:
        try:
            t = _dt.fromisoformat(entry["time"].replace("Z", "+00:00"))
        except (KeyError, ValueError, TypeError):
            continue
        local = t + _td(hours=7)
        day_key = local.strftime("%Y-%m-%d")
        info = by_day.setdefault(day_key, {"precip": 0.0, "temps": [], "has_precip": False})

        data = entry.get("data") or {}
        inst = (data.get("instant") or {}).get("details") or {}
        temp = inst.get("air_temperature")
        if isinstance(temp, (int, float)):
            info["temps"].append(float(temp))

        six = (data.get("next_6_hours") or {}).get("details") or {}
        precip6 = six.get("precipitation_amount")
        if isinstance(precip6, (int, float)):
            info["precip"] += float(precip6)
            info["has_precip"] = True

    days = sorted(by_day)[:7]
    rows = []
    for i, day_key in enumerate(days):
        info = by_day[day_key]
        temps = info["temps"]
        if not temps:
            continue
        tmax, tmin = max(temps), min(temps)
        tmean = sum(temps) / len(temps)
        doy = _dt.strptime(day_key, "%Y-%m-%d").timetuple().tm_yday
        rows.append({
            "day": i, "date": day_key,
            "precip": round(info["precip"], 1),
            "et0": round(_hargreaves_et0(tmin, tmax, tmean, lat, doy), 2),
            "tmax": round(tmax, 1),
            "source": "metno",
        })

    # Cùng tiêu chí với weather_7d(): cần đủ mẫu để không phải 'khô giả'.
    valid_precip_days = sum(1 for r, dk in zip(rows, days) if by_day[dk]["has_precip"])
    if len(rows) < 4 or valid_precip_days < max(1, len(rows) // 2):
        return None
    return rows


# Open-Meteo chỉ nhận tối đa 100 toạ độ mỗi lần gọi; quá số này API trả lỗi và
# ta sẽ mất TOÀN BỘ lô. Mọi hàm *_multi vì thế phải tự chia lô bên trong —
# bên gọi không cần biết giới hạn này.
_MAX_POINTS = 100


def _chunks(points: list, size: int = _MAX_POINTS):
    for i in range(0, len(points), size):
        yield points[i:i + size]


def _parallel_chunks(points, build_url, timeout):
    """Chia lô rồi gọi các lô ĐỒNG THỜI, ghép lại đúng thứ tự.

    Open-Meteo chỉ nhận 100 toạ độ mỗi lượt, nên lưới bộ gen 180 ô hay bản đồ
    nhiệt 11x11 phải chia thành nhiều lô. Trước đây các lô chạy nối tiếp: lô sau
    chờ lô trước xong. Chúng độc lập hoàn toàn nên chạy cùng lúc được, và trần
    đồng thời trong jobs.upstream() vẫn giữ cho nguồn miễn phí không bị nã dồn.

    Lô nào hỏng trả None cho đúng số điểm của lô đó — KHÔNG được lệch chỉ số,
    vì người gọi ghép kết quả theo vị trí với danh sách điểm ban đầu.
    """
    from app.services import jobs

    lots = list(_chunks(points))

    def _task(chunk):
        return lambda: _get(build_url(chunk), timeout=timeout)

    responses = jobs.gather([_task(c) for c in lots])

    out = []
    for chunk, d in zip(lots, responses):
        if d is None:
            out.extend([None] * len(chunk))
            continue
        # Một điểm -> Open-Meteo trả object; nhiều điểm -> trả mảng.
        items = d if isinstance(d, list) else [d]
        out.extend(_rows_from_daily(items[i] if i < len(items) else None)
                   for i in range(len(chunk)))
    return out


def historical_weather_multi(points: list[tuple[float, float]],
                             start: str, end: str):
    """Thời tiết lịch sử (ERA5) cho NHIỀU điểm trong MỘT lần gọi.

    Archive API cũng nhận danh sách toạ độ, nên dựng được bộ gen khí hậu cho cả
    lưới toàn quốc mà không phải gọi hàng trăm lượt. Trả list (cùng thứ tự với
    `points`) gồm list dict hoặc None.
    """
    if not points:
        return []

    def _url(chunk):
        lat_q = ",".join(f"{la:.4f}" for la, _ in chunk)
        lon_q = ",".join(f"{lo:.4f}" for _, lo in chunk)
        return (
            "https://archive-api.open-meteo.com/v1/archive"
            f"?latitude={lat_q}&longitude={lon_q}"
            f"&start_date={start}&end_date={end}"
            "&daily=precipitation_sum,et0_fao_evapotranspiration,temperature_2m_max"
            "&timezone=auto"
        )

    return _parallel_chunks(points, _url, 120.0)


def weather_multi(points: list[tuple[float, float]]):
    """Dự báo 7 ngày cho NHIỀU điểm trong MỘT lần gọi.

    Open-Meteo nhận danh sách toạ độ phân tách bằng dấu phẩy — 49 điểm chỉ tốn
    ~0,4 s và một lượt gọi. Đây là thứ khiến bản đồ nhiệt (C06) khả thi mà không
    đốt hết hạn mức. Trả list (cùng thứ tự với `points`) gồm list dict hoặc None.
    """
    if not points:
        return []

    def _url(chunk):
        lat_q = ",".join(f"{la:.4f}" for la, _ in chunk)
        lon_q = ",".join(f"{lo:.4f}" for _, lo in chunk)
        return (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat_q}&longitude={lon_q}"
            "&daily=precipitation_sum,et0_fao_evapotranspiration,temperature_2m_max"
            "&forecast_days=7&timezone=auto"
        )

    return _parallel_chunks(points, _url, 25.0)


def _rows_from_daily(item):
    """Chuyển một phần tử phản hồi Open-Meteo thành list dict, hoặc None."""
    if not item or "daily" not in item:
        return None
    dd = item["daily"]
    try:
        times = dd["time"]
        precip = [_num(v) for v in dd.get("precipitation_sum", [])]
        et0 = [_num(v) for v in dd.get("et0_fao_evapotranspiration", [])]
        tmax = [_num(v) for v in dd.get("temperature_2m_max", [])]
    except (KeyError, TypeError):
        return None
    if not times or len([p for p in precip if p is not None]) < max(1, len(times) // 2):
        return None
    return [
        {"day": i, "date": times[i],
         "precip": precip[i] if i < len(precip) and precip[i] is not None else 0.0,
         "et0": et0[i] if i < len(et0) and et0[i] is not None else 0.0,
         "tmax": tmax[i] if i < len(tmax) and tmax[i] is not None else 0.0}
        for i in range(len(times))
    ]


def elevation_multi(points: list[tuple[float, float]]):
    """Cao độ cho nhiều điểm trong một lần gọi. Trả list float|None."""
    if not points:
        return []
    from app.services import jobs

    lots = list(_chunks(points))

    def _task(chunk):
        lat_q = ",".join(f"{la:.5f}" for la, _ in chunk)
        lon_q = ",".join(f"{lo:.5f}" for _, lo in chunk)
        url = ("https://api.open-meteo.com/v1/elevation"
               f"?latitude={lat_q}&longitude={lon_q}")
        return lambda: _get(url, timeout=20.0)

    responses = jobs.gather([_task(c) for c in lots])

    out: list[float | None] = []
    for chunk, d in zip(lots, responses):
        try:
            vals = [float(x) for x in d["elevation"]]
        except (KeyError, TypeError, ValueError):
            out.extend([None] * len(chunk))
            continue
        out.extend(vals[i] if i < len(vals) else None for i in range(len(chunk)))
    return out


def elevation_m(lat: float, lon: float):
    d = _get(f"https://api.open-meteo.com/v1/elevation?latitude={lat}&longitude={lon}")
    try:
        return float(d["elevation"][0])
    except (KeyError, IndexError, TypeError):
        return None


def slope_deg(lat: float, lon: float, step_m: float = 500.0):
    """Độ dốc THẬT (độ) từ chênh cao độ 4 hướng lân cận (Open-Meteo DEM).

    Lấy cao độ tại tâm + Bắc/Nam/Đông/Tây cách ~step_m, tính gradient địa hình
    rồi quy ra góc dốc. Trả None nếu không lấy được dữ liệu.
    """
    dlat = step_m / 111_320.0
    dlon = step_m / (111_320.0 * max(0.1, math.cos(math.radians(lat))))
    # thứ tự: tâm, Bắc, Nam, Đông, Tây
    lats = [lat, lat + dlat, lat - dlat, lat, lat]
    lons = [lon, lon, lon, lon + dlon, lon - dlon]
    lat_q = ",".join(f"{v:.5f}" for v in lats)
    lon_q = ",".join(f"{v:.5f}" for v in lons)
    d = _get(f"https://api.open-meteo.com/v1/elevation?latitude={lat_q}&longitude={lon_q}")
    try:
        e = [float(x) for x in d["elevation"]]
        _c, n, s, ea, w = e[0], e[1], e[2], e[3], e[4]
        dz_ns = (n - s) / (2 * step_m)
        dz_ew = (ea - w) / (2 * step_m)
        grad = math.hypot(dz_ns, dz_ew)
        return round(math.degrees(math.atan(grad)), 1)
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def historical_weather(lat: float, lon: float, start: str, end: str):
    """Thời tiết THẬT trong quá khứ (Open-Meteo Archive, nền ERA5, không cần key).

    Dùng cho backtest kiểm chứng: model có báo trước sự kiện thật hay không.
    Trả list dict {day,date,precip,et0,tmax} hoặc None.
    """
    url = (
        "https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={lat}&longitude={lon}"
        f"&start_date={start}&end_date={end}"
        "&daily=precipitation_sum,et0_fao_evapotranspiration,temperature_2m_max"
        "&timezone=auto"
    )
    d = _get(url, timeout=15.0)
    if not d or "daily" not in d:
        return None
    dd = d["daily"]
    try:
        return [
            {
                "day": i,
                "date": dd["time"][i],
                "precip": float(dd["precipitation_sum"][i] or 0.0),
                "et0": float((dd.get("et0_fao_evapotranspiration") or [])[i] or 0.0),
                "tmax": float((dd.get("temperature_2m_max") or [])[i] or 0.0),
            }
            for i in range(len(dd["time"]))
        ]
    except (KeyError, IndexError, TypeError):
        return None


def river_discharge_7d(lat: float, lon: float):
    """Lưu lượng sông THẬT 7 ngày (GloFAS qua Open-Meteo Flood API, không cần key).

    Trả list dict {day, date, discharge, mean} hoặc None. `mean` là trung bình
    khí hậu của chính đoạn sông đó — nên tỉ số discharge/mean đã là dị thường
    chuẩn hoá sẵn, không cần tự dựng khí hậu nền.

    Đây là tín hiệu lũ mà cơ quan phòng chống thiên tai thực sự dùng: mưa mới
    là nguyên nhân, lưu lượng sông mới là thứ gây ngập.
    """
    url = (
        "https://flood-api.open-meteo.com/v1/flood"
        f"?latitude={lat}&longitude={lon}"
        "&daily=river_discharge,river_discharge_mean&forecast_days=7"
    )
    d = _get(url, timeout=12.0)
    if not d or "daily" not in d:
        return None
    dd = d["daily"]
    try:
        times = dd["time"]
        cur = [_num(v) for v in dd.get("river_discharge", [])]
        mean = [_num(v) for v in dd.get("river_discharge_mean", [])]
    except (KeyError, TypeError):
        _bust(url)
        return None
    if not times or not any(v is not None for v in cur):
        _bust(url)
        return None
    return [
        {"day": i, "date": times[i],
         "discharge": cur[i] if i < len(cur) else None,
         "mean": mean[i] if i < len(mean) else None}
        for i in range(len(times))
    ]


def marine_7d(lat: float, lon: float):
    """Nhiệt mặt nước & sóng THẬT 7 ngày (Open-Meteo Marine API, không cần key).

    Chỉ có dữ liệu ở điểm biển/ven biển; sâu trong đất liền trả None.
    Trả list dict {day, date, sst, wave} hoặc None.
    """
    url = (
        "https://marine-api.open-meteo.com/v1/marine"
        f"?latitude={lat}&longitude={lon}"
        "&daily=sea_surface_temperature_max,wave_height_max&forecast_days=7"
    )
    d = _get(url, timeout=12.0)
    if not d or "daily" not in d:
        return None
    dd = d["daily"]
    try:
        times = dd["time"]
        sst = [_num(v) for v in dd.get("sea_surface_temperature_max", [])]
        wave = [_num(v) for v in dd.get("wave_height_max", [])]
    except (KeyError, TypeError):
        _bust(url)
        return None
    # Không có nhiệt mặt nước ⇒ điểm này không phải vùng nước → coi như không hỗ trợ.
    if not times or not any(v is not None for v in sst):
        _bust(url)
        return None
    return [
        {"day": i, "date": times[i],
         "sst": sst[i] if i < len(sst) else None,
         "wave": wave[i] if i < len(wave) else None}
        for i in range(len(times))
    ]


def solar_annual(lat: float, lon: float):
    """Bức xạ mặt trời trung bình năm (kWh/m²/ngày) từ NASA POWER."""
    url = (
        "https://power.larc.nasa.gov/api/temporal/climatology/point"
        "?parameters=ALLSKY_SFC_SW_DWN&community=RE"
        f"&longitude={lon}&latitude={lat}&format=JSON"
    )
    d = _get(url, timeout=12.0)
    try:
        return float(d["properties"]["parameter"]["ALLSKY_SFC_SW_DWN"]["ANN"])
    except (KeyError, TypeError):
        return None
