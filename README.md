<<<<<<< Updated upstream
## Chạy thử Load Generator

Cần Python 3. Mở hai terminal tại thư mục gốc của repo.

Terminal 1 chạy mock server:

```powershell
py src/load-generator/mock_server.py
```

Khi server báo đang nghe trên cổng 19000, chạy ở terminal 2:

```powershell
py src/load-generator/client.py --port 19000 --clients 10 --output experiments/raw-data/demo-c10.csv
```

Mặc định payload là 1.024 byte, warm-up 5 giây và đo 20 giây.
Đổi `--clients` thành 1, 10 hoặc 50 và dùng tên CSV mới cho mỗi lượt.
Khi phân tích CSV, lọc `phase=measure`. Dòng `status=ok` là phản hồi
đã khớp cả request ID và payload.

Đã kiểm tra cục bộ với mock server ở 1, 10 và 50 client, và đã xác nhận
CSV ghi lỗi khi server tắt. Việc tích hợp sẽ thực hiện khi server nhóm sẵn sàng.# tcp-server-load-benchmark
=======
# TCP Server Load Benchmark

## TCP server (thành viên 2)

Server TCP echo nằm trong `src/server/`. Server xử lý nhiều kết nối đồng thời; mỗi
request là một JSON object UTF-8 kết thúc bằng ký tự xuống dòng (`\n`). Cách đóng
khung này giúp server phân biệt các request liên tiếp trên cùng một kết nối.

Request hợp lệ có dạng:

```json
{"requestId":"req-1","payload":"hello"}
```

Server trả lại đúng `requestId` và `payload`:

```json
{"requestId":"req-1","payload":"hello"}
```

`payload` có thể là chuỗi, số, boolean, `null`, mảng hoặc object JSON. Request sai
định dạng nhận response có `error.code` (`invalid_json`, `invalid_request` hoặc
`request_too_large`). Lỗi kết nối, client ngắt đột ngột và timeout được ghi log
phía server; các lỗi của một client không làm dừng server.

### Chạy server

Yêu cầu Python 3.9 trở lên, không cần cài package ngoài:

```powershell
python src/server/server.py --host 127.0.0.1 --port 9000
```

Thay `--host` bằng địa chỉ IP cần bind (dùng `0.0.0.0` để nhận kết nối từ máy
khác trong mạng). Có thể cấu hình thêm `--max-request-bytes` (mặc định 1 MiB)
và `--client-timeout` (mặc định 30 giây). Dừng server bằng `Ctrl+C`.

### Chạy kiểm thử

```powershell
python -m unittest discover -s tests -v
```
>>>>>>> Stashed changes
