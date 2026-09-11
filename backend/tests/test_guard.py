"""A2 — rào chắn con số cho LLM: số bịa KHÔNG được lọt tới người dùng."""
from app.services import guard


def test_gives_number_present_in_source_through():
    src = "TerraScore: 72/100. Độ mặn đo được 3,1 phần nghìn."
    out, removed = guard.strip_invented_numbers(
        "Điểm của bạn là 72/100, độ mặn 3,1‰.", guard.numbers_in(src))
    assert removed == []
    assert "72" in out and "3,1" in out


def test_invented_number_is_redacted():
    # Nguồn KHÔNG hề nhắc tới 8,5 hay 96% — model bịa ra.
    src = "TerraScore: 72/100. Nguy cơ xâm nhập mặn ở mức trung bình."
    out, removed = guard.strip_invented_numbers(
        "Độ mặn hiện tại là 8,5 phần nghìn, khả năng thiệt hại 96%.",
        guard.numbers_in(src))
    assert "8,5" not in out
    assert "96" not in out
    assert guard.REDACT in out
    assert len(removed) == 2


def test_benign_days_and_years_pass():
    out, removed = guard.strip_invented_numbers(
        "Trong 7 ngày tới, tương tự mùa lũ 2020.", allowed=set())
    assert removed == []
    assert "7" in out and "2020" in out


def test_stats_counts_redactions():
    before = guard.stats()["numbers_removed"]
    guard.strip_invented_numbers("giá trị 4321 đồng", allowed=set())
    after = guard.stats()["numbers_removed"]
    assert after == before + 1


def test_copilot_output_is_guarded(monkeypatch):
    """Đầu-cuối: LLM trả câu có số bịa → answer() phải ẩn nó trước khi tới người."""
    from app.services import copilot, llm
    from app.schemas import Location

    # LLM giả bịa một con số tiền lớn KHÔNG thể có trong facts (vốn là chỉ số 0–100).
    monkeypatch.setattr(llm, "complete",
                        lambda *a, **k: "Thiệt hại ước tính lên tới 4.321.000 đồng.")
    res = copilot.answer("ruộng tôi có mặn không?", Location(lat=10.24, lon=106.38))
    assert "4.321.000" not in res.answer
    assert guard.REDACT in res.answer
