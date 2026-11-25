# Đánh giá ảnh hưởng của số lượng Client đồng thời đến hiệu năng TCP Server

Dự án nghiên cứu thực nghiệm đo lường và phân tích hiệu năng của ứng dụng **TCP Server viết bằng Python** khi chịu tải đồng thời ở các mức **1, 10 và 50 Client**, tập trung vào các chỉ số: Thông lượng (*Throughput*), Độ trễ trung bình (*Average Latency*), Độ trễ phân vị 95 (*p95 Latency*), Tỷ lệ lỗi (*Error Rate*) và Mức tiêu thụ tài nguyên (*CPU, RAM*).

---

## 1. Cấu trúc thư mục dự án

```text
project-root/
├── .gitignore                          # Loại trừ file tạm (__pycache__/, venv/, .vscode/)
├── README.md                           # Tài liệu hướng dẫn cài đặt và tái tạo thực nghiệm
│
├── src/                                # Mã nguồn chính của hệ thống
│   ├── protocol/                       # Module định nghĩa giao thức tầng ứng dụng
│   │   ├── __init__.py
│   │   └── framing.py                  # Length-Prefixed Framing (4-byte Big-Endian) chống dính gói
│   ├── server/                         # Mã nguồn TCP Server
│   │   ├── __init__.py
│   │   └── server.py                   # TCP Server xử lý đa kết nối đồng thời
│   └── load-generator/                 # Chương trình giả lập tải Client
│       ├── client.py                   # Tạo tải đồng thời 1, 10, 50 Clients & ghi log CSV
│       └── mock_server.py              # Server giả lập phục vụ kiểm thử nội bộ
│
├── tests/                              # Bộ kiểm thử chức năng và chịu lỗi
│   └── test_qa_server.py               # Kiểm thử 1/nhiều client, ngắt kết nối đột ngột, dữ liệu lỗi
│
├── experiments/                        # Cấu hình, dữ liệu thô và phân tích thực nghiệm
│   ├── configs/                        # Kịch bản và script tự động hóa thực nghiệm
│   │   ├── run-config.json             # Tham số IP, Port, mức tải (1/10/50), payload 1024 bytes
│   │   ├── env_info.py                 # Script thu thập thông số phần cứng & môi trường chạy
│   │   └── run_experiments.py          # Script chạy lặp tự động 3 lần cho mỗi mức tải
│   ├── raw-data/                       # Dữ liệu đo thô định dạng CSV (loadgen_c*_r*.csv, per_run_summary.csv)
│   ├── analysis/                       # Xử lý thống kê và tổng hợp kết quả
│   │   ├── analyze_results.py          # Script tính TB ± SD, p95 latency, throughput, CPU
│   │   └── aggregate_summary.csv       # Bảng tổng hợp chỉ số trung bình và độ lệch chuẩn
│   └── figures/                        # Biểu đồ trực quan hóa kết quả thực nghiệm (.png)
│
└── docs/                               # Tài liệu đặc tả và báo cáo nghiên cứu
    ├── project-management.md           # Bảng phân công và theo dõi tiến độ nhóm
    ├── protocal-spec.md                # Đặc tả giao thức bản tin JSON và quy tắc framing
    ├── report-tv1-section.md           # Nội dung kiến trúc & giao thức hệ thống
    ├── report-analysis.md              # Nội dung phân tích số liệu & giới hạn hệ thống
    └── Bao_Cao_Research_TCP_Server.pdf # Báo cáo nghiên cứu hoàn chỉnh (PDF)
```

---

## 2. Yêu cầu môi trường

* **Hệ điều hành:** Windows 10/11 hoặc Linux (thực nghiệm chuẩn hóa trên hệ thống 12 logical cores).
* **Ngôn ngữ:** Python 3.10 trở lên.
* **Thư viện sử dụng:**
  * Thư viện chuẩn Python: `socket`, `threading` / `selectors`, `struct`, `json`, `csv`, `time`.
  * Thư viện bổ trợ (dùng cho giám sát tài nguyên và vẽ biểu đồ): `psutil`, `matplotlib`.

