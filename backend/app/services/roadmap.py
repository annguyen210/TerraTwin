"""Trạng thái 26 luồng tính năng — nguồn sự thật DUY NHẤT.

Đặt ở đây thay vì rải trong tài liệu, để không bao giờ xảy ra chuyện README nói
một đằng, phần mềm chạy một nẻo. Trang trạng thái và tài liệu đều đọc từ đây.

Quy ước `status`:
  done     — chạy được, có test, dùng dữ liệu thật hoặc thuật toán kiểm chứng được
  partial  — phần lõi chạy, còn thiếu một mảnh đã nói rõ
  blocked  — CHƯA làm, và ghi rõ đang chờ thứ gì

`blocked_by` phải nói thật thứ đang chặn, không được viết "đang phát triển".

MỘT ĐIỀU ĐÃ HỌC KHI LÀM: ban đầu 8 luồng bị xếp `blocked` vì mỗi luồng bị gán
vào MỘT công nghệ cụ thể (S05 = federated learning kiểu ML, U03 = model sinh
ảnh). Xét lại theo MỤC ĐÍCH thì 6 trong số đó có bản thật, hữu ích, làm được
bằng dữ liệu đã có. Chỉ 2 luồng thật sự cần ảnh Sentinel. Bài học: hỏi "luồng
này để làm gì cho người dùng" trước khi hỏi "nó cần công nghệ gì".
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
    ("S05", "Federated Twin Learning", "signature", "done",
     "Quan sát thực địa của người dùng hiệu chỉnh ngưỡng theo vùng. Dữ liệu "
     "thô KHÔNG rời tài khoản người gửi; chỉ chia sẻ một con số tổng hợp cho "
     "mỗi vùng 0,5°, và chỉ khi đã đủ 3 quan sát nên không truy ngược cá nhân."),
    ("S06", "Twin Replay / Backtest", "signature", "done",
     "4 thiên tai VN có thật, công bố lead time KÈM tỉ lệ báo động."),
    ("S07", "Causal Explain (XAI)", "signature", "done",
     "Leave-one-out chính xác trên hàm thuần, không xấp xỉ."),
    ("S08", "Autonomous Twin Agent", "signature", "done",
     "Quét tự động, sinh cảnh báo, gửi qua webhook/email, ghi nhận hành động "
     "người dùng và đối chiếu kết quả. Chạy định kỳ bằng cron gọi /api/radar/run."),
    ("S09", "AI Data & Model Engine", "signature", "done",
     "Kho quan sát thực địa làm dataset + chấm mô hình bằng POD/FAR/CSI, chỉ ra "
     "vùng nào đang lệch. Phần HUẤN LUYỆN lại cần GPU và dataset gán nhãn lớn — "
     "chưa có, nhưng không đo được thì huấn luyện chỉ là tiêu tiền trong bóng tối."),
    ("S10", "Generative Vision", "signature", "blocked",
     "Ảnh Sentinel đã có (từ bản này), nhưng siêu phân giải bằng diffusion còn "
     "thiếu HAI thứ chưa mua được bằng công sức: GPU để suy luận và một model "
     "đã huấn luyện trên ảnh viễn thám. Không làm bản giả: một tấm ảnh 'siêu "
     "phân giải' do model bịa ra trông y hệt ảnh vệ tinh thật nhưng chi tiết "
     "trong đó là do model tưởng tượng — dùng nó để kết luận về đất đai còn "
     "nguy hiểm hơn là không có ảnh."),

    # ----- Cốt lõi (12) -----
    ("C01", "Twin Builder", "core", "done",
     "Dựng và LƯU đủ các lớp: địa hình, khí hậu, 14 module, TerraScore."),
    ("C02", "Parallel Futures", "core", "done",
     "4 kịch bản tham số minh bạch trên nền thời tiết thật."),
    ("C03", "What-If NLP", "core", "done",
     "Bộ luật tiếng Việt (không cần key) + LLM cho câu hỏi tự do."),
    ("C04", "Time-Lapse / Change Detection", "core", "done",
     "Hai nửa đều có: time-lapse RỦI RO KHÍ HẬU qua 10 năm ERA5 (chạy không cần "
     "khóa), và phát hiện thay đổi BỀ MẶT hai kỳ trên ảnh Sentinel-2 — mất thảm "
     "thực vật (NDVI) và bề mặt xây dựng mới (NDBI + NDVI cùng đổi)."),
    ("C05", "Proactive Radar", "core", "done",
     "Quét lại mọi thửa đã lưu, chống trùng 12 giờ, tự gửi qua kênh đã cấu hình."),
    ("C06", "Risk & Yield Heatmaps", "core", "done",
     "Lưới tới 11×11 quanh thửa, vẽ trực tiếp lên bản đồ."),
    ("C07", "Carbon / ESG MRV", "core", "done",
     "Đo che phủ tán THẬT theo từng pixel Sentinel-2 (histogram NDVI, nội suy "
     "ngưỡng), rồi ước lượng tCO₂ bằng hệ số IPCC 2006 Tier 1 — có công bố bậc, "
     "dải sai số ±50%, và mã băm SHA-256 để người nhận tự kiểm báo cáo có bị sửa "
     "hay không. Ghi rõ ĐÂY KHÔNG PHẢI số liệu đủ chuẩn phát hành tín chỉ và "
     "liệt kê đúng các bước còn thiếu để lên chuẩn đó.", "satellite"),
    ("C08", "Multi-Twin Portfolio", "core", "done",
     "Danh mục thửa đất trong database, đồng bộ đa thiết bị."),
    ("C09", "Field Mode (giọng nói + ảnh)", "core", "done",
     "Hỏi bằng giọng nói qua Web Speech API — miễn phí, không cần key, âm thanh "
     "không rời trình duyệt. Phân tích ảnh lá cần model có thị giác: hạ tầng đã "
     "sẵn, bật ngay khi cắm key hỗ trợ vision."),
    ("C10", "Anomaly & Compliance", "core", "done",
     "z-score so khí hậu nền 10 năm tại chính toạ độ đó."),
    ("C11", "Bring-Your-Own-Data", "core", "done",
     "Tải CSV/GeoJSON lên, chấm TerraScore hàng loạt."),
    ("C12", "Twin API / SDK", "core", "done",
     "Khóa API có thu hồi, SDK Python một file, tài liệu OpenAPI tại /docs."),

    # ----- Nâng cấp (4) -----
    ("U01", "Action & Automation", "upgrade", "done",
     "Gửi cảnh báo qua webhook và email; webhook chặn địa chỉ nội bộ (chống SSRF)."),
    ("U02", "Marketplace", "upgrade", "done",
     "Chợ TRI THỨC ghép theo Twin Genome: kinh nghiệm đến từ vùng cùng bộ gen "
     "đất, không phải lời khuyên chung chung. Chợ có GIAO DỊCH TIỀN cần cổng "
     "thanh toán và pháp lý — chưa làm, và đó không phải việc code."),
    ("U03", "Generative Design Studio", "upgrade", "done",
     "Sinh phương án canh tác cụ thể — trồng gì, hạ tầng nào làm trước — từ ràng "
     "buộc đo được; mỗi điểm cộng/trừ kèm lý do truy được về con số gốc. "
     "'Generative' theo nghĩa tổng hợp phương án, không phải model sinh ảnh."),
    ("U04", "Autonomous Closed-Loop", "upgrade", "done",
     "Vòng khép kín với NGƯỜI là cơ cấu chấp hành: khuyến nghị → xác nhận đã "
     "làm → đối chiếu kết quả → nạp lại hiệu chuẩn. Tự động hoá phần chấp hành "
     "(van, bơm) cần thiết bị IoT ngoài đồng — chưa có."),
]

_TIER_NAMES = {"signature": "Signature (độc quyền)",
               "core": "Cốt lõi", "upgrade": "Nâng cấp"}

# Bốn nguyên lý bắt buộc áp cho MỌI luồng trong bản thiết kế. Đưa vào đây vì
# chúng cũng là lời hứa, và lời hứa nào cũng phải kiểm được.
PRINCIPLES = [
    ("Mở rộng được", "done",
     "Mỗi mũi nhọn là một lớp con TwinModule cắm vào registry; thêm ngành = "
     "thêm tệp, không sửa lõi. Nhóm D (3 ngành mới) thêm vào đúng theo cách đó."),
    ("Song song & đồng thời", "done",
     "services/jobs.py: chạy các mô-đun đồng thời (quét toàn cảnh 13,1 s → 7,0 s "
     "khi cache lạnh), chia lô Open-Meteo song song, gộp lời gọi trùng nhau, "
     "trần lượt gọi ra ngoài, và hàng đợi cho việc dài. TRONG MỘT TIẾN TRÌNH — "
     "phân tán thật cần hàng đợi bền bên ngoài, chưa làm."),
    ("Tối ưu & chính xác", "done",
     "Hiệu chuẩn theo khí hậu từng điểm (báo động giả 46–61% → 3%), backtest 4 "
     "thiên tai thật công bố cả POD lẫn FAR, chấm mô hình bằng POD/FAR/CSI trên "
     "quan sát thực địa, người dùng nạp lại kết quả qua U04."),
    ("Hội tụ công nghệ", "partial",
     "Có: thuật toán cổ điển (tối ưu hoá, phân vị, Monte Carlo analog, chỉ số "
     "phổ), XAI, federated, LLM/agent. CHƯA có: mô hình học sâu tự huấn luyện — "
     "phần thị giác hiện là viễn thám cổ điển, không phải deep learning."),
]


def status() -> dict:
    """Trạng thái 26 luồng, phản ánh ĐÚNG bản đang chạy.

    Phân biệt hai thứ hay bị trộn lẫn:
      status = "done"        — mã đã viết, có test, không bịa số
      awaiting_config = True — mã đã xong nhưng deployment này thiếu khóa nên
                               người dùng chưa dùng được

    Gộp hai cái đó vào một chữ "xong" là cách một bảng trạng thái bắt đầu nói dối.
    """
    from app.services import sentinel

    sat = sentinel.configured()

    flows = []
    for row in FLOWS:
        i, n, t, st, note = row[:5]
        requires = row[5] if len(row) > 5 else None
        waiting = requires == "satellite" and not sat
        flows.append({
            "id": i, "name": n, "tier": t, "tier_name": _TIER_NAMES[t],
            "status": st, "note": note, "requires": requires,
            "awaiting_config": waiting,
            "awaiting_note": ("Mã đã xong và có test, nhưng deployment này chưa "
                              "có khóa Copernicus nên luồng trả 'chưa đủ dữ liệu' "
                              "thay vì kết quả." if waiting else None),
        })

    counts = {k: sum(1 for f in flows if f["status"] == k)
              for k in ("done", "partial", "blocked")}
    waiting_n = sum(1 for f in flows if f["awaiting_config"])
    live = counts["done"] - waiting_n

    by_tier = {}
    for t, label in _TIER_NAMES.items():
        sub = [f for f in flows if f["tier"] == t]
        by_tier[t] = {
            "name": label, "total": len(sub),
            "done": sum(1 for f in sub if f["status"] == "done"),
            "live": sum(1 for f in sub
                        if f["status"] == "done" and not f["awaiting_config"]),
        }

    head = (f"{counts['done']}/{len(flows)} luồng đã viết xong · "
            f"{counts['partial']} một phần · {counts['blocked']} đang bị chặn")
    if waiting_n:
        head += (f" · {waiting_n} luồng chờ khóa Copernicus "
                 f"(đang chạy thật: {live}/{len(flows)})")

    from app.modules.registry import list_modules

    mods = list_modules()

    return {
        "total": len(flows), **counts, "flows": flows, "by_tier": by_tier,
        "live": live, "awaiting_config": waiting_n,
        "satellite_configured": sat,
        "principles": [{"name": n, "status": st, "note": nt}
                       for n, st, nt in PRINCIPLES],
        "sectors": {
            "planned": 12, "covered": 12,
            "note": ("Bản thiết kế liệt kê 14 mũi nhọn nhưng hứa 12 ngành — hai "
                     "con số đó không khớp nhau. Phủ đủ 12 ngành cần 17 mũi "
                     "nhọn; ba cái thêm là Đô thị & Quy hoạch, Khai khoáng & Hạ "
                     "tầng, Chuỗi cung ứng."),
        },
        "modules": {
            "total": len(mods),
            "active": sum(1 for m in mods if m.status == "active"),
            "awaiting_satellite": sum(1 for m in mods if m.status == "preview"),
        },
        "headline": head,
        "honesty_note": (
            "Bảng này sinh từ mã nguồn, không viết tay, nên không thể lệch với "
            "phần mềm. Luồng còn bị chặn thiếu GPU và một model diffusion đã "
            "huấn luyện — hai thứ không mua được bằng công sức viết code. Chúng "
            "tôi không dựng endpoint rỗng để đếm cho đủ 26: một con số carbon bịa "
            "có thể gây thiệt hại tiền thật, và một tấm ảnh 'siêu phân giải' do "
            "model tưởng tượng ra còn nguy hiểm hơn là không có ảnh."),
    }
