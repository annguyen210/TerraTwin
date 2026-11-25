"""KHÍ HẬU 2050 CỦA THỬA — mô phỏng CMIP6 HighResMIP, đo bằng HIỆU SỐ so với chính mô hình đó (nâng cấp 24/11/2026).

Câu người mua đất, ngân hàng và giám khảo đều hỏi: "10–25 năm nữa mảnh đất này thế nào?". Dự báo 7 ngày không trả lời
được; lịch sử 10 năm (ERA5, radar) chỉ nói quá khứ. Phần này đưa ra 5 chỉ số khí hậu của ô ~50 km quanh thửa, thời kỳ
2041–2050 so với 1995–2014 (mốc nền của IPCC AR6):

  · ngày nắng nóng (nhiệt độ cao nhất ≥ 35 °C — ngưỡng nắng nóng của Tổng cục KTTV)
  · ngày mưa rất to (≥ 50 mm/ngày — ngưỡng "mưa rất to" của Tổng cục KTTV)
  · lượng mưa ngày lớn nhất trong năm (Rx1day)
  · chuỗi ngày khô dài nhất trong năm (CDD, mưa < 1 mm)
  · tổng lượng mưa năm

TRUNG THỰC VỀ GIỚI HẠN — ghi ngay trên kết quả:
  · Nguồn: Open-Meteo Climate API, 3 mô hình HighResMIP độ phân giải cao của ba nhóm độc lập (EC-Earth3P-HR — châu Âu,
    MRI-AGCM3-2-S — Nhật, ~20 km, MPI-ESM1-2-XR — Đức), hạ quy mô ~10 km. Kịch bản tương lai của HighResMIP là phát thải
    CAO (tương đương SSP5-8.5) — trần trên hợp lý, không phải kịch bản chắc chắn.
  · Dùng HIỆU SỐ tương lai − nền của CÙNG mô hình (phương pháp delta) để khử sai lệch riêng của từng mô hình; giá trị
    nền tuyệt đối của mô hình có thể lệch thực đo — chỉ để tham khảo.
  · Báo trung vị VÀ dải (nhỏ nhất–lớn nhất) giữa 3 mô hình. Mô hình không cùng chiều thì nói "chưa chắc chiều thay đổi".
  · Ô lưới 0,5° (~55 km): đây là khí hậu VÙNG quanh thửa, không phải vi khí hậu của thửa.

Chi phí: một ô mới tốn ~450 lượt gọi Open-Meteo (gói miễn phí 600 lượt/phút, 10.000/ngày) — nên chỉ lưu CHỈ SỐ đã tính
(vài trăm byte, không lưu chuỗi ngày thô ~0,6 MB vào CSDL Neon), giữ 180 ngày, mỗi ô chỉ tính một lần.

Nước biển dâng (thửa ven biển, thấp): IPCC AR6 WG1 bảng 9.9 — mực nước biển trung bình toàn cầu năm 2050 so với
1995–2014: SSP5-8.5 0,23 m (khoảng có khả năng 0,20–0,29 m). Sụt lún ĐBSCL (InSAR, Minderhoud và cộng sự): ~1–3 cm/năm.
"""
from __future__ import annotations

import statistics
from datetime import datetime, timezone

from app.services import cache_store
from app.services.reqlang import tr

URL = "https://climate-api.open-meteo.com/v1/climate"
MODELS = ("EC_Earth3P_HR", "MRI_AGCM3_2_S", "MPI_ESM1_2_XR")
MODEL_NAMES = {"EC_Earth3P_HR": "EC-Earth3P-HR", "MRI_AGCM3_2_S": "MRI-AGCM3-2-S", "MPI_ESM1_2_XR": "MPI-ESM1-2-XR"}
BASE = ("1995-01-01", "2014-12-31")
FUTURE = ("2041-01-01", "2050-12-31")
CELL = 0.5
_TTL = 180 * 86400
_CACHE_V = 1