Cài đặt nhanh các thư viện bổ trợ (nếu cần):
```bash
pip install psutil matplotlib
```

---

## 3. Hướng dẫn tái tạo thực nghiệm

### Bước 1: Kiểm tra thông số môi trường và chạy kiểm thử chức năng
Thu thập thông tin cấu hình máy tính và chạy bộ test đảm bảo Server xử lý đúng giao thức và ngoại lệ:
```bash
python experiments/configs/env_info.py
python -m unittest tests/test_qa_server.py
```

### Bước 2: Khởi chạy TCP Server và Load Generator thủ công (tùy chọn)
Mở 2 cửa sổ Terminal tại thư mục gốc dự án:
* **Terminal 1 (Chạy Server):**
  ```bash
  python src/server/server.py
  ```
* **Terminal 2 (Chạy Client tạo tải):**
  ```bash
  python src/load-generator/client.py
  ```

### Bước 3: Chạy toàn bộ kịch bản thực nghiệm tự động (3 lần lặp / mức tải)
Chạy script điều phối để tự động thực thi lần lượt các mức **1, 10 và 50 Client** (mỗi mức lặp 3 lần độc lập, tách riêng pha `warmup` và pha `measure` 20 giây với kích thước gói tin 1024 bytes):
```bash
python experiments/configs/run_experiments.py
```
Dữ liệu chi tiết từng request và từng lượt chạy sẽ được xuất vào thư mục `experiments/raw-data/`.

### Bước 4: Tổng hợp số liệu thống kê và xuất biểu đồ
Chạy script phân tích để tính các chỉ số `TB ± SD` (`aggregate_summary.csv`) và lưu biểu đồ vào `experiments/figures/`:
```bash
python experiments/analysis/analyze_results.py
```

---

## 4. Tóm tắt kết quả thực nghiệm chính

Kết quả đo đạc trung bình qua 3 lần chạy độc lập (`TB ± SD`) ở pha đo chính thức (tổng cộng 4.392.852 request):

| Số Client | Throughput (req/s) | Avg Latency (ms) | p95 Latency (ms) | Server CPU (%) | Error Rate (%) |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **1** | 20,621.08 ± 1,717.76 | 0.0373 ± 0.0033 | 0.0580 ± 0.0165 | 56.59 ± 2.33 | 0% |
| **10** | 26,943.77 ± 415.17 | 0.3544 ± 0.0054 | 0.6883 ± 0.0136 | 184.33 ± 4.96 | 0% |
| **50** | 25,649.35 ± 162.73 | 1.9315 ± 0.0124 | 4.0470 ± 0.0197 | 194.79 ± 0.91 | 0% |

---

## 5. Phân công thành viên

| Vai trò | Họ và tên / MSSV | Nhiệm vụ chính |
| :---: | :--- | :--- |
| **TV1** | `[Điền tên TV1]` | Thiết kế kiến trúc, đặc tả giao thức & module `framing.py`, quản lý tiến độ |
| **TV2** | `[Điền tên TV2]` | Lập trình TCP Server đa kết nối (`server.py`) và cơ chế ghi log lỗi |
| **TV3** | `[Điền tên TV3]` | Lập trình chương trình tạo tải (`client.py`) và cấu hình kịch bản đo |
| **TV4** | `[Điền tên TV4]` | Xây dựng bộ kiểm thử (`test_qa_server.py`), chạy đo 3 lần lặp & thu thập `raw-data` |
| **TV5** | `[Điền tên TV5]` | Viết script xử lý thống kê (`analyze_results.py`), vẽ biểu đồ & phân tích kết quả |
| **TV6** | `[Điền tên TV6]` | Nghiên cứu cơ sở lý thuyết, tổng hợp & biên tập Báo cáo PDF, hoàn thiện `README.md` |
