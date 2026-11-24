from pathlib import Path
import argparse
import re
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "experiments" / "raw-data"
OUT = ROOT / "experiments" / "analysis"
FIG = ROOT / "experiments" / "figures"
DURATION_SECONDS = 20.0
EXPECTED_LEVELS = [1, 10, 50]


def read_loadgen_files():
    files = sorted(RAW.glob("loadgen_c*_r*.csv"))
    if not files:
        raise FileNotFoundError(f"Không tìm thấy loadgen_c*_r*.csv trong {RAW}")
    frames = []
    for path in files:
        match = re.fullmatch(r"loadgen_c(\d+)_r(\d+)\.csv", path.name)
        if not match:
            continue
        clients, run = map(int, match.groups())
        df = pd.read_csv(path)
        required = {"run_id", "client_count", "client_id", "request_id", "phase",
                    "sent_ms", "received_ms", "latency_ms", "status"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"{path.name} thiếu cột: {sorted(missing)}")
        df["source_file"] = path.name
        df["clients_from_filename"] = clients
        df["run_from_filename"] = run
        frames.append(df)
    if not frames:
        raise ValueError("Không có file CSV nào đúng định dạng loadgen_cN_rN.csv")
    return frames


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, default=DURATION_SECONDS,
                        help="Thời gian đo chính thức (giây), mặc định 20")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)

    frames = read_loadgen_files()
    run_rows, check_rows = [], []
    all_measure = []

    for df in frames:
        filename = df["source_file"].iloc[0]
        clients = int(df["clients_from_filename"].iloc[0])
        run = int(df["run_from_filename"].iloc[0])
        measure = df[df["phase"].astype(str).str.lower() == "measure"].copy()
        all_measure.append(measure)
        ok = measure["status"].astype(str).str.lower().eq("ok")
        success = measure[ok]
        latency = pd.to_numeric(success["latency_ms"], errors="coerce").dropna()

        duplicate_count = int(measure.duplicated(
            subset=["run_id", "client_id", "request_id"], keep=False
        ).sum())

        sent = pd.to_numeric(measure["sent_ms"], errors="coerce")
        received = pd.to_numeric(measure["received_ms"], errors="coerce")
        stored = pd.to_numeric(measure["latency_ms"], errors="coerce")
        expected = received - sent
        comparable = sent.notna() & received.notna() & stored.notna()
        latency_diff = (stored[comparable] - expected[comparable]).abs()
        latency_mismatch = int((latency_diff > 0.01).sum())

        success_latency_missing = int(
            (ok & (stored.isna() | (stored < 0))).sum()
        )

        check_rows.append({
            "file": filename, "clients": clients, "run": run,
            "measure_rows": len(measure),
            "duplicate_request_identity_rows": duplicate_count,
            "latency_mismatch_rows_over_0_01ms": latency_mismatch,
            "success_missing_or_negative_latency_rows": success_latency_missing,
        })

        total = len(measure)
        successes = int(ok.sum())
        failures = total - successes
        run_rows.append({
            "clients": clients, "run": run, "file": filename,
            "total_requests": total, "successful_requests": successes,
            "failed_requests": failures,
            "throughput_req_s": successes / args.duration,
            "error_rate_pct": failures / total * 100 if total else np.nan,
            "avg_latency_ms": latency.mean() if len(latency) else np.nan,
            "p95_latency_ms": latency.quantile(0.95) if len(latency) else np.nan,
            "max_latency_ms": latency.max() if len(latency) else np.nan,
        })

    per_run = pd.DataFrame(run_rows).sort_values(["clients", "run"])
    checks = pd.DataFrame(check_rows).sort_values(["clients", "run"])
    per_run.to_csv(OUT / "per_run_summary.csv", index=False, encoding="utf-8-sig")
    checks.to_csv(OUT / "validation_checks.csv", index=False, encoding="utf-8-sig")

    aggregate = per_run.groupby("clients").agg(
        runs=("run", "count"),
        total_requests_mean=("total_requests", "mean"),
        success_mean=("successful_requests", "mean"),
        failure_mean=("failed_requests", "mean"),
        throughput_mean=("throughput_req_s", "mean"),
        throughput_std=("throughput_req_s", "std"),
        throughput_min=("throughput_req_s", "min"),
        throughput_max=("throughput_req_s", "max"),
        error_rate_mean_pct=("error_rate_pct", "mean"),
        avg_latency_mean_ms=("avg_latency_ms", "mean"),
        p95_latency_mean_ms=("p95_latency_ms", "mean"),
    ).reset_index()

    summary_path = RAW / "run_summary.csv"
    if summary_path.exists():
        cpu = pd.read_csv(summary_path)
        cpu_agg = cpu.groupby("clients").agg(
            cpu_server_process_avg_pct=("cpu_server_avg_pct", "mean"),
            cpu_server_total_machine_avg_pct=("cpu_server_avg_pct_of_total", "mean"),
            cpu_server_process_max_avg_pct=("cpu_server_max_pct", "mean"),
            server_rss_avg_mb=("server_rss_mb", "mean"),
            cpu_loadgen_avg_pct=("cpu_loadgen_avg_pct", "mean"),
            server_alive_all_runs=("server_alive_after", "all"),
            loadgen_exit_zero_all_runs=("loadgen_exit", lambda s: bool((s == 0).all())),
        ).reset_index()
        aggregate = aggregate.merge(cpu_agg, on="clients", how="left")

    aggregate.to_csv(OUT / "aggregate_summary.csv", index=False, encoding="utf-8-sig")

    # Plot 1: throughput mean +/- sample standard deviation.
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.errorbar(aggregate["clients"], aggregate["throughput_mean"],
                yerr=aggregate["throughput_std"].fillna(0),
                marker="o", capsize=5, linewidth=2)
    ax.set(title="TCP Server: Clients vs Throughput",
           xlabel="Number of concurrent clients", ylabel="Throughput (requests/second)")
    ax.set_xticks(aggregate["clients"])
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIG / "clients_vs_throughput.png", dpi=180)
    plt.close(fig)

    # Plot 2: use CPU normalized to total logical cores for a 0-100% machine scale.
    if "cpu_server_total_machine_avg_pct" in aggregate.columns:
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.plot(aggregate["clients"], aggregate["cpu_server_total_machine_avg_pct"],
                marker="o", linewidth=2)
        ax.set(title="TCP Server: Clients vs Server CPU (normalized)",
               xlabel="Number of concurrent clients",
               ylabel="Server CPU (% of total logical-core capacity)")
        ax.set_xticks(aggregate["clients"])
        ax.set_ylim(bottom=0)
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        fig.savefig(FIG / "clients_vs_cpu.png", dpi=180)
        plt.close(fig)

    # Text report for reproducible QA.
    expected = set(EXPECTED_LEVELS)
    observed = set(per_run["clients"].unique())
    lines = [
        "VALIDATION REPORT - TV5",
        f"CSV files analyzed: {len(per_run)}",
        f"Client levels observed: {sorted(observed)}",
        f"Expected client levels: {EXPECTED_LEVELS}",
        f"Total measured requests: {int(per_run['total_requests'].sum())}",
        f"Successful measured requests: {int(per_run['successful_requests'].sum())}",
        f"Failed measured requests: {int(per_run['failed_requests'].sum())}",
        f"Duplicate request identity rows: {int(checks['duplicate_request_identity_rows'].sum())}",
        f"Latency mismatch rows (>0.01 ms): {int(checks['latency_mismatch_rows_over_0_01ms'].sum())}",
        f"Successful rows with missing/negative latency: {int(checks['success_missing_or_negative_latency_rows'].sum())}",
        f"All expected client levels present: {expected.issubset(observed)}",
        "Note: validation checks are based on exported CSV fields; they do not prove protocol conformance.",
    ]
    (OUT / "validation_report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nĐã lưu kết quả tại: {OUT}")
    print(f"Đã lưu biểu đồ tại: {FIG}")


if __name__ == "__main__":
    main()
