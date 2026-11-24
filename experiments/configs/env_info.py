import json
import platform
import socket
import subprocess
import sys
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[2]


def cpu_model():
    try:
        for line in open("/proc/cpuinfo", encoding="utf-8"):
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    if platform.system() == "Windows":
        try:
            out = subprocess.run(["powershell", "-NoProfile", "-Command",
                                  "(Get-CimInstance Win32_Processor).Name"],
                                 capture_output=True, text=True, timeout=10).stdout.strip()
            if out:
                return out
        except Exception:  # noqa: BLE001
            pass
    return platform.processor() or "không xác định (ghi tay)"


def git_commit():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, timeout=5).stdout.strip() or "không có git"
    except Exception:  # noqa: BLE001
        return "không có git"


def main():
    info = {
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "machine": platform.machine(),
        "cpu_model": cpu_model(),
        "cpu_physical_cores": psutil.cpu_count(logical=False),
        "cpu_logical_cores": psutil.cpu_count(logical=True),
        "ram_gb": round(psutil.virtual_memory().total / 2 ** 30, 1),
        "python": sys.version.split()[0],
        "git_commit": git_commit(),
        "network": "loopback 127.0.0.1, Server và Load Generator cùng một máy",
        "hostname": socket.gethostname(),
        "ghi_chu_thu_cong": "Ghi thêm: tên/đời máy, cắm sạc hay dùng pin, chế độ nguồn (High performance?), đã đóng app nền chưa",
    }
    out = ROOT / "experiments" / "raw-data" / "environment.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")
    print("| Thông số | Giá trị |\n|---|---|")
    for k, v in info.items():
        print(f"| {k} | {v} |")


if __name__ == "__main__":
    main()
