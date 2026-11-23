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