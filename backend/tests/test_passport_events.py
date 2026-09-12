"""Passport đếm ĐỢT, không đếm cửa sổ trượt (sửa lỗi '1206 lần sạt lở')."""
from datetime import date, timedelta

from app.services import passport


def _run(start: str, n: int, step: int = 1):
    """n cửa sổ vượt ngưỡng, cách nhau step ngày, bắt đầu từ start."""
    d0 = date.fromisoformat(start)
    return [((d0 + timedelta(days=i * step)).isoformat(), 80.0 + i) for i in range(n)]


def test_one_long_episode_is_one_event():
    # 10 ngày liên tiếp vượt ngưỡng = MỘT đợt (không phải 10).
    ev = passport._group_events(_run("2020-10-01", 10))
    assert len(ev) == 1


def test_windowed_flood_not_counted_per_window():
    # Mô phỏng lỗi cũ: 1206 cửa sổ liên tiếp → vẫn chỉ 1 đợt.
    ev = passport._group_events(_run("2018-01-01", 1206))
    assert len(ev) == 1


def test_separate_episodes_counted_apart():
    # Ba cụm cách nhau >14 ngày = ba đợt.
    seq = (_run("2020-10-01", 5) + _run("2021-06-01", 4) + _run("2022-09-01", 6))
    ev = passport._group_events(seq)
    assert len(ev) == 3


def test_gap_within_threshold_is_same_event():
    # Hai cụm cách 10 ngày (≤14) = cùng một đợt.
    seq = _run("2020-10-01", 3) + _run("2020-10-14", 3)   # cách 13 ngày
    ev = passport._group_events(seq)
    assert len(ev) == 1


def test_peak_date_is_max_value_in_event():
    seq = [("2020-10-01", 72.0), ("2020-10-03", 95.0), ("2020-10-05", 80.0)]
    ev = passport._group_events(seq)
    assert len(ev) == 1 and ev[0]["peak_date"] == "2020-10-03"


def test_empty():
    assert passport._group_events([]) == []
