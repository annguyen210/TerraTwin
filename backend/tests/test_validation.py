"""Ràng buộc đầu vào Location — chặn toạ độ/diện tích vô lý."""
import pytest
from pydantic import ValidationError

from app.schemas import Location


def test_valid_vn_location():
    loc = Location(lat=10.03, lon=105.78, area_ha=2.5)
    assert loc.lat == 10.03 and loc.area_ha == 2.5


@pytest.mark.parametrize("lat,lon", [(999, 9999), (0, -160), (48.85, 2.35)])  # đảo, TBD, Paris
def test_reject_out_of_service_area(lat, lon):
    with pytest.raises(ValidationError):
        Location(lat=lat, lon=lon)


def test_reject_negative_area():
    with pytest.raises(ValidationError):
        Location(lat=10, lon=106, area_ha=-500)


def test_reject_absurd_area():
    with pytest.raises(ValidationError):
        Location(lat=10, lon=106, area_ha=9.9e9)
