"""Gói TerraTwin.

Đặt TRƯỚC KHI bất kỳ module nào nạp numpy/onnxruntime (26/10/2026): thư viện BLAS đi kèm numpy tạo một luồng — kèm
vùng đệm ~30 MB — cho MỖI nhân CPU nó thấy. Đo ở máy 8 luồng: nạp numpy +235 MB, API vừa khởi động 322 MB; giới hạn
1 luồng: +10 MB và 97 MB. Render miễn phí chỉ cấp 0,1 CPU và 512 MB nhưng tiến trình vẫn thấy nhân của cả máy chủ vật
lý — nhiều luồng không nhanh hơn, chỉ tốn bộ nhớ và tranh nhau 0,1 CPU (nghi gốc của việc API mất phản hồi giữa các lượt
E2E production 23, 25, 26/10). setdefault: đặt biến môi trường khác thì vẫn ghi đè được (vd. chạy huấn luyện ở máy).
"""
import os as _os
import ssl as _ssl
import urllib.request as _ur

for _k in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    _os.environ.setdefault(_k, "1")

# MỘT SSLContext cho mọi lượt gọi HTTPS ra ngoài (8/11/2026). urlopen()/HTTPSConnection không truyền context thì MỖI lượt
# gọi tạo context mới và nạp lại cả kho chứng chỉ CA — việc chạy trong OpenSSL, GIL bị giữ suốt (đo: 40,7 ms/lần ở máy 8
# luồng, dùng lại context 0,24 ms). Mở một thửa mới gọi ra ngoài vài trăm lần (~460 cảnh radar, chỉ số Sentinel-2,
# Open-Meteo…); trên Render 0,1 CPU, phần nạp chứng chỉ giữ GIL đủ lâu để /api/health quá 5 s và Render khởi động lại
# instance (Events: "HTTP health check failed (timed out after 5 seconds)"). Context dùng chung an toàn giữa các luồng;
# opener cài đặt toàn cục để mọi urlopen() không truyền context đều dùng nó.
TLS_CONTEXT = _ssl.create_default_context()
_ur.install_opener(_ur.build_opener(_ur.HTTPSHandler(context=TLS_CONTEXT)))
