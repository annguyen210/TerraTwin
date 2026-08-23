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


# CSDL RIÊNG CHO MỖI LẦN CHẠY TEST.
#
# Trước đây test ghi thẳng vào backend/terratwin.db — cùng file với bản chạy
# tay. Sau hàng trăm lượt chạy nó phình lên 38,7 MB, và hậu quả có hai mặt:
#
#   · Chậm: mọi truy vấn quét qua đống rác tích luỹ, bộ test từ 144 giây kéo
#     dài thành hơn hai mươi phút.
#   · Nguy hiểm hơn: test bắt đầu phụ thuộc vào TRẠNG THÁI SÓT LẠI. Chính vì
#     bảng api_keys đã tồn tại sẵn nên bước _ensure_columns() không bao giờ
#     được chạm tới, và một cột thêm thiếu sẽ chỉ vỡ ở production chứ không
#     bao giờ đỏ ở đây.
#
# Đặt TRƯỚC khi bất kỳ chỗ nào import app.db, vì DATABASE_URL đọc lúc nạp module.
import socket
import tempfile

# LƯỚI AN TOÀN: không lượt gọi mạng nào được treo vô hạn trong test.
#
# Vài test cố tình gọi mạng thật (đo số lượt gọi, kiểm chứng nguồn), nên không
# chặn hẳn được. Nhưng một lượt gọi LỌT LƯỚI — như test_cache từng gọi
# api.open-meteo.com/elevation mà không ai để ý — sẽ không đỏ, nó TREO, và cả
# bộ test đứng im cho tới khi ai đó bấm huỷ. Đặt trần ở đây để hỏng thì hỏng
# nhanh và nhìn thấy được.
#
# Lưu ý: trần này không cứu được lúc phân giải DNS treo, vì getaddrinfo() của
# Python không nhận timeout. Xem chú thích ở realdata._fetch.
socket.setdefaulttimeout(20.0)

_DB = os.path.join(tempfile.mkdtemp(prefix="terratwin-test-"), "test.db")
os.environ["TERRATWIN_DATABASE_URL"] = f"sqlite:///{_DB}"


import pytest

# Dựng/di trú schema NGAY khi nạp conftest.
#
# TestClient(app) không kích hoạt lifespan, nên init_db() trong main.py không
# chạy trong test. Trước đây bộ test vẫn xanh chỉ vì file terratwin.db còn sót
# lại từ một lần chạy thật — nghĩa là mọi test dùng CSDL đang dựa vào tình cờ.
# Tệ hơn: đúng bước _ensure_columns() (thứ vá schema cho bản deploy CŨ) không
# bao giờ được test chạm tới, nên một cột thêm thiếu sẽ chỉ vỡ ở production.
from app.db import init_db

init_db()


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
