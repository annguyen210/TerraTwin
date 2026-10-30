# Kịch bản demo 3 phút + hỏi–đáp giám khảo

Một câu chuyện duy nhất: **"Định mua đất? Kiểm lời rao trước khi xuống tiền."** Mọi thứ khác (canh đất, so sánh,
hàng loạt, EUDR, 18 công cụ chuyên sâu) chỉ nhắc khi giám khảo hỏi. Trang đầu đã gọt theo đúng câu chuyện này
(29/10/2026): nút đầu tiên là "Kiểm một tin đăng mẫu — ruộng ngập bão Yagi".

**Thửa demo:** ruộng xã Tuệ Tĩnh, Hải Phòng (Cẩm Giàng, Hải Dương cũ), toạ độ `20.9716, 106.2834`. Bản đồ ngập UNOSAT
ngày 10/9/2024 (bão Yagi) ghi điểm này ngập. Thửa dự phòng: Hoàn Lão, Quảng Trị `17.6118, 106.5026` (lũ 28/10/2020,
UNOSAT 29/10/2020). Cả hai được hâm nóng tự động mỗi 6 giờ (`backend/app/services/demo_plots.py`).

**Tin mẫu** (`frontend/lib/demo.ts`) do TerraTwin soạn để minh hoạ, **không phải tin rao thật**. Ô kiểm tin tự ghi
dòng đó; khi nói cũng phải nói rõ như vậy.

## Chuẩn bị

| Khi nào | Việc |
|---|---|
| Ngày trước | Chạy thử toàn bộ kịch bản trên bản thật, ghi lại kết quả thật vào cột "Kết quả thật" bên dưới. Quay màn hình một lượt chạy trơn tru làm **video dự phòng**. |
| Ngày trước | Mở `/status`: API, CSDL, email đều xanh. Render miễn phí có 750 giờ/tháng cho cả workspace — nếu tháng thi đã dùng gần hết thì cân nhắc gói Starter cho riêng tháng đó. |
| 15 phút trước | GitHub → Actions → **Keep warm** → Run workflow (mặc định giữ 90 phút, đọc sẵn 3 thửa demo). |
| 5 phút trước | Mở sẵn 3 tab: trang đầu `terratwin-web.vercel.app`, `/kiem`, `/mo-hinh`. Tắt thông báo máy. Không đăng nhập tài khoản quản trị trên máy trình chiếu. |
| Nếu API không trả lời | Chiếu video dự phòng, nói thẳng: "máy chủ miễn phí đang ngủ — đây là bản quay lúc nó chạy". |

## Kịch bản (3 phút)

