"""Gói TerraTwin.

Đặt TRƯỚC KHI bất kỳ module nào nạp numpy/onnxruntime (26/10/2026): thư viện BLAS đi kèm numpy tạo một luồng — kèm
vùng đệm ~30 MB — cho MỖI nhân CPU nó thấy. Đo ở máy 8 luồng: nạp numpy +235 MB, API vừa khởi động 322 MB; giới hạn
1 luồng: +10 MB và 97 MB. Render miễn phí chỉ cấp 0,1 CPU và 512 MB nhưng tiến trình vẫn thấy nhân của cả máy chủ vật
lý — nhiều luồng không nhanh hơn, chỉ tốn bộ nhớ và tranh nhau 0,1 CPU (nghi gốc của việc API mất phản hồi giữa các lượt
E2E production 23, 25, 26/10). setdefault: đặt biến môi trường khác thì vẫn ghi đè được (vd. chạy huấn luyện ở máy).
"""
import os as _os

for _k in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    _os.environ.setdefault(_k, "1")
