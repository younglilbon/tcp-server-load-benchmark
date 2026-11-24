# Đặc tả Kiến trúc & Giao thức Truyền thông (Protocol Specification)

## 1. Kiến trúc hệ thống & Mô hình xử lý kết nối

### 1.1. Tổng quan kiến trúc
Hệ thống gồm 2 tiến trình (process) chạy độc lập trên cùng máy đo thông qua TCP/IPv4 (mặc định `127.0.0.1:8080`, cấu hình linh hoạt qua tham số hoặc file config):
* **TCP Server (`src/server/`):** Lắng nghe kết nối, đọc từng bản tin Request và gửi trả nguyên vẹn Response (Echo).
* **Load Generator (`src/load-generator/`):** Khởi tạo $N$ Client logic ($N \in \{1, 10, 50\}$). Mỗi Client duy trì **một kết nối TCP riêng biệt** trong suốt phiên đo.

```text
+-----------------------+                        +-----------------------------------+
|    Load Generator     |                        |            TCP Server             |
|  (Separate Process)   |                        |        (Separate Process)         |
|                       |   TCP Connection #1    |                                   |
|  [Client Logic 1] ----+----------------------->|  Listener Socket (IP:Port)        |
|  [Client Logic 2] ----+----------------------->|         |                         |
|         ...           |   TCP Connection #N    |         v                         |
|  [Client Logic N] ----+----------------------->|  Thread Pool (Worker Threads)     |
|                       |                        |  -> Framing Decoder (framing.py)  |
|  (Đo Latency, p95,    |   Echo Response Frame  |         |                         |
|   Throughput, Error)  |<-----------------------+  Echo Handler (Phản hồi y nguyên)|
+-----------------------+                        +-----------------------------------+
```

### 1.2. Mô hình đồng thời của TCP Server: Thread Pool
* **Mô hình lựa chọn:** **Thread Pool** (`concurrent.futures.ThreadPoolExecutor` kết hợp TCP Blocking Socket).
* **Cơ sở lựa chọn:**
  1. Tái sử dụng tập luồng công nhân (worker threads) thay vì tạo/hủy OS thread liên tục cho từng kết nối, hạn chế chi phí chuyển ngữ cảnh (context switching) khi tăng số Client từ 1 lên 10 và 50.
  2. Tương thích trực tiếp với module đóng gói nhị phân `src/protocol/framing.py`, giúp mã nguồn Server rõ ràng, dễ kiểm soát ngoại lệ trên từng socket độc lập.

---

## 2. Quy tắc đóng gói & Phân tách gói tin (Length-Prefixed Framing)

### 2.1. Cấu trúc khung bản tin (Frame Format)
Để khắc phục hiện tượng phân mảnh hoặc dính gói tin trên dòng byte TCP, mọi bản tin Request và Response đều dùng chung định dạng nhị phân gồm **12 bytes Header** + **Payload**:

```text
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                       Body Length (4 bytes)                   |  -> uint32 Big-Endian (= 8 + len(Payload))
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                                                               |
+                     Request ID (8 bytes)                      +  -> uint64 Big-Endian
|                                                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                                                               |
~                  Payload Data (N bytes)                       ~  -> Mặc định 1024 bytes (1 KB)
|                                                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

* **`Body Length` (4 bytes, `uint32` Big-Endian, `!I`):** Tổng số byte theo sau 4 byte độ dài (`8 + len(Payload)`). Giá trị hợp lệ nằm trong khoảng `[8, 65536]` bytes.
* **`Request ID` (8 bytes, `uint64` Big-Endian, `!Q`):** Mã định danh duy nhất của từng request. Server phải giữ nguyên giá trị này trong gói Response.
* **`Payload Data` ($N$ bytes):** Dữ liệu thử nghiệm kích thước cố định `1024 bytes` (1 KB).

### 2.2. Hàm dùng chung (`src/protocol/framing.py`)
TV 2 (Server) và TV 3 (Load Generator) import trực tiếp 2 hàm chuẩn sau để giao tiếp:
* `pack_message(request_id: int, payload: bytes) -> bytes`: Đóng gói bản tin trước khi gọi `sock.sendall()`.
* `recv_message(sock: socket.socket) -> tuple[int, bytes]`: Đọc vòng lặp đủ 4 byte header, kiểm tra giới hạn `[8, 65536]` và đọc đủ phần thân bản tin.

---

## 3. Quy tắc xử lý lỗi & Tham số thực nghiệm chuẩn

| Tình huống | Yêu cầu xử lý phía Server | Yêu cầu xử lý phía Client (Load Generator) |
| :--- | :--- | :--- |
| **Client ngắt kết nối đột ngột** | Bắt `ConnectionResetError` / `EOF`, đóng socket Client đó và giữ Server hoạt động bình thường. | Ghi nhận lỗi kết nối nếu xảy ra trong pha đo. |
| **Timeout** | Đặt `sock.settimeout(5.0)` cho mỗi kết nối Client. | Đặt `sock.settimeout(3.0)`. Quá hạn tính là 1 request lỗi. |
| **Gói tin sai định dạng / quá cỡ** | `recv_message()` ném `ProtocolError` khi `body_len < 8` hoặc `> 65536` $\rightarrow$ từ chối và đóng socket vi phạm. | Đối chiếu `resp_id == req_id` và `resp_payload == req_payload`; sai lệch tính là 1 request lỗi. |

* **Tham số đo thống nhất:** Payload `1024 bytes` (1 KB), Warm-up `5 giây`, Thời gian đo chính thức `20 giây`, các mức Client: `1`, `10`, `50`, lặp lại tối thiểu `3 lần`/mức.

---

## 4. Cấu trúc thư mục chuẩn của toàn dự án
Các thành viên tuân thủ cây thư mục gốc khi đẩy bài lên GitHub:
* `src/protocol/`: Module framing dùng chung (TV 1)
* `src/server/`: Mã nguồn TCP Server (TV 2)
* `src/load-generator/`: Mã nguồn Load Generator (TV 3)
* `experiments/configs/`, `raw-data/`, `analysis/`, `figures/`: Cấu hình, dữ liệu thô CSV/JSON, script kiểm chứng và biểu đồ (TV 3, TV 4, TV 5)
* `docs/`: Tài liệu đặc tả, quản lý tiến độ và nội dung báo cáo (TV 1, TV 6)
