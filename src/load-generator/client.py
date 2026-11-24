import argparse
import csv
import json
import math
import socket
import struct
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

MAX_FRAME = 1024 * 1024
CSV_FIELDS = ["run_id", "client_count", "client_id", "request_id",
              "phase", "sent_ms", "received_ms", "latency_ms", "status"]


def recv_exact(sock, n):
    data = bytearray()
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise EOFError("Connection closed")
        data.extend(chunk)
    return bytes(data)


def encode_frame(obj):
    body = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if not 0 < len(body) <= MAX_FRAME:
        raise ValueError("Invalid frame length")
    return struct.pack("!I", len(body)) + body


def recv_frame(sock):
    n = struct.unpack("!I", recv_exact(sock, 4))[0]
    if not 0 < n <= MAX_FRAME:
        raise ValueError("Invalid frame length")
    return json.loads(recv_exact(sock, n).decode("utf-8"))


def positive_int(value):
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError("Must be positive")
    return n


def parse_args():
    p = argparse.ArgumentParser(description="TCP Echo Load Generator")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=positive_int, default=9000)
    p.add_argument("--clients", type=positive_int, default=1)
    p.add_argument("--payload-bytes", type=positive_int, default=1024)
    p.add_argument("--warmup", type=int, default=5)
    p.add_argument("--duration", type=positive_int, default=20)
    p.add_argument("--timeout", type=positive_int, default=3)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.warmup < 0 or a.port > 65535:
        p.error("Invalid warmup or port")
    if a.payload_bytes > MAX_FRAME - 256:
        p.error("Payload too large for frame")
    return a


def run_client(args, client_id, payload, run_id, barrier, clock):
    rows = []
    connection = None
    sequence = 0
    barrier.wait()
    start = clock["start"]
    measure_start = start + args.warmup
    end = measure_start + args.duration
    try:
        while time.perf_counter() < end:
            attempted = time.perf_counter()
            sent = received = None
            sequence += 1
            request_id = f"client-{client_id:02d}-seq-{sequence:06d}"
            try:
                if connection is None:
                    connection = socket.create_connection((args.host, args.port), timeout=args.timeout)
                message = encode_frame({"requestId": request_id,
                                        "timestamp": time.time(), "payload": payload})
                if time.perf_counter() >= end:
                    break
                sent = time.perf_counter()
                connection.sendall(message)
                response = recv_frame(connection)
                valid = (isinstance(response, dict) and response.get("status") == "OK"
                         and response.get("requestId") == request_id
                         and response.get("payload") == payload)
                received = time.perf_counter()
                status = "ok" if valid else "response_mismatch"
            except TimeoutError:
                status = "timeout"
            except EOFError:
                status = "disconnected"
            except (ValueError, UnicodeError):
                status = "invalid_response"
            except OSError:
                status = "socket_error"
            event = sent if sent is not None else attempted
            phase = "warmup" if event < measure_start else "measure"
            latency = round((received - sent) * 1000, 3) if received is not None and sent is not None else None
            rows.append((run_id, args.clients, client_id, request_id, phase,
                         round((sent - start) * 1000, 3) if sent is not None else None,
                         round((received - start) * 1000, 3) if received is not None else None,
                         latency, status))
            if status != "ok":
                if connection is not None:
                    connection.close()
                    connection = None
                time.sleep(0.05)
    finally:
        if connection is not None:
            connection.close()
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
    with args.output.open("x", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(CSV_FIELDS)
        with ThreadPoolExecutor(max_workers=args.clients) as executor:
            futures = [executor.submit(run_client, args, i, payload, run_id, barrier, clock)
                       for i in range(1, args.clients + 1)]
            for future in futures:
                rows = future.result()
                writer.writerows(rows)
                for row in rows:
                    if row[4] == "measure":
                        attempts += 1
                        if row[8] == "ok":
                            latencies.append(row[7])
    successes = len(latencies)
    print(f"Da ghi {args.output}")
    print(f"Pha do: {attempts} lan thu, {successes} thanh cong")
    print(f"Throughput: {successes / args.duration:.2f} request/giay")
    if attempts:
        print(f"Error rate: {(attempts - successes) / attempts:.2%}")
    if latencies:
        latencies.sort()
        print(f"Latency trung binh: {sum(latencies) / successes:.3f} ms")
        print(f"p95 latency: {latencies[math.ceil(0.95 * successes) - 1]:.3f} ms")


if __name__ == "__main__":
    main()