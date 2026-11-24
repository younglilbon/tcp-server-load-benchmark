"""Bộ test QA (TV4) cho TCP Echo Server + Load Generator.

Kiểm thử "hộp đen": Server được bật ở PROCESS RIÊNG (src/server/server.py) rồi test gửi dữ liệu qua socket thật,
giống cách Load Generator làm. Test tự tắt Server khi xong và báo lỗi nếu Server bị crash.

Chạy (từ thư mục gốc của repo):
    python tests/test_qa_server.py            # chạy + ghi kết quả vào experiments/raw-data/test-results.txt
    python -m unittest tests.test_qa_server -v

Log phía Server trong lúc test: experiments/raw-data/qa-test-server.log
"""
import csv
import json
import random
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER_SCRIPT = ROOT / "src" / "server" / "server.py"
LOADGEN_SCRIPT = ROOT / "src" / "load-generator" / "client.py"
RAW_DIR = ROOT / "experiments" / "raw-data"

HOST = "127.0.0.1"
MAX_REQUEST_BYTES = 65536   # giới hạn dùng cho test (khớp đặc tả TV1: 65536)
CLIENT_TIMEOUT = 2.0        # timeout ngắn để test TC14 nhanh
PAYLOAD_1KB = "A" * 1024    # giống payload của Load Generator

PORT = None
_proc = None
_log = None


def _free_port():
    with socket.socket() as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def setUpModule():
    global PORT, _proc, _log
    PORT = _free_port()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    _log = open(RAW_DIR / "qa-test-server.log", "w", encoding="utf-8")
    _proc = subprocess.Popen(
        [sys.executable, str(SERVER_SCRIPT), "--host", HOST, "--port", str(PORT),
         "--max-request-bytes", str(MAX_REQUEST_BYTES), "--client-timeout", str(CLIENT_TIMEOUT)],
        cwd=ROOT, stdout=_log, stderr=subprocess.STDOUT,
    )
    end = time.time() + 10
    while time.time() < end:
        try:
            socket.create_connection((HOST, PORT), timeout=0.5).close()
            return
        except OSError:
            time.sleep(0.2)
    _proc.kill()
    raise RuntimeError("Server không khởi động được, xem experiments/raw-data/qa-test-server.log")


def tearDownModule():
    crashed = _proc.poll() is not None
    if not crashed:
        _proc.terminate()
        try:
            _proc.wait(5)
        except subprocess.TimeoutExpired:
            _proc.kill()
    _log.close()
    if crashed:
        raise AssertionError("Server đã bị CRASH trong lúc chạy test")


class Conn:
    """Một kết nối TCP tới Server, nói giao thức JSON-kết-thúc-bằng-\\n."""

    def __init__(self):
        self.sock = socket.create_connection((HOST, PORT), timeout=5)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.reader = self.sock.makefile("rb")

    def send(self, raw: bytes):
        self.sock.sendall(raw)

    def send_json(self, obj):
        self.send(json.dumps(obj).encode("utf-8") + b"\n")

    def recv_json(self):
        line = self.reader.readline()
        if not line:
            raise ConnectionError("Server đã đóng kết nối")
        return json.loads(line)

    def echo(self, request_id, payload):
        self.send_json({"requestId": request_id, "payload": payload})
        return self.recv_json()

    def close(self):
        for closer in (self.reader.close, self.sock.close):
            try:
                closer()
            except OSError:
                pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def assert_server_alive(tc):
    """Server còn sống = process chưa chết VÀ một Client mới được echo đúng."""
    tc.assertIsNone(_proc.poll(), "Process Server đã chết")
    with Conn() as c:
        tc.assertEqual(c.echo("alive-check", "ping"), {"requestId": "alive-check", "payload": "ping"})


# ===================== 1 Client =====================
class TestSingleClient(unittest.TestCase):
    def test_tc01_single_client_echo(self):
        with Conn() as c:
            self.assertEqual(c.echo("r1", "hello"), {"requestId": "r1", "payload": "hello"})

    def test_tc02_payload_1kb_exact_match(self):
        with Conn() as c:
            self.assertEqual(c.echo("1-1", PAYLOAD_1KB), {"requestId": "1-1", "payload": PAYLOAD_1KB})

    def test_tc03_200_sequential_requests_one_connection(self):
        with Conn() as c:
            for i in range(200):
                self.assertEqual(c.echo(f"1-{i}", PAYLOAD_1KB), {"requestId": f"1-{i}", "payload": PAYLOAD_1KB})


