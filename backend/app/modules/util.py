"""Tiện ích dùng chung cho các module dạng dự báo (7 ngày)."""
from __future__ import annotations

from typing import Callable

from app.schemas import Assessment, ForecastPoint, Location
from app.services.reqlang import tr


def risk_of(v: float, safe: float, warning: float) -> str:
    if v >= warning:
        return "danger"
    if v >= safe:
        return "warning"
    return "safe"


def make_forecast(series_data, unit: str, safe: float, warning: float) -> list[ForecastPoint]:
    return [
        ForecastPoint(day=d, date=dt, value=v, unit=unit, risk=risk_of(v, safe, warning))
        for (d, dt, v) in series_data
    ]


def peak(fc: list[ForecastPoint]) -> ForecastPoint:
    return max(fc, key=lambda f: f.value)


def first_danger(fc: list[ForecastPoint]):
    return next((f for f in fc if f.risk == "danger"), None)


def need_data_assessment(module, loc: Location, needs: str, will_do: str,
                         next_step: str = "") -> Assessment:
    """Kết quả TRUNG THỰC cho module chưa có nguồn dữ liệu thật.

    KHÔNG bịa con số/phát hiện. Nêu rõ cần nguồn gì và module sẽ làm gì khi có.
    """
    return Assessment(
        module_id=module.id, module_name=module.disp_name(), location=loc,
        status="need_data", risk_level="unknown", is_real=False,
        headline=tr(f"Chưa đủ dữ liệu để phân tích vùng này — {needs}",
                    f"Not enough data to analyze this area yet — {needs}"),
        detail=tr(f"Kiến trúc module đã sẵn sàng. Khi tích hợp {needs}, module sẽ "
                  f"{will_do}. Hiện CHƯA có nguồn ảnh nên không đưa ra con số để tránh "
                  "sai lệch.",
                  f"The module is ready. Once {needs} is integrated, it will "
                  f"{will_do}. No imagery yet, so no numbers are given, to avoid error."),
        recommendation=next_step or tr("Đang trong lộ trình tích hợp nguồn dữ liệu.",
                                       "Data-source integration is on the roadmap."),
        confidence=None, data_sources=module.disp_data_sources(),
    )


def conf_band(confidence: float, is_real: bool) -> tuple[float, float]:
    """Khoảng tin cậy quanh điểm ước lượng — hẹp hơn khi có dữ liệu thật."""
    half = 0.08 if is_real else 0.15
    return round(max(0.0, confidence - half), 2), round(min(1.0, confidence + half), 2)


def assessment_from_series(module, loc: Location, series_data, unit: str,
                           safe: float, warning: float,
                           texts: Callable, detail: str,
                           confidence: float = 0.7, is_real: bool = False,
                           data_sources: list[str] | None = None) -> Assessment:
    fc = make_forecast(series_data, unit, safe, warning)
    pk, fd = peak(fc), first_danger(fc)
    lvl = risk_of(pk.value, safe, warning)
    head, rec = texts(lvl, pk, fd)
    lo, hi = conf_band(confidence, is_real)
    return Assessment(
        module_id=module.id, module_name=module.disp_name(), location=loc, status="ok",
        risk_level=lvl, headline=head, detail=detail, recommendation=rec,
        confidence=confidence, confidence_low=lo, confidence_high=hi, is_real=is_real,
        forecast=fc, data_sources=data_sources or module.disp_data_sources(),
    )


def _needs_sentinel(what: str) -> str:
    """Mô tả thứ đang thiếu — nói rõ thiếu KHÓA hay thiếu ẢNH QUANG MÂY.

    Hai nguyên nhân này khác nhau hoàn toàn với người dùng: một cái họ tự sửa
    được trong mười phút, một cái phải chờ trời. Gộp chung thành "chưa đủ dữ
    liệu" là bỏ mặc họ không biết làm gì tiếp.
    """
    from app.services import sentinel
    if not sentinel.configured():
        return tr(f"{what} — phần mềm chưa được cấu hình khóa Copernicus",
                  f"{what} — Copernicus key not configured yet")
    return tr(f"{what} — đã có khóa nhưng chưa lấy được ảnh quang mây cho vùng này",
              f"{what} — key present but no cloud-free imagery for this area yet")


def _next_sentinel() -> str:
    from app.services import sentinel
    if not sentinel.configured():
        return tr("Đăng ký miễn phí tại dataspace.copernicus.eu, tạo OAuth client, "
                  "rồi đặt TERRATWIN_COPERNICUS_ID và TERRATWIN_COPERNICUS_SECRET. "
                  "Không tốn phí và không cần thẻ.",
                  "Register free at dataspace.copernicus.eu, create an OAuth client, "
                  "then set TERRATWIN_COPERNICUS_ID and TERRATWIN_COPERNICUS_SECRET. "
                  "No cost, no card needed.")
    return tr("Sentinel-2 bay qua mỗi khoảng 5 ngày và mùa mưa thường bị mây che. "
              "Thử lại sau vài ngày — phần mềm tự dùng tấm ảnh quang mây gần nhất.",
              "Sentinel-2 passes every ~5 days and the rainy season is often cloudy. "
              "Try again in a few days — the app uses the nearest cloud-free image.")