HOT_C = 35.0          # nắng nóng (Tổng cục KTTV)
HEAVY_MM = 50.0       # mưa rất to (Tổng cục KTTV)
DRY_MM = 1.0          # ngày khô

SLR_2050 = {"median_m": 0.23, "low_m": 0.20, "high_m": 0.29,
            "source": "IPCC AR6 WG1, bảng 9.9 — SSP5-8.5, 2050 so với 1995–2014"}
COASTAL_KM = 30.0
LOW_M = 10.0

# (id, đơn vị, cách so: "abs" = hiệu số tuyệt đối, "pct" = phần trăm)
IND = (("tx35", "days", "abs"), ("r50", "days", "abs"), ("rx1day", "mm", "pct"), ("cdd", "days", "abs"),
       ("prcptot", "mm", "pct"))
NAMES = {
    "tx35": ("Ngày nắng nóng (≥ 35 °C) mỗi năm", "Hot days (≥ 35 °C) per year"),
    "r50": ("Ngày mưa rất to (≥ 50 mm) mỗi năm", "Very heavy rain days (≥ 50 mm) per year"),
    "rx1day": ("Lượng mưa ngày lớn nhất trong năm", "Wettest day of the year"),
    "cdd": ("Chuỗi ngày khô dài nhất trong năm", "Longest dry spell of the year"),
    "prcptot": ("Tổng lượng mưa năm", "Annual rainfall"),
}


def snap(v: float) -> float:
    return round(round(float(v) / CELL) * CELL, 2)


def _url(lat: float, lon: float, start: str, end: str) -> str:
    return (f"{URL}?latitude={lat}&longitude={lon}&start_date={start}&end_date={end}"
            f"&models={','.join(MODELS)}&daily=temperature_2m_max,precipitation_sum")


def yearly_indicators(dates: list[str], tmax: list, pr: list) -> dict | None:
    """5 chỉ số trung bình theo NĂM từ chuỗi ngày. Bỏ ngày thiếu số; năm thiếu > 10% ngày thì bỏ cả năm."""
    by_year: dict[str, list[tuple]] = {}
    for d, t, p in zip(dates, tmax, pr):
        by_year.setdefault(d[:4], []).append((t, p))
    rows = []
    for y, vals in sorted(by_year.items()):
        ok = [(t, p) for t, p in vals if t is not None and p is not None]
        if len(ok) < 0.9 * len(vals) or len(ok) < 300:
            continue
        run = best = 0
        for _t, p in ok:
            run = run + 1 if p < DRY_MM else 0
            best = max(best, run)
        rows.append({"tx35": sum(1 for t, _ in ok if t >= HOT_C), "r50": sum(1 for _, p in ok if p >= HEAVY_MM),
                     "rx1day": max(p for _, p in ok), "cdd": best, "prcptot": sum(p for _, p in ok)})
    if len(rows) < 5:
        return None
    return {k: round(statistics.fmean(r[k] for r in rows), 2) for k, _u, _c in IND} | {"years": len(rows)}


def _per_model(raw: dict) -> dict[str, dict]:
    dd = raw.get("daily") or {}
    out = {}
    for m in MODELS:
        ind = yearly_indicators(dd.get("time") or [], dd.get(f"temperature_2m_max_{m}") or [],
                                dd.get(f"precipitation_sum_{m}") or [])
        if ind:
            out[m] = ind
    return out


def combine(base: dict[str, dict], fut: dict[str, dict]) -> list[dict] | None:
    """Trung vị + dải giữa các mô hình, mỗi mô hình so với CHÍNH NÓ (delta). Cần ≥ 2 mô hình đủ cả hai thời kỳ."""
    ms = [m for m in MODELS if m in base and m in fut]
    if len(ms) < 2:
        return None
    rows = []
    for k, unit, how in IND:
        b = [base[m][k] for m in ms]
        f = [fut[m][k] for m in ms]
        d = [(fut[m][k] - base[m][k]) if how == "abs" else
             (100.0 * (fut[m][k] - base[m][k]) / base[m][k] if base[m][k] else 0.0) for m in ms]
        same_sign = all(x > 0 for x in d) or all(x < 0 for x in d)
        rows.append({"id": k, "unit": unit, "how": how, "base": round(statistics.median(b), 1),
                     "future": round(statistics.median(f), 1), "delta": round(statistics.median(d), 1),
                     "delta_min": round(min(d), 1), "delta_max": round(max(d), 1), "agree": same_sign,
                     "per_model": {m: round(x, 1) for m, x in zip(ms, d)}})
    return rows