# ===================== Nhiều Client =====================
def _worker(client_id, n_requests, errors):
    try:
        with Conn() as c:
            for i in range(n_requests):
                rid = f"{client_id}-{i}"
                payload = f"client{client_id}:" + PAYLOAD_1KB
                if c.echo(rid, payload) != {"requestId": rid, "payload": payload}:
                    errors.append(f"client {client_id}: sai response ở request {i}")
                    return
    except Exception as exc:  # noqa: BLE001
        errors.append(f"client {client_id}: {exc!r}")


class TestMultiClient(unittest.TestCase):
    def _run(self, n_clients):
        errors = []
        threads = [threading.Thread(target=_worker, args=(cid, 50, errors)) for cid in range(1, n_clients + 1)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(60)
        self.assertEqual(errors, [], errors[:5])

    def test_tc04_10_clients_concurrent(self):
        self._run(10)

    def test_tc05_50_clients_concurrent(self):
        self._run(50)


# ===================== Framing (tách message) =====================
class TestFraming(unittest.TestCase):
    def test_tc06_request_split_into_single_bytes(self):
        # Gửi từng byte một: Server phải ghép đủ dòng rồi mới trả lời
        raw = json.dumps({"requestId": "frag", "payload": "xin chào"}).encode("utf-8") + b"\n"
        with Conn() as c:
            for b in raw:
                c.send(bytes([b]))
                time.sleep(0.003)
            self.assertEqual(c.recv_json(), {"requestId": "frag", "payload": "xin chào"})

    def test_tc07_three_requests_in_one_send(self):
        batch = b"".join(
            json.dumps({"requestId": i, "payload": p}).encode("utf-8") + b"\n"
            for i, p in [(1, "aaa"), (2, "bbb"), (3, PAYLOAD_1KB)]
        )
        with Conn() as c:
            c.send(batch)
            self.assertEqual([c.recv_json() for _ in range(3)],
                             [{"requestId": 1, "payload": "aaa"},
                              {"requestId": 2, "payload": "bbb"},
                              {"requestId": 3, "payload": PAYLOAD_1KB}])


# ===================== Client ngắt kết nối bất thường =====================
class TestAbnormalDisconnect(unittest.TestCase):
    def test_tc08_disconnect_in_the_middle_of_a_request(self):
        c = Conn()
        c.send(b'{"requestId":"half","payload":"' + b"x" * 500)   # chưa có dấu đóng + \n
        c.close()
        time.sleep(0.3)
        assert_server_alive(self)

    def test_tc09_abrupt_reset_rst(self):
        c = Conn()
        c.send_json({"requestId": "rst", "payload": "x"})
        c.sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
        c.sock.close()   # SO_LINGER=0 -> gửi RST thay vì FIN
        time.sleep(0.3)
        assert_server_alive(self)


# ===================== Dữ liệu không hợp lệ / quá cỡ =====================
class TestInvalidData(unittest.TestCase):
    def test_tc10a_invalid_json_gets_error_and_connection_continues(self):
        with Conn() as c:
            c.send(b"{not-json}\n")
            self.assertEqual(c.recv_json()["error"]["code"], "invalid_json")
            # cùng kết nối vẫn dùng tiếp được
            self.assertEqual(c.echo("next", "ok"), {"requestId": "next", "payload": "ok"})

    def test_tc10b_missing_required_fields(self):
        with Conn() as c:
            for raw in (b'{"requestId":"no-payload"}\n', b'{"payload":"no-id"}\n', b"[1,2,3]\n", b'"just a string"\n'):
                c.send(raw)
                self.assertEqual(c.recv_json()["error"]["code"], "invalid_request", raw)
            self.assertEqual(c.echo("still-ok", "x"), {"requestId": "still-ok", "payload": "x"})

    def test_tc10c_empty_line_and_non_utf8_bytes(self):
        with Conn() as c:
            c.send(b"\n")
            self.assertEqual(c.recv_json()["error"]["code"], "invalid_json")
            c.send(b"\xff\xfe\xfd\n")
            self.assertEqual(c.recv_json()["error"]["code"], "invalid_json")
            self.assertEqual(c.echo("after", "ok"), {"requestId": "after", "payload": "ok"})

    def test_tc10d_random_binary_garbage_then_close(self):
        for _ in range(5):
            c = Conn()
            c.send(bytes(random.getrandbits(8) for _ in range(300)))
            c.close()
        time.sleep(0.3)
        assert_server_alive(self)

    def test_tc11_oversize_request_rejected(self):
        line = json.dumps({"requestId": "big", "payload": "B" * (MAX_REQUEST_BYTES + 1000)}).encode("utf-8") + b"\n"
        c = Conn()
        answer = None
        try:
            try:
                c.send(line)
                answer = c.recv_json()
            except (OSError, ValueError):
                pass   # Server đóng/reset kết nối khi đang nhận dữ liệu quá cỡ cũng là hành vi chấp nhận được
        finally:
            c.close()
        if answer is not None:
            self.assertEqual(answer["error"]["code"], "request_too_large")
        assert_server_alive(self)

    def test_tc12_bad_client_does_not_affect_good_client(self):
        bad = Conn()
        bad.send(b'{"requestId":"never-finished","payload":"abc')   # treo, không bao giờ gửi \n
        try:
            with Conn() as good:
                for i in range(20):
                    self.assertEqual(good.echo(f"g-{i}", PAYLOAD_1KB), {"requestId": f"g-{i}", "payload": PAYLOAD_1KB})
        finally:
            bad.close()

    def test_tc13_burst_of_60_bad_clients_then_recover(self):
        def bad(i):
            try:
                c = Conn()
                c.send(bytes(random.getrandbits(8) for _ in range(random.randint(1, 200))))
                if i % 2:
                    c.sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
                c.sock.close()
            except OSError:
                pass
        threads = [threading.Thread(target=bad, args=(i,)) for i in range(60)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        time.sleep(0.5)
        assert_server_alive(self)


# ===================== Timeout =====================
class TestTimeout(unittest.TestCase):
    def test_tc14_idle_connection_closed_after_timeout(self):
        c = Conn()
        c.sock.settimeout(CLIENT_TIMEOUT + 4)
        started = time.time()
        try:
            data = c.sock.recv(1)
        except ConnectionResetError:
            data = b""
        elapsed = time.time() - started
        c.close()
        self.assertEqual(data, b"", "Server phải đóng kết nối idle")
        self.assertGreaterEqual(elapsed, CLIENT_TIMEOUT - 0.5)
        self.assertLess(elapsed, CLIENT_TIMEOUT + 3)
        assert_server_alive(self)


# ===================== Load Generator (TV3) chạy với Server thật =====================
def _run_loadgen(port, clients, duration, tmpdir, timeout_s=3):
    out = Path(tmpdir) / f"lg_c{clients}.csv"
    proc = subprocess.run(
        [sys.executable, str(LOADGEN_SCRIPT), "--host", HOST, "--port", str(port), "--clients", str(clients),
         "--warmup", "0", "--duration", str(duration), "--timeout", str(timeout_s), "--output", str(out)],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
        env={**__import__("os").environ, "PYTHONUTF8": "1"},
    )
    rows = list(csv.DictReader(open(out, newline="", encoding="utf-8"))) if out.exists() else []
    return proc, rows


class TestLoadGenerator(unittest.TestCase):
    def _check(self, clients):
        with tempfile.TemporaryDirectory() as tmp:
            proc, rows = _run_loadgen(PORT, clients, 2, tmp)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        measure = [r for r in rows if r["phase"] == "measure"]
        self.assertGreater(len(measure), 0, "CSV không có dòng phase=measure")
        self.assertEqual({r["status"] for r in measure}, {"ok"})
        self.assertEqual(len({r["client_id"] for r in measure}), clients)

    def test_tc15_loadgen_1_client_all_ok(self):
        self._check(1)

    def test_tc16_loadgen_10_clients_all_ok(self):
        self._check(10)

    def test_tc17_loadgen_records_errors_when_server_down(self):
        dead_port = _free_port()   # không có ai lắng nghe
        with tempfile.TemporaryDirectory() as tmp:
            proc, rows = _run_loadgen(dead_port, 2, 1, tmp, timeout_s=1)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertGreater(len(rows), 0)
        self.assertTrue(all(r["status"] != "ok" for r in rows))


class _Tee:
    def __init__(self, console, file):
        self.console, self.file = console, file

    def write(self, text):
        self.file.write(text)
        enc = getattr(self.console, "encoding", None) or "utf-8"
        self.console.write(text.encode(enc, "replace").decode(enc))

    def flush(self):
        self.file.flush()
        self.console.flush()


if __name__ == "__main__":
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    with open(RAW_DIR / "test-results.txt", "w", encoding="utf-8") as out:
        result = unittest.TextTestRunner(stream=_Tee(sys.stderr, out), verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    sys.exit(0 if result.wasSuccessful() else 1)