| Thời gian | Bấm | Nói (ý chính, không đọc thuộc) | Kết quả thật (điền khi tập) |
|---|---|---|---|
| 0:00–0:20 | (trang đầu) | "Sau bão Yagi, người bán đất ở đồng bằng Bắc Bộ vẫn viết 'đất cao ráo, không bao giờ ngập'. Người mua kiểm câu đó bằng cách nào? Hỏi hàng xóm. TerraTwin cho họ cách khác: hỏi vệ tinh." | |
| 0:20–1:00 | **Kiểm một tin đăng mẫu — ruộng ngập bão Yagi** → **Đối chiếu với số đo** | "Đây là tin mẫu chúng tôi soạn, nhưng thửa là thật. Máy tách năm lời khẳng định và đặt từng câu cạnh số đo." Chỉ vào câu **"không bao giờ ngập" → Mâu thuẫn**: radar thấy nước phủ, có ngày 12/9/2024. Chỉ câu **"thổ cư" → Không đủ dữ liệu**: "Pháp lý chúng tôi không đoán — dữ liệu địa chính không công khai." | Mâu thuẫn: … · Khớp: … · Không đủ: … |
| 1:00–1:45 | Tab **Hồ sơ** → dải lịch sử nước → bấm đợt **9/2024** | "Đây là 9 năm ảnh radar Sentinel-1 của đúng thửa này, nhìn xuyên mây, chụp được cả giữa bão. Mỗi chấm là một ngày nước phủ." Bấm đợt → ảnh radar ngày đó hiện trên bản đồ. "Bản đồ ngập UNOSAT của Liên Hợp Quốc ngày 10/9/2024 cũng ghi điểm này ngập — đó là bản đồ của người khác, không phải của chúng tôi." | Số đợt: … · ý kiến U-Net đợt 9/2024: … |
| 1:45–2:25 | Quay lại **Kiểm chứng** → **Đưa kết quả vào Hồ sơ đất số ký số** → trang hồ sơ → tab `/kiem` dán mã | "Kết quả thành hồ sơ có chữ ký số, ghi vào sổ minh bạch, neo thời gian lên Bitcoin. Người bán, ngân hàng quét QR là kiểm lại được — sửa một chữ là báo đỏ, kể cả chúng tôi sửa." | Mã hồ sơ: … · "Bản gốc — đã kiểm chứng" |
| 2:25–3:00 | (cuộn trang đầu tới **Vì sao tin được**) | "Chúng tôi tự chấm bằng dữ liệu người khác làm ra: 60/80 điểm ngập trên bản đồ UNOSAT radar bắt được, 0/73 điểm khô bị báo nhầm. Chỗ yếu cũng công khai: vệ tinh khác Sentinel-1 chỉ khớp 6/16. TerraTwin không nói đất tốt hay xấu — nó đưa bằng chứng để người mua tự quyết, và ai cũng kiểm lại được." | |

Ba điều **không nói**: "chính xác 100%"; số người dùng hay số khách khi chưa có thật; "thay sổ đỏ / thay thẩm định
viên". Không gọi nhãn AI là nhãn người.

## Hỏi–đáp giám khảo hay hỏi

**1. Khác gì Google Earth hay chụp ảnh gửi ChatGPT?**
Google Earth cho xem ảnh, không đếm số lần nước phủ một thửa qua 9 năm; ảnh quang học bị mây che đúng lúc bão.
Chatbot đoán theo hiểu biết chung về vùng, không ai chấm điểm câu trả lời và đoạn chữ ai cũng sửa được. TerraTwin đọc
radar của đúng thửa, công bố tỉ lệ sai, ký số kết quả. (Bảng so sánh có ngay trên trang đầu.)

**2. Radar sai thì sao? Chính xác bao nhiêu?**
Đối chiếu 10 trận lũ 2020–2025 trên bản đồ UNOSAT: 60/80 điểm ngập có đợt nước (0,75), 0/73 điểm khô bị báo nhầm.
Phần thật sự độc lập — bản đồ từ vệ tinh khác Sentinel-1 — chỉ 6/16. Sai nhiều ở đô thị, rừng rậm, sườn dốc; chu kỳ
chụp 6–12 ngày nên lọt đợt ngập ngắn. Tất cả có trên `/mo-hinh`.

**3. Kiểm tin rao "F1 0,98" nghĩa là gì?**
Đó là độ đúng của việc **nhận ra câu khẳng định** trong tin (câu nào nói "không ngập", câu nào nói "thổ cư"…) trên 30
tin rao Facebook thật, nhãn do người gán, chấm một lần sau khi khoá luật. Nó không phải độ đúng của phán quyết Khớp/Mâu
thuẫn — phán quyết dựa trên radar và địa hình ở câu 2. Giới hạn đã công khai: chủ dự án tự gán nhãn; 0/5 chỗ sửa
luật lần 9 có trong mẫu mới nên chưa được kiểm; các lần trước có lần trượt, cũng công bố.

**4. Sao không kiểm được thổ cư, quy hoạch?**
Cần dữ liệu địa chính, không công khai qua mạng. TerraTwin trả lời "Không đủ dữ liệu" thay vì đoán, và ghi rõ người
mua phải hỏi văn phòng đăng ký đất đai.

