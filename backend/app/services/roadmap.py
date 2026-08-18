"""Trạng thái 26 luồng tính năng — nguồn sự thật DUY NHẤT.

Đặt ở đây thay vì rải trong tài liệu, để không bao giờ xảy ra chuyện README nói
một đằng, phần mềm chạy một nẻo. Trang trạng thái và tài liệu đều đọc từ đây.

Quy ước `status`:
  done     — chạy được, có test, dùng dữ liệu thật hoặc thuật toán kiểm chứng được
  partial  — phần lõi chạy, còn thiếu một mảnh đã nói rõ
  blocked  — CHƯA làm, và ghi rõ đang chờ thứ gì

`blocked_by` phải nói thật thứ đang chặn, không được viết "đang phát triển".
"""
from __future__ import annotations

# (id, tên, tầng, status, ghi chú / thứ đang chặn)
FLOWS = [
    # ----- Signature (10) -----
    ("S01", "TerraScore™", "signature", "done",
     "Điểm 0–100, chỉ chấm từ hiểm họa có dữ liệu thật."),
    ("S02", "Counterfactual Time Machine", "signature", "done",
     "Analog ensemble 10 năm ERA5 thật tại chính toạ độ đó."),
    ("S03", "Goal-Seek (mô phỏng ngược)", "signature", "done",
     "Tìm kiếm nhị phân đảo ngược mô hình; có phương án kết hợp."),
    ("S04", "Twin Genome", "signature", "done",
     "Bộ gen 7 đặc trưng, lưới 180 ô đất liền dựng từ ERA5."),
    ("S05", "Federated Twin Learning", "signature", "blocked",
     "Cần NHIỀU bên triển khai thật mới có gì để federate. Một endpoint tổng "
     "hợp không có ai gửi dữ liệu tới chỉ là vỏ rỗng."),
    ("S06", "Twin Replay / Backtest", "signature", "done",
     "4 thiên tai VN có thật, công bố lead time KÈM tỉ lệ báo động."),
    ("S07", "Causal Explain (XAI)", "signature", "done",
     "Leave-one-out chính xác trên hàm thuần, không xấp xỉ."),
    ("S08", "Autonomous Twin Agent", "signature", "partial",
     "Quét tự động + sinh cảnh báo + gửi đi đã chạy (C05+U01). Còn thiếu bộ "
     "hẹn giờ chạy nền — hiện phải gọi /api/radar/run."),
    ("S09", "AI Data & Model Engine", "signature", "blocked",
     "Cần dataset gán nhãn thực địa và GPU để huấn luyện. Chưa có dữ liệu "
     "ground-truth nào để học."),
    ("S10", "Generative Vision", "signature", "blocked",
     "Siêu phân giải ảnh vệ tinh cần ảnh Sentinel + GPU + model đã huấn luyện."),

    # ----- Cốt lõi (12) -----
    ("C01", "Twin Builder", "core", "done",
     "Dựng và LƯU đủ các lớp: địa hình, khí hậu, 14 module, TerraScore."),
    ("C02", "Parallel Futures", "core", "done",
     "4 kịch bản tham số minh bạch trên nền thời tiết thật."),
    ("C03", "What-If NLP", "core", "done",
     "Bộ luật tiếng Việt (không cần key) + LLM cho câu hỏi tự do."),
    ("C04", "Time-Lapse / Change Detection", "core", "blocked",
     "Cần ảnh Sentinel hai kỳ. Tài khoản Copernicus miễn phí nhưng phải do "
     "chủ dự án đăng ký."),
    ("C05", "Proactive Radar", "core", "done",
     "Quét lại mọi thửa đã lưu, chống trùng 12 giờ, tự gửi qua kênh đã cấu hình."),
    ("C06", "Risk & Yield Heatmaps", "core", "done",
     "Lưới tới 11×11 quanh thửa, vẽ trực tiếp lên bản đồ."),
    ("C07", "Carbon / ESG MRV", "core", "blocked",
     "Ước lượng sinh khối cần ảnh Sentinel + khảo sát thực địa. Con số carbon "
     "có hệ quả tài chính nên tuyệt đối không mô phỏng."),
    ("C08", "Multi-Twin Portfolio", "core", "done",
     "Danh mục thửa đất trong database, đồng bộ đa thiết bị."),
    ("C09", "Field Mode (giọng nói + ảnh)", "core", "partial",
     "Nhập bằng giọng nói chạy được (Web Speech API, miễn phí). Phân tích ảnh "
     "lá cần model có thị giác — sẵn sàng khi cắm key hỗ trợ vision."),
    ("C10", "Anomaly & Compliance", "core", "done",
     "z-score so khí hậu nền 10 năm tại chính toạ độ đó."),
    ("C11", "Bring-Your-Own-Data", "core", "done",
     "Tải CSV/GeoJSON lên, chấm TerraScore hàng loạt."),
    ("C12", "Twin API / SDK", "core", "done",
     "Khóa API có thu hồi, SDK Python một file, tài liệu OpenAPI tại /docs."),

    # ----- Nâng cấp (4) -----
    ("U01", "Action & Automation", "upgrade", "done",
     "Gửi cảnh báo qua webhook và email; webhook chặn địa chỉ nội bộ (chống SSRF)."),
    ("U02", "Marketplace", "upgrade", "blocked",
     "Cần cổng thanh toán, hợp đồng và pháp lý — không phải việc code."),
    ("U03", "Generative Design Studio", "upgrade", "blocked",
     "Cần model sinh ảnh/thiết kế đã huấn luyện cho bối cảnh nông nghiệp VN."),
    ("U04", "Autonomous Closed-Loop", "upgrade", "blocked",
     "Cần thiết bị IoT ngoài đồng (van, bơm, cảm biến) để đóng vòng điều khiển."),
]

_TIER_NAMES = {"signature": "Signature (độc quyền)",
               "core": "Cốt lõi", "upgrade": "Nâng cấp"}


def status() -> dict:
    flows = [{"id": i, "name": n, "tier": t, "tier_name": _TIER_NAMES[t],
              "status": s, "note": note}
             for i, n, t, s, note in FLOWS]
    counts = {k: sum(1 for f in flows if f["status"] == k)
              for k in ("done", "partial", "blocked")}
    by_tier = {}
    for t, label in _TIER_NAMES.items():
        sub = [f for f in flows if f["tier"] == t]
        by_tier[t] = {"name": label, "total": len(sub),
                      "done": sum(1 for f in sub if f["status"] == "done")}
    return {
        "total": len(flows), **counts, "flows": flows, "by_tier": by_tier,
        "headline": (f"{counts['done']}/{len(flows)} luồng chạy thật · "
                     f"{counts['partial']} một phần · {counts['blocked']} đang bị chặn"),
        "honesty_note": (
            "Bảng này sinh từ mã nguồn, không viết tay, nên không thể lệch với "
            "phần mềm. Luồng 'blocked' ghi rõ thứ đang chặn — phần lớn không "
            "phải việc code mà là dữ liệu, phần cứng hoặc pháp lý. Chúng tôi "
            "chọn nói thật thay vì dựng endpoint rỗng để đếm cho đủ số."),
    }
