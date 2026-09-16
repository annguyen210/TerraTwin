"""S03 — Goal-Seek: mô phỏng NGƯỢC.

Dự báo trả lời "sắp xảy ra gì". Goal-Seek trả lời câu người dùng thật sự hỏi:
  - Đang nguy hiểm → "cần điều kiện gì thì mới an toàn?"
  - Đang an toàn   → "còn chịu được bao nhiêu nữa trước khi vượt ngưỡng?"

Cách làm: tìm kiếm nhị phân trên chính mô hình chỉ số đang chạy (hàm thuần,
đơn điệu theo lượng mưa/địa hình) → kết quả kiểm chứng được, không phải AI đoán.
"""
from __future__ import annotations

from app.services import datasources as ds
from app.services import hazard
from app.services import realdata
from app.services.reqlang import tr

_ITERS = 40          # đủ để sai số < 1e-6 trên khoảng tìm kiếm
_RAIN_MAX = 20.0     # trần hệ số mưa khi dò biên an toàn


def _fmt_mult(x: float) -> str:
    """Hệ số mưa có thể rất nhỏ (0.007) — làm tròn 2 chữ số là sai 40%."""
    if x >= 1.0:
        return f"{x:.2f}"
    if x >= 0.01:
        return f"{x:.3f}"
    return f"{x:.4f}"


def _peak_at_rain(module_id, lat, lon, rows, mult: float) -> float:
    return hazard.peak_of(
        hazard.index_series(module_id, lat, lon, hazard.transform(rows, rain_mult=mult))
    )


def _peak_at_terrain(module_id, lat, lon, rows, terrain: float) -> float:
    """Đỉnh khi ép giá trị địa hình — cùng tầng hiệu chuẩn với baseline."""
    from app.services import calibration
    s, ok = calibration.calibrated_with_terrain(module_id, lat, lon, rows, terrain)
    if ok and s:
        return hazard.peak_of(s)
    if module_id == "flood":
        return hazard.peak_of(ds.flood_index(rows, terrain))
    return hazard.peak_of(ds.landslide_index(rows, terrain))


