# Nội dung Báo cáo Nghiên cứu — Phần phụ trách của Thành viên 1

## 1. Câu hỏi nghiên cứu và Phạm vi

### 1.1. Câu hỏi nghiên cứu
Đề tài xây dựng một nguyên mẫu dịch vụ phản hồi tối giản (Echo Benchmark) trên giao thức TCP nhằm trả lời câu hỏi nghiên cứu:
> **"Khi số lượng Client đồng thời tăng, latency, throughput và mức sử dụng CPU của TCP Server thay đổi như thế nào?"**

### 1.2. Phạm vi nghiên cứu
* **Dịch vụ thử nghiệm:** Ứng dụng Console hoạt động theo cơ chế Request/Response qua TCP/IPv4. Client gửi bản tin gồm `requestId` và `payload` (cố định 1 KB); Server nhận và phản hồi nguyên vẹn bản tin đó.
* **Môi trường triển khai:** TCP Server và chương trình tạo tải (Load Generator) chạy ở hai tiến trình (process) độc lập trên cùng một máy tính (giao diện loopback `127.0.0.1`) nhằm loại trừ độ trễ đường truyền vật lý. Mỗi Client logic mở một kết nối TCP riêng biệt.
* **Giới hạn đề tài:** Khảo sát tập trung vào tác động của số lượng kết nối đồng thời (các mức $1, 10, 50$ Clients) trên **một mô hình xử lý kết nối duy nhất (Thread Pool)**. Nghiên cứu không so sánh nhiều mô hình xử lý, không thử nghiệm nhiều kích thước payload và không xây dựng giao diện đồ họa (GUI).

---

## 2. Cơ sở lý thuyết

### 2.1. Truyền dữ liệu dòng byte trên TCP và bài toán Framing
TCP (Transmission Control Protocol) là giao thức tầng giao vận hướng kết nối, đảm bảo dữ liệu đến đích tin cậy và đúng thứ tự dưới dạng **dòng byte liên tục (byte-stream)**. Khác với UDP phân tách sẵn từng gói tin độc lập, TCP không lưu ranh giới logic của thông điệp tầng ứng dụng. Do cơ chế gom đệm của tầng giao vận (như thuật toán Nagle hoặc phân mảnh TCP), một lần gọi hàm `recv()` ở phía nhận có thể chỉ thu được một phần gói tin hoặc nhận gộp nhiều gói tin dính liền nhau.

Để giải quyết hiện tượng này, tầng ứng dụng phải quy định cơ chế phân tách thông điệp (**Message Framing**). Kỹ thuật **Length-Prefixed Framing** (gắn tiền tố độ dài cố định 4 byte ở đầu mỗi khung truyền) cho phép bên nhận biết chính xác tổng số byte cần đọc cho trọn vẹn một bản tin trước khi giải mã dữ liệu.

### 2.2. Mô hình xử lý đồng thời trên TCP Server
Để phục vụ nhiều Client cùng lúc, TCP Server thường triển khai theo một trong ba hướng:
1. **Blocking Socket (Thread-per-Connection):** Cấp phát một luồng hệ điều hành riêng cho từng kết nối; đơn giản nhưng tiêu tốn bộ nhớ stack và chi phí chuyển ngữ cảnh khi lượng kết nối tăng cao.
2. **Thread Pool:** Duy trì sẵn một nhóm luồng công nhân (worker threads) tái sử dụng được để xử lý các kết nối từ hàng đợi, giúp kiểm soát tài nguyên CPU và bộ nhớ ổn định.
3. **Asynchronous Socket (Non-blocking I/O):** Dùng vòng lặp sự kiện (`asyncio` / `epoll` / `IOCP`) để điều phối nhiều kết nối trên ít luồng thông qua cơ chế vào/ra bất đồng bộ.

### 2.3. Các chỉ số đánh giá hiệu năng
* **Độ trễ (Latency — ms):** Thời gian tính từ lúc Client bắt đầu gửi Request đến khi nhận đủ Response hợp lệ. Báo cáo đánh giá cả **Latency trung bình** và **p95 Latency** (ngưỡng độ trễ mà 95% số request hoàn thành nhanh hơn hoặc bằng giá trị này, phản ánh độ trễ đuôi khi tải cao).
* **Thông lượng (Throughput — req/s):** Tổng số request được xử lý thành công chia cho thời gian đo chính thức.
* **Tỷ lệ lỗi (Error Rate — %):** Tỷ lệ phần trăm số request thất bại (do timeout, ngắt kết nối hoặc sai lệch `requestId`/payload) trên tổng số request phát sinh.
* **Mức sử dụng CPU (%):** Tỷ lệ tài nguyên CPU mà tiến trình TCP Server tiêu thụ trong suốt khoảng thời gian đo.

---

## 3. Kiến trúc hệ thống và Đặc tả Protocol

### 3.1. Kiến trúc tổng thể
Hệ thống tách biệt tiến trình sinh tải (Load Generator) và tiến trình phục vụ (TCP Server) nhằm tránh tranh chấp trực tiếp bộ nhớ và luồng thực thi trong nội bộ tiến trình. TCP Server sử dụng mô hình **Thread Pool** tiếp nhận kết nối từ socket lắng nghe và giao cho các worker thread xử lý độc lập. *(Chèn sơ đồ kiến trúc từ file `docs/protocol-spec.md` mục 1.1 vào báo cáo)*.

### 3.2. Thiết kế giao thức Binary Echo Protocol
Mỗi bản tin trao đổi giữa Client và Server được đóng gói theo chuẩn nhị phân Network Byte Order (Big-Endian) gồm 3 trường:
1. **Body Length (4 bytes, `uint32`):** Độ dài phần thân đi kèm (`8 + len(payload)`). Giá trị được kiểm tra chặt chẽ trong khoảng $[8, 65536]$ bytes để loại bỏ gói tin rác hoặc vượt quá kích thước cho phép.
2. **Request ID (8 bytes, `uint64`):** Số định danh tăng dần cho mỗi yêu cầu của Client, dùng để đối chiếu tính chính xác khi nhận phản hồi.
3. **Payload (1024 bytes):** Mảng byte dữ liệu cố định 1 KB.

Mọi ngoại lệ như Client ngắt kết nối đột ngột, quá thời gian chờ (`timeout`) hoặc gói tin sai độ dài đều được bắt và xử lý gói gọn trong phạm vi luồng phục vụ Client đó, đảm bảo Server duy trì hoạt động ổn định cho các kết nối còn lại.
