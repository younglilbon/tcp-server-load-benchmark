import argparse
import csv
import json
import math
import socket
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from threading import Barrier


CSV_FIELDS = [
    "run_id",
    "client_count",
    "client_id",
    "request_id",
    "phase",
    "sent_ms",
    "received_ms",
    "latency_ms",
    "status",
]


def positive_int(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("Phải là số nguyên lớn hơn 0")
    return number


def parse_args():
    parser = argparse.ArgumentParser(description="TCP Echo Load Generator")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=positive_int, default=9000)
    parser.add_argument("--clients", type=positive_int, default=1)
    parser.add_argument("--payload-bytes", type=positive_int, default=1024)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--duration", type=positive_int, default=20)
    parser.add_argument("--timeout", type=positive_int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.warmup < 0:
        parser.error("--warmup phải từ 0 trở lên")
    if args.port > 65535:
        parser.error("--port phải nằm trong khoảng 1–65535")

    return args


def exchange(connection, reader, request_id, payload):
    request = {"requestId": request_id, "payload": payload}
    message = (json.dumps(request) + "\n").encode("utf-8")

    sent_at = time.perf_counter()
    connection.sendall(message)
    reply = reader.readline(len(message) + 1)
    received_at = time.perf_counter()

    if not reply:
        return sent_at, None, "disconnected"
    if not reply.endswith(b"\n"):
        return sent_at, None, "invalid_response"

    try:
        response = json.loads(reply)
    except (ValueError, UnicodeError):
        return sent_at, received_at, "invalid_response"

    if (
        isinstance(response, dict)
        and response.get("requestId") == request_id
        and response.get("payload") == payload
    ):
        return sent_at, received_at, "ok"

    return sent_at, received_at, "response_mismatch"


def run_client(args, client_id, payload, run_id, barrier, clock):
    rows = []
    sequence = 0
    connection = None
    reader = None

    barrier.wait()
    start = clock["start"]
    measure_start = start + args.warmup
    measure_end = measure_start + args.duration

    with ExitStack() as resources:
        while time.perf_counter() < measure_end:
            attempted_at = time.perf_counter()
            sent_at = None
            received_at = None
            sequence += 1
            request_id = f"{client_id}-{sequence}"

            try:
                if connection is None:
                    connection = resources.enter_context(
                        socket.create_connection(
                            (args.host, args.port),
                            timeout=args.timeout,
                        )
                    )
                    reader = resources.enter_context(connection.makefile("rb"))

                if time.perf_counter() >= measure_end:
                    break

                sent_at, received_at, status = exchange(
                    connection, reader, request_id, payload
                )
            except TimeoutError:
                status = "timeout"
            except OSError:
                status = "socket_error"

            event_at = sent_at if sent_at is not None else attempted_at
            phase = "warmup" if event_at < measure_start else "measure"

            latency_ms = (
                (received_at - sent_at) * 1000
                if sent_at is not None and received_at is not None
                else None
            )
            rows.append(
                (
                    run_id,
                    args.clients,
                    client_id,
                    request_id,
                    phase,
                    round((sent_at - start) * 1000, 3)
                    if sent_at is not None else None,
                    round((received_at - start) * 1000, 3)
                    if received_at is not None else None,
                    round(latency_ms, 3) if latency_ms is not None else None,
                    status,
                )
            )

            if status != "ok":
                resources.close()
                connection = None
                reader = None
                time.sleep(0.05)

    return rows


def main():
    args = parse_args()
    run_id = uuid.uuid4().hex
    payload = "A" * args.payload_bytes
    clock = {}

    def start_timer():
        clock["start"] = time.perf_counter()

    barrier = Barrier(args.clients, action=start_timer)

    args.output.parent.mkdir(parents=True, exist_ok=True)

    attempts = 0
    latencies = []

    # Chế độ "x" giữ lại dữ liệu nếu tên file đã tồn tại.
    with args.output.open("x", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(CSV_FIELDS)

        with ThreadPoolExecutor(max_workers=args.clients) as executor:
            futures = [
                executor.submit(
                    run_client, args, client_id, payload, run_id, barrier, clock
                )
                for client_id in range(1, args.clients + 1)
            ]
            for future in futures:
                rows = future.result()
                writer.writerows(rows)
                for row in rows:
                    if row[4] == "measure":
                        attempts += 1
                        if row[8] == "ok":
                            latencies.append(row[7])

    successes = len(latencies)
    print(f"Đã ghi {args.output}")
    print(f"Pha đo: {attempts} lần thử, {successes} thành công")
    print(f"Throughput: {successes / args.duration:.2f} request/giây")
    if attempts:
        print(f"Error rate: {(attempts - successes) / attempts:.2%}")
    if latencies:
        latencies.sort()
        p95 = latencies[math.ceil(0.95 * successes) - 1]
        print(f"Latency trung bình: {sum(latencies) / successes:.3f} ms")
        print(f"p95 latency: {p95:.3f} ms")


if __name__ == "__main__":
    main()