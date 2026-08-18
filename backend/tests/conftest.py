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
