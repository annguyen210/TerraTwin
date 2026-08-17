"""Module mặn: KHÔNG báo động giả nội địa; đo khoảng cách bờ biển đúng toàn quốc."""
from app.services import datasources as ds
from app.services import realdata


def test_distance_to_coast_nationwide():
    # Hạ Long sát biển → nhỏ; Hà Nội & Đà Lạt sâu trong đất liền → lớn.
    assert ds.distance_to_coast_km(20.95, 107.08) < 20      # Hạ Long
    assert ds.distance_to_coast_km(21.03, 105.85) > 50      # Hà Nội
    assert ds.distance_to_coast_km(11.94, 108.44) > 40      # Đà Lạt


def _peak(lat, lon):
    return max(v for _, _, v in ds.get_salinity_context(lat, lon)["series"])


def test_no_false_alarm_inland(monkeypatch):
    # cao độ giả lập nội địa/núi để không phụ thuộc mạng
    monkeypatch.setattr(realdata, "elevation_m", lambda la, lo: 22.0)   # Hà Nội ~ 20-24 m
    assert _peak(21.03, 105.85) < 1.0                       # Hà Nội an toàn
    monkeypatch.setattr(realdata, "elevation_m", lambda la, lo: 1480.0)  # Đà Lạt núi
    assert _peak(11.94, 108.44) < 0.5                       # núi: gần 0


def test_warns_at_coastal_delta(monkeypatch):
    monkeypatch.setattr(realdata, "elevation_m", lambda la, lo: 2.0)    # cửa sông thấp
    assert _peak(9.95, 106.60) >= 4.0                       # Bến Tre ven biển: nguy hiểm
