"""KẾ HOẠCH THỬA CỦA BẠN — gom mọi thứ rời rạc thành MỘT câu trả lời hành động.

VÌ SAO CÓ FILE NÀY. Phần mềm đã trả lời được "có rủi ro gì" (scan), "cần điều
kiện gì để an toàn" (goalseek), "vùng nào giống thửa này" (genome), và tự canh
nền (radar). Nhưng mỗi thứ nằm một nơi, nên trải nghiệm rơi vào "chọn chỗ → đọc
kết luận → hết", rất mông lung. File này KHÔNG thêm mô hình mới — nó COMPOSE
những thứ đã có thành bốn phần người dùng thật sự cần:

  1. VIỆC CẦN LÀM   — cảnh báo → việc cụ thể, có NGÀY, ưu tiên nguy hiểm trước.
  2. NGÀY AN TOÀN   — 7 ngày tới ngày nào không có cảnh báo (để làm đồng).
  3. GIÁ TRỊ RỦI RO — quy ra tiền phần đang chịu rủi ro, ƯỚC LƯỢNG THÔ và nói rõ.
  4. TỰ CANH        — trạng thái nền + năng lực rà soát tự động.

Phần "vùng tương đồng" (genome) do frontend gọi riêng để không chặn phản hồi này.

TRUNG THỰC LÀ RÀNG BUỘC SỐ MỘT. Phần giá trị rủi ro là ƯỚC LƯỢNG dựng từ hai giả
định công khai (giá trị vụ/ha theo loại canh tác + tỉ lệ thiệt hại điển hình của
hiểm họa), KHÔNG phải đo cho thửa này. Trả ra kèm giả định để người dùng đổi và
tự phán đoán — không đưa một con số chính xác giả tạo, không cộng dồn các hiểm
họa chồng lên cùng một thửa để thổi phồng.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from app.schemas import Location
from app.services import hazard, scan
from app.services.reqlang import tr

# Giá trị vụ tham chiếu (doanh thu gộp/ha/vụ, VND) — khoảng THÔ phổ biến ở Việt
# Nam, để người dùng đổi được. Không phải đo cho thửa này.
CROP_VALUE: dict[str, tuple[int, int, str]] = {
    "lua":      (30_000_000, 50_000_000, "Lúa"),
    "raumau":   (80_000_000, 200_000_000, "Rau màu"),
    "caphe":    (60_000_000, 120_000_000, "Cà phê"),
    "cayanqua": (100_000_000, 300_000_000, "Cây ăn quả"),
    "tom":      (150_000_000, 500_000_000, "Tôm / thuỷ sản"),
}
CROP_LABEL_EN = {"lua": "Rice", "raumau": "Vegetables", "caphe": "Coffee",
                 "cayanqua": "Fruit trees", "tom": "Shrimp / aquaculture"}
DEFAULT_CROP = "lua"

# Tỉ lệ thiệt hại điển hình NẾU hiểm họa xảy ra mà không kịp ứng phó. Khoảng, vì
# thiệt hại thật phụ thuộc mức độ và thời điểm — con số đơn lẻ ở đây là bịa.
LOSS_FRACTION: dict[str, tuple[float, float]] = {
    "flood":          (0.4, 1.0),
    "upstream_flood": (0.4, 1.0),
    "drought":        (0.1, 0.4),
    "wildfire":       (0.5, 1.0),
    "landslide":      (0.6, 1.0),
    "salinity":       (0.2, 0.6),
    "storm_damage":   (0.2, 0.7),
    "pest":           (0.1, 0.4),
    "aquaculture":    (0.2, 0.6),
    "yield":          (0.1, 0.3),
}

_WEEKDAY_VI = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"]
_WEEKDAY_EN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _weekday_vi(iso: str) -> str:
    try:
        i = datetime.strptime(iso, "%Y-%m-%d").weekday()
        return tr(_WEEKDAY_VI[i], _WEEKDAY_EN[i])
    except ValueError:
        return ""


def _lead_days(first_iso: str | None, today: date) -> int | None:
    if not first_iso:
        return None
    try:
        d = datetime.strptime(first_iso, "%Y-%m-%d").date()
    except ValueError:
        return None
    return max(0, (d - today).days)


def _money(v: float) -> str:
    """Rút gọn tiền cho dễ đọc: 12,5 triệu / 1,2 tỷ."""
    if v >= 1_000_000_000:
        return tr(f"{v / 1_000_000_000:.1f} tỷ".replace(".", ","), f"{v / 1_000_000_000:.1f}B ₫")
    if v >= 1_000_000:
        return tr(f"{v / 1_000_000:.1f} triệu".replace(".", ","), f"{v / 1_000_000:.1f}M ₫")
    return tr(f"{v:,.0f} đ".replace(",", "."), f"{v:,.0f} ₫")


def build(loc: Location, crop: str = DEFAULT_CROP) -> dict:
    crop = crop if crop in CROP_VALUE else DEFAULT_CROP
    sc = scan.scan(loc)
    alerts = sc.alerts                      # đã lọc: thật + là mối đe doạ, nguy hiểm trước
    today = date.today()
    horizon = [(today + timedelta(days=i)).isoformat() for i in range(7)]

    # --- Bản đồ NGÀY → hiểm họa (để dựng cả việc cần làm lẫn ngày an toàn) ---
    by_day: dict[str, list[str]] = {d: [] for d in horizon}
    for m in alerts:
        for d in m.risk_dates:
            by_day.setdefault(d, []).append(m.name)

    # ============ 1. VIỆC CẦN LÀM ============
    actions = []
    for m in alerts:
        first = min(m.risk_dates) if m.risk_dates else m.peak_date
        lead = _lead_days(first, today)
        actions.append({
            "id": m.id, "name": m.name, "icon": m.icon,
            "risk_level": m.risk_level, "headline": m.headline,
            "do": m.recommendation,
            "when": first, "when_weekday": _weekday_vi(first) if first else "",
            "lead_days": lead,
            "peak": m.peak, "unit": m.unit,
            # goalseek chỉ chạy trên hiểm họa mô hình hoá được (lũ/sạt/hạn/cháy)
            "can_ask": hazard.supports(m.id),
        })
    # Nguy hiểm trước; cùng mức thì việc gần hơn lên trên.
    actions.sort(key=lambda a: (0 if a["risk_level"] == "danger" else 1,
                                a["lead_days"] if a["lead_days"] is not None else 99))

    # ============ 2. NGÀY AN TOÀN (7 ngày tới) ============
    days = []
    for d in horizon:
        hz = sorted(set(by_day.get(d, [])))
        days.append({"date": d, "weekday": _weekday_vi(d),
                     "safe": not hz, "hazards": hz})
    safe_dates = [d["date"] for d in days if d["safe"]]
    if not alerts:
        sw_headline = tr("Không có cảnh báo nào trong 7 ngày tới — mọi ngày đều thuận cho việc đồng áng.",
                         "No alerts in the next 7 days — every day is fine for fieldwork.")
    elif safe_dates:
        first_safe = days[[d["date"] for d in days].index(safe_dates[0])]
        sw_headline = tr(f"Cửa sổ an toàn gần nhất: {first_safe['weekday']} "
                         f"({first_safe['date'][5:]}) — không cảnh báo nào. "
                         f"Có {len(safe_dates)}/7 ngày trống.",
                         f"Nearest safe window: {first_safe['weekday']} "
                         f"({first_safe['date'][5:]}) — no alerts. "
                         f"{len(safe_dates)}/7 days clear.")
    else:
        sw_headline = tr("Cả 7 ngày tới đều có ít nhất một cảnh báo — chọn ngày ít "
                         "hiểm họa nhất trong lịch, hoặc hoãn việc nhạy cảm.",
                         "Every day in the next 7 has at least one alert — pick the "
                         "least-hazardous day, or postpone sensitive work.")

    # ============ 3. GIÁ TRỊ ĐANG CHỊU RỦI RO (ước lượng thô) ============
    v_lo, v_hi, crop_label = CROP_VALUE[crop]
    area = loc.area_ha if (loc.area_ha and loc.area_ha > 0) else None
    unit_area = area if area else 1.0        # chưa vẽ thửa → tính trên 1 ha
    items = []
    for m in alerts:
        lf = LOSS_FRACTION.get(m.id)
        if lf is None:
            continue                          # hiểm họa không quy ra thiệt hại mùa vụ
        lo = unit_area * lf[0] * v_lo
        hi = unit_area * lf[1] * v_hi
        items.append({
            "id": m.id, "name": m.name, "icon": m.icon,
            "loss_pct": [int(lf[0] * 100), int(lf[1] * 100)],
            "stake_lo": round(lo), "stake_hi": round(hi),
            "stake_text": f"{_money(lo)} – {_money(hi)}",
            "lead_days": _lead_days(min(m.risk_dates) if m.risk_dates else None, today),
        })
    # KHÔNG cộng dồn: nhiều hiểm họa trên cùng một thửa chồng lấn nhau. Lấy hiểm
    # họa lớn nhất làm mức "đang chịu rủi ro" — bảo thủ, không thổi phồng.
    worst_hi = max((it["stake_hi"] for it in items), default=0)
    worst_lo = max((it["stake_lo"] for it in items), default=0)
    # Giá trị vụ (gộp) của thửa — để nói dương tính khi an toàn: "chừng này giá trị
    # đang được canh giữ", thay vì một câu trống rỗng. Vẫn là giả định, gắn cờ rõ.
    plot_lo = round(unit_area * v_lo)
    plot_hi = round(unit_area * v_hi)
    _on_vi = "trên thửa" if area else "mỗi ha"
    _on_en = "for this plot" if area else "per ha"
    _crop_en = CROP_LABEL_EN.get(crop, crop_label)
    _area_vi = f" × {area} ha" if area else "/ha"
    _assume_vi = (
        f"Ước lượng THÔ theo giả định {crop_label} ({_money(v_lo)}–{_money(v_hi)}/ha"
        + _area_vi + "). "
        + ("Phần chịu rủi ro = giá trị vụ × tỉ lệ thiệt hại điển hình của hiểm họa. " if items else "")
        + "KHÔNG phải đo cho thửa này — đổi loại canh tác để tính lại."
        + ("" if area else " Vẽ hoặc nhập diện tích thửa để ra tổng theo thửa."))
    _assume_en = (
        f"ROUGH estimate assuming {_crop_en} ({_money(v_lo)}–{_money(v_hi)}/ha"
        + _area_vi + "). "
        + ("At-risk = crop value × the hazard's typical loss rate. " if items else "")
        + "NOT measured for this plot — change the crop type to recompute."
        + ("" if area else " Draw or enter the plot area for a per-plot total."))
    value = {
        "available": True,
        "at_risk": bool(items),
        "crop": crop, "crop_label": tr(crop_label, CROP_LABEL_EN.get(crop, crop_label)),
        "crop_value_range": [v_lo, v_hi],
        "area_ha": area, "per_unit": area is None,
        "items": items,
        "worst_lo": worst_lo, "worst_hi": worst_hi,
        "plot_lo": plot_lo, "plot_hi": plot_hi,
        "plot_text": f"{_money(plot_lo)} – {_money(plot_hi)}",
        "headline": (
            tr(f"Tối đa ~{_money(worst_hi)} {_on_vi} đang chịu rủi ro "
               f"(lấy hiểm họa lớn nhất, KHÔNG cộng dồn).",
               f"Up to ~{_money(worst_hi)} {_on_en} at risk "
               f"(largest single hazard, NOT summed).")
            if items else
            tr(f"✅ Giá trị vụ ~{_money(plot_lo)}–{_money(plot_hi)} {_on_vi} đang được "
               f"canh giữ — không hiểm họa nào đe doạ trong 7 ngày tới.",
               f"✅ Crop value ~{_money(plot_lo)}–{_money(plot_hi)} {_on_en} is being "
               f"protected — no hazard threatens it in the next 7 days.")),
        "assumption": tr(_assume_vi, _assume_en),
    }

    # ============ 4. TỰ CANH (song sinh sống) ============
    ts = sc.terrascore
    n_alerts = len(alerts)
    watch = {
        "grade": ts.grade, "score": ts.score,
        "n_alerts": n_alerts,
        "real_data_ratio": sc.real_data_ratio,
        "headline": (tr(f"Điểm nền {ts.score}/100 ({ts.grade}) · {n_alerts} cảnh báo đang mở.",
                        f"Baseline score {ts.score}/100 ({ts.grade}) · {n_alerts} open alert(s).") if n_alerts else
                     tr(f"Điểm nền {ts.score}/100 ({ts.grade}) · chưa có cảnh báo nào.",
                        f"Baseline score {ts.score}/100 ({ts.grade}) · no alerts yet.")),
        "capability": tr("Lưu thửa → TerraTwin tự rà nền 6 giờ một lần và báo TRƯỚC "
                         "qua web / email / webhook, kể cả lúc 3 giờ sáng khi bạn "
                         "không mở app. Bạn không phải nhớ vào xem.",
                         "Save the plot → TerraTwin scans in the background every 6 hours "
                         "and warns you IN ADVANCE via web / email / webhook, even at 3 a.m. "
                         "when the app is closed. You don't have to remember to check."),
    }

    return {
        "location": {"lat": loc.lat, "lon": loc.lon},
        "generated_at": sc.generated_at,
        "n_alerts": n_alerts,
        "actions": actions,
        "safe_window": {"days": days, "safe_dates": safe_dates,
                        "headline": sw_headline},
        "value": value,
        "watch": watch,
        "crops": [{"id": k, "label": tr(v[2], CROP_LABEL_EN.get(k, v[2]))}
                  for k, v in CROP_VALUE.items()],
    }
