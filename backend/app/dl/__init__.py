"""Lớp học sâu — CHẠY TRÊN MÁY CÓ GPU, không phải trên máy chủ sản phẩm.

Ba bước, theo đúng thứ tự:
    python -m app.dl.fetch  --smoke     ← thử một ô, ~1 phút
    python -m app.dl.fetch              ← tải bộ dữ liệu, vài giờ
    python -m app.dl.train  --smoke     ← thử một vòng, ~30 giây
    python -m app.dl.train              ← huấn luyện
    python -m app.dl.export             ← xuất ONNX cho máy chủ

Máy chủ sản phẩm KHÔNG cần torch. Nó chỉ đọc tệp .onnx qua onnxruntime, và nếu
không có tệp đó thì lớp này trả None — đúng kỷ luật của phần còn lại: thiếu thì
nói thiếu, không đoán.
"""
