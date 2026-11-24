import argparse
import csv
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "experiments" / "raw-data"
CHILD_ENV = {**os.environ, "PYTHONUTF8": "1"}   # tránh lỗi in tiếng Việt khi chuyển hướng stdout trên Windows


def wait_port(host, port, timeout=10):
    import socket
    end = time.time() + timeout
    while time.time() < end:
        try:
            socket.create_connection((host, port), timeout=0.5).close()
            return True
        except OSError:
            time.sleep(0.2)
    return False


def run_one(cfg, clients, run_idx, cpu_writer, overwrite):
    tag = f"c{clients}_r{run_idx}"
    out_csv = RAW / f"loadgen_{tag}.csv"
    if out_csv.exists():
        if not overwrite:
            raise SystemExit(f"{out_csv.name} đã tồn tại. Dùng --overwrite nếu muốn chạy lại (sẽ mất dữ liệu cũ).")
        out_csv.unlink()

    server_cmd = [sys.executable, str(ROOT / cfg["server_script"]), "--host", cfg["host"],
                  "--port", str(cfg["port"]), *cfg["server_args"]]
    lg_cmd = [sys.executable, str(ROOT / cfg["loadgen_script"]), "--host", cfg["host"], "--port", str(cfg["port"]),
              "--clients", str(clients), "--payload-bytes", str(cfg["payload_bytes"]),
              "--warmup", str(cfg["warmup_s"]), "--duration", str(cfg["duration_s"]),
              "--output", str(out_csv), *cfg["loadgen_extra_args"]]

    with open(RAW / f"server_{tag}.log", "w", encoding="utf-8") as slog, \
            open(RAW / f"loadgen_{tag}.stdout.txt", "w", encoding="utf-8") as lgout:
        server = subprocess.Popen(server_cmd, cwd=ROOT, stdout=slog, stderr=subprocess.STDOUT, env=CHILD_ENV)
        try:
            if not wait_port(cfg["host"], cfg["port"]):
                raise RuntimeError("Server không khởi động được (cổng bị chiếm? xem server_*.log)")
            sp = psutil.Process(server.pid)
            t_launch = time.time()
            lg = subprocess.Popen(lg_cmd, cwd=ROOT, stdout=lgout, stderr=subprocess.STDOUT, env=CHILD_ENV)
            lp = psutil.Process(lg.pid)

            t_win_start = t_launch + cfg["warmup_s"] + 1
            t_win_end = t_launch + cfg["warmup_s"] + cfg["duration_s"]
            time.sleep(max(0, t_win_start - time.time()))
            sp.cpu_percent(None); lp.cpu_percent(None); psutil.cpu_percent(None)   # mồi bộ đếm

            s_cpu, l_cpu, y_cpu = [], [], []
            t0 = time.time()
            while True:
                time.sleep(cfg["cpu_sample_interval_s"])
                if time.time() > t_win_end or lg.poll() is not None:
                    break
                if server.poll() is not None:
                    raise RuntimeError("Server bị CRASH trong lúc đo!")
                s = sp.cpu_percent(None)
                try:
                    l = lp.cpu_percent(None)
                except psutil.NoSuchProcess:
                    break
                y = psutil.cpu_percent(None)
                s_cpu.append(s); l_cpu.append(l); y_cpu.append(y)
                cpu_writer.writerow([clients, run_idx, round(time.time() - t0, 2), s, l, y])

            lg_exit = lg.wait(timeout=cfg["warmup_s"] + cfg["duration_s"] + 60)
            server_alive = server.poll() is None
            rss = round(sp.memory_info().rss / 2 ** 20, 1) if server_alive else None
        finally:
            server.terminate()
            try:
                server.wait(5)
            except subprocess.TimeoutExpired:
                server.kill()

    avg = lambda xs: round(sum(xs) / len(xs), 2) if xs else None
    cores = psutil.cpu_count(logical=True)
    return {
        "clients": clients, "run": run_idx, "start": datetime.fromtimestamp(t_launch).isoformat(timespec="seconds"),
        "cpu_server_avg_pct": avg(s_cpu), "cpu_server_max_pct": max(s_cpu) if s_cpu else None,
        "cpu_server_avg_pct_of_total": round(avg(s_cpu) / cores, 2) if s_cpu else None,
        "cpu_loadgen_avg_pct": avg(l_cpu), "cpu_system_avg_pct": avg(y_cpu),
        "cpu_samples": len(s_cpu), "logical_cores": cores, "server_rss_mb": rss,
        "server_alive_after": server_alive, "loadgen_exit": lg_exit, "loadgen_csv": out_csv.name,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "experiments" / "configs" / "run-config.json"))
    ap.add_argument("--quick", action="store_true", help="chạy thử nhanh (warm-up 1s, đo 3s, 1 lần). Số liệu này KHÔNG dùng cho báo cáo")
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args()

    cfg = json.loads(Path(a.config).read_text(encoding="utf-8"))
    if a.quick:
        cfg.update(warmup_s=1, duration_s=3, repeats=1, cooldown_s=1)
        print("*** CHẾ ĐỘ CHẠY THỬ: số liệu không dùng cho báo cáo ***")
    RAW.mkdir(parents=True, exist_ok=True)
    print(f"Mức Client {cfg['client_levels']} x {cfg['repeats']} lần | payload {cfg['payload_bytes']} B | "
          f"warm-up {cfg['warmup_s']}s | đo {cfg['duration_s']}s")

    rows = []
    with open(RAW / "cpu_samples.csv", "w", newline="", encoding="utf-8") as f:
        cw = csv.writer(f)
        cw.writerow(["clients", "run", "t_s", "cpu_server_pct", "cpu_loadgen_pct", "cpu_system_pct"])
        for n in cfg["client_levels"]:
            for r in range(1, cfg["repeats"] + 1):
                print(f"[{datetime.now():%H:%M:%S}] {n} Client, lần {r}/{cfg['repeats']} ...", flush=True)
                row = run_one(cfg, n, r, cw, a.overwrite)
                rows.append(row)
                f.flush()
                tail = (RAW / f"loadgen_c{n}_r{r}.stdout.txt").read_text(encoding="utf-8", errors="replace").strip().splitlines()[1:]
                print("   " + " | ".join(tail))
                print(f"   CPU Server TB {row['cpu_server_avg_pct']}% (max {row['cpu_server_max_pct']}%), "
                      f"Load Generator TB {row['cpu_loadgen_avg_pct']}%")
                if not row["server_alive_after"] or row["loadgen_exit"] != 0:
                    print("   !!! CẢNH BÁO: Server chết hoặc Load Generator thoát lỗi, kiểm tra log")
                time.sleep(cfg["cooldown_s"])

    with open(RAW / "run_summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("Xong. Xem experiments/raw-data/run_summary.csv")


if __name__ == "__main__":
    main()