def _fetch_period(lat: float, lon: float, period: tuple[str, str]) -> dict | None:
    from app.services import realdata
    host = URL.split("/")[2]
    import time
    if realdata._host_exhausted(host, time.time()):
        return None
    return realdata._fetch(_url(lat, lon, *period), timeout=120.0)


def raw(lat: float, lon: float) -> dict | None:
    """Số đo (không phụ thuộc ngôn ngữ) cho ô 0,5° quanh điểm — nhớ đệm bền 180 ngày. None = chưa lấy được."""
    la, lo = snap(lat), snap(lon)
    key = cache_store.make_key("climate2050", _CACHE_V, la, lo)
    hit = cache_store.get(key)
    if hit is not None:
        return hit
    b = _fetch_period(la, lo, BASE)
    if not b:
        return None
    f = _fetch_period(la, lo, FUTURE)
    if not f:
        return None
    rows = combine(_per_model(b), _per_model(f))
    if rows is None:
        return None
    out = {"cell": {"lat": la, "lon": lo, "size_deg": CELL}, "models": [m for m in MODELS],
           "base": list(BASE), "future": list(FUTURE), "indicators": rows,
           "computed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")}
    cache_store.put(key, out, ttl_seconds=_TTL)
    return out


def localize(r: dict, lat: float, lon: float) -> dict:
    """Câu chữ tính lúc ĐỌC (nhớ đệm dùng chung hai ngôn ngữ) + phần ven biển (khoảng cách biển, độ cao thửa)."""
    from app.services import datasources as ds
    items = []
    for row in r["indicators"]:
        # Bộ chấm trợ lý v4 (25/11/2026): trung vị nền, trung vị tương lai, trung vị thay đổi lấy RIÊNG trên 3 mô hình
        # nên có thể ngược chiều nhau (BMT: 31.9 → 30.4 mm mà "+8.1%"). Giá trị 2041–2050 hiển thị = nền + thay đổi
        # trung vị — luôn khớp con số thay đổi; trung vị tương lai thô giữ ở "future_median".
        row = dict(row)
        row["future_median"] = row["future"]
        row["future"] = round(row["base"] + row["delta"] if row["how"] == "abs"
                              else row["base"] * (1 + row["delta"] / 100.0), 1)
        vi, en = NAMES[row["id"]]
        u_vi, u_en = ("ngày", "days") if row["unit"] == "days" else ("mm", "mm")
        if row["how"] == "abs":
            ch = tr(f"{row['delta']:+g} {u_vi} (3 mô hình: {row['delta_min']:+g} đến {row['delta_max']:+g})",
                    f"{row['delta']:+g} {u_en} (3 models: {row['delta_min']:+g} to {row['delta_max']:+g})")
        else:
            ch = tr(f"{row['delta']:+g}% (3 mô hình: {row['delta_min']:+g}% đến {row['delta_max']:+g}%)",
                    f"{row['delta']:+g}% (3 models: {row['delta_min']:+g}% to {row['delta_max']:+g}%)")
        trend = (tr("các mô hình cùng chiều", "models agree on direction") if row["agree"] else
                 tr("chưa chắc chiều thay đổi — các mô hình không cùng chiều", "direction uncertain — models disagree"))
        items.append({**row, "name": tr(vi, en), "change": ch, "trend": trend,
                      "base_txt": f"{row['base']:g} {tr(u_vi, u_en)}", "future_txt": f"{row['future']:g} {tr(u_vi, u_en)}"})
    out = {**r, "indicators": items, "scenario": tr("phát thải cao (HighResMIP, tương đương SSP5-8.5)",
                                                    "high emissions (HighResMIP, ≈ SSP5-8.5)"),
           "model_names": [MODEL_NAMES[m] for m in r["models"]],
           "caveats": [
               tr("Khí hậu mô phỏng của VÙNG ~55 km quanh thửa, không phải dự báo thời tiết và không phải vi khí hậu của thửa.",
                  "Simulated climate of the ~55 km REGION around the plot — not a weather forecast, not the plot's microclimate."),
               tr("So mỗi mô hình với CHÍNH NÓ thời kỳ 1995–2014 (phương pháp delta) để khử sai lệch mô hình; số nền tuyệt đối "
                  "của mô hình có thể lệch thực đo.",
                  "Each model is compared with ITSELF over 1995–2014 (delta method) to remove model bias; absolute baseline "
                  "values may differ from observations."),
               tr("Kịch bản phát thải cao — trần trên hợp lý của rủi ro, không phải điều chắc chắn xảy ra.",
                  "High-emission scenario — a plausible upper bound of risk, not a certainty."),
           ],
           "sources": ["Open-Meteo Climate API — CMIP6 HighResMIP (" + ", ".join(MODEL_NAMES[m] for m in r["models"]) + ")"]}
    km = ds.distance_to_coast_km(lat, lon)
    if km <= COASTAL_KM:
        try:
            elev = ds.elevation_proxy(lat, lon)
        except Exception:  # noqa: BLE001
            elev = None
        if elev is not None and elev <= LOW_M:
            s = SLR_2050
            txt = tr(f"Thửa cách biển khoảng {km:.0f} km, cao khoảng {elev:g} m (mô hình số độ cao, sai số vài mét ở đồng bằng). "
                     f"Đến 2050 mực nước biển dâng khoảng {s['median_m']:.2f} m (khoảng {s['low_m']:.2f}–{s['high_m']:.2f} m) — "
                     "triều cường và nước dâng do bão sẽ lên cao hơn tương ứng.",
                     f"The plot is about {km:.0f} km from the sea, about {elev:g} m high (elevation model, a few metres of error "
                     f"in deltas). By 2050 sea level rises about {s['median_m']:.2f} m ({s['low_m']:.2f}–{s['high_m']:.2f} m) — "
                     "spring tides and storm surges reach correspondingly higher.")
            if ds.salinity_zone(lat, lon) in ("Đồng bằng sông Cửu Long", "Mekong Delta"):
                txt += tr(" Ở ĐBSCL, đất còn lún khoảng 1–3 cm/năm do khai thác nước ngầm (đo bằng radar giao thoa, Minderhoud "
                          "và cộng sự) — nhiều nơi lún nhanh hơn nước biển dâng.",
                          " In the Mekong Delta the land also sinks about 1–3 cm/year from groundwater pumping (InSAR, "
                          "Minderhoud et al.) — in many places faster than sea-level rise.")
            out["sea_level"] = {**s, "coast_km": round(km, 1), "elevation_m": elev, "text": txt}
            out["sources"].append(s["source"])
    return out


def assess(lat: float, lon: float) -> dict:
    """Kết quả cho API: {available, ...}. Không ném lỗi."""
    try:
        r = raw(lat, lon)
    except Exception:  # noqa: BLE001 — nguồn ngoài hỏng không được làm sập trang
        r = None
    if r is None:
        return {"available": False,
                "message": tr("Chưa lấy được số liệu khí hậu 2050 lúc này (nguồn Open-Meteo đang bận hoặc chặn hạn mức) — "
                              "thử lại sau vài phút. Mỗi vùng chỉ cần tính một lần.",
                              "Could not fetch the 2050 climate data right now (Open-Meteo busy or rate-limited) — try again "
                              "in a few minutes. Each region only needs computing once.")}
    return {"available": True, **localize(r, lat, lon)}
