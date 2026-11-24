# Quản lý Tiến độ Dự án & Bảng Đóng góp Thành viên

## 1. Kế hoạch triển khai 4 tuần

| Tuần | Công việc chính | Phụ trách | Trạng thái / Tiêu chí hoàn thành |
| :--- | :--- | :--- | :--- |
| **Tuần 1** | Chốt câu hỏi, phạm vi, protocol, cấu trúc repo & dựng khung cơ bản | TV 1 (chủ trì), TV 2, TV 3 | Hoàn thành `protocol-spec.md`, module `framing.py`; Server & Load Generator kết nối được với nhau. |
| **Tuần 2** | Hoàn thiện Prototype, xử lý kết nối, timeout, disconnect & dữ liệu lỗi | TV 2, TV 3, TV 4 | Server và Load Generator chạy ổn định với Framing; xử lý tốt các ca ngắt kết nối và gói tin sai định dạng. |
| **Tuần 3** | Chạy các mức Client (1, 10, 50), lưu dữ liệu thô & vẽ biểu đồ | TV 4, TV 5 | Đủ dữ liệu CSV/JSON ($\ge 3$ lần chạy/mức); hoàn thành script kiểm tra chéo 3 trường hợp và $\ge 2$ biểu đồ. |
| **Tuần 4** | Phân tích kết quả, hoàn thiện báo cáo PDF, README & slide demo | TV 6, TV 1 & Cả nhóm | Hoàn thiện báo cáo 4–6 trang nội dung chính, kiểm tra chéo toàn nhóm trước khi nộp bài. |

---

## 2. Bảng đóng góp của các thành viên (Đưa vào Báo cáo PDF)

| STT | Thành viên | Vai trò chính | Công việc cụ thể & Sản phẩm bàn giao |
| :--- | :--- | :--- | :--- |
| 1 | *[TV 1]* | Kiến trúc, Protocol & Điều phối | Chốt mô hình Thread Pool và quy tắc Framing, lập trình module `src/protocol/framing.py`, viết đặc tả Protocol, quản lý GitHub/merge nhánh, viết phần Câu hỏi, phạm vi, cơ sở lý thuyết & kiến trúc báo cáo. |
| 2 | *[TV 2]* | Lập trình TCP Server | Xây dựng Console TCP Server (`src/server/`), cấu hình IP/Port, xử lý lỗi ngắt kết nối/timeout/gói tin rác. |
| 3 | *[TV 3]* | Lập trình Load Generator | Xây dựng chương trình tạo tải độc lập (`src/load-generator/`), đối chiếu `requestId`/payload, đo latency/throughput/error rate và xuất CSV/JSON. |
| 4 | *[TV 4]* | Kiểm thử (QA) & Thực nghiệm | Xây dựng bộ test case kiểm chứng, chạy thực nghiệm 3 lần/kịch bản (1, 10, 50 Clients) trên 1 máy cố định và đo CPU Server. |
| 5 | *[TV 5]* | Phân tích dữ liệu & Biểu đồ | Viết script kiểm tra chéo độc lập dữ liệu thô (`experiments/analysis/`), vẽ $\ge 2$ biểu đồ và phân tích độ dao động. |
| 6 | *[TV 6]* | Báo cáo PDF, Tài liệu & Slide | Biên tập báo cáo PDF hoàn chỉnh (4–6 trang), chuẩn hóa trích dẫn, viết `README.md` và làm slide/video demo. |