**5. Dữ liệu từ đâu, có hợp pháp không?**
Sentinel-1/2 (Copernicus, mở miễn phí), ERA5 (khí hậu tái phân tích), ESA WorldCover, bản đồ ngập UNOSAT công khai,
OpenStreetMap. Ghi nguồn ở từng câu kết quả.

**6. Đã có ai dùng chưa?**
Trả lời đúng số thật tại thời điểm thi (phiếu góp ý ở `/thi-diem`, xác nhận thực địa từng đợt nước). Nếu chưa có thì
nói "đang thí điểm" — đừng làm tròn lên.

**7. Kiếm tiền thế nào?**
Giai đoạn thử nghiệm: miễn phí, mọi tài khoản đủ tính năng, chưa thu tiền. Hướng khách trả tiền là tổ chức: ngân hàng
và công ty bảo hiểm thẩm định nhiều thửa (`/batch`, API có khoá), doanh nghiệp xuất khẩu cà phê, cao su cần hồ sơ
không phá rừng cho EU (`/eudr`), môi giới muốn chứng minh đất "sạch". Người mua lẻ dùng miễn phí.

**8. Chi phí vận hành?**
0 đồng hiện nay: web trên Vercel, API trên Render miễn phí, CSDL Neon. Giới hạn: API ngủ sau 15 phút không dùng, 750
giờ/tháng cho cả workspace. Ra thị trường thì trả gói máy chủ — chi phí nhỏ so với một lần thẩm định.

**9. Mở rộng được không?**
Mỗi thửa mới đọc radar lần đầu mất 1–3 phút, sau đó giữ 6 ngày; chạy qua hàng đợi bền. Nhiều người dùng thì tăng máy
chủ và số luồng đọc — không phải viết lại.

**10. Chữ ký số chứng minh được gì?**
Chứng minh hồ sơ **không bị sửa** sau khi phát hành và **phát hành lúc nào** (sổ Merkle RFC 6962, neo OpenTimestamps
lên Bitcoin, script kiểm độc lập `ops/verify_dossier.py`). Nó **không** chứng minh đất sẽ không ngập trong tương lai,
và không thay giấy chứng nhận quyền sử dụng đất.

**11. AI nằm ở đâu?**
U-Net trên ảnh radar cho ý kiến thứ hai từng đợt nước; mô hình loại đất từ AlphaEarth; mô hình ngôn ngữ chỉ viết lại lời
từ bằng chứng có sẵn, câu nào có con số lạ bị bỏ. Mỗi mô hình chỉ bật khi qua ngưỡng đặt trước; các bản trượt vẫn nằm
trên `/mo-hinh`.

**12. Quyền riêng tư?**
Không lưu nguyên văn tin rao người dùng dán; hồ sơ vườn ẩn tên chủ hộ mặc định; tuân Luật Bảo vệ dữ liệu cá nhân
91/2025 (`/privacy`).

**13. Zillow từng gắn điểm rủi ro khí hậu rồi phải gỡ — sao TerraTwin khác?**
Không đưa một điểm số hộp đen: mỗi câu kết quả bấm ra số đo, ngày, nguồn; tự công bố tỉ lệ sai trên dữ liệu độc lập.

**14. Ai làm phần nào?**
Tự trả lời thật: phần bạn quyết định (hướng sản phẩm, thửa demo, gán nhãn tin rao, thí điểm) và phần dùng công cụ hỗ
trợ lập trình. Giám khảo đánh giá cao sự rõ ràng hơn là nói quá.

## Sau mỗi lần tập

- Điền cột "Kết quả thật"; nếu kết quả khác kịch bản (ví dụ radar không thấy đợt 9/2024) thì **sửa lời nói theo dữ
  liệu**, không sửa dữ liệu theo lời nói.
- Ghi thời gian thật của từng đoạn; quá 3 phút thì bỏ đoạn hồ sơ ký số, chỉ nói một câu.
