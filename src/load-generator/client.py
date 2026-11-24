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