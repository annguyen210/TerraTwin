"""Cấu hình chung cho toàn bộ test.

Phải đặt biến môi trường TRƯỚC khi bất kỳ test nào import app.main, vì
main.py đọc chúng ở thời điểm nạp module.
"""
import os

# Rate limiter dùng bộ đếm trong bộ nhớ theo IP, và cả bộ test chạy từ cùng một
# "IP". Không tắt thì các test sau sẽ nhận 429 chỉ vì các test trước đã chạy —
# lỗi giả, không liên quan gì tới thứ đang được kiểm tra.
os.environ["TERRATWIN_RATE_LIMIT"] = "0"

# Secret cố định để token tạo trong một test dùng được suốt phiên.
os.environ.setdefault("TERRATWIN_SECRET", "test-secret-khong-dung-cho-production")

# Bộ hẹn giờ rà soát nền không được chạy trong test: nó sẽ tự gọi Open-Meteo và
# ghi cảnh báo giữa chừng, làm test khác thấy dữ liệu lạ xuất hiện từ hư không.
os.environ["TERRATWIN_RADAR_INTERVAL_H"] = "0"


import pytest


@pytest.fixture(autouse=True)
def _khong_goi_overpass_that(monkeypatch, request):
    """Chặn mọi lời gọi Overpass THẬT trong test.

    Overpass là dịch vụ công cộng: chậm 10–60 giây, giới hạn 2 slot mỗi IP, và
    có lúc trả 429. Để test thật sự gọi ra đó nghĩa là bộ test vừa chậm vừa đỏ
    ngẫu nhiên theo tâm trạng của một máy chủ ở nước khác — và khi nó đỏ thì
    không ai biết là lỗi code hay lỗi mạng.

    Mặc định trả None (đúng như khi Overpass không phản hồi), nên các mô-đun
    nhóm D rơi vào nhánh "chưa đủ dữ liệu" — nhánh đó cũng cần được test.
    Test nào muốn có dữ liệu OSM thì tự monkeypatch `osm._query` của mình; đặt
    sau fixture này nên sẽ ghi đè được.
    """
    if "goi_overpass_that" in request.keywords:
        return
    from app.services import osm
    monkeypatch.setattr(osm, "_query", lambda q: None)