def _solve(fn, lo: float, hi: float, target: float, rising: bool) -> float | None:
    """Tìm x trong [lo,hi] sao cho fn(x) ≈ target. `rising`: fn tăng theo x."""
    flo, fhi = fn(lo), fn(hi)
    if rising and not (flo <= target <= fhi):
        return None
    if not rising and not (fhi <= target <= flo):
        return None
    for _ in range(_ITERS):
        mid = (lo + hi) / 2.0
        v = fn(mid)
        if (v < target) == rising:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def run(module_id: str, lat: float, lon: float,
        target: float | None = None) -> dict | None:
    if not hazard.supports(module_id):
        return None
    name, unit = hazard.name_unit(module_id)
    target = hazard.SAFE if target is None else float(target)

    rows = realdata.weather_7d(lat, lon)
    if not rows:
        return {
            "module_id": module_id, "module_name": name, "unit": unit,
            "available": False, "is_real": False,
            "message": tr("Chưa lấy được thời tiết thật — không mô phỏng ngược trên số liệu mẫu.",
                          "Couldn't fetch real weather — no inverse simulation on sample data."),
            "levers": [],
        }

    current = _peak_at_rain(module_id, lat, lon, rows, 1.0)
    safe_now = current < target
    levers: list[dict] = []

    # --- Đòn bẩy 1: LƯỢNG MƯA ---
    f_rain = lambda m: _peak_at_rain(module_id, lat, lon, rows, m)
    if safe_now:
        x = _solve(f_rain, 1.0, _RAIN_MAX, target, rising=True)
        if x is None:
            levers.append({
                "lever": tr("Lượng mưa", "Rainfall"), "kind": "headroom", "feasible": True,
                "answer": tr(f"Chịu được mưa gấp hơn {_RAIN_MAX:.0f} lần mà vẫn dưới ngưỡng.",
                             f"Can take over {_RAIN_MAX:.0f}× the rain and still stay below threshold."),
                "value": None,
            })
        else:
            levers.append({
                "lever": tr("Lượng mưa", "Rainfall"), "kind": "headroom", "feasible": True,
                "answer": tr(f"Còn chịu được mưa gấp {_fmt_mult(x)} lần dự báo "
                             f"(+{(x-1)*100:.0f}%) trước khi chạm ngưỡng {target:.0f}.",
                             f"Can still take {_fmt_mult(x)}× the forecast rain "
                             f"(+{(x-1)*100:.0f}%) before hitting threshold {target:.0f}."),
                "value": round(x, 4),
            })
    else:
        # Nền địa hình có thể đã ở/trên ngưỡng: khi đó dù mưa = 0 vẫn không an toàn.
        # Không được trả lời suy biến "giảm 100% lượng mưa".
        peak_no_rain = f_rain(0.0)
        x = None if peak_no_rain >= target else _solve(f_rain, 0.0, 1.0, target, rising=True)
        if x is None:
            levers.append({
                "lever": tr("Lượng mưa", "Rainfall"), "kind": "required", "feasible": False,
                "answer": tr(f"Dù không mưa một giọt, chỉ số vẫn là {peak_no_rain:.1f} "
                             f"(≥ ngưỡng {target:.0f}) — rủi ro nền đến từ địa hình, "
                             "không phải mưa sắp tới. Giảm mưa một mình không đủ.",
                             f"Even with zero rain, the index is still {peak_no_rain:.1f} "
                             f"(≥ threshold {target:.0f}) — the base risk comes from terrain, "
                             "not the incoming rain. Cutting rain alone isn't enough."),
                "value": None,
            })
        else:
            levers.append({
                "lever": tr("Lượng mưa", "Rainfall"), "kind": "required", "feasible": True,
                "answer": tr(f"Phải giảm {(1-x)*100:.0f}% lượng mưa dự báo "
                             f"(còn {_fmt_mult(x)} lần) mới xuống dưới ngưỡng {target:.0f}.",
                             f"Would need {(1-x)*100:.0f}% less forecast rain "
                             f"({_fmt_mult(x)}× left) to drop below threshold {target:.0f}."),
                "value": round(x, 4),
            })

    # --- Đòn bẩy 2: ĐỊA HÌNH (hành động được: tôn nền / chọn lô khác) ---
    if module_id == "flood":
        elev_now = ds.elevation_proxy(lat, lon)
        f_elev = lambda e: _peak_at_terrain("flood", lat, lon, rows, e)
        x = _solve(f_elev, elev_now, elev_now + 60.0, target, rising=False)
        if x is None:
            levers.append({
                "lever": tr("Cao độ nền", "Ground elevation"), "kind": "required", "feasible": False,
                "answer": tr(f"Nền hiện ~{elev_now} m. Tôn nền tới +60 m vẫn không đủ — "
                             "chỉ số ngập đang do lượng mưa chi phối.",
                             f"Ground is ~{elev_now} m. Raising it +60 m still isn't enough — "
                             "the flood index is rain-driven here."),
                "value": None,
            })
        else:
            need = max(0.0, x - elev_now)
            levers.append({
                "lever": tr("Cao độ nền", "Ground elevation"), "kind": "required", "feasible": True,
                "answer": (tr(f"Nền hiện ~{elev_now} m; cần cao ~{x:.1f} m "
                              f"(tôn thêm ~{need:.1f} m) để xuống dưới ngưỡng.",
                              f"Ground is ~{elev_now} m; needs ~{x:.1f} m "
                              f"(raise ~{need:.1f} m) to drop below threshold.")
                           if need > 0.05 else
                           tr(f"Nền hiện ~{elev_now} m đã đủ cao so với ngưỡng.",
                              f"Ground is ~{elev_now} m — already high enough vs threshold.")),
                "value": round(x, 1),
            })

    if module_id == "landslide":
        slope_now, _ = ds.slope_context(lat, lon)
        f_slope = lambda s: _peak_at_terrain("landslide", lat, lon, rows, s)
        x = _solve(f_slope, 0.0, max(slope_now, 1.0), target, rising=True)
        if x is None:
            levers.append({
                "lever": tr("Độ dốc sườn", "Slope"), "kind": "info", "feasible": True,
                "answer": tr(f"Độ dốc ~{slope_now}° — với lượng mưa này, mọi độ dốc "
                             "trong khoảng đều dưới ngưỡng.",
                             f"Slope ~{slope_now}° — with this rain, every slope in range "
                             "stays below threshold."),
                "value": None,
            })
        else:
            levers.append({
                "lever": tr("Độ dốc sườn", "Slope"), "kind": "required", "feasible": True,
                "answer": tr(f"Độ dốc hiện ~{slope_now}°. Ngưỡng an toàn với lượng mưa "
                             f"này là ~{x:.1f}° — sườn dốc hơn mức đó cần gia cố/di dời.",
                             f"Slope is ~{slope_now}°. The safe threshold at this rain is "
                             f"~{x:.1f}° — steeper than that needs reinforcement/relocation."),
                "value": round(x, 1),
            })

    # Nếu KHÔNG đòn bẩy đơn lẻ nào đủ, tìm phương án KẾT HỢP (chỉ lũ: tôn nền + thoát nước).
    combined = None
    if not safe_now and not any(l["feasible"] for l in levers) and module_id == "flood":
        elev_now = ds.elevation_proxy(lat, lon)
        for extra in (1.0, 2.0, 3.0, 5.0, 8.0):
            e = elev_now + extra
            f = lambda m: _peak_at_terrain(
                "flood", lat, lon, hazard.transform(rows, rain_mult=m), e)
            if f(0.0) >= target:
                continue
            x = _solve(f, 0.0, 1.0, target, rising=True)
            if x is not None:
                combined = {
                    "answer": tr(f"Không đòn bẩy đơn lẻ nào đủ. Phương án kết hợp: tôn nền "
                                 f"thêm ~{extra:.0f} m (lên ~{e:.1f} m) VÀ giảm "
                                 f"{(1-x)*100:.0f}% lượng nước đọng (thoát nước/bơm) "
                                 f"thì mới xuống dưới ngưỡng {target:.0f}.",
                                 f"No single lever is enough. Combined: raise the ground "
                                 f"~{extra:.0f} m (to ~{e:.1f} m) AND cut standing water "
                                 f"by {(1-x)*100:.0f}% (drainage/pumping) to drop below "
                                 f"threshold {target:.0f}."),
                    "elevation_gain_m": extra, "rain_mult": round(x, 4),
                }
                break
        if combined is None:
            combined = {
                "answer": tr("Không có phương án nào trong tầm khảo sát (tôn nền tới +8 m, "
                             "thoát nước tới 100%) đưa được về dưới ngưỡng. Lô đất này "
                             "chịu rủi ro ngập nền cao — nên cân nhắc vị trí khác.",
                             "No option in the searched range (raise up to +8 m, drainage up "
                             "to 100%) drops it below threshold. This plot has high base flood "
                             "risk — consider a different location."),
                "elevation_gain_m": None, "rain_mult": None,
            }

    headline = (tr(f"Đang an toàn ({current:.1f} {unit}) — còn dư địa trước ngưỡng {target:.0f}.",
                   f"Currently safe ({current:.1f} {unit}) — headroom before threshold {target:.0f}.")
                if safe_now else
                tr(f"Đang vượt ngưỡng ({current:.1f} {unit}) — đây là điều kiện để trở lại an toàn.",
                   f"Currently over threshold ({current:.1f} {unit}) — here's what it takes to get back to safe."))

    return {
        "module_id": module_id, "module_name": name, "unit": unit,
        "available": True, "is_real": True,
        "current_peak": round(current, 1), "target": target, "safe_now": safe_now,
        "headline": headline, "levers": levers, "combined": combined,
        "method": tr("Tìm kiếm nhị phân trên chính mô hình cảnh báo đang chạy "
                     "(40 vòng lặp) — kết quả tái lập được, không phải AI phỏng đoán.",
                     "Binary search on the live alert model (40 iterations) — reproducible, "
                     "not an AI guess."),
    }
